# Sedrava experimental 0.13 A2 — typed SQLite CRUD routes

**Draft source only. No release, production API or multi-user identity system.** This work is stacked on A1 PR #48 and requires a later integration against the approved 0.12 namespace/package baseline.

The examples/server_013_api_tasks.sdr file adds a closed, explicit set of GET/POST/PATCH/DELETE endpoints on a declared SQLite table. Only list/create/read/update/delete actions are valid. Identifiers are compiler-checked, all user data is sent as SQL parameters, no arbitrary Python or SQL source execution.

~~~text
endpoint GET "/api/tasks" -> list tasks
endpoint POST "/api/tasks" -> create tasks
endpoint GET "/api/tasks/{id}" -> read tasks
endpoint PATCH "/api/tasks/{id}" -> update tasks
endpoint DELETE "/api/tasks/{id}" -> delete tasks
~~~

**OFF by default.** Isolated loopback-only tests require SEDRAVA_API_EXPERIMENTAL_ENABLE=1 and a fresh random SEDRAVA_API_EXPERIMENTAL_TOKEN of at least 32 printable ASCII characters. Requests supply Authorization: Bearer <token> and a localhost Host. Both ASGI client/server addresses must be loopback. Never publish this token in JS, URLs, generated files or logs. A single shared test token is **not user authentication or per-record authorization**. Reverse proxy forwarding can make remote clients appear local: never expose this API through an Internet-facing proxy.

~~~sh
# Only from checked experimental source/its own wheel.
sedrava check examples/server_013_api_tasks.sdr
sedrava build server examples/server_013_api_tasks.sdr --output build/server-api
export SEDRAVA_DB_PATH="$PWD/build/tasks.sqlite"
python build/server-api/server.py migrate
export SEDRAVA_API_EXPERIMENTAL_ENABLE=1
export SEDRAVA_API_EXPERIMENTAL_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
python -m pip install uvicorn
cd build/server-api
python -m uvicorn server:app --host 127.0.0.1 --port 8000
~~~

Input: JSON <=8192 bytes; int32, real boolean, bounded UTF-8 text; unknown/duplicate members rejected. List: limit 1..50, offset 0..10000, ordered by id. All mutations use SQLite BEGIN IMMEDIATE + commit/rollback. GET item returns a content ETag; PATCH/DELETE require matching If-Match, returning 409 for conflict or 428 for a missing precondition. ETags hash the current row, not a monotonic revision counter; ABA updates can evade detection. HTTP error envelopes redact internals. Migration and backups remain explicit A1 functions, never implicit at startup.

No end-user sessions, tenant/row isolation, CSRF-with-cookies (no cookies), rate limiting, production concurrency certification, PostgreSQL, distributed transactions or public reverse-proxy deployment. **NO-GO for publicly accessible user data.** The next independent gate is real user identity and deny-by-default authorization per record.
