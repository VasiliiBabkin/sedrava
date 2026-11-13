"""Bounded, strictly typed JSON data for the opt-in Sedrava host target.

This module does not register any operation in Web, Android or the core stdlib.
"""
import json
from dataclasses import dataclass

from sedrava_core import checked_int, checked_text

MAX_JSON_BYTES = 4096
MAX_JSON_NODES = 128
MAX_JSON_DEPTH = 8
MAX_JSON_FIELDS = 32

class HostInvalidJson(ValueError):
    """Malformed or schema-invalid JSON supplied as data."""


class HostJsonLookupFailure(ValueError):
    """Missing key/index or type mismatch in an otherwise valid JSON document."""


class HostJsonOperationFailure(ValueError):
    """Invalid typed JSON transformation on an input document."""



@dataclass(frozen=True)
class JsonValue:
    value: object


def validate_json(value):
    """Reject floats, duplicate-key ambiguities, oversized and non-scalar strings."""
    nodes = 0

    def visit(item, depth):
        nonlocal nodes
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            raise ValueError("Host JSON resource limit exceeded")
        if item is None or type(item) is bool:
            return
        if type(item) is int:
            checked_int(item)
            return
        if type(item) is str:
            checked_text(item)
            return
        if type(item) is list:
            if len(item) > MAX_JSON_NODES:
                raise ValueError("Host JSON array exceeds limit")
            for child in item:
                visit(child, depth + 1)
            return
        if type(item) is dict:
            if len(item) > MAX_JSON_FIELDS:
                raise ValueError("Host JSON object exceeds field limit")
            for key, child in item.items():
                if type(key) is not str:
                    raise ValueError("Host JSON keys must be text")
                checked_text(key)
                visit(child, depth + 1)
            return
        raise ValueError("Unsupported JSON value (floats and non-JSON types are forbidden)")

    visit(value, 0)
    return JsonValue(value)


def dumps(value):
    if not isinstance(value, JsonValue):
        raise ValueError("Expected host JSON value")
    validate_json(value.value)
    raw = json.dumps(value.value, sort_keys=True, ensure_ascii=False,
                     allow_nan=False, separators=(",", ":"))
    if len(raw.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError("Host JSON exceeds 4096-byte limit")
    return raw


def loads(raw):
    if type(raw) is not str or len(raw.encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError("Host JSON exceeds 4096-byte limit")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def decimal(value):
        if len(value) > 11:
            raise ValueError("JSON integer exceeds int32")
        return checked_int(int(value))

    def invalid_constant(value):
        raise ValueError("Invalid JSON constant")

    try:
        parsed = json.loads(raw, parse_int=decimal,
                            parse_float=lambda _: (_ for _ in ()).throw(ValueError("JSON floats are forbidden")),
                            parse_constant=invalid_constant,
                            object_pairs_hook=unique)
    # Recursion during decoding is caused by bounded but deeply nested input,
    # not an engine/work-budget error. Do not catch recursion around execution.
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise HostInvalidJson("Invalid strict JSON input") from exc
    try:
        return validate_json(parsed)
    except ValueError as exc:
        raise HostInvalidJson("JSON value violates strict data constraints") from exc


def lookup(document, key, expected):
    if not isinstance(document, JsonValue):
        raise ValueError("Host JSON document required")
    value = document.value
    if type(value) is dict and type(key) is str and key in value:
        result = value[key]
    elif type(value) is list and type(key) is int and 0 <= key < len(value):
        result = value[key]
    else:
        raise HostJsonLookupFailure("JSON key/index missing or invalid")
    if expected is JsonValue:
        return validate_json(result)
    if type(result) is not expected:
        raise HostJsonLookupFailure("JSON value has incorrect type")
    return result


def count(document):
    if not isinstance(document, JsonValue) or type(document.value) not in (list, dict):
        raise HostJsonOperationFailure("JSON count requires array or object")
    return len(document.value)


def new_object():
    return JsonValue({})


def put(document, key, value):
    if not isinstance(document, JsonValue) or type(document.value) is not dict:
        raise HostJsonOperationFailure("JSON field assignment requires object")
    if type(key) is not str or not key or len(key) > 128 or key in document.value:
        raise HostJsonOperationFailure("Invalid or duplicate JSON object field")
    checked_text(key)
    value = value.value if isinstance(value, JsonValue) else value
    fields = dict(document.value)
    fields[key] = value
    try:
        return validate_json(fields)
    except ValueError as exc:
        raise HostJsonOperationFailure("JSON assignment violates resource/type constraints") from exc
