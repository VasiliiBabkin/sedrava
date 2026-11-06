# Typed errors + exhaustive match: implementation evidence

## Recovery baseline

PR #55 original head: 8d677b8c62d994ff8ff0a6f2b5af94a7ae7ec3cb.
Recovery: cb10863ea8d82c8c4a73e8242d733226183ba2ac. Invalid fixtures used function
calls in state initializers and a nonexistent block-test grammar. Corrected fixtures
use literal state, action calls and `test name: actions -> condition`. Added
negative regressions rather than expanding grammar. 392 local tests passed with
zero skips; 8 effects tests pass. Real original Effects example executed in Python,
generated JS and compiled Kotlin (count 2,4). Effects CI matrices on that SHA:
https://github.com/VasiliiBabkin/sedrava/actions/runs/42296995356 and
https://github.com/VasiliiBabkin/sedrava/actions/runs/42297001719 — success.
Old failures were inspected, not hidden. Other source branches are unchanged.

## Implemented scope

- Shared bounded error-sum types, stable IDs, immutable scalar payloads.
- Contextual typed Ok/Err atop the existing Result model, opaque legacy boundary.
- Shared Match IR; static type/scope/exhaustiveness checks; conservative fuel/steps.
- Python, generated JS and Kotlin evaluate only the selected branch.
- Imported declarations/constructors/typed signatures and hygienic arm binders;
  authored source maps retained; reserved original names checked before lowering.
- No Host operations, new permissions, persisted Result/errors or general generics.
- RU/EN specifications and real standalone/modular examples are bundled.

## First executable checkpoint (not final-SHA proof)

22 focused tests passed before the extra resource/engine-boundary regressions.
Python/Node/compiled Kotlin complete-state traces pass. Chromium performed actual
UI actions and reload/rejected-storage checks. Android APK, JVM, Lint and
instrumentation compilation succeeded locally (76 tasks); APK signature and
permission allowlist verified. Local emulator/physical device are unavailable
(no /dev/kvm); hosted API35 workflow is the device-test gate.

Full regression and dedicated Python 3.10/3.12/3.13, Chromium/Firefox/WebKit and
Android API35 CI run on the final committed source. Exact SHA, counts, artifacts
and conclusions are recorded in the draft PR and source-bound CI receipts to avoid
claiming old-checkpoint results as final-head results.

## Remaining boundaries / Ограничения

Experimental source lowering, not a native multi-file typed IR. Some diagnostics
point to the enclosing expression/arm rather than an individual field. Only scalar
success types for user-error Results; legacy record/list Result support retained.
No match expression, multi-line functions, recursive closures, error persistence,
JSON decoder, schema migration, Host/Server bridge or permission grant mechanism.
Stable error IDs do not themselves establish wire compatibility or authority.

Для Host A3 нужны отдельно проверенные адаптеры ожидаемых ошибок и runtime-политики.
Server не включён: его безопасность и интеграция требуют отдельных проверок.
Публикация и объединение не выполняются этим заданием.

## Recovery follow-up / second checkpoint

All 22 recovery workflows on cb10863ea8d82c8c4a73e8242d733226183ba2ac
completed successfully. All old red job logs were reviewed and traced to the
invalid fixtures; no suppressed tests or changed initializer grammar.

An introduced negative engine-overflow fixture retained an old built-in test that
expected success. Code generators correctly ran and rejected that test. The
fixture now has a valid initial-state built-in test, while independent Python/JS/
Kotlin checks still assert the overflow and complete rollback. The old failed CI
is retained. 34 focused cases subsequently passed, including imported resource
accounting, limits, source coordinates, JSON codes and immutable/nominal values.

A real constructor/value-namespace ambiguity was found and fixed: only the error
type symbol can construct a variant, not an error-valued parameter/local. Effects
also verifies the constructor's structural typed metadata before treating it as
pure; an arbitrary AST marker cannot masquerade as that constructor.
Final cross-platform CI follows the next committed SHA; final counts are in PR #56.

35 focused tests passed at the final working-tree checkpoint, including real
legacy record Result matching and identity retention. The imported JSON diagnostic
regression separately passed with source errors.sdr:8 and SDR-E1201. The dedicated
Chromium job also runs both existing HTTP browser tests that are intentionally
absent from Python-only jobs. Final exact-head regression follows the commit;
checkpoint results do not substitute for its CI receipts.


A final name-resolution reproduction showed an error type named int could shadow
primitive function annotations while error fields still used primitive int.
The new error-type declaration registry now rejects built-in type-name collisions,
using the same authored-name validator before namespace lowering and in the core.
No existing record/value/function naming grammar was changed. Direct/imported
negative regressions and RU/EN contract record this necessary boundary.

Legacy functions named Ok/Err/error_id were valid before this slice. They retain
lexical priority over the new intrinsics, with real Python/JS/Kotlin regression.
A noncallable value/parameter cannot silently turn into an intrinsic call; pattern
tags remain syntax independent of function names. This avoids a compatibility
regression without expanding the old grammar or weakening Result typing.
