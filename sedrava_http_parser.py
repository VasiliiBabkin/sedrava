"""Parse an explicitly scoped Sedrava HTTP service declaration.

Experimental API0 syntax; not yet part of the app/site parser.
Example:
service articles:
    origin "https://api.example.com"
    path "/articles"
    timeout 5000
    max-bytes 262144
    response many:
        title text
        id int32
"""
import re
import shlex
from sedrava_http import ApiService, JsonField, JsonResponse


def parse_service(source: str):
    if type(source) is not str or len(source) > 32768:
        raise ValueError("API declaration exceeds source limit")
    lines = [(n, raw) for n, raw in enumerate(source.splitlines(), 1)
             if raw.strip() and not raw.lstrip().startswith("#")]
    if not lines:
        raise ValueError("Missing service declaration")
    head = re.fullmatch(r"service ([A-Za-z][A-Za-z0-9_]{0,63}):", lines[0][1])
    if not head:
        raise ValueError(f"Line {lines[0][0]}: expected service name:")
    props = {}
    fields = []
    response_many = None
    for number, raw in lines[1:]:
        if "\t" in raw or raw.rstrip() != raw:
            raise ValueError(f"Line {number}: tabs and trailing spaces are not allowed")
        if raw.startswith("    ") and not raw.startswith("        "):
            if raw in ("    response one:", "    response many:"):
                if response_many is not None:
                    raise ValueError(f"Line {number}: duplicate response schema")
                response_many = raw == "    response many:"
                continue
            if response_many is not None:
                raise ValueError(f"Line {number}: properties must precede response schema")
            try:
                words = shlex.split(raw.strip())
            except ValueError as exc:
                raise ValueError(f"Line {number}: malformed property") from exc
            if len(words) != 2 or words[0] not in ("origin", "path", "timeout", "max-bytes") or words[0] in props:
                raise ValueError(f"Line {number}: invalid or duplicate property")
            if words[0] in ("timeout", "max-bytes"):
                if not re.fullmatch(r"[0-9]+", words[1]):
                    raise ValueError(f"Line {number}: expected unsigned integer")
                props[words[0]] = int(words[1])
            else:
                if not re.fullmatch(r'    '+words[0]+r' "[^"\\]*"', raw):
                    raise ValueError(f"Line {number}: URL must be a quoted literal")
                props[words[0]] = words[1]
        elif raw.startswith("        ") and not raw.startswith("            ") and response_many is not None:
            match = re.fullmatch(r"        ([A-Za-z][A-Za-z0-9_]{0,63}) (text|int32|bool)", raw)
            if not match:
                raise ValueError(f"Line {number}: invalid response field")
            fields.append(JsonField(match[1], match[2]))
        else:
            raise ValueError(f"Line {number}: unexpected indentation or declaration")
    if not {"origin", "path"} <= props.keys() or response_many is None:
        raise ValueError("Service requires origin, path and response schema")
    service = ApiService(head[1], props["origin"], props["path"],
                         props.get("timeout", 10000), props.get("max-bytes", 262144))
    schema = JsonResponse(tuple(fields), many=response_many)
    return service, schema
