> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# Sedrava Server A6 — durable SQLite receipts and managed `db_get`

Status: **experimental, local-only (127.0.0.1), not a release or production DB**.

A6 depends on the **independent SedravaSQL** library at exact Git commit
`e36ab0f2e706b4177e203a6aca0a3711918b77da`.
This is an opt-in mode independent of A5. No automatic A5 migration or silent
replacement. The old A1–A5 server modes remain available with their previous
limits and storage formats.

## First run

Use a fresh, private directory (0700) and a new database file. On Unix
SedravaSQL creates a 0600 file; symlinks, public-mode files and extra
hardlinks are rejected.

```sh
mkdir -m 700 -p /ABSOLUTE/TRUSTED/a6
sedrava-native server check examples/native_server/sqlite_a5.sdr
sedrava-native server run examples/native_server/sqlite_a5.sdr \
  --transactional --sqlite-v2-state /ABSOLUTE/TRUSTED/a6/state.sqlite \
  --port 8081 --max-requests 100 --idle-ms 30000
```

To write an HTTP action, send an `Idempotency-Key` of 12..64 ASCII
characters and optionally the `X-Sedrava-If-Revision` CAS header.
Every successful write commits the typed state, audit record and exact
HTTP receipt together inside **one SQLite transaction**.
The full HTTP reply is stored in the SedravaSQL `receipts` table, rather than
in the limited JSON state snapshot.

**The A6 32-receipt restriction is removed** for this mode. Every request key
is retained and its response can be replayed across restarts. **No automatic
eviction, TTL, archive or GC exists yet.** The database grows without a
predefined entry cap; when disk/resources run out, a write can fail closed.
Do not manually delete receipts: that can invalidate the retry contract.
Periodic backup and explicit quota/retention policy are required before
real-world workloads.

A6 writes a distinct `sedrava.server.sqlite.v2` state envelope in
the `sedrava_native_a6` namespace, tied to exact source hash and
declaration signature. Modifying the .sdr program selects a new key;
there is **no automatic migration**. A stale second server process
returns HTTP 503 on CAS conflict and exits; this is not cooperative
multiwriter execution. No public listener/TLS/authentication is included.

## First direct data operation from Sedrava

A6 supports a narrowly scoped read-only expression in a **GET response**:

```sedrava
server "A6 SQL Read Example"
state enabled: bool = true
route GET "/note":
    respond 200 { note: db_get("public_notes/welcome"), enabled: state.enabled }
```

The `db_get("namespace/key")` expression reads a *managed UTF-8 key/value*
from SedravaSQL at request time, so updates from another SedravaSQL client
can appear immediately. The path is a literal fixed in source, not a user
argument. Namespace and key accept 1–128 ASCII letters/digits/`._-`.
Namespaces beginning with `sedrava_native` are reserved and rejected.
The result is bounded to 1024 Unicode scalar values without control
characters. Missing or deleted values return 404 `DB_KEY_NOT_FOUND`;
unreadable or invalid values fail closed (503). Use
[the example](../examples/native_server/sqlite_a6_read.sdr).

To populate it, use the independent SedravaSQL CLI against the same DB:

```sh
sedravasql init /ABSOLUTE/TRUSTED/a6/state.sqlite
sedravasql put /ABSOLUTE/TRUSTED/a6/state.sqlite public_notes welcome "Привет" \
  --expect 0 --request-key welcome-change-00001
```

`db_get` is not arbitrary SQL, not a write statement, not a dynamic query
and not an SQL transaction language. Only GET response expressions permit it;
other modes or routes fail validation before listening. Future typed write
operations need an atomic multi-key state+receipt+audit contract.

## Verification

```sh
cargo fmt --manifest-path rust/Cargo.toml --all -- --check
cargo test --manifest-path rust/Cargo.toml --locked --offline --all-targets
cargo build --manifest-path rust/Cargo.toml --locked --offline --bin sedrava-native
python3 scripts/verify_native_server_sqlite_a6.py
python3 scripts/verify_native_server_db_read.py
```

Tests use disposable directories, local TCP and separate SedravaSQL CLI,
not production data or public network listeners. See the
[A6 verification report](../evidence/native-server/2026-11-23-a6-sqlite.md)
for exact scope. Physical power-loss durability, hostile same-UID file
races, Windows/macOS, external authentication, resource quotas,
backup retention, migration and long-term storage are not verified.
