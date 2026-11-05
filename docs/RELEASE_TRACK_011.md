# Sedrava 0.11 release train — current status

**Published stable:** [0.11.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0) ([PyPI](https://pypi.org/project/sedrava/0.11.0/)), exact source `c9cde75e3d2e2c7eafeeaec10c73fec627816e68`, Android versionCode 11002. Earlier stable [0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) ([PyPI](https://pypi.org/project/sedrava/0.10.0/)) and experimental [0.11.0rc1](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1) ([PyPI](https://pypi.org/project/sedrava/0.11.0rc1/)) remain available. The RC source was `6051310a2ba2d542966588f12e0360c3f7c2a4d9`; see [RC audit](UPGRADE_AUDIT_011.md) and [PR #42](https://github.com/VasiliiBabkin/sedrava/pull/42).

**Completed:** Stable 0.11.0 was reviewed and merged via [PR #44](https://github.com/VasiliiBabkin/sedrava/pull/44). The exact source passed 36/36 checks; the main-branch merge commit passed 11/11 checks. [GitHub/PyPI workflow](https://github.com/VasiliiBabkin/sedrava/actions/runs/41951910157) succeeded with exact reviewed wheel and sdist.

## Required acceptance

Read-only release candidate and upgrade workflows must check current source version, clean wheel/sdist, old app/Web/Android behavior, four new Web applications and browser test engines. Perform real published 0.10 → stable → 0.10 and published RC → stable → RC Python upgrade checks. Android API35 tests must validate 10003 → 11002 and debug-only rollback without clearing user data. Verify full Python matrix, code quality/security, archive integrity, documentation and limitations.

The stable release was published from the exact audited source and immutable artifacts, without modifying the historical production publisher pinned to `v0.10.0`. The one-shot 0.11 publisher was disabled after publication. Wheel SHA-256: `5780c3cb14f33b95689c518809254e269a3396bb02720e88f9407b9abbd24626`; sdist SHA-256: `453096116a9da834c4db9023069962cc0d5bf18acb88e403994ad61a339ef70b`.

## Scope boundaries

The 0.11 line provides `site` and `webapp` targets, typed Web state/actions/components/functions, forms/tables/dialogs/routes and bounded public HTTP clients. **Not included:** generated backend, SQLite/PostgreSQL, authentication, data migrations, physical Android certification or experimental 0.12 namespaces/packages. Those live in separate unmerged [PR #39](https://github.com/VasiliiBabkin/sedrava/pull/39), [#40](https://github.com/VasiliiBabkin/sedrava/pull/40), [#41](https://github.com/VasiliiBabkin/sedrava/pull/41) and [#43](https://github.com/VasiliiBabkin/sedrava/pull/43). Future 0.12 alpha must reconcile with the *published* 0.11 baseline.

[Stable acceptance](STABLE_RELEASE_GATES_011.md) · [Candidate EN](RELEASE_NOTES_0_11_0.en.md) · [RU](RELEASE_NOTES_0_11_0.ru.md) · [RC audit](UPGRADE_AUDIT_011.md).
