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

## Browser matrix audit

The final local regression passed 359 tests without skips, real Chromium app/WebApp
traces, clean wheel/sdist installation, payload reproducibility and actual stable
upgrade/rollback. Android debug APK/JVM/Lint/instrumentation compilation and merged
permissions/signature verification passed. During final CI inspection the original
A2 browser step was found to default to Chromium even in other-engine jobs; both
browser scripts now inherit the matrix engine. The imported-module script already
selected its engine explicitly. This is a coverage correction, not weakened tests.
The new CI-only checkpoint requires fresh exact-SHA workflows. One intermediate
navigation run failed downloading an Android system-image ZIP before emulator
startup; it did not execute/fail an application assertion. Final runs remain the
authoritative evidence and their links/counts are maintained in draft PR #52.

## Bounded package traversal correction

Final independent inspection found that sorted(rglob(...)) materialized an
unbounded tree before checking file/byte counts; empty directories escaped both
limits. Replaced it with iterative scandir traversal that counts all entries before
sorting/descending, bounds depth/path length, and retains canonical file ordering
and existing in-bounds lock bytes. Five regressions check early enumeration stop,
atomic lock preservation, depth/path caps, empty-directory compatibility, hidden
entries and the old file boundary. The 12 package tests pass. This is a real
resource-limit correction; final SHA/CI must advance and rerun. Previous exact-head
CI had 21/23 successful runs; two WebKit installers were still fetching slow Ubuntu
packages, not failing application assertions. Their success is not evidence for
the subsequent source change. Current evidence remains in draft PR #52.

## Original-binder and typed-region audit

Reproduction showed invalid module declarations/binders such as state true, a
false/class function parameter and let class could be accepted after hygiene hid
the original reserved word. The common lexical validator now runs before lowering
(and remains shared with the core). A related valid-program defect required a
structural correction: value binders named int/text/list/Result must not rewrite
type annotations or statement keywords. Function and parameter grammar/limits are
shared; only typed/value/name regions are lowered. Inline action locals use the
same hygienic path as block actions, preserving original expression columns. Entry
locals cannot shadow explicit aliases; record labels are not qualified references.

Added real Python/JS/Kotlin traces for these contextual identifiers, negative
reserved-binder/alias/field-label cases, inline runtime positions, parameter bounds
and bulk-character provenance equivalence. Batched replacements, incremental
ownership and chained scope lookup also remove repeated whole-line/history copies.
40 focused integration tests pass; the full new regression is running before the
next exact-head checkpoint. Earlier SHA results remain historical, not final proof.

## UI expansion boundary checkpoint

42 focused integration tests and the full 378-test working-tree regression pass,
with real Chromium app/WebApp/legacy navigation and a static site whose private
component/style names are use/style (computed padding 37px). UI templates cannot
add domain record fields; root record labels never become alias substitutions.
Substitution growth is checked before string/source-map materialization and parent
output before concatenation. The shared bulk mapper retains caller positions.
This is a checkpoint, not final-SHA CI evidence.

## Physical-line Unicode correction checkpoint

A raw U+2028 literal in an imported function/state reproduced an unterminated
literal because generic splitlines treated scalar text as source boundaries.
Current frontends/source maps now share LF/CRLF physical_lines, including client
HTTP/source extraction. No runtime text normalization is introduced. The Kotlin
conformance harness likewise preserves scalar data in generated code/JSON rows.
Added NEL/LS/PS + astral-slice differential tests, exact scalar error columns and
CRLF compatibility. The real example now has nine actions, including scalars,
and the static contextual-style fixture contains literal separators.
45 integration tests and the full 381-test local regression pass without skips;
real Chromium app/WebApp/static-site/navigation also passes. One new fixture
initially used the nonexistent text_len; corrected to the existing text_length,
without adding an alias or weakening validation.

CI dependency preparation now selects the official Ubuntu archive instead of
the measured slow Azure mirror (43.3 MB / 21 min 47 sec). Only matching source URIs
change; signing keys/settings remain unchanged and three regressions verify this.
The helper is restricted to disposable GitHub CI and sudo preserves only the
public GITHUB_ACTIONS flag. Intermediate head 2b58c85 already passed the complete
bounded-core push workflow with the new mirror. Final exact-head CI/archives/native
checks are rerun after this checkpoint; definitive links/counts are in draft PR #52.
