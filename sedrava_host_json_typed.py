"""A4: bounded, in-memory typed JSON text lookup for trusted Host programs.

This is a closed expected-error family, not a filesystem permission bypass.
JSON parsing, policy, type integrity and runtime budget failures remain fatal.
"""
from sedrava_errors import ErrorType, ErrorValue
from sedrava_host_json import JsonValue
from sedrava_results import ResultType, ResultValue, validate as validate_result

HOST_JSON_LOOKUP_ERROR = ErrorType(
    "HostJsonLookupError", "sedrava.host.json.lookup.v1", False, (
        ("MissingKey", ()),
        ("InvalidIndex", ()),
        ("UnexpectedType", ()),
    ),
)
HOST_JSON_LOOKUP_RESULT = ResultType(str, HOST_JSON_LOOKUP_ERROR)


def _expected_error(variant):
    if variant not in dict(HOST_JSON_LOOKUP_ERROR.variants):
        raise ValueError("Unknown typed JSON lookup failure")
    error = ErrorValue(HOST_JSON_LOOKUP_ERROR, variant, ())
    return validate_result(ResultValue(HOST_JSON_LOOKUP_RESULT, error=error))


def lookup_text_result(document, key):
    """Read a text field or array element; return only expected shape errors.

    Input must already be a validated JsonValue (via strict Host argument,
    file read, object construction or JSON transformation). Never capture
    ValueError raised by validation or Core budget checks.
    """
    if type(document) is not JsonValue or type(key) not in (str, int):
        raise ValueError("Invalid typed JSON lookup runtime operands")
    value = document.value
    if type(value) is dict:
        if type(key) is not str:
            return _expected_error("UnexpectedType")
        if key not in value:
            return _expected_error("MissingKey")
        found = value[key]
    elif type(value) is list:
        if type(key) is not int or not 0 <= key < len(value):
            return _expected_error("InvalidIndex")
        found = value[key]
    else:
        return _expected_error("UnexpectedType")
    if type(found) is not str:
        return _expected_error("UnexpectedType")
    return validate_result(ResultValue(HOST_JSON_LOOKUP_RESULT, value=found))
