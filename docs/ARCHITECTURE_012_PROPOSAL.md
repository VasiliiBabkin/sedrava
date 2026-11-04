# Sedrava — architecture proposal for scalable modules, packages and trusted server apps

**Status: PROPOSAL ONLY. Nothing in this document changes the language, executable CLI or published 0.10.0.** Namespaces, versioned packages, `build server`, SQL, databases and authentication described here are **not yet implemented**. Target milestone numbers 0.12+ are tentative; do not market them as released.

Reference baseline: [experimental 0.11 integration PR #36](https://github.com/VasiliiBabkin/sedrava/pull/36), [native documentation PR #37](https://github.com/VasiliiBabkin/sedrava/pull/37), [server boundaries](011_EXTENSION_BOUNDARIES.md).

## Problem and source-of-truth

Currently `sedrava_modules.py` expands local `.sdr` imports textually, root-constrained and bounded, into a **flat** declaration space. It supports components/styles/records/functions as compile-time definitions; there are no namespace-qualified identities, private/public visibility contracts, general packages, compiler-stable plugin ABI or executable server target. The WebApp browser can call declared HTTP services, **but it does not provide a trusted backend**. `main` remains published 0.10.0; not all features of PR #36 are merged.

Goal: "Describe → generate" for substantial projects while keeping source and dependencies auditable and deterministic. Avoid introducing arbitrary host-language execution as a shortcut.

## Decision record A — module identities and namespaces (FIRST implementation)

### Proposed author experience (illustrative syntax, NOT compilable today)

```sedrava
module company.contacts

export record Contact:
    name: text
    email: text

private fn normalize(value: text) -> text = trim(value)

export fn has_name(value: text) -> bool = trim(value) != ""
```

```sedrava
module company.dashboard

import "contacts.sdr" as contacts

# Qualified symbol identity avoids collisions:
# contacts.Contact; contacts.has_name
```

The exact `module`, `export`, `private` and qualified-reference tokens are **design proposals**. Write grammar/AST proposals first, decide names before implementing, then freeze the syntax for a milestone.

**Contract:**
1. Stable canonical module IDs (ASCII qualified identifiers, normalized once). Root module and explicitly imported aliases only; no implicit global namespace or implicit shadowing.
2. Public exports are explicit; unexported declarations are private. Private identifiers never appear in public metadata, generated interfaces or package exports. Duplicate exports, ambiguous aliases and reserved names fail compilation.
3. A symbol's identity includes module ID + local name + symbol kind, never just a flattened string. Type checking, IR, code generation, diagnostics and source maps all preserve this identity through Web, Python and Android targets where applicable.
4. Imports are root-confined and compile-time deterministic. Reject cycles, missing imports, alias collisions, symlinks, path traversal, unapproved remote fetch and oversized dependencies. Re-export must be explicit. Errors show the true originating file, line, column and import chain.
5. Existing flat `import "...sdr"` source MUST keep working for the currently documented 0.11 experimental semantics. An explicit new module mode may offer namespaced imports; do not silently reinterpret old source. Add a mechanical migration diagnostic/command before deprecation.
6. Functions, records and components are in initial module scope. Shared state, services, server routes and side effects require an explicit later contract: import must not silently grant capabilities.
7. Different targets must either have matching semantics or return a compile-time "unsupported target" diagnostic. Never silently drop declarations.

**Required tests:** alias collisions, private export leak, function/record identity, same name in separate modules, nested imports, cycles, path containment, Unicode spoofing/reserved names, reproducible bundle, source maps for generated code, compatibility with previously green 0.10/0.11 examples.

### Completion gate

Three independently compiled library modules with colliding local names can be imported under aliases in one real example, type-check and run through all relevant generated targets. A negative test verifies private symbols cannot be referenced. The compiler exposes source-relative diagnostics. All legacy compatibility suites remain green.

## Decision record B — package system (SECOND implementation)

Proposed manifest and lockfile, not currently supported:

```toml
# sedrava.toml — example design
[package]
name = "example.taskboard"
version = "0.1.0"

[dependencies]
"sedrava.std.web" = "0.1.0"
```

- Package name/version, declared target platforms, namespace roots and exported modules have a deterministic manifest schema.
- `sedrava.lock` records exact dependency identities, versions, hashes, transitive dependency tree, compatibility and approved download origins.
- Explicit `vendor`/offline mode; no network resolution during an ordinary reproducible build unless deliberately opted in.
- Verify hashes before interpreting external source. Reject lockfile drift, dependency cycles and namespace collisions.
- Define minimum compiler/language-version bounds; semantic compatibility and migration policy. Reserve `std` namespace; never allow user packages to impersonate standard modules.
- Packages can contain checked Sedrava source, templates and reviewed static resources. This is **not** permission to execute arbitrary Python, JavaScript, SQL, Kotlin or native plugins.
- Standard libraries should be modular: `std.collections`, `std.text`, `std.web`, `std.storage` (when available). Importing an SDK never implicitly grants server, filesystem or networking authority.

**Gate:** two versioned third-party fixture packages, a transitive dependency, conflict/mismatch negative tests, offline clean checkout, tampered archive detection, cross-target compatibility checks, clear source diagnostics.

## Decision record C — trusted server runtime and database (THIRD implementation)

### First target

New explicitly separated command **proposal**: `sedrava build server <source.sdr> --output <dir>`. Generate a restricted **Python ASGI backend**, initially SQLite using a maintained server stack and Python's standard `sqlite3` where applicable. This is a target choice to validate, not a present feature.

Keep `build site` and `build webapp` static/browsable and compatible. Never bundle database credentials into frontend assets, sourcemaps, manifests or CI logs. WebApp typed HTTP services can call the generated backend through exactly declared routes and response schemas.

### Proposed declarative source sketch (NOT compilable)

```sedrava
module taskboard.server

database tasks:
    driver sqlite
    location env "TASKBOARD_DB_PATH"

table Task:
    id: int
    title: text
    done: bool

endpoint GET "/api/tasks":
    # The eventual query API is intentionally not specified here.
    # Define typed filters, owner scopes and bounded pages first.
```

Do **not** implement the illustrated `endpoint`/SQL syntax verbatim before a reviewed spec. In particular, browser-owned `state` and `rule` are not trusted authorization mechanisms.

### Minimum server contract

1. Explicit allowed methods/routes, typed bounded request/response schemas and status mapping, normalized path parameters, request body limits, deterministic canonical JSON/UTF-8, escaping, defined timeout/cancel and no unsanitized code injection.
2. Schema declarations have stable IDs, ownership and migration versions. SQLite first for single-node workloads; document WAL/busy-timeout/concurrent-writer limits and realistic backup/restore. PostgreSQL second; MariaDB optional after adapter stability.
3. Parameterized SQL only; no string interpolation of user input in SQL, identifiers or paths. Map typed query constructs to parameterized statements; no implicit "GET all data" exposure.
4. Full transaction per domain action including invariant checks and database commit; failed validation/permission/exception rolls back. Concurrency conflict and idempotency policies are explicit. Retry cannot silently double-create records.
5. Authentication uses maintained standards/providers, secure session handling and current library best practices. Authorization is separate: deny by default, independently checked on every route and individual record. Never trust client-supplied user IDs, roles or owner fields.
6. CSRF protections for cookie-based sessions, secure cookie flags, request rate/body limits, auditable logging that redacts secrets/PII, safe error envelopes, explicit CORS, threat-model review. Do not write homemade cryptography.
7. Manage secrets via runtime environment/secret manager, not checked-in `.sdr`, browser bundle, lockfile, debug logs or generated public artifacts.
8. Deployment must provide database location ownership/permissions, pinned dependencies, health checks, Nginx reverse proxy guidance, rollback/migration compatibility and tested backup restoration. Never allow the server target to touch arbitrary filesystem/network resources by default.
9. A single-server process and SQLite is the starting point, **not** a claim of distributed/multi-tenant production readiness. Publish clear concurrency and reliability limitations.

### Minimum live acceptance

Build an authenticated taskboard against actual SQLite on the CI runner. Exercise create/read/update/delete for two independent users and prove user A cannot access user B's data. Verify restart durability, failed transaction rollback, SQL injection attempts, CSRF, limit handling, migration forward/back compatibility, concurrent writes and real backup → restore. Use real generated server output, not a mocked success-only adapter. Add database corruption handling and restore/rollback tests before production recommendation.

**Gate:** passing Python unit tests + real ASGI integration + real browser-to-API E2E + security regression + installed-package clean-room build; no known P0/P1. Any missing auth/authorization/storage guarantee must be documented as NO-GO for public multiuser deployment.

## Related work that must accompany serious-project support

- Explicit error/result types and typed validation for external I/O; async/timeouts/cancellation model for HTTP; ordinary domain actions retain atomicity.
- More complete scalar types: decimal/fixed-point monetary values with documented rounding; 64-bit IDs or opaque identity type; timestamps/timezones. No silent widening of existing signed int32 operations.
- Namespaced standard library and documented capability declarations; static code analysis for leaks, dead imports, shadowing and public API compatibility.
- Stable compiler/CLI output contracts, symbol-aware IDE completion and Go-to-definition, reproducible tests and golden fixtures.
- Storage migration/versioning, package compatibility and published release-support policy.
- Real deployment example with separate webapp, backend, secrets, migrations and rollback; source-controlled integration tests.

## Proposed implementation order and version policy

A. Stabilize experimental WebApp 0.11 functionality and maintain the public stable 0.10 baseline.  
B. Namespaces, lexical imports, visibility and precise diagnostics.  
C. Package manifests/lockfile, reproducible offline builds, compatibility.  
D. Server route + SQLite transactional skeleton, *without promising auth*.  
E. Authentication + authorization + real multi-user data isolation and audit.  
F. PostgreSQL adapter, migrations/backups, production hardening.  
G. More scalar types/SDK/IDE support and library ecosystem.

Milestone numbers such as **0.12**/**0.13** are planning labels, not release commitments; choose versions only after tested scope and compatibility review. Backend and namespace work should be isolated in draft PRs; do not merge or publish based solely on demonstration tests.

## Prioritized autonomous Codex implementation contract

Start with **A/B**, not F. Inspect the latest compiler branch and dependent PRs. Implement namespaced AST + symbol table and regression tests, not a text-replacement workaround. Keep every commit reproducible, create a separate draft PR, record current SHA/tests/known limitations, and stop only for genuine environment or approval blockers. If scope cannot be finished in one session, preserve an explicit checkpoint; do not claim all features are complete.

After namespace gates pass, do C, then D and E in separate reviewed PRs. Server/database functionality must never be announced until actual integration and isolation tests pass. Production deployment requires owner approval.

## Why this is different from "database support like PHP"

PHP runs trusted server code; present Sedrava 0.11 WebApps run client code in the browser. A browser-accessible JSON API alone is not a server-side database driver. The proposed server target establishes an independent trust boundary, explicit storage/transactions, identity, and per-record authorization.
