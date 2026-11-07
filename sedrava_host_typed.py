"""Host A3: bridge real Core 0.12 typed Result/Error values to scoped text I/O.

No host-side parallel Result implementation. Only the existing POSIX Host A2
read implementation is used. Catchable errors never include capability/policy
or resource-budget violations; those remain fatal runtime events.
"""
import errno
from sedrava_errors import ErrorType, ErrorValue
from sedrava_results import ResultType, ResultValue, validate as validate_result

HOST_READ_ERROR = ErrorType(
    "HostReadError", "sedrava.host.read.v1", True, (
        ("FileNotFound", (("path", str),)),
        ("PermissionDenied", (("path", str),)),
        ("InvalidEncoding", (("path", str),)),
        ("InvalidPath", (("reason", str),)),
        ("ResourceTooLarge", (("limit_bytes", int),)),
        ("TextTooLong", (("limit_scalars", int),)),
        ("IOFailure", (("operation", str),)),
    ),
)
HOST_READ_RESULT = ResultType(str, HOST_READ_ERROR)


class HostInvalidPath(ValueError):
    """Invalid value, not a capability escape."""


class HostResourceTooLarge(ValueError):
    """Expected file-size limit; distinct from execution/work budget."""


class HostTextTooLong(ValueError):
    """Decoded UTF-8 exceeds the Core 1024-scalar text limit."""


class HostPolicyViolation(ValueError):
    """A forbidden filesystem object or symlink traversal. Not a Result."""


def _err(variant, **values):
    fields = dict(HOST_READ_ERROR.variants)[variant]
    error = ErrorValue(HOST_READ_ERROR, variant,
                       tuple(values[name] for name, _ in fields))
    return validate_result(ResultValue(HOST_READ_RESULT, error=error))


def read_result(root_fd, path):
    """Read once and convert only registered, expected file errors.

    This is a trusted host primitive; any unknown exception propagates.
    """
    from sedrava_host import _read
    try:
        return validate_result(ResultValue(HOST_READ_RESULT, value=_read(root_fd, path)))
    except HostInvalidPath:
        return _err("InvalidPath", reason="invalid_relative_path")
    except HostResourceTooLarge:
        return _err("ResourceTooLarge", limit_bytes=4096)
    except HostTextTooLong:
        return _err("TextTooLong", limit_scalars=1024)
    except FileNotFoundError:
        return _err("FileNotFound", path=path)
    except PermissionError:
        return _err("PermissionDenied", path=path)
    except UnicodeError:
        return _err("InvalidEncoding", path=path)
    except OSError as exc:
        # ELOOP/ENOTDIR can indicate an attempted symlink traversal.
        # Treat ambiguity conservatively: never expose it as catchable.
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise HostPolicyViolation("Disallowed filesystem traversal") from exc
        if exc.errno in (errno.EAGAIN, errno.EINTR, errno.EIO, errno.ENOSPC, errno.ESTALE):
            return _err("IOFailure", operation="read")
        raise


def execute_match(result, arms, values):
    """Execute statically checked arm; only primitive body actions are allowed."""
    validate_result(result, HOST_READ_RESULT)
    selected = "Ok" if result.error is None else result.error.variant
    for arm in arms:
        if arm.tag != selected and arm.tag != "Err":
            continue
        if arm.tag == "Err" and result.error is None:
            continue
        scope = dict(values)
        for binder, field in arm.bindings:
            if arm.tag == "Ok":
                scope[binder] = result.value
            elif arm.tag == "Err":
                scope[binder] = result.error
            else:
                fields = dict(HOST_READ_ERROR.variants)[arm.tag]
                index = [name for name, _ in fields].index(field)
                scope[binder] = result.error.values[index]
        from sedrava_core import evaluate
        return evaluate(arm.body[0].first, scope)
    raise AssertionError("Exhaustiveness invariant violated")
