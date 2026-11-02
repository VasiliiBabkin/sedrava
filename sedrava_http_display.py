"""Parse declarative HTTP API0 card display fields and UI text.

The optional display block must be the final service section.
"""
import json
import re

_HEADER = re.compile(r"    display cards:")
_FIELD = re.compile(r"        ([A-Za-z][A-Za-z0-9_]{0,63})$")
_OPTION = re.compile(r'        (heading|loading|empty|error) (".*")$')


def _extract(source):
    if type(source) is not str:
        raise ValueError("Expected HTTP service source")
    lines = source.splitlines(keepends=True)
    indices = [i for i, line in enumerate(lines)
               if _HEADER.fullmatch(line.rstrip("\r\n"))]
    if not indices:
        return source, None, {}
    if len(indices) != 1:
        raise ValueError("Only one display declaration is allowed")
    start = indices[0]
    fields = []
    options = {}
    for line in lines[start + 1:]:
        raw = line.rstrip("\r\n")
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = _OPTION.fullmatch(raw)
        if match:
            key, literal = match.groups()
            if key in options:
                raise ValueError("Duplicate HTTP display option: " + key)
            try:
                value = json.loads(literal)
            except (ValueError, TypeError) as exc:
                raise ValueError("Invalid HTTP display string") from exc
            if type(value) is not str or not value or len(value) > 160:
                raise ValueError("HTTP display text must contain 1-160 characters")
            options[key] = value
            continue
        match = _FIELD.fullmatch(raw)
        if not match:
            raise ValueError("Display must be the final service section with eight-space-indented declarations")
        fields.append(match.group(1))
    if not fields or len(fields) > 64 or len(set(fields)) != len(fields):
        raise ValueError("Display requires 1-64 distinct fields")
    return "".join(lines[:start]), fields, options


def split_display(source: str):
    core, fields, _ = _extract(source)
    return core, fields


def parse_display_options(source: str):
    _, _, options = _extract(source)
    return {("title" if key == "heading" else key): value
            for key, value in options.items()}


def parse_display_service(source: str):
    from sedrava_http_parser import parse_service
    core, selected, _ = _extract(source)
    service, schema = parse_service(core)
    names = {field.name for field in schema.fields}
    if selected is not None and not set(selected) <= names:
        raise ValueError("Display references a field absent from the response schema")
    return service, schema, selected if selected is not None else [field.name for field in schema.fields]
