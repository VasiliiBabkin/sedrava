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
