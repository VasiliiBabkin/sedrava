"""Experimental read-only ASGI health runtime and transactional SQLite migrations.

No public CRUD, authentication, sessions or multi-tenant access exists in slice A.
Migration application is explicit; importing the ASGI app never upgrades a DB.
"""
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from sedrava_server_schema import load_manifest

LEDGER = "_sedrava_migrations"


class MigrationError(ValueError):
    """Database version, checksum, schema or migration violation."""


def _path(manifest, *, must_exist):
    value = os.environ.get(manifest["db_env"], "")
    if not value or "\x00" in value or value.startswith("file:"):
        raise MigrationError("Set a local absolute SQLite path using " + manifest["db_env"])
    path = Path(value)
    if not path.is_absolute() or str(path) in ("/", "/dev/null"):
        raise MigrationError("SQLite path must be an absolute regular file path")
    if not path.parent.is_dir() or path.is_symlink():
        raise MigrationError("SQLite path parent is missing or database is a symlink")
    if path.exists() and not path.is_file():
        raise MigrationError("SQLite destination is not a regular file")
    if must_exist and not path.exists():
        raise MigrationError("SQLite database has not been migrated; run server.py migrate")
    return path


def _open(manifest, *, must_exist=False):
    path = _path(manifest, must_exist=must_exist)
    conn = sqlite3.connect(str(path), timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _digest(migration):
    raw = json.dumps(migration, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _quote(identifier):
    # All identifiers come only from the parsed/revalidated restricted source.
    return '"' + identifier + '"'


def _default_sql(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(value)
    return "'" + value.replace("'", "''") + "'"


def _column(field, *, adding=False):
    name, kind = field["name"], field["type"]
    col = _quote(name)
    if kind == "text":
        decl = "TEXT NOT NULL CHECK(length(" + col + ") <= " + str(field["length"]) + ")"
    elif kind == "bool":
        decl = "INTEGER NOT NULL CHECK(" + col + " IN (0, 1))"
    elif kind == "int":
        decl = ("INTEGER NOT NULL CHECK(typeof(" + col +
                ") = 'integer' AND " + col + " BETWEEN -2147483648 AND 2147483647)")
    else:
        raise MigrationError("Unknown field type")
    if "default" in field:
        decl += " DEFAULT " + _default_sql(field["default"])
    elif adding:
        raise MigrationError("Added NOT NULL fields require a default")
    return col + " " + decl


def _apply(conn, op):
    table = _quote(op["table"])
    if op["op"] == "create":
        columns = ['"id" INTEGER PRIMARY KEY AUTOINCREMENT']
        columns.extend(_column(f) for f in op["fields"])
        conn.execute("CREATE TABLE " + table + " (" + ", ".join(columns) + ")")
    elif op["op"] == "add":
        conn.execute("ALTER TABLE " + table + " ADD COLUMN " + _column(op["field"], adding=True))
    else:
        raise MigrationError("Unsupported migration operation")


def _ledger(conn, manifest):
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (LEDGER,)
    ).fetchone()
    if not exists:
        raise MigrationError("Missing migration ledger; run server.py migrate")
    rows = conn.execute('SELECT version, checksum FROM "' + LEDGER + '" ORDER BY version').fetchall()
    expected = manifest["migrations"]
    versions = [int(row["version"]) for row in rows]
    if versions != list(range(1, len(rows) + 1)):
        raise MigrationError("Migration ledger has missing or reordered versions")
    if len(rows) > len(expected):
        raise MigrationError("Database is newer than this server; refuse downgrade")
    for row in rows:
        mig = expected[row["version"] - 1]
        if row["checksum"] != _digest(mig):
            raise MigrationError("Applied migration was changed: version " + str(row["version"]))
    return len(rows)


def _verify_tables(conn, manifest, *, through=None):
    # Verify the declared fields and reject unexpected extra columns or deleted tables.
    tables = {}
    for migration in manifest["migrations"][:through]:
        for op in migration["operations"]:
            table = op["table"]
            if op["op"] == "create":
                tables[table] = [("id", "INTEGER")] + [
                    (f["name"], "TEXT" if f["type"] == "text" else "INTEGER")
                    for f in op["fields"]]
            else:
                f = op["field"]
                tables[table].append((f["name"], "TEXT" if f["type"] == "text" else "INTEGER"))
    for table, expected in tables.items():
        actual = conn.execute("PRAGMA table_info(" + _quote(table) + ")").fetchall()
        columns = [(row["name"], row["type"].upper()) for row in actual]
        if columns != expected or not actual or actual[0]["pk"] != 1:
            raise MigrationError("Database schema drift: " + table)


def verify_database(directory):
    manifest = load_manifest(directory)
    conn = _open(manifest, must_exist=True)
    try:
        version = _ledger(conn, manifest)
        if version != len(manifest["migrations"]):
            raise MigrationError("Database needs migration; run server.py migrate")
        _verify_tables(conn, manifest)
        return {"status": "ok", "schema_version": version}
    finally:
        conn.close()


def migrate_database(directory):
    manifest = load_manifest(directory)
    conn = _open(manifest)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute('CREATE TABLE IF NOT EXISTS "' + LEDGER + '" ('
                         'version INTEGER PRIMARY KEY, checksum TEXT NOT NULL)')
            applied = _ledger(conn, manifest)
            _verify_tables(conn, manifest, through=applied)
            for migration in manifest["migrations"][applied:]:
                for op in migration["operations"]:
                    _apply(conn, op)
                conn.execute('INSERT INTO "' + LEDGER + '" (version, checksum) VALUES (?, ?)',
                             (migration["version"], _digest(migration)))
            _verify_tables(conn, manifest)
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    return verify_database(directory)


def backup_database(directory, destination):
    manifest = load_manifest(directory)
    source = _path(manifest, must_exist=True)
    target = Path(destination).absolute()
    if target == source or target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise MigrationError("Backup destination must be new and outside the database path")
    verify_database(directory)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".sedrava-backup-", delete=False) as handle:
            temporary = Path(handle.name)
        os.chmod(temporary, 0o600)
        src = _open(manifest, must_exist=True)
        dst = sqlite3.connect(str(temporary))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        # Exclusive hardlink prevents races and accidental overwrite.
        os.link(temporary, target)
        return {"backup": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class HealthApp:
    def __init__(self, directory):
        self.directory = Path(directory)
        verify_database(directory)

    def status(self):
        return verify_database(self.directory)

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                event = await receive()
                if event["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif event["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
            return
        if scope["type"] != "http":
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
                return
            raise ValueError("Unsupported ASGI scope")
        method, path = scope.get("method"), scope.get("path")
        extra_headers = []
        if method == "GET" and path == "/health":
            try:
                payload = self.status()
                status = 200
            except (MigrationError, sqlite3.DatabaseError, OSError, ValueError):
                payload, status = {"status": "unavailable"}, 503
        else:
            from sedrava_server_api import handle_request
            status, payload, extra_headers = await handle_request(self.directory, scope, receive)
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json; charset=utf-8"),
                                (b"cache-control", b"no-store"),
                                (b"content-length", str(len(raw)).encode("ascii")),
                                (b"x-content-type-options", b"nosniff")] + extra_headers})
        await send({"type": "http.response.body", "body": raw})


def make_app(directory):
    return HealthApp(directory)
