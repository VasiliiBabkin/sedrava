"""Parse optional declarative display configuration in an HTTP API0 service.

Syntax (after response fields):
    display cards:
        title
        id

This is a presentation projection, never a relaxation of response validation.
"""
import re

_HEADER = re.compile(r"    display cards:")
_FIELD = re.compile(r"        ([A-Za-z][A-Za-z0-9_]{0,63})")


def split_display(source: str):
    if type(source) is not str:
        raise ValueError("Expected HTTP service source")
    lines = source.splitlines(keepends=True)
    indices = [i for i, line in enumerate(lines) if _HEADER.fullmatch(line.rstrip("\r\n"))]
    if not indices:
        return source, None
    if len(indices) != 1:
        raise ValueError("Only one display declaration is allowed")
    start = indices[0]
    selected = []
    for line in lines[start + 1:]:
        raw = line.rstrip("\r\n")
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = _FIELD.fullmatch(raw)
        if not match:
            raise ValueError("Display must be the final service section with eight-space-indented field names")
        selected.append(match.group(1))
    if not selected or len(selected) > 64 or len(set(selected)) != len(selected):
        raise ValueError("Display requires 1-64 distinct fields")
    return "".join(lines[:start]), selected


def parse_display_service(source: str):
    from sedrava_http_parser import parse_service
    core, selected = split_display(source)
    service, schema = parse_service(core)
    names = {field.name for field in schema.fields}
    if selected is not None and not set(selected) <= names:
        raise ValueError("Display references a field absent from the response schema")
    return service, schema, selected if selected is not None else [field.name for field in schema.fields]
