"""Experimental typed SQLite CRUD routes for Sedrava 0.13 A2.

The route grammar is deliberately closed. Data endpoints are OFF unless an
explicit local-only test gate and a high-entropy bearer token are configured.
A shared bearer token is NOT user authentication or per-row authorization.
No arbitrary SQL or host-language code from Sedrava input is executed.
"""
import hashlib
import hmac
import json
import os
import re
import sqlite3
from urllib.parse import parse_qs

from sedrava_server_runtime import _open, _ledger, _verify_tables, _quote
from sedrava_server_schema import load_manifest

_ROUTE = re.compile(
    r'^endpoint (GET|POST|PATCH|DELETE) "(/api/([a-z][a-z0-9_]{0,31})(/\{id\})?)"'
    r' -> (list|create|read|update|delete) ([a-z][a-z0-9_]{0,31})$'
)
_RULES = {
    ("GET", False): "list",
    ("POST", False): "create",
    ("GET", True): "read",
    ("PATCH", True): "update",
    ("DELETE", True): "delete",
}
_MAX_BODY = 8192
_MAX_ROWS = 50
_INT_MAX = 2147483647
_TOKEN_ENV = "SEDRAVA_API_EXPERIMENTAL_TOKEN"
_ENABLE_ENV = "SEDRAVA_API_EXPERIMENTAL_ENABLE"


class APIError(ValueError):
    def __init__(self, status, code):
        super().__init__(code)
        self.status, self.code = status, code


def parse_routes(lines, tables):
    """Compile explicit endpoint declarations after the last migration."""
    if len(lines) > 80:
        raise ValueError("More than 80 endpoints")
    routes, seen = [], set()
    for number, line in lines:
        match = _ROUTE.fullmatch(line)
        if match is None:
            raise ValueError(f"Line {number}: column 1: invalid typed endpoint")
        method, path, path_table, suffix, action, table = match.groups()
        is_item = bool(suffix)
        if table not in tables or path_table != table:
            raise ValueError(f"Line {number}: column 1: endpoint references missing or different table")
        if _RULES.get((method, is_item)) != action:
            raise ValueError(f"Line {number}: column 1: HTTP method, path and operation disagree")
        if (method, path) in seen:
            raise ValueError(f"Line {number}: column 1: duplicate HTTP endpoint")
        seen.add((method, path))
        routes.append({"method": method, "path": path, "action": action, "table": table})
    if not routes:
        raise ValueError("Empty endpoint section")
    return routes


def _pairs(pairs):
    data = {}
    for name, value in pairs:
        if name in data:
            raise ValueError("duplicate JSON member")
        data[name] = value
    return data


def _no_constant(value):
    raise ValueError("non-finite JSON number")


def _decode_request(raw):
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_no_constant)
    except (UnicodeError, ValueError):
        raise APIError(400, "invalid_json") from None
    if not isinstance(value, dict):
        raise APIError(400, "expected_record")
    return value


def _validate(fields, record, *, partial):
    if not isinstance(record, dict) or not record or "id" in record:
        raise APIError(400, "invalid_record")
    allowed = {item["name"]: item for item in fields}
    if any(name not in allowed for name in record):
        raise APIError(400, "invalid_record")
    if not partial and any(name not in record and "default" not in item
                           for name, item in allowed.items()):
        raise APIError(400, "missing_required_field")
    payload = {}
    for name, field in allowed.items():
        if name in record:
            value = record[name]
        elif not partial and "default" in field:
            value = field["default"]
        else:
            continue
        kind = field["type"]
        if kind == "bool":
            if type(value) is not bool:
                raise APIError(400, "invalid_bool")
            payload[name] = 1 if value else 0
        elif kind == "int":
            if type(value) is not int or not -2147483648 <= value <= _INT_MAX:
                raise APIError(400, "invalid_int")
            payload[name] = value
        elif kind == "text":
            if not isinstance(value, str) or len(value) > field["length"] or "\x00" in value:
                raise APIError(400, "invalid_text")
            try:
                value.encode("utf-8")
            except UnicodeError:
                raise APIError(400, "invalid_text") from None
            payload[name] = value
    return payload


def _view(row, fields):
    if row is None:
        raise APIError(404, "not_found")
    result = dict(row)
    for field in fields:
        if field["type"] == "bool":
            result[field["name"]] = bool(result[field["name"]])
    return result


def _etag(row):
    encoded = json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return '"sha256-' + hashlib.sha256(encoded).hexdigest() + '"'


def _only_header(scope, name):
    matches = [value for key, value in scope.get("headers", ())
               if key.lower() == name]
    if len(matches) > 1:
        raise APIError(400, "duplicate_header")
    return matches[0] if matches else None


def _local_test_gate(scope):
    """Deny by default. Loopback + explicit enable + token, NEVER production auth."""
    if os.environ.get(_ENABLE_ENV) != "1":
        raise APIError(404, "not_found")
    client = scope.get("client")
    server = scope.get("server")
    hosts = ("127.0.0.1", "::1")
    if not isinstance(client, (list, tuple)) or not isinstance(server, (list, tuple)):
        raise APIError(403, "local_only")
    if not client or not server or client[0] not in hosts or server[0] not in hosts:
        raise APIError(403, "local_only")
    host = _only_header(scope, b"host")
    if host is None or re.fullmatch(rb'(?:localhost|127\.0\.0\.1|\[::1\])(?::[0-9]{1,5})?', host.lower()) is None:
        raise APIError(403, "local_only")
    token = os.environ.get(_TOKEN_ENV, "")
    if not (32 <= len(token) <= 128 and token.isascii() and token.isprintable() and
            not any(char.isspace() for char in token)):
        raise APIError(503, "test_token_not_configured")
    supplied = _only_header(scope, b"authorization")
    if supplied is None or not hmac.compare_digest(supplied, ("Bearer " + token).encode()):
        raise APIError(401, "unauthorized")


def _match_route(manifest, scope):
    method, path = scope.get("method"), scope.get("path", "")
    if not isinstance(path, str) or "%" in path or len(path) > 120:
        raise APIError(404, "not_found")
    for route in manifest.get("routes", []):
        if method != route["method"]:
            continue
        template = route["path"]
        if template.endswith("/{id}"):
            prefix = template[:-5] + "/"
            if not path.startswith(prefix):
                continue
            tail = path[len(prefix):]
            if re.fullmatch(r"[1-9][0-9]{0,9}", tail) and int(tail) <= _INT_MAX:
                return route, int(tail)
        elif path == template:
            return route, None
    raise APIError(404, "not_found")


def _pagination(scope):
    raw = scope.get("query_string", b"")
    if not isinstance(raw, bytes) or len(raw) > 128:
        raise APIError(400, "invalid_query")
    try:
        args = parse_qs(raw.decode("ascii"), strict_parsing=True, keep_blank_values=True)
    except (UnicodeError, ValueError):
        raise APIError(400, "invalid_query") from None
    if any(name not in ("limit", "offset") or len(values) != 1 for name, values in args.items()):
        raise APIError(400, "invalid_query")
    def number(key, default, maximum, minimum=0):
        value = args.get(key, [str(default)])[0]
        if not re.fullmatch(r"0|[1-9][0-9]{0,5}", value):
            raise APIError(400, "invalid_query")
        result = int(value)
        if result < minimum or result > maximum:
            raise APIError(400, "invalid_query")
        return result
    return number("limit", 20, _MAX_ROWS, 1), number("offset", 0, 10000)


async def _body(scope, receive):
    if _only_header(scope, b"content-type") != b"application/json":
        raise APIError(415, "json_required")
    raw = bytearray()
    while True:
        message = await receive()
        if message.get("type") != "http.request":
            raise APIError(400, "incomplete_request")
        chunk = message.get("body", b"")
        if not isinstance(chunk, bytes):
            raise APIError(400, "invalid_body")
        if len(raw) + len(chunk) > _MAX_BODY:
            raise APIError(413, "body_too_large")
        raw.extend(chunk)
        if not message.get("more_body", False):
            break
    return _decode_request(bytes(raw))


def _headers_for(item):
    return [(b"etag", _etag(item).encode("ascii"))]


async def handle_request(directory, scope, receive):
    """Return (status, JSON, extra headers); no raw HTTP/SQL exception leaks."""
    try:
        manifest = load_manifest(directory)
        route, key = _match_route(manifest, scope)
        _local_test_gate(scope)
        action, table = route["action"], route["table"]
        fields = manifest["tables"][table]
        if action != "list" and scope.get("query_string"):
            raise APIError(400, "invalid_query")
        if action == "list":
            limit, offset = _pagination(scope)
        else:
            limit = offset = None
        if action in ("create", "update"):
            body = _validate(fields, await _body(scope, receive), partial=action == "update")
        else:
            body = None
        supplied_etag = None
        if action in ("update", "delete"):
            header = _only_header(scope, b"if-match")
            if header is None:
                raise APIError(428, "precondition_required")
            try:
                supplied_etag = header.decode("ascii")
            except UnicodeError:
                raise APIError(400, "invalid_precondition") from None
            if re.fullmatch(r'"sha256-[0-9a-f]{64}"', supplied_etag) is None:
                raise APIError(400, "invalid_precondition")
        conn = _open(manifest, must_exist=True)
        try:
            conn.execute("BEGIN IMMEDIATE" if action in ("create", "update", "delete") else "BEGIN")
            try:
                applied = _ledger(conn, manifest)
                if applied != len(manifest["migrations"]):
                    raise APIError(503, "schema_unavailable")
                _verify_tables(conn, manifest)
                table_sql = _quote(table)
                if action == "list":
                    rows = conn.execute("SELECT * FROM " + table_sql +
                                        " ORDER BY id ASC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
                    result = (200, {"items": [_view(row, fields) for row in rows]}, [])
                elif action == "create":
                    cols = list(body)
                    query = ("INSERT INTO " + table_sql + " (" +
                             ",".join(_quote(c) for c in cols) + ") VALUES (" +
                             ",".join("?" for _ in cols) + ")")
                    cursor = conn.execute(query, [body[k] for k in cols])
                    row = conn.execute("SELECT * FROM " + table_sql + " WHERE id=?",
                                       (cursor.lastrowid,)).fetchone()
                    item = _view(row, fields)
                    result = (201, {"item": item}, _headers_for(item))
                else:
                    row = conn.execute("SELECT * FROM " + table_sql + " WHERE id=?", (key,)).fetchone()
                    item = _view(row, fields)
                    if action == "read":
                        result = (200, {"item": item}, _headers_for(item))
                    else:
                        if not hmac.compare_digest(supplied_etag, _etag(item)):
                            raise APIError(409, "conflict")
                        if action == "update":
                            cols = list(body)
                            sql = ("UPDATE " + table_sql + " SET " +
                                   ",".join(_quote(k) + "=?" for k in cols) + " WHERE id=?")
                            conn.execute(sql, [body[k] for k in cols] + [key])
                            changed = conn.execute("SELECT * FROM " + table_sql + " WHERE id=?", (key,)).fetchone()
                            current = _view(changed, fields)
                            result = (200, {"item": current}, _headers_for(current))
                        else:
                            conn.execute("DELETE FROM " + table_sql + " WHERE id=?", (key,))
                            result = (200, {"deleted": True, "id": key}, [])
                conn.execute("COMMIT")
                return result
            except Exception:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
        finally:
            conn.close()
    except APIError as exc:
        return exc.status, {"error": exc.code}, []
    except (ValueError, OSError, sqlite3.Error):
        return 503, {"error": "unavailable"}, []
