"""Experimental Sedrava server declaration parser and deterministic generator (0.13 slice A).

Only a closed, additive migration language is accepted. No arbitrary SQL or host
source interpolation is permitted. This is not a public multi-user API.
"""
import json
import re
from pathlib import Path

MAX_SOURCE = 65536
IDENT = r"[a-z][a-z0-9_]{0,31}"
IDENT_RE = re.compile(r"^" + IDENT + r"$")
ENV_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
COLUMN_RE = re.compile(r"^(" + IDENT + r"): (text\(([1-9][0-9]{0,3})\)|int|bool)(?: default (.+))?$")
CREATE_RE = re.compile(r"^    create table (" + IDENT + r"):$")
ADD_RE = re.compile(r"^    add column (" + IDENT + r")\.(" + IDENT + r"): (text\(([1-9][0-9]{0,3})\)|int|bool) default (.+)$")
MIGRATION_RE = re.compile(r"^migration ([1-9][0-9]{0,2}):$")
TITLE_RE = re.compile(r'^server "([^"\\\n]{1,80})"$')
DB_RE = re.compile(r"^database sqlite env ([A-Z][A-Z0-9_]{0,63})$")


def _fail(number, message):
    raise ValueError("Line %d: column 1: %s" % (number, message))


def _identifier(name, number):
    if not IDENT_RE.fullmatch(name) or name == "id" or name.startswith("sedrava_"):
        _fail(number, "invalid or reserved SQL identifier")


def _column(name, kind, size, default, number):
    _identifier(name, number)
    column = {"name": name, "type": "text" if kind.startswith("text(") else kind}
    if column["type"] == "text":
        length = int(size)
        if length > 1024:
            _fail(number, "text capacity exceeds 1024")
        column["length"] = length
    if default is not None:
        if column["type"] == "text":
            try:
                value = json.loads(default)
            except (ValueError, TypeError):
                _fail(number, "text default must be a JSON string")
            if not isinstance(value, str) or len(value) > column["length"] or "\x00" in value:
                _fail(number, "text default exceeds bounds")
        elif column["type"] == "bool":
            if default not in ("true", "false"):
                _fail(number, "bool default must be true or false")
            value = default == "true"
        else:
            if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)", default):
                _fail(number, "invalid int default")
            value = int(default)
            if not -2147483648 <= value <= 2147483647:
                _fail(number, "int default out of range")
        column["default"] = value
    return column


def parse_server(source):
    if not isinstance(source, str) or len(source) > MAX_SOURCE or "\x00" in source:
        raise ValueError("Server source exceeds size or character limits")
    raw = [(i, ln.rstrip()) for i, ln in enumerate(source.splitlines(), 1)
           if ln.strip() and not ln.lstrip().startswith("#")]
    if any("\t" in line or "\r" in line for _, line in raw):
        raise ValueError("Server source must use spaces and LF")
    if len(raw) < 4:
        raise ValueError("Expected server, database and migration declarations")
    title = TITLE_RE.fullmatch(raw[0][1])
    db = DB_RE.fullmatch(raw[1][1])
    if not title or not db or not ENV_RE.fullmatch(db.group(1)):
        _fail(raw[0][0], 'Expected server "Name" and database sqlite env VARIABLE')
    migrations = []
    tables = {}
    index = 2
    routes = []
    while index < len(raw):
        line_no, text = raw[index]
        if text.startswith("endpoint "):
            from sedrava_server_api import parse_routes
            routes = parse_routes(raw[index:], tables)
            index = len(raw)
            break
        match = MIGRATION_RE.fullmatch(text)
        if not match or int(match.group(1)) != len(migrations) + 1 or len(migrations) >= 128:
            _fail(line_no, "migrations must be contiguous from version 1 (maximum 128)")
        operations = []
        index += 1
        while index < len(raw) and raw[index][1].startswith("    "):
            number, line = raw[index]
            created = CREATE_RE.fullmatch(line)
            added = ADD_RE.fullmatch(line)
            if created:
                table = created.group(1)
                _identifier(table, number)
                if table in tables:
                    _fail(number, "table declared twice")
                index += 1
                fields = []
                while index < len(raw) and raw[index][1].startswith("        "):
                    num, text = raw[index]
                    cm = COLUMN_RE.fullmatch(text[8:])
                    if not cm or cm.group(4) is not None:
                        _fail(num, "expected indented field: name: text(N)|int|bool without default")
                    field = _column(cm.group(1), cm.group(2), cm.group(3), None, num)
                    if field["name"] in [f["name"] for f in fields]:
                        _fail(num, "duplicate field")
                    fields.append(field)
                    if len(fields) > 32:
                        _fail(num, "more than 32 fields in table")
                    index += 1
                if not fields:
                    _fail(number, "table needs at least one field")
                tables[table] = [f.copy() for f in fields]
                operations.append({"op": "create", "table": table, "fields": fields})
            elif added:
                table, name = added.group(1), added.group(2)
                if table not in tables:
                    _fail(number, "cannot add column to undeclared table")
                field = _column(name, added.group(3), added.group(4), added.group(5), number)
                if any(f["name"] == name for f in tables[table]) or len(tables[table]) >= 32:
                    _fail(number, "duplicate field or table capacity reached")
                tables[table].append(field.copy())
                operations.append({"op": "add", "table": table, "field": field})
                index += 1
            else:
                _fail(number, "unsupported migration operation (only create table/add column)")
            if len(operations) > 32:
                _fail(number, "more than 32 operations per migration")
        if not operations:
            _fail(line_no, "empty migration")
        migrations.append({"version": len(migrations) + 1, "operations": operations})
    if not migrations:
        raise ValueError("At least one migration is required")
    return {"format": 1, "server": title.group(1), "db_env": db.group(1),
            "migrations": migrations, "tables": tables, "routes": routes}


def load_manifest(directory):
    directory = Path(directory)
    source = (directory / "source.sdr").read_text(encoding="utf-8")
    expected = parse_server(source)
    stored = json.loads((directory / "schema.json").read_text(encoding="utf-8"))
    if stored != expected:
        raise ValueError("Generated schema differs from its reviewed Sedrava source")
    return expected


def build_server(source, output, source_path=None):
    spec = parse_server(source)
    output = Path(output).resolve()
    if output.exists() and not output.is_dir():
        raise ValueError("Server output must be a directory")
    names = ("source.sdr", "schema.json", "server.py", "README.md")
    if source_path is not None and Path(source_path).resolve() in {output / n for n in names}:
        raise ValueError("Output would overwrite Sedrava source")
    if any((output / name).is_symlink() for name in names):
        raise ValueError("Refusing to overwrite symlink output")
    from sedrava_cli import atomic_write_text
    script = '''"""Generated from restricted Sedrava server declarations; no embedded credentials."""
import argparse
from pathlib import Path
from sedrava_server_runtime import make_app, migrate_database, backup_database

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="Sedrava experimental SQLite server")
    cli.add_argument("command", choices=("migrate", "backup", "check"))
    cli.add_argument("destination", nargs="?")
    args = cli.parse_args()
    if args.command == "migrate":
        if args.destination: cli.error("migrate does not take a destination")
        print(migrate_database(ROOT))
    elif args.command == "check":
        if args.destination: cli.error("check does not take a destination")
        print(make_app(ROOT).status())
    else:
        if not args.destination: cli.error("backup requires a new output file")
        print(backup_database(ROOT, Path(args.destination)))
else:
    app = make_app(ROOT)
'''
    readme = '''# Generated Sedrava server — experimental slice A2

This source declares SQLite schema and forward-only migrations.
GET /health is available. Declared typed data endpoints are DISABLED by default.
For isolated loopback development tests only, set:
SEDRAVA_API_EXPERIMENTAL_ENABLE=1
SEDRAVA_API_EXPERIMENTAL_TOKEN=<random secret of at least 32 ASCII characters>
Call only from 127.0.0.1 with Authorization: Bearer <token>.
This single token is NOT multi-user authentication or per-record authorization.
Never put the token in browser JavaScript, URLs, source or public logs.
DO NOT expose the development data API through Nginx or the public Internet.

The separately installed Sedrava runtime is required (from the matching
experimental branch; stable 0.11.0 does not support this target).

Set the database path in the environment (see schema.json db_env). Ensure
the parent directory exists and is writable by the server account.

1. Before upgrades, stop the server and make a verified backup:
   python server.py backup /path/to/new-backup.sqlite
2. Apply explicit forward-only migrations:
   python server.py migrate
3. Run without exposing a public interface (requires separate uvicorn):
   python -m pip install uvicorn
   python -m uvicorn server:app --host 127.0.0.1 --port 8000
4. GET http://127.0.0.1:8000/health

Older server sources refuse databases with newer migration versions.
Restore backup *offline* only, after stopping all server processes.
Never edit old migrations or schema.json manually; append new migrations
to source.sdr and rebuild. A migration has no automatic DOWN operation.
'''
    output.mkdir(parents=True, exist_ok=True)
    for name, body in (("source.sdr", source), ("schema.json", json.dumps(spec, ensure_ascii=False, sort_keys=True, indent=2) + "\n"),
                       ("server.py", script), ("README.md", readme)):
        atomic_write_text(output / name, body)
    return output / "server.py"
