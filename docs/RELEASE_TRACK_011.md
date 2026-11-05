# Sedrava 0.11 release train — current status

**Published:** stable version [0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) ([PyPI](https://pypi.org/project/sedrava/0.10.0/)) and experimental [0.11.0rc1 prerelease](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1) ([PyPI](https://pypi.org/project/sedrava/0.11.0rc1/)). RC source SHA: `6051310a2ba2d542966588f12e0360c3f7c2a4d9`. Real 0.10 upgrade/rollback, browser and hosted Android API35 evidence: [audit](UPGRADE_AUDIT_011.md) and [PR #42](https://github.com/VasiliiBabkin/sedrava/pull/42).

**In development:** stable **0.11.0**, versionCode **11002**, source branch `release/011-stable-preparation`. This version is not published. Fresh exact-head acceptance is required; an earlier green RC is not sufficient.

## Required acceptance

Read-only release candidate and upgrade workflows must check current source version, clean wheel/sdist, old app/Web/Android behavior, four new Web applications and browser test engines. Perform real published 0.10 → stable → 0.10 and published RC → stable → RC Python upgrade checks. Android API35 tests must validate 10003 → 11002 and debug-only rollback without clearing user data. Verify full Python matrix, code quality/security, archive integrity, documentation and limitations.

After the exact stable candidate SHA and artifacts are reviewed, the owner must separately authorize merge, stable tag and intended GitHub/PyPI publication. The existing production publisher remains pinned to `v0.10.0`.

## Scope boundaries

The 0.11 line provides `site` and `webapp` targets, typed Web state/actions/components/functions, forms/tables/dialogs/routes and bounded public HTTP clients. **Not included:** generated backend, SQLite/PostgreSQL, authentication, data migrations, physical Android certification or experimental 0.12 namespaces/packages. Those live in separate unmerged [PR #39](https://github.com/VasiliiBabkin/sedrava/pull/39), [#40](https://github.com/VasiliiBabkin/sedrava/pull/40), [#41](https://github.com/VasiliiBabkin/sedrava/pull/41) and [#43](https://github.com/VasiliiBabkin/sedrava/pull/43). Future 0.12 alpha must reconcile with a *published* 0.11 baseline.

[Stable acceptance](STABLE_RELEASE_GATES_011.md) · [Candidate EN](RELEASE_NOTES_0_11_0.en.md) · [RU](RELEASE_NOTES_0_11_0.ru.md) · [RC audit](UPGRADE_AUDIT_011.md).
