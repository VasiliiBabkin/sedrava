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
