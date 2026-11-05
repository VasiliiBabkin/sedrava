# Sedrava — stable 0.11.0 published on GitHub and PyPI

**Describe the application; get the application. / Описал — получил.**

**[Dedication / Посвящение](DEDICATION.md):** Геннадию Ивановичу Смирных — учителю информатики, благодаря которому автор Sedrava понял и полюбил программирование.

**Current stable release:** [Sedrava 0.11.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0) ([PyPI](https://pypi.org/project/sedrava/0.11.0/)), Android versionCode **11002**. The previous stable [0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) ([PyPI](https://pypi.org/project/sedrava/0.10.0/)) and historical RCs remain available.

**Historical prerelease:** [0.11.0rc1](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1) ([PyPI](https://pypi.org/project/sedrava/0.11.0rc1/)) preceded the stable 0.11.0 release. Verified 0.10 and RC upgrade/rollback, browsers and Android API35 are documented in [stable release notes](docs/RELEASE_NOTES_0_11_0.ru.md).

Start with [Quick Start](docs/QUICKSTART.md), the [text reference](docs/LANGUAGE_0_10_TEXT.md), [text profile example](examples/text_profile.sdr), and [measured report](docs/TEXT_010_REPORT.md). The [task manager](examples/task_manager.sdr) now uses records and lists directly in `.sdr`; the [navigation example](docs/NAVIGATION_QUICKSTART.en.md) adds guarded screens and Back.

## Getting started

**Describe the application; get the application. / Опиши приложение — получи приложение.**

Sedrava is an experimental declarative programming language for small applications: describe text/int32/boolean state, typed record collections, derived values, atomic actions, invariants and a simple UI; generate a standalone Web app or an Android/Compose project from the same source.

**For learning and experimental development, not production.** The 0.11.0 package is public; historical Intent 0.7 packages belong to a separate project history.

[Quick Start / Быстрый старт](docs/QUICKSTART.md) · [Русский](docs/README.ru.md) · [English](docs/README.en.md)

## Install and try

Python 3.10+ is required; Git is optional for installation from PyPI. In a virtual environment:

```sh
python -m pip install sedrava==0.11.0
sedrava --version
# Clone the source repository for checked-in example files:
git clone https://github.com/VasiliiBabkin/sedrava.git
cd sedrava
sedrava check examples/reference_09.sdr
sedrava test examples/reference_09.sdr
sedrava run examples/reference_09.sdr add add
sedrava build web examples/reference_09.sdr --output build/web/index.html
python -m http.server 8000 --directory build/web
```

Open http://localhost:8000. Android generation:

```sh
sedrava build android examples/reference_09.sdr --output build/reference-09-android
```

To produce an APK, install a full JDK, SDK 35 and Gradle 8.11.1 and follow the [build guide](docs/BUILD.md). `build android` generates sources; it does not invoke Gradle. No accounts, telemetry, advertising or cloud runtime services.

## Documentation

- [Quick Start: installation and first program](docs/QUICKSTART.md)
- [0.10 text semantics](docs/LANGUAGE_0_10_TEXT.md), [records and collections](docs/RECORDS_COLLECTIONS_010.md), [navigation](docs/NAVIGATION_010_CONTRACT.md); [historical 0.9 reference](docs/LANGUAGE_0_9.md)
- [Web and Android builds](docs/BUILD.md)
- [Complete executable examples](examples/README.md): constrained counter, manual countdown, habit progress, validated input and Sedrava 0.9 Lab
- [FAQ and troubleshooting](docs/FAQ.md) · [Known limitations](docs/KNOWN_LIMITATIONS.md)
- [Changelog](CHANGELOG.md) · [0.10.0 release notes](docs/RELEASE_NOTES_0_10_0.md) · [historical 0.9 notes](docs/RELEASE_NOTES_0_9_0a1.md)
- [Roadmap](docs/ROADMAP.md) · [0.10 design](docs/PLAN_0_10_UI.md)

**Post-release manual smoke test:** On 2026-11-01, `sedrava==0.10.0` was installed from PyPI on Linux/Python 3.13; CLI checks, one embedded test, two actions and Web HTML generation passed. Browser functionality was confirmed by the tester. [Full evidence and limitations](docs/MANUAL_LINUX_WEB_SMOKE_0_10_0_2026-11-01.md). This does not close physical Android acceptance.

## Architecture and verification

Source → restricted typed AST (`sedrava_core.py`) → interpreter / Web (`web_codegen.py`) / Android (`android_codegen_v03.py`). Builds run embedded language tests. Actions change a candidate state sequentially; all final rules must hold before atomic commit. Integers and arithmetic intermediates are checked signed 32-bit values. Python runtime has no third-party dependencies and never executes source through `eval`/`exec`.

```sh
python -m pip install ".[test]"
python -m unittest discover -s tests -v
python -m pip install playwright
python -m playwright install --with-deps chromium
python scripts/test_web_browser.py
python -m pip install build twine
python -m build
python -m twine check dist/*
python scripts/audit_dist.py
```

Node.js is needed for differential conformance tests; Chromium tests are a separate real-browser suite. Android build/Lint is separate from UI acceptance. Previously supplied manual Android 16 results are preserved in [acceptance evidence](docs/ANDROID_09_ACCEPTANCE.md); they do not verify newly changed APKs. See the audit for current results and infrastructure limitations.

**License:** [Apache 2.0](LICENSE) · [Contributing](CONTRIBUTING.md) · [Code of Conduct](CODE_OF_CONDUCT.md). Official documentation website: [sedrava.virtreal.ru](https://sedrava.virtreal.ru/), maintained separately in [sedrava-site](https://github.com/VasiliiBabkin/sedrava-site).

## Records and collections / Записи и коллекции (0.10)

Version 0.10.0 includes typed records and bounded ordered lists, stable IDs, atomic actions, strict snapshots and generated Web/Compose UI.
Записи и списки входят в опубликованную 0.10.0.

- [English task-manager guide](docs/RECORDS_QUICKSTART.en.md)
- [Руководство на русском](docs/RECORDS_QUICKSTART.ru.md)
- [Measured coverage / Фактические проверки](docs/COLLECTIONS_010_REPORT.md)

## Multi-screen navigation / Многоэкранная навигация (0.10)

Named screens, guarded atomic transitions and a bounded Back stack are implemented
in the core and both generators. One `.sdr` file generates the two-screen task manager.
Экраны и переходы входят в опубликованную 0.10.0.

- [English guide](docs/NAVIGATION_QUICKSTART.en.md)
- [Русское руководство](docs/NAVIGATION_QUICKSTART.ru.md)
- [Syntax and semantics](docs/NAVIGATION_010_CONTRACT.md)
- [Measured report](docs/NAVIGATION_010_REPORT.md)

## Release engineering / Подготовка и проверка релиза 0.10

Independent deterministic Android IDs and `--application-id` are implemented.
Независимые Android-приложения собираются с постоянным ID; название отделено от пакета.
[English identity/build guide](docs/ANDROID_ID.en.md) · [Русская инструкция](docs/ANDROID_ID.ru.md).
Wheel/sdist include examples, documentation and license under `sys.prefix/share/sedrava`.
Дистрибутив с примерами, документацией и лицензией опубликован на PyPI.

Measured RC readiness / Фактическая готовность RC: [report / отчёт](docs/RELEASE_READINESS_010_REPORT.md).

## 0.10.0rc1 preparation / Подготовка RC (not published)

[Release notes EN](docs/RELEASE_NOTES_0_10_0rc1.en.md) · [RU](docs/RELEASE_NOTES_0_10_0rc1.ru.md) · [Upgrade/rollback EN](docs/UPGRADE_0_10_0rc1.en.md) · [RU](docs/UPGRADE_0_10_0rc1.ru.md) · [RC report](docs/RC_010_REPORT.md).
Use a verified local wheel in a separate environment; no PyPI/TestPyPI RC has been published.
Установка — из проверенного локального wheel в отдельное окружение; автоматической миграции данных нет.

Stability / стабильность: [audit](docs/STABILITY_AUDIT_010.md), [compatibility](docs/COMPATIBILITY_010.md), [release gates](docs/STABLE_RELEASE_GATES_010.md). Stabilization changes are not a new release; rc1 artifacts remain unchanged.

## 0.10.0rc2 preparation / Подготовка RC2 (not published)

[Release notes EN](docs/RELEASE_NOTES_0_10_0rc2.en.md) · [RU](docs/RELEASE_NOTES_0_10_0rc2.ru.md) · [Upgrade/rollback EN](docs/UPGRADE_0_10_0rc2.en.md) · [RU](docs/UPGRADE_0_10_0rc2.ru.md) · [RC2 report](docs/RC2_010_REPORT.md).
Historical rc1/rc2 artifacts remain unchanged.

## Published 0.10.0 / Опубликованная 0.10.0

Tag **v0.10.0** resolves to commit `688a320025a0d38235eb90c780362ec26b0708e2`; wheel and sdist are published to PyPI. Android versionCode **10003**. Release workflow and CI succeeded; physical-device acceptance of the final 0.10 APK is **not documented**. See [release notes](docs/RELEASE_NOTES_0_10_0.md), [physical-device checklist](docs/PHYSICAL_DEVICE_010.md), [stable gates](docs/STABLE_RELEASE_GATES_010.md), and [owner's publishing checklist](docs/PUBLISH_0_10_0.md).


**Version boundary:** Responsive site and WebApp generation are available in [stable 0.11.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0), not in 0.10.0. Official Astro/Starlight documentation and the separate Sedrava-generated site remain different build systems.

## Experimental Web UI 0.11 / Экспериментальный Web UI 0.11

Source-branch feature, separate from published RC2. Режим из этой ветки, отдельно от опубликованного RC2.

```sh
sedrava check examples/web_ui_011_landing.sdr
sedrava build site examples/web_ui_011_landing.sdr --output build/site
python -m http.server 8000 --directory build/site
```

13 static primitives, responsive layouts and safe assets; no deployment. 13 статических компонентов, адаптивность и безопасные ресурсы; без публикации сайта. [English](docs/WEB_UI_011.en.md) · [Русский](docs/WEB_UI_011.ru.md). Existing application commands are unchanged. Команды приложений не изменены.


## Experimental 0.11 integration / Экспериментальная интеграция

The released 0.11 integration adds shared composition, pure functions, bounded collection queries, forms/tables/dialogs, hash routes, local styling and typed public HTTP. It is included in published stable 0.11.0, but is not a generated backend/auth/database service.

Реализованные возможности, сборка четырёх проектов и ограничения: [English guide](docs/011_WEB_PLATFORM.en.md), [руководство](docs/011_WEB_PLATFORM.ru.md), [actual status](docs/011_IMPLEMENTATION_STATUS.md). Existing published 0.10.0 instructions above remain applicable to their original targets.


## Published stable 0.11.0 and historical 0.11.0rc1

The [experimental RC](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1) is available from [PyPI](https://pypi.org/project/sedrava/0.11.0rc1/) after exact-source CI, distribution checks and practical 0.10 upgrade/rollback testing. It provides responsive `site` generation, interactive `webapp`, typed Web state/components/functions, forms, routes, collection queries and validated public HTTP clients.

The **stable 0.11.0 candidate is not yet published**. It requires fresh exact-head CI and a separate publication decision. [Stable gates](docs/STABLE_RELEASE_GATES_011.md) · [EN release notes](docs/RELEASE_NOTES_0_11_0.en.md) · [RU](docs/RELEASE_NOTES_0_11_0.ru.md). Namespaces, package lockfiles, trusted server, SQLite, authentication and automatic migration are not in 0.11. The official documentation website still uses Astro/Starlight.
