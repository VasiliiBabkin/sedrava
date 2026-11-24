# Sedrava — Roadmap / Дорожная карта

## Native Rust Core / Экспериментальный перенос ядра

**Current detailed coverage:** [full migration status and release gates](RUST_FULL_MIGRATION.ru.md). The experimental native core now also implements records, bounded lists, pure functions, queries, scalar stdlib and navigation; Web/Android generators, modules, Host effects and persistence still use Python.


- Отдельная ветка: experiment/rust-core-migration.
- Реализовано самостоятельное Rust-ядро для ограниченного набора скалярных
  .sdr-программ (парсер, проверка типов, интерпретатор, CLI).
- Тестовые программы сравниваются с Python через
  [scripts/verify_rust_core.py](../scripts/verify_rust_core.py).
- Код не заменяет опубликованную Python 0.11.0; генераторы Web/Android,
  records/collections, imports и Host Effects пока не перенесены.
- Решение и следующие этапы: [ADR](ADR_RUST_CORE.md) и
  [руководство](RUST_CORE_MIGRATION.ru.md).
- Любое утверждение о скорости должно быть ограничено сценарием,
  датой, оборудованием и воспроизводимыми измерениями.

## Published releases / Опубликованные версии

- **0.10.0**, previous stable version: [GitHub](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0), [PyPI](https://pypi.org/project/sedrava/0.10.0/), published 31 October 2026. Unicode, records, bounded lists, navigation and Web/Android generation.
- **0.11.0rc1**, published experimental *prerelease*: [GitHub](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1), [PyPI](https://pypi.org/project/sedrava/0.11.0rc1/), published 4 November 2026. Responsive `site`, typed interactive `webapp`, pure functions, collections, forms, hash routes and bounded public HTTP clients.
- **0.11.0**, **published stable**: [GitHub](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0), [PyPI](https://pypi.org/project/sedrava/0.11.0/), published 5 November 2026. Reviewed Web platform, versionCode 11002 and real prior-version upgrade/rollback tests. [Release gates](STABLE_RELEASE_GATES_011.md).
- **0.12.0a1**, *unpublished experimental alpha*: namespaces/aliases [PR #39](https://github.com/VasiliiBabkin/sedrava/pull/39), original-source diagnostics [PR #40](https://github.com/VasiliiBabkin/sedrava/pull/40), offline local packages/locks [PR #41](https://github.com/VasiliiBabkin/sedrava/pull/41) and alpha preparation [PR #43](https://github.com/VasiliiBabkin/sedrava/pull/43). Must be reconciled on the now-published stable 0.11 baseline.

## Direction / Направление

**0.11 stable** retains the published RC functionality and previously supported app/Web/Android targets. It does not include 0.12-qualified imports/packages, a trusted server, database, authentication or automatic schema migrations. The browser HTTP client depends on an independently operated API.

**0.12 and later** will develop a native typed symbol IR, package-qualified module imports, extension interfaces and developer tooling. A future server/SQLite path is a design proposal rather than an implemented feature or committed release date. No production security certification is claimed for released pre-1.0 versions.

**Release discipline:** Python 3.10/3.12/3.13, actual browser and Android tests, clean-installed wheel/sdist, reproducibility, 0.10 and published RC upgrade/rollback, known limitations and explicit owner approval for exact source SHA and hashes. [0.11 RC upgrade audit](UPGRADE_AUDIT_011.md) · [EN guide](011_WEB_PLATFORM.en.md) · [RU guide](011_WEB_PLATFORM.ru.md) · [0.10 stability](STABILITY_AUDIT_010.md).

The official [documentation website](https://sedrava.virtreal.ru/) is built separately with Astro/Starlight. A Sedrava-generated dev preview is separate. **Describe the application; get the application. / Опиши — получи.**

## Long-term objective: Sedrava self-hosted compiler

The goal is a compiler written in Sedrava that compiles its own source via
reproducible stage-1/2/3 bootstrapping. **This is not implemented/released.**
Rust remains the tested bootstrap compiler; stable 0.11.0 is Python-based.
Read the [self-hosting roadmap](SELF_HOSTING_ROADMAP.ru.md) for exact gates.
SedravaSQL is a separate database project and is not required for building
the language compiler.

### Self-hosting lexer A0 preview

A limited ASCII-token scanner is implemented in real Sedrava source and executed via native Rust CLI. It requires one external CLI action per input scalar, so it is **not** autonomous or self-hosting. A new portable text_at(text,index) Unicode-scalar primitive has Rust/Python/JS parity tests; Kotlin runtime source was updated but a Kotlin compiler is unavailable in the tested VDS environment. See [detailed Russian evidence](SELF_HOSTING_LEXER_A0.ru.md).

### Native bounded loop and self-hosting lexer A1

An experimental bounded while condition limit N statement (1..256) is supported in the Rust interpreter and native Web/Android code generators. A one-action Sedrava-authored lexer uses this internal loop; it no longer relies on one external CLI action per character. Stable Python 0.11 has no such syntax. 81 native tests and an independent lexical golden corpus pass. Web JS syntax checked with Node; Kotlin compilation not available on the VDS. This is **not** a self-hosted compiler. See [A1 protocol](SELF_HOSTING_LEXER_A1.ru.md).

### Native 0.12.0-alpha.1 candidate (2026-11-23)

The native Rust CLI has a separate 0.12.0-alpha.1 candidate version.
It is not a published release. Ubuntu Linux validation included
81 Rust tests, 390 Python/Rust differential examples, 7 CLI smoke
gates, Host and A6 regression, versioned binary packaging and offline
installation. The Python 0.11 stable package remains unchanged.
Android APK, Windows/macOS, full 0.11 parity, cross-browser validation
and release security review are still BLOCKERS for stable 0.12.
[Release notes](RELEASE_NOTES_NATIVE_0_12_0_ALPHA1.ru.md) ·
[gate matrix](NATIVE_012_ALPHA_ACCEPTANCE.md).

### Verified published 0.11.0 compatibility sample and Kotlin/JVM (2026-11-23)

Native 0.12 alpha was checked against the **exact published Python 0.11**
tag (not the developing main): 297 Git blobs verified, 898 run/test/check
comparisons without observed mismatch under the limited criteria.
Seven published Site/WebApp sources build in both engines and pass
determinism/assets/JS syntax checks. Four jsdom interactions pass in
each relevant engine; generated Kotlin was really compiled/run with
Gradle Kotlin/JVM. Real Chromium browser acceptance was attempted but
the download was blocked, Android SDK/APK is unavailable. No new
stable/beta release authorization is implied.
[Detailed evidence (RU)](NATIVE_012_STABLE011_PARITY.ru.md).

### 0.12.0-alpha.1 real Android debug APK smoke (2026-11-23)

Android SDK Platform 35 + Build Tools 35 were installed on VDS (retained
for future development). A real debug Android APK was generated from
`examples/android_native_test.sdr` via native Rust CLI and compiled by
Gradle 8.11.1 / Android Gradle Plugin 8.9.2 / Kotlin 2.0.21. Android
Build Tools verified the APK, v2 debug signature, package, minSdk 26,
targetSdk 35 and no dangerous system permissions. **Device install,
on-phone behavior and OTA/upgrade are NOT TESTED** until user completes
physical smoke. See [Android APK protocol](NATIVE_012_ANDROID_APK_SMOKE.ru.md).

### Self-hosting lexer A2 (2026-11-23)

A2 extends the one-action Sedrava-authored scanner to quoted Unicode
strings with basic escapes, comments, whitespace and compound
operators, still with <=256 scalar input and <=100 token limits.
68 accepted + 16 rejected independent oracle cases PASS, A1 corpus
and 81 Rust unit tests PASS. Native-generated Kotlin/Android
assembleDebug succeeds. Full grammar/AST/self-hosting remain NO-GO.
[RU evidence and reproduction](SELF_HOSTING_LEXER_A2.ru.md).

### Self-hosting A3: token source spans and tiny assignment AST (2026-11-23)

A Sedrava-authored scanner preserves its A2 subset and now yields
UTF-8-independent Unicode-scalar [offset,end) spans, 1-based line and
column, and operator-vs-punctuation kinds. One additional action
builds one typed Assignment(name,literal,start,end) AST node only for
identifier = integer. 112 accepted / 19 rejected token cases and
6 accepted / 9 rejected AST cases PASS. A1/A2 and 81 Rust tests PASS.
A real generated Android/Kotlin debug APK was also compiled by
Gradle/Android SDK on VDS and signature-verified (no device test).
This does NOT implement a full parser or stage 1/2/3 self-hosting.
[Protocol (RU)](SELF_HOSTING_LEXER_A3.ru.md).

### Experimental self-hosting parser A4 (2026-11-23)

A4 adds a separate Sedrava-authored scan_layout action producing
NEWLINE/INDENT/DEDENT for strict four-space indentation (<=8 levels)
and a limited parse_binary action with two literal operands or
the fixed precedence form INTEGER +/- INTEGER * / INTEGER.
Independent corpus: layout 106 accepted / 10 rejected, expression
AST 12 accepted / 15 rejected, plus A1-A3 regressions and 81 Rust
tests PASS. Not a general grammar, shared token stream or self-hosting.
A real Android/Kotlin debug APK also compiled via Gradle on the VDS
and its signature was verified; physical Android execution is NOT TESTED.
[Detailed limitations (RU)](SELF_HOSTING_PARSER_A4.ru.md).

### Experimental self-hosting A5.1: ordered token stream (2026-11-23)

Three separately executed Sedrava actions scan lexical tokens, scan
strict four-space layout and merge them by Unicode-scalar start offset
into a single UnifiedToken list, prioritizing layout at equal offsets.
91 accepted / 10 rejected oracle samples PASS; Rust 81 PASS; generated
Android/Kotlin assembleDebug PASS (no device execution). The merger is
limited to 100 output tokens, 256 input scalars, fresh-run IDs and a
narrow subset with no strings in layout code. No full grammar/AST.
[RU details](SELF_HOSTING_UNIFIED_A51.ru.md).

### Native server A7 (2026-11-24): read-only SedravaSQL revision

A7 adds typed db_revision("namespace/key") to the local native server
DSL, next to db_get. For the same key both fields reuse one managed
SedravaSQL row read, with checked int32 revision conversion.
Live independent CLI writes and Sedrava GET updates PASS; seven
invalid DSL cases PASS, overflow fails closed, 82 Rust tests PASS,
A6 integration regressions PASS. No arbitrary SQL/write/multi-key
snapshot. See RUST_NATIVE_SERVER_A7_DB_METADATA.ru.md.

### Experimental server A8: one-key SedravaSQL write (2026-11-24)

Server DSL now supports bounded, statically checked
`db_put "namespace/key" = request.FIELD` as the ONLY effect
in a `PUT` route; the response is composed from immutable request
scalars/literals. A8 delegates to SedravaSQL SQLite
`Database::mutate_with_response` so business KV row, audit and
original HTTP receipt are committed in ONE SQL transaction.
Per-key CAS and source/route-scoped idempotency are replayable after
restart; separate X-Sedrava-KV-Revision response header distinguishes
the key from A6 server-state revision. Negative DSL cases, real
cross-process HTTP/CLI and four controlled SQL commit windows tested
on disposable loopback databases. No cross-key/state atomic
transactions, general SQL, public network service or hardware
power-loss certification. [RU details](RUST_NATIVE_SERVER_A8_DB_PUT.ru.md).

### Native server A9: 2 managed keys plus one server state (experimental)

The A9 fixed-form server DSL declares exactly two
db_batch_put namespace/key = request.text expect request.int
statements followed by one state.set. Per-key CAS and separate A6
server-state CAS are checked within the same opt-in SedravaSQL B6
SQLite BEGIN IMMEDIATE transaction. All three record updates,
legacy audit/receipts and a durable batch response are all-or-none.
Replay after restart, concurrent server invalidation, external CLI CAS
conflict, 12 invalid DSL cases and four debug SQLite crash windows
PASS on disposable localhost-only databases.
The compiler pins SedravaSQL commit 7aad14da (B6).
No general SQL, arbitrary batch, multi-key GET snapshot, public API,
or hardware power-loss certification.
[Full RU protocol](RUST_NATIVE_SERVER_A9_ATOMIC_BATCH.ru.md).

### Native Server A10: multi-key coherent GET (experimental, 2026-11-24)

A10 pins SedravaSQL B7 commit 225bf905 and delegates all distinct
db_get/db_revision expressions in a single HTTP GET to ONE
read-only SQLite WAL snapshot. Up to 16 unique literal managed keys,
with fail-closed 404 for absent/deleted key, 503 on invalid text or
overflowing int32 revision. Existing A7/A8/A9 syntax unchanged.
Two independent Sedrava processes passed 81 A9 batch writes and
242 concurrent GET reads with no mixed revisions, validating persisted
audit/receipts. In-memory server state is NOT part of a B7 read
snapshot; neither multiple GETs nor other backends gain this
consistency guarantee. [RU protocol](RUST_NATIVE_SERVER_A10_COHERENT_GET.ru.md).

### Experimental self-hosting A5.2 (2026-11-24)

The Sedrava-authored parse_program action reads actual A5.1
UnifiedToken stream, returning bounded assignment+indent AST:
name/literal, depth, line, Unicode-scalar [start,end) positions.
Narrow grammar only ASCII name=integer lines and 4-space layout.
30 accepted and 22 rejected programs PASS against independent
AST/layout/token oracles, plus pre-merge/double-parse rejection;
83 Rust tests PASS. No full language grammar, IR, type checking,
self-hosted stage 1/2/3 or new Android APK.
See SELF_HOSTING_PARSER_A52.ru.md.

### Self-hosting A5.3: bounded arithmetic AST over unified tokens

A Sedrava-written parse_expression_program action builds typed
integer/binary expression nodes with Unicode source spans, stable
node IDs and 4-space layout nesting from real A5.1 unified tokens.
Supports 1..3 integer literals with + - * /, multiplicative precedence
and left-associativity for equal ranks. Independent Python oracle
acceptance: 37 valid and 23 invalid source cases PASS. Rust 83 tests
PASS. No parentheses, identifiers RHS, general expression grammar,
type checker, IR or stage 1/2/3. [RU report](SELF_HOSTING_PARSER_A53.ru.md).

### Self-hosting A5.4a: bounded stack-based arithmetic parser

Sedrava-authored two-stack parser supports more than three integer operands and nested groups within existing token/source budgets. Independent recursive tree oracle; block headers, structured diagnostics, RHS identifiers and full grammar remain pending. [RU protocol](SELF_HOSTING_PARSER_A54.ru.md).

### Self-hosting A5.4b: restricted block headers and first syntax diagnostic

Sedrava-authored validation of action and literal-boolean if headers, mandatory indentation and arithmetic assignment syntax before AST parsing. [RU protocol](SELF_HOSTING_PARSER_A54B.ru.md). Lexical diagnostics and full grammar remain pending.

### Self-hosting A5.5: compound RHS expressions

Sedrava-written parser adds identifier/boolean/unary/binary AST with precedence, comparisons and logical operators. Restricted block grammar and experimental division remain; no type or semantic analysis. [RU protocol](SELF_HOSTING_PARSER_A55.ru.md).

### Native Server A11: immutable native index backend

Explicit SHA-approved read-only backend using SedravaSQL B12 VerifiedIndexReader. Exclusive loopback GET routes with existing db_get/db_revision; no SQLite database opened in this mode, no native live writes. [RU protocol](RUST_NATIVE_SERVER_A11_INDEX.ru.md).

### Native Server A12/A13: exclusive native log writes and restart verification

Two business records, state and durable HTTP receipt in one native batch; read-only GET uses B13. Real loopback HTTP, replay after normal restart and simulated process exit after sync, torn frame rejected. [RU protocol](RUST_NATIVE_SERVER_A12_LOG.ru.md). No public deployment, automatic repair or physical power-loss claim.

### Self-hosting A5.6a: compound if conditions

Shared stack expression grammar for condition AST, source spans and block depth. [RU protocol](SELF_HOSTING_PARSER_A56A.ru.md). Else, calls and typing remain pending.

### Self-hosting A5.6b: linked else branches

Explicit header IDs, matching depth, nonempty body and structured orphan/duplicate diagnostics. [RU protocol](SELF_HOSTING_PARSER_A56B.ru.md). Function calls remain pending.

### Native server: B14 dependency update

Pin staged native replay engine; preserve existing A10–A13 backend contracts.

VDS: 83 Rust tests and A10/A11/A12/A13 integration regressions PASS with pinned B14 (70236fa8db2e2761a5f1a9672056b201d42fdb98).

### Self-hosting A5.6c: function call AST

[Named calls with positional arguments](SELF_HOSTING_PARSER_A56C.ru.md), nested calls and source spans. Name resolution and types pending.

### Native server B15a: write admission limits

[HTTP 507 capacity with continued reads and replay](RUST_NATIVE_SERVER_B15A_BUDGET.ru.md). VDS 83 Rust tests and A10–A13 regressions PASS.

### Self-hosting A5.7: explicit symbol context and scalar type checking

[Name resolution, signatures and scalar types](SELF_HOSTING_PARSER_A57.ru.md). Declaration parsing and full language semantics pending.

### Native server A15: verified offline archive restore

[Operator procedure and HTTP regression](RUST_NATIVE_SERVER_A15_ARCHIVE.ru.md). VDS: 83 Rust tests, A10–A13, B15a and A15 PASS. A14 wider DSL transactions remain pending.

### Native SQL host A16

[Typed SQL parameters from a dedicated Sedrava source domain](RUST_NATIVE_DATABASE_A16.ru.md).

### Self-host A5.8a/b

[Inline declarations and typed expression IR](SELF_HOSTING_PARSER_A58.ru.md).

### A17: static native SQL HTTP API

[Explicit loopback SQL routes](RUST_NATIVE_SQL_API_A17.ru.md).

### A5.9a

[Execute scalar IR instructions](SELF_HOSTING_EXECUTOR_A59A.ru.md).

### A18: optional SQL API auth

[Private digest file and reader/writer roles](RUST_NATIVE_SQL_API_A18.ru.md).

### A5.9b

[Branch execution](SELF_HOSTING_EXECUTOR_A59B.ru.md).

### A5.10a

[Function IR VM](SELF_HOSTING_FUNCTION_VM_A510A.ru.md).

### A19 practical demo

[Sales backend example](SALES_DEMO_A19.ru.md).

### A5.10b

[Function source-to-IR compiler](SELF_HOSTING_FUNCTION_COMPILER_A510B.ru.md).

### A20

[Atomic SQL transaction routes and foreign keys](SALES_DEMO_A20.ru.md). GUI and public deployment pending.

### A5.10c

[Local declarations and block bodies](SELF_HOSTING_FUNCTION_COMPILER_A510C.ru.md). B21/B22 disk read image remains separate from SQL execution.

### A5.10d

[Conditional return and recursive source functions](SELF_HOSTING_FUNCTION_COMPILER_A510D.ru.md).

### A21 — sequential transaction routes

[Read-your-writes and replay](SALES_DEMO_A21.ru.md). GUI remains pending.

### A5.11a

[While loops and mutable locals](SELF_HOSTING_FUNCTION_COMPILER_A511A.ru.md). B24 separate pager/WAL is not yet connected to SQL.

### A5.11b

[Nested control blocks](SELF_HOSTING_FUNCTION_COMPILER_A511B.ru.md).

### Practical WebApp

[Service journal](SERVICE_JOURNAL_DEMO.ru.md), browser-local only. B25 disk tree is not yet the SQL backend.
