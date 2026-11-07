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


class HostSetupRejected(ValueError):
    """Denied before any host instructions execute."""


def _error_code(exc, phase):
    from sedrava_host_typed import HostInvalidPath, HostPolicyViolation, HostResourceTooLarge
    if isinstance(exc, HostSetupRejected) or phase == "setup":
        return "CONFIGURATION_REJECTED", "rejected"
    if isinstance(exc, HostPolicyViolation):
        return "POLICY_VIOLATION", "fault"
    if isinstance(exc, OSError) and exc.errno in (errno.ELOOP, errno.ENOTDIR):
        return "POLICY_VIOLATION", "fault"
    if isinstance(exc, HostInvalidPath):
        return "INVALID_PATH", "failed"
    if isinstance(exc, HostResourceTooLarge):
        return "RESOURCE_TOO_LARGE", "failed"
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
    if status == "rejected" and (phase != "setup" or commit != "not_started"):
        raise ValueError("Rejected host work must not have executed")
    if status == "fault" and commit == "committed":
        raise ValueError("Fault cannot claim committed success")
    if status == "success" and (outcome.get("error") is not None or commit == "unknown"):
        raise ValueError("Successful host work cannot include error/unknown commit")
    if status != "success" and (outcome.get("error") is None or outcome.get("result") is not None):
        raise ValueError("Unsuccessful host work needs an error, no result")
    if phase != "commit" and commit in ("committed", "unknown"):
        raise ValueError("Only commit phase can commit")
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
