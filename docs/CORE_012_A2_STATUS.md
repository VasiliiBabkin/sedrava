# Bounded core continuation — working status / Текущее состояние

Experimental child branch of PR #50 (`feature/012-bounded-core-text-loops-a1`),
verified starting SHA **b3dab652223077af41b7f02db6803a1b79d4758f**.
Stable `main`, 0.11.0 tags/PyPI/site, namespace PR #47 and server PR #48/#49 are
not modified or merged. Source VERSION remains the inherited 0.11.0 compatibility
baseline; these source-SHA-labelled experiments are not a published 0.11 feature.

## Implemented checkpoint

- Common static work accounting includes nested repetition, pure-function call
  costs, bounded query callbacks/sort comparisons, invariant checks and derived recomputation.
  Static ceiling and runtime fuel **1,000,000 units**, with the existing 10,000
  statement/depth limits retained. Units are conservative AST/collection visits,
  not CPU milliseconds; scalar/record/text size limits apply separately.
- Both generated JS and Kotlin reserve the same per-statement fuel as Python,
  before evaluating a potentially failing statement. Exhaustion aborts the whole
  transition; it cannot commit an intermediate state.
- Literal `repeat i in range(start, end[, step]):` now allows signed int32 bounds,
  negative steps and empty ranges; zero step and >100 iterations reject. Existing
  `range(0, N)` remains compatible. New negative/empty examples are positive tests;
  obsolete A1 negative cases now check zero step/int32 overflow instead.
- The pure Kotlin domain adapter no longer emits Android SharedPreferences I/O
  when `_domain_only` is requested. Persistent fixtures compile on real JVM
  without Android stubs; complete state/acceptance traces can be compared.

- `list<int|bool|text>(max=N)` supports typed literals, append, strict positional
  indexing/slicing/removal/replacement, exact-value search, capacity, sorting and
  checked integer sum. N is explicit 1..100; bool is not int. Function parameter
  and return capacities must match exactly. New value lists use strict snapshots;
  existing record-list fingerprints, IDs and next_id encoding remain unchanged.
- `for value in collection:` / `for index, value in collection:` visits an immutable
  entry snapshot. Both bounded lists and scalar text are supported; loop bindings
  cannot be assigned or leak. `list_identity(records,index)` bridges position to
  stable ID; positional record replacement preserves the existing ID.

## Work still required in this engineering pass

1. Complete actual browser/Android-device A1 regressions (not just helper strings).
2. Broader boundary/snapshot/browser/device verification of the new list/loop surface.
3. Explicit versioned Unicode normalization on all targets; no reliance on
   different host Unicode versions or UTF-16 indexing.
4. Typed Result values and explicit expected-error handling, with no exception
   message classification or catch-all conversion of engine faults.
5. RU/EN syntax/limits, clean archive installation, final exact-SHA CI and report.

Map/Set are deliberately not promised: ordered iteration, portable key equality,
strict snapshot schema and identity semantics need a separate reviewed contract.
Namespace integration needs explicit reconciliation against PR #47; it is not
implied by passing the old flat-module tests. No server-platform integration.

Русский: это рабочий журнал, не объявление готовности. Реализованные части выше
отделены от следующих этапов. Итоговые SHA/CI и ограничения будут зафиксированы
после фактических проверок; никакого релиза или merge этот документ не разрешает.

## Second checkpoint

Implemented the pinned Unicode 15.0.0 data generator and shared normalization/full
case-fold algorithms; original data SHA-256 and license are vendored. Python,
actual generated JS and JVM adapters run official conformance vectors. New
`Result<T, Error>` is ephemeral and first-order: try_add/try_chr/try_at,
result_ok/result_code/result_or; no persisted Result or arbitrary error variants.
The compiler rejects Result state and implicit unwrap. Expected errors never catch
argument, invariant, engine or fuel faults. See CORE_012_A2.md and CORE_012_A2_RU.md.

First actual Chromium run passed 14 UI transitions, complete-state comparison,
keyboard access, persistence/reload and rejected-storage preservation. Initial clean
wheel/sdist installs passed outside the checkout, including both experimental
examples, old 0.9/0.10 apps and site/webapp generation. These preliminary checks
precede the final SHA; final runs are recorded separately below.

Added dedicated Python 3.10/3.12/3.13, three-browser and Android API35 workflow jobs
for the dependent base branch. Existing tests were retained. Added JVM and Compose
harnesses beside generated code (not manual fixes to application sources).

Namespace dry-run against a1c7200888da9aad103dd79210b2e3b70c3e6a4c found an
actual packaging module-list conflict; CLI/source mapping and WebApp expansion also
need reconciliation. This is NOT proof of a working namespace integration. Keep
#47 independent until an explicitly reviewed integration branch passes both suites.

## Verification gates / Критерии проверки

- Implementation checkpoint: `581cb795e449a9851f20f469b8727cda155d9f41`;
  final test/harness hardening follows on the same draft PR #51.
- Official data: 19,074 normalization rows, 95,370 transformed inputs / 381,480
  normalization assertions per target; 1,530 default-full case-fold vectors.
  Tests execute generated Node and real compiled Kotlin, never host normalizers.
- The new fixture passes its 3 embedded Sedrava tests. Chromium passes 14 real
  button transitions, all state fields, atomic rejection, reload and corrupted /
  incompatible storage retention. A seeded 64-action corpus broadens differential
  coverage without unbounded fuzzing.
- Local Android: generated debug APK assembled and one full-state JVM oracle
  passed. APK v2 signature and permission allowlist verified (debug key, not a
  production signing key). First instrumentation compilation exposed a nullable
  test-harness parameter; fixed in the harness generator, no application patch.
  Final APK/Lint/instrumentation build and hosted API35 execution must pass before
  device support can be claimed. Local adb has no connected device; no /dev/kvm.
- Initial wheel and sdist archive audit and both isolated installed-package checks
  passed. Final workflow repeats clean builds and checks on the exact checkout.
  Local inherited version labels remain 0.11.0: these archives are experimental
  SHA-bound test artifacts and MUST NOT be uploaded as the stable package.
- The first in-flight full run reported an unapproved emulator action pin while
  the workflow was being corrected; the corrected pinned action matches existing
  reviewed workflows and the security audit passes. No tests were disabled.

The final SHA, each workflow outcome and artifact URLs are maintained in the PR
body after CI finishes, rather than guessing future run IDs in this source file.
`core_a2_receipt.py` emits actual checkout SHA/tool versions/output SHA-256 in CI.
The final branch remains experimental. GO is limited to review of verified
features; NO-GO for a release or automatic namespace integration. Remaining scope:
Map/Set, nested value lists, persisted/custom-error Results, grapheme/locale text
operations, Unicode versions beyond 15.0.0 and namespace reconciliation. No tests
on physical Android hardware. No stable release/tag/package/site changes.
