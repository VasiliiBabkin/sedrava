# Sedrava 0.11 release train — status and audited gates

**Status: 0.11.0rc1 source candidate under preparation; not released or merged into main.**
Published baseline: [v0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0).
Candidate branch: `release/011-rc1-preparation`, based on [integration PR #36](https://github.com/VasiliiBabkin/sedrava/pull/36).

## Frozen proposed 0.11 scope

- Support the already implemented `site` and browser `webapp` targets, preserving 0.10 `app`, Web and Android.
- Static page composition, local checked assets, styling, typed component/slot lowering, functional domain expressions.
- Bounded reactive state/actions, routes, forms/dialogs/tables/collections, checked public HTTP clients with explicit bounds and failures.
- Four source examples: `platform_site`, `platform_tasks`, `platform_catalog`, `platform_crm`.
- No claim of full runtime component instance properties, source-column maps, timezone/clock libraries or arbitrary native extensions.
- Namespace-qualified modules, lockfile packages and dependency management remain in the separate 0.12 experimental line.
- No trusted backend, database, user authentication, authorization, secret storage or production multiuser guarantee.

## Required exact-SHA GO gates

1. Complete Python tests pass for exact candidate SHA; no known release-blocking regressions.
2. Existing Python 3.10/3.12/3.13, legacy 0.9/0.10 and Android/Compose/JVM/Lint workflows pass on candidate SHA.
3. Four generated projects build and run in the platform browser acceptance, including Chromium, Firefox, WebKit; verify screenshots/artifacts match SHA.
4. Build exactly one wheel and sdist, check metadata, archive/source integrity and reproducible payloads; clean-install both archives outside checkout.
5. Check upgrades from published 0.10 in separate environments and, where identical signing identity permits, Android upgrade/data retention; document rollback limits.
6. Security audit reports no new workflow privileges, unreviewed publishing paths, exposed secrets or unsafe generated code in covered tests.
7. RU/EN source docs and `sedrava-site` describe released 0.10 and *unpublished* RC/alpha without dead release links or claiming database support.
8. Owner reviews immutable SHA, complete CI jobs, installed artifacts, limitations, release notes and intended publication destination.

Release-candidate test workflow `.github/workflows/release-011-candidate.yml` is read-only and **cannot publish**.
Existing `.github/workflows/publish-pypi.yml` remains intentionally pinned to the immutable 0.10 stable tag. It must not be broadened to a version wildcard to publish 0.11.

## Publication sequence after GO

Create and review the exact-source RC artifact inventory; verify PyPI/TestPyPI version availability and distribution identity.
After separate owner approval for SHA/digest/target, create `v0.11.0rc1` tag and GitHub prerelease (and PyPI/TestPyPI only if explicitly approved and configured).
Observe/test candidate, fix any blocking errors in new RC, and only then plan `0.11.0` final with a separate fresh review and publication contract.
Never move an existing published tag or replace registry files.

## Parallel 0.12 alpha

[PR #39](https://github.com/VasiliiBabkin/sedrava/pull/39), [#40](https://github.com/VasiliiBabkin/sedrava/pull/40), [#41](https://github.com/VasiliiBabkin/sedrava/pull/41) form a stacked experimental namespace/provenance/offline-package line.
An eventual `0.12.0a1` must rebase onto the *released* 0.11 baseline, satisfy the same security/reproducibility gates and be explicitly published as a prerelease, never confused with stable 0.11.

## Independent practical upgrade gate / Практическая проверка обновления

See [actual baseline hashes and audit](UPGRADE_AUDIT_011.md), [EN upgrade/rollback](UPGRADE_0_11_0rc1.en.md) and [RU instructions](UPGRADE_0_11_0rc1.ru.md). The read-only `upgrade-011.yml` uses the real published **0.10.0** wheel/sdist and the exact-head candidate artifacts. Its `sedrava-upgrade-final-report` must say GO for the same source SHA; an old 0.9/early-RC test or clean installation alone does not satisfy this gate. Android normal downgrade rejection and debug-only rollback are distinct. Final technical readiness still requires all other applicable exact-head workflows and owner publication approval.
