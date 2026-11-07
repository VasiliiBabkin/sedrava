"""Versioned, bounded HostExecutionResult protocol for trusted host workers.

Not a public HTTP endpoint, authorization layer or remote job service.
Never serializes OS paths, Python exception messages or tracebacks.
"""
import errno
import json
from dataclasses import dataclass

PROTOCOL = "sedrava.host.execution.v1"
STATUSES = frozenset(("success", "failed", "fault", "rejected"))
PHASES = frozenset(("setup", "execute", "commit"))
COMMIT_STATES = frozenset(("not_started", "not_applicable", "committed", "unknown"))
FAILED_CODES = frozenset((
    "FILE_NOT_FOUND", "PERMISSION_DENIED", "FILE_EXISTS",
    "INVALID_ENCODING", "INVALID_PATH", "RESOURCE_TOO_LARGE",
    "TEXT_TOO_LONG", "DIRECTORY_NOT_EMPTY", "IO_FAILURE",
    "INVALID_JSON", "JSON_LOOKUP_FAILED", "JSON_OPERATION_FAILED",
))
FAULT_CODES = frozenset(("POLICY_VIOLATION", "IO_FAULT", "ENGINE_FAULT"))
REJECTED_CODES = frozenset(("CONFIGURATION_REJECTED",))



class HostSetupRejected(ValueError):
    """Denied before any host instructions execute."""


def _error_code(exc, phase):
    from sedrava_host_typed import HostInvalidPath, HostPolicyViolation, HostResourceTooLarge
    if isinstance(exc, HostSetupRejected) or phase == "setup":
        return "CONFIGURATION_REJECTED", "rejected"
    if isinstance(exc, HostPolicyViolation):
        return "POLICY_VIOLATION", "fault"
    from sedrava_host_json import (HostInvalidJson, HostJsonLookupFailure,
                                   HostJsonOperationFailure)
    if isinstance(exc, HostInvalidJson):
        return "INVALID_JSON", "failed"
    if isinstance(exc, HostJsonLookupFailure):
        return "JSON_LOOKUP_FAILED", "failed"
    if isinstance(exc, HostJsonOperationFailure):
        return "JSON_OPERATION_FAILED", "failed"
    if isinstance(exc, OSError) and exc.errno in (errno.ELOOP, errno.ENOTDIR):
        return "POLICY_VIOLATION", "fault"
    if isinstance(exc, HostInvalidPath):
        return "INVALID_PATH", "failed"
    if isinstance(exc, HostResourceTooLarge):
        return "RESOURCE_TOO_LARGE", "failed"
    from sedrava_host_typed import HostTextTooLong
    if isinstance(exc, HostTextTooLong):
        return "TEXT_TOO_LONG", "failed"
    if isinstance(exc, FileNotFoundError):
        return "FILE_NOT_FOUND", "failed"
    if isinstance(exc, PermissionError):
        return "PERMISSION_DENIED", "failed"
    if isinstance(exc, FileExistsError):
        return "FILE_EXISTS", "failed"
    if isinstance(exc, UnicodeError):
        return "INVALID_ENCODING", "failed"
    if isinstance(exc, OSError):
        if exc.errno in (errno.ENOTEMPTY, errno.EEXIST):
            return "DIRECTORY_NOT_EMPTY" if exc.errno == errno.ENOTEMPTY else "FILE_EXISTS", "failed"
        if exc.errno in (errno.EIO, errno.ENOSPC, errno.EINTR, errno.ESTALE, errno.EAGAIN):
            return "IO_FAILURE", "failed"
        return "IO_FAULT", "fault"
    # Unknown ValueError/engine bug is NOT silently converted to a catchable error.
    return "ENGINE_FAULT", "fault"


def validate_outcome(outcome):
    if not isinstance(outcome, dict) or outcome.get("protocol") != PROTOCOL:
        raise ValueError("Unknown HostExecutionResult protocol")
    status, phase, commit = (outcome.get("status"), outcome.get("phase"), outcome.get("commit_state"))
    if status not in STATUSES or phase not in PHASES or commit not in COMMIT_STATES:
        raise ValueError("Invalid HostExecutionResult enum")
    if status == "rejected":
        if phase != "setup" or commit != "not_started":
            raise ValueError("Rejected host work must not have executed")
    elif phase == "setup":
        raise ValueError("Only rejected can occur before execution")
    elif status == "success":
        if (phase == "execute" and commit != "not_applicable") or (
                phase == "commit" and commit != "committed"):
            raise ValueError("Success must reflect its final execution/commit phase")
    elif (phase == "execute" and commit != "not_started") or (
            phase == "commit" and commit != "unknown"):
        raise ValueError("Failure/fault must conservatively reflect commit state")
    if status == "success":
        if outcome.get("error") is not None:
            raise ValueError("Successful host work cannot include error")
    elif outcome.get("error") is None or outcome.get("result") is not None:
        raise ValueError("Unsuccessful host work needs an error, no result")
    expected_codes = {
        "failed": FAILED_CODES, "fault": FAULT_CODES, "rejected": REJECTED_CODES
    }
    if status != "success":
        error = outcome.get("error")
        if (type(error) is not dict or set(error) != {"code", "retryable"}
                or type(error.get("code")) is not str
                or error["code"] not in expected_codes[status]
                or type(error.get("retryable")) is not bool):
            raise ValueError("Invalid HostExecutionResult error schema/code")
        if error["retryable"]:
            raise ValueError("A3 protocol does not authorize automatic retries")
    elif type(outcome.get("result")) is not dict:
        raise ValueError("Successful HostExecutionResult requires a result object")
    if set(outcome) != {"protocol", "status", "phase", "commit_state", "result", "error"}:
        raise ValueError("HostExecutionResult has unknown or missing fields")
    raw = json.dumps(outcome, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(raw.encode("utf-8")) > 16_384:
        raise ValueError("HostExecutionResult exceeds transport size")
    return outcome


def reject(reason="CONFIGURATION_REJECTED"):
    # Fixed, non-user-controlled public error code only.
    if reason != "CONFIGURATION_REJECTED":
        raise ValueError("Unsupported setup error code")
    return validate_outcome({
        "protocol": PROTOCOL, "status": "rejected", "phase": "setup",
        "commit_state": "not_started", "result": None,
        "error": {"code": reason, "retryable": False},
    })


def execute_protocol(program, **options):
    """Execute existing A2 runtime, keeping its permission gates authoritative."""
    from sedrava_host import run_host
    phase = "setup"

    def phase_changed(new_phase):
        nonlocal phase
        if new_phase not in PHASES:
            raise AssertionError("Invalid runtime phase")
        phase = new_phase

    try:
        output = run_host(program, on_phase=phase_changed, **options)
    except Exception as exc:
        code, status = _error_code(exc, phase)
        # After entering commit, an I/O error can follow successful os.replace.
        # Always report unknown commit state; never automatically retry.
        commit = "unknown" if phase == "commit" else "not_started"
        return validate_outcome({
            "protocol": PROTOCOL, "status": status, "phase": phase,
            "commit_state": commit, "result": None,
            "error": {"code": code, "retryable": False},
        })
    return validate_outcome({
        "protocol": PROTOCOL, "status": "success",
        "phase": "commit" if phase == "commit" else "execute",
        "commit_state": "committed" if phase == "commit" else "not_applicable",
        "result": output, "error": None,
    })
