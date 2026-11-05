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
