# Namespaces + bounded core integration — working evidence

Unpublished 0.12.0a1 / Android 12001. Integration base: PR #47
`a1c7200888da9aad103dd79210b2e3b70c3e6a4c`; merged history of #50/#51 through
`5e118756718914334daee1c0f932c3973917736c`. Stable main and server #48/#49 are
unchanged. This is a new dependent draft, not a merge of any existing PR.

## Implementation checkpoint

- Unified packaging lists include namespaces, source provenance, local packages,
  typed bounded lists, Result, cost accounting and pinned Unicode data.
- App CLI and parse_document now expand checked modules, not only site/WebApp.
  Imported domain code is checked together by the one core parser/type checker
  and static/runtime budget model; no backend-specific module interpreter.
- Modules can own state/derive/action (and persist owned states), in addition to
  record/fn/component/style. Explicit export controls qualified access. Imported
  state/derive/action blocks are scheduled at domain declaration boundaries;
  entry declaration order stays checked. Module actions/derives cannot capture
  ambient entry states. Functions remain pure, non-recursive expression functions;
  loops are in typed module actions, not a new function interpreter.
- Original paths/lines and character maps survive lexical name replacement and
  component instantiation. Runtime expression failures carry their original file
  into CLI text/JSON diagnostics. WebApp uses the same expanded domain provenance.
- Local package verification distinguishes bool/float from integer schema values,
  rejects oversized lock output before replacement, rejects unlocked vendor imports,
  and verifies the bytes actually read against the verified package hashes.
- Reserved generated symbols are rejected inside modules as well as entry files;
  non-ASCII namespace identifier tokens reject instead of implicit Python NFKC
  identifier normalization bypassing privacy. Unicode text literals remain valid.

Initial old namespace/provenance/package tests and the new real modular .sdr app
check/embedded tests pass. Complete cross-platform, final-SHA CI and archive
verification are still pending. These initial checks do not establish readiness.

Next: positive/negative imported-function/action differential corpus, column/error
regressions, package security regressions, modular WebApp browser fixtures, actual
Android/JVM/API35, clean installed distributions, bilingual contracts, final report.

## Implemented verification checkpoint

Added hygienic function/action local binders, public qualified CLI action lookup,
source-input overwrite guards and exact lexical identifier diagnostics. Existing
flat files with generated-looking names keep their old semantics outside scoped
imports. Alias-renaming snapshot stability, nested function diagnostic columns,
component substitution columns, ambient capture, lock schema types, lock output
atomicity and read-after-verification digest guards have regression tests.

Real Chromium modular app + WebApp scenarios pass complete-state traces (7 actions
per presentation), reload and retained invalid/incompatible storage. Python/Node/
compiled Kotlin modular trace passes, including Result of a record. First full
combined suite: 336 tests passed before later additional regressions. Final count
and exact-SHA platform/CI evidence will be recorded in the PR after all checks.

## Scope/provenance hardening checkpoint

Module-owned rule invariants use the common validator and budget. Scope validation
precedes initial evaluation. UI components/slots cannot become action/domain
macros that bypass module binding isolation. Mixed legacy imports cannot name a
private generated symbol. Character origins now preserve caller argument locations
through nested ref substitutions, while template errors point to their definitions.

25 integration regressions pass, including actual generated Node/compiled Kotlin
traces and original-file/column checks. Real Chromium passes app and WebApp (8
actions each), module invariant rollback, persistence and rejected storage; a legacy
navigation fixture checks a prototype-named state and browser Back/Forward.
Display labels retain user-visible names instead of compiler-generated IDs.

Package readers bound actual reads (including files changed after stat), snapshot
manifest bytes consistently, reject oversized integers and compare locks against a
strict typed schema. Actual compiled vendor bytes must match captured verified
hashes. No remote imports, code execution or new server capabilities are added.

Final full regression, three-browser jobs, JVM/APK/Lint/API35 and installed archive
checks are being rerun on the next exact-head checkpoint. Final outcomes and
artifacts will be recorded in this PR; intermediate runs are not release evidence.

CI confirmed the Python 3.10 clean-install omission: base CLI worked, but the new
installed locked-package example requires the declared packages extra in its
isolated venv. Tests now exercise base commands first, install the extra, then
verify locked packages. Missing-parser errors retain the actionable extra-install
hint instead of being misreported as corrupt TOML. No dependency checks were bypassed.

## Final source-position checkpoint

The last compiler changes make structural import failures carry typed original
locations (including nested missing files and private-export access after name
lowering). Mixed legacy import failures map through the same checked character
origins. Reusing ExpandedSource preserves scope, public symbols and provenance.
30 focused integration tests and real Chromium app/WebApp/legacy navigation
scenarios pass. Intermediate commit 9898592 completed all 23 applicable workflow
runs successfully; the subsequent four source-position changes require their own
exact-head rerun. No intermediate success is used as final-SHA evidence.

## Legacy component compatibility checkpoint

Scoped components/slots remain UI-only. The unscoped 0.11 expansion path retains
action macros: a new regression executes its complete state in Python, generated
JavaScript and compiled Kotlin. The real published 0.11.0 -> candidate -> 0.11.0
clean-environment audit also checks and builds this unchanged WebApp in all phases.
The first attempt correctly exposed the previous candidate restriction; rebuilt
archives pass the audit without modifying the fixture or weakening scoped tests.
31 integration regressions pass; final full suite and exact-head CI follow this
checkpoint. The last previous full suite passed 358 tests.
