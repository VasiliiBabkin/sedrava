# Sedrava — Roadmap / Дорожная карта

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

### Experimental bounded core A2 (dependent on PR #50)

Source-only work: typed bounded scalar lists, snapshot foreach, signed bounded
ranges, portable work accounting, Unicode 15 normalization/folding and ephemeral
expected Result values. Contracts and remaining limitations:
[English](CORE_012_A2.md), [Русский](CORE_012_A2_RU.md),
[evidence/status](CORE_012_A2_STATUS.md). These are not published stable 0.11
features; Map/Set, persisted Results and namespace reconciliation remain separate.

### 0.12 namespaced bounded-core integration (unpublished)

A1/A2 and #47 are combined in a separate draft: module-owned states/actions,
hygienic bindings, shared limits, original character provenance and strict locked
imports. [EN](CORE_NAMESPACES_012.md) / [RU](CORE_NAMESPACES_012.ru.md). This
supersedes the earlier pure-declarations-only module restriction on this branch;
no server, release or publication is implied. Final evidence is in the draft PR.

## Core 0.12 typed-errors dependent experiment

Closed/open errors, scalar Result<T,E> pairs and exhaustive action match are
implemented on the corrected Effects A1 branch; see
[TYPED_ERRORS_MATCH_012.en.md](TYPED_ERRORS_MATCH_012.en.md) and
[TYPED_ERRORS_MATCH_012.ru.md](TYPED_ERRORS_MATCH_012.ru.md).
Integration remains gated by exact-head cross-platform CI and review. This is not
a stable release. Host A3 / Server bridges, persisted errors, wire codecs and
public generics remain future separately audited work.
