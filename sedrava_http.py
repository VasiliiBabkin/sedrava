"""Strict, dependency-free HTTP API declaration validation for future Sedrava Web apps.

This module does not perform network requests. It validates a small, explicit
capability manifest so the forthcoming Web adapter has a testable trust boundary.
"""
from dataclasses import dataclass
import ipaddress
import re
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ApiService:
    name: str
    origin: str
    path: str
    timeout_ms: int = 10000
    max_bytes: int = 262144

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", self.name):
            raise ValueError("Service name must be a valid identifier")
        parsed = urlsplit(self.origin)
        if (parsed.scheme != "https" or not parsed.hostname or
                parsed.username is not None or parsed.password is not None or
                parsed.port not in (None, 443) or parsed.path not in ("", "/") or
                parsed.query or parsed.fragment or parsed.netloc.endswith(".")):
            raise ValueError("API origin must be a bare HTTPS origin")
        host = parsed.hostname
        if host == "localhost" or host.endswith(".localhost"):
            raise ValueError("Localhost is not an allowed public API origin")
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            if not re.fullmatch(r"[a-zA-Z0-9-]+(?:\\.[a-zA-Z0-9-]+)+", host):
                raise ValueError("API origin requires a valid public DNS hostname")
            if any(not part or part.startswith("-") or part.endswith("-") for part in host.split(".")):
                raise ValueError("Invalid DNS label")
        else:
            if not ip.is_global:
                raise ValueError("Non-public IP origins are not allowed")
        if (not self.path.startswith("/") or self.path.startswith("//") or
                any(part in (".", "..") for part in self.path.split("/")) or
                any(c in self.path for c in "?#\\\\") or
                re.search(r"%(?:2e|2f|5c|00|0[0-9a-f]|1[0-9a-f])", self.path, re.I) or
                any(ord(c) < 33 or ord(c) > 126 for c in self.path)):
            raise ValueError("API path must be a fixed, safe ASCII path")
        if type(self.timeout_ms) is not int or not 100 <= self.timeout_ms <= 30000:
            raise ValueError("Timeout must be between 100 and 30000 ms")
        if type(self.max_bytes) is not int or not 1 <= self.max_bytes <= 1048576:
            raise ValueError("Response limit must be between 1 and 1048576 bytes")

    @property
    def url(self):
        return self.origin.rstrip("/") + self.path

# A bounded, explicit JSON response schema for the first read-only connector.
# Fields are declared rather than inferred from untrusted response values.
@dataclass(frozen=True)
class JsonField:
    name: str
    kind: str

    def __post_init__(self):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", self.name):
            raise ValueError("Invalid JSON field name")
        if self.kind not in ("text", "int32", "bool"):
            raise ValueError("Unsupported JSON field type")


@dataclass(frozen=True)
class JsonResponse:
    fields: tuple
    many: bool = False
    max_items: int = 100

    def __post_init__(self):
        if type(self.fields) is not tuple or not self.fields or len(self.fields) > 32:
            raise ValueError("JSON schema requires 1..32 fields")
        if any(type(f) is not JsonField for f in self.fields):
            raise ValueError("Expected JsonField declarations")
        if len({f.name for f in self.fields}) != len(self.fields):
            raise ValueError("Duplicate JSON field")
        if type(self.many) is not bool or type(self.max_items) is not int or not 1 <= self.max_items <= 1000:
            raise ValueError("Invalid JSON collection limits")

    def validate(self, data):
        import json
        # Reject unbounded nesting and payloads before accepting any state.
        try:
            raw = json.dumps(data, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError, OverflowError, RecursionError) as exc:
            raise ValueError("Invalid JSON response") from exc
        if len(raw.encode("utf-8")) > 1048576:
            raise ValueError("JSON response exceeds size limit")
        items = data if self.many else [data]
        if type(items) is not list or len(items) > self.max_items:
            raise ValueError("JSON response has unexpected collection shape or size")
        output = []
        for item in items:
            if type(item) is not dict or set(item) != {f.name for f in self.fields}:
                raise ValueError("JSON record fields do not match schema")
            checked = {}
            for field in self.fields:
                value = item[field.name]
                if field.kind == "text":
                    if type(value) is not str or len(value) > 1024 or any(ord(c) < 32 and c not in "\\n\\t" for c in value):
                        raise ValueError("Invalid JSON text field: " + field.name)
                elif field.kind == "int32":
                    if type(value) is not int or not -(2**31) <= value < 2**31:
                        raise ValueError("Invalid JSON int32 field: " + field.name)
                elif type(value) is not bool:
                    raise ValueError("Invalid JSON bool field: " + field.name)
                checked[field.name] = value
            output.append(checked)
        return output if self.many else output[0]
