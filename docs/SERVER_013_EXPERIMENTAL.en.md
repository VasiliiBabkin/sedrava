# Sedrava experimental server / SQLite — slice 0.13 A1

**Unreleased, separate draft PR.** Neither stable 0.11.0 nor experimental 0.12 includes this target. This prototype is isolated on the published 0.11 baseline and must later be reconciled with 0.12 namespaces.

## Implemented boundary

A restricted server declaration supports a SQLite database path obtained from a runtime environment variable and consecutive, additive migrations. Allowed operations are create table and add column with a checked default. Fields are int32, bool or text(1–1024); identifiers are strict ASCII. Arbitrary SQL, destructive schema changes and host Python execution from Sedrava are forbidden.

~~~sh
python sedrava_cli.py check examples/server_013_tasks.sdr
python sedrava_cli.py build server examples/server_013_tasks.sdr --output build/server
export SEDRAVA_DB_PATH="$PWD/build/tasks.db"
python build/server/server.py migrate
python build/server/server.py check
python -m pip install uvicorn
cd build/server
python -m uvicorn server:app --host 127.0.0.1 --port 8000
# GET http://127.0.0.1:8000/health
~~~

Output: server.py, original source.sdr, checked schema.json and local README.md. ASGI imports verify the schema version, **never automatically applying migrations**.

## Safety and rollback

Migrations run in a single BEGIN IMMEDIATE SQLite transaction with SHA-256 checksums recorded in _sedrava_migrations. A failed operation rolls back the DDL and its ledger entry. Changing an already-applied migration, skipping a version, or starting an older binary on a newer schema fails closed. Only NOT NULL additive columns with a checked literal default are supported.

Before schema changes, stop the server and create a verified new snapshot via python server.py backup /absolute/path/new-backup.sqlite (SQLite online backup API). No destructive DOWN migration exists; restore the snapshot only while fully offline, accounting for SQLite WAL/SHM. Never edit generated schema.json directly; it is checked against the parsed source.sdr.

## Explicit limitations

ASGI exposes **GET /health only**, with all other HTTP paths returning 404. No generated CRUD, user authentication, per-record authorization, public multi-user API, PostgreSQL, browser/Android state migrations, or production deployment/certification. **NO-GO for public data service.** Next independent slices: typed API routes and transactions, real two-user authorization/isolation, concurrency/backup recovery, then PostgreSQL.

References: https://www.sqlite.org/lang_altertable.html and https://docs.python.org/3/library/sqlite3.html
