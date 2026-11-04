# Independent upgrade/rollback audit / Независимый аудит обновления и отката

Scope: published **0.10.0 → unpublished 0.11.0rc1 → 0.10.0**, PR #42,
`release/011-rc1-preparation`. No releases/tags, registry upload, merge or deployment.
This audit adds installation tests and documentation; it does not change language
features, published baseline bytes, application IDs or storage formats.

## Immutable original inputs / Исходные проверенные входные данные

Published tag `v0.10.0` resolves to **688a320025a0d38235eb90c780362ec26b0708e2**.
All **14 root Python modules** in the actual downloaded wheel were independently
compared byte-for-byte with that Git commit. Downloads were from the real PyPI
0.10.0 JSON index and `files.pythonhosted.org`, not a reconstructed old checkout.

| Published file | Verified SHA-256 |
| --- | --- |
| sedrava-0.10.0-py3-none-any.whl | `97063ea99d823017d57f41cefdcf45ba289370661b68e4f8c15a6531abbab219` |
| sedrava-0.10.0.tar.gz | `92d9de3705cbba30124370b014d4da12ab8076cf6a31e6bc33cff326678e24c3` |

Initial candidate source: **b4830ae4914eace61271cffa1800fdb4fb8bf23f**.
Actual successful [candidate run 41886360101](https://github.com/VasiliiBabkin/sedrava/actions/runs/41886360101),
[artifact 13350862919](https://github.com/VasiliiBabkin/sedrava/actions/runs/41886360101/artifacts/13350862919).
Downloaded ZIP SHA-256: `a5a4b99c8748379b0ddf766ddc08272e176b2aa209d6a225fc82f60cc4eaed7e`.

| Initial candidate file | Verified SHA-256 |
| --- | --- |
| sedrava-0.11.0rc1-py3-none-any.whl | `f0c82aef46bc34a46d8bd68bdacf7652946414603263d2233814a8fec4435b85` |
| sedrava-0.11.0rc1.tar.gz | `0e634c44a8f63df3fbcf787c9b52e4259e9b35b6760669fcc21bf767475959a5` |

These are original **b4830ae** hashes, never relabelled as a later commit. New
commits build new archives: their actual hashes and exact source SHA are recorded
in `upgrade-install.json`, `inventory.json` and final CI evidence. Archive container
hash reproducibility is distinct from deterministic payload/output reproducibility.

## Completed local practical checkpoint / Фактически выполнено локально

Python **3.12.14**. Original downloaded candidate archives were installed outside
the checkout with source import paths removed. Results:

- **Four independent clean environments:** baseline wheel/sdist and RC wheel/sdist.
- **Three in-place phases in one fifth venv:** 0.10 before, RC upgrade, 0.10 reverse
  installation. Every installed version was checked via CLI and installed metadata.
- At all seven phases: `check`, `test`, `run`, `build web`, `build android` on
  `reference_09`, `text_profile`, `task_manager`, `task_manager_navigation` copied
  from the installed published baseline. Complete observed states match; user
  source hashes stay unchanged. Docs/license/examples are actually installed.
- Every candidate phase also builds all four `platform_*` site/tasks/catalog/CRM
  projects from installed package resources, without generated-code edits.
- Repeated Web/site/WebApp outputs match exactly. Complete generated trees from
  wheel/sdist and reinstalled same-version tools match. Android version metadata
  intentionally differs between 0.10 and RC and is not expected to be identical.
- Actual CLI state with `Алиса 😀` survives upgrade, is changed by RC, and is read
  after reverse installation without rewriting the snapshot during read-only run.
- **Four real Chromium cases passed** against wheel-generated output: strict
  collection/navigation full-snapshot update/edit/rollback/cold reload; scalar
  Unicode and invariant rollback; malformed/duplicate/incompatible data protection;
  four installed new Web projects including real loopback HTTP success/HTTP 500.
  The schema case additionally recompiles the same app with list capacity **100 → 99**,
  retaining origin/path/title: even saved data within the new bound must be rejected
  because its schema signature differs; reverting compatible HTML recovers the old bytes.
  Unknown envelope fields and altered `signature` are separate negative cases.
- Full local existing Python regression: **268 passed**. Release security policy
  accepts the added read-only, fully SHA-pinned workflow; publisher is unchanged.

No product P0/P1 was confirmed by this initial checkpoint. Test development exposed
incorrect assumptions about the historical error wording; assertions were aligned
with the actual documented alert, while exact original-byte and state checks remain.
This is not a claim that every possible upgrade or schema migration is supported.

## Android and exact-head final gate / Android и итог на точном SHA

Locally SDK 35/JDK/Gradle are present, but `adb devices` lists no device, there is no
emulator executable/system image and `/dev/kvm` is absent. **No local APK installation
or physical-device test is claimed.** Hosted API35 installation tests are a separate
job, not a substitution with JVM tests.

`upgrade-011.yml`:

1. Builds exactly one candidate wheel/sdist pair on the checked-out PR head; downloads
   pinned published baseline files; executes the seven installation phases.
2. Transfers those same tested artifacts and unmodified generated app sources to
   Chromium/Firefox/WebKit and Android jobs. Browser counts are **four per engine**.
3. Builds same-signer APKs with the unchanged ID, checks actual signatures,
   permissions and **10003 → 11001**, seeds old UI, installs with `-r`, checks full
   state/cold launch, edits in RC, exercises rotation/recreation/system Back.
4. Requires normal downgrade to fail without data loss, then tests the permitted
   **debug-only `-r -d`** return to the original APK. Malformed/incompatible data
   survives update/restart/debug rollback without clearing or uninstalling target data.
5. Emits `sedrava-upgrade-final-report` only from actual receipts and job results.
   `upgrade_gate: GO` requires successful package/device jobs and all **three**
   four-case browser receipts with the exact candidate SHA. Missing/failed/wrong-SHA
   evidence yields **NO-GO**, never inferred success. Publication remains unauthorized.

The final commit SHA is supplied by CI rather than embedding a self-referential
commit in this document. PR #42 records the final successful/failed run and artifact
links after actual completion. Downloaded machine reports provide exact final SHA,
wheel/sdist and APK hashes, signer fingerprint, complete storage observations,
actual browser/tool versions, device properties and raw logs/screenshots/traces.
Earlier green workflow runs do not establish readiness of a later commit.

## Release decision / Решение о готовности

**Technical GO requires** the final exact-head upgrade report to say GO **and** all
applicable existing Python/platform/Android/distribution workflows to succeed.
Otherwise **NO-GO**; record the failing gate. This document alone grants no publication
permission. The final actual decision and immutable run links are in PR #42 and the
CI report; no package is uploaded by this audit.

Limits: unchanged supported storage schemas only; no automatic migrations, Web
origin/path/title transfer, production Android version downgrade, physical hardware,
crash/power-loss or concurrent-writer certification. Debug APK signature is not a
production signing guarantee. Sources and raw rejected storage must be backed up.
See [EN instructions](UPGRADE_0_11_0rc1.en.md) / [RU instructions](UPGRADE_0_11_0rc1.ru.md).

Русский: локально проверены реальные PyPI/CI архивы, четыре чистые установки,
обновление и обратная установка в одном venv, полные состояния/байты генерации,
CLI-сохранения и четыре настоящих Chromium-сценария. Локальная Python-регрессия —
268 тестов. Установочные Android-испытания выполняет только отдельный API35 job;
их нельзя считать успешными по одной компиляции. Итоговый GO возможен только по
фактическим успешным отчётам того же SHA; физическое устройство не проверялось.
