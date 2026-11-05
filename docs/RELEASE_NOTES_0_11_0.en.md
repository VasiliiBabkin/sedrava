# Sedrava 0.11.0 — published stable release

**Published** on GitHub (https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0) and PyPI (https://pypi.org/project/sedrava/0.11.0/) on 5 November 2026. The reviewed release tag points to source commit `c9cde75e3d2e2c7eafeeaec10c73fec627816e68`, merged into main through [PR #44](https://github.com/VasiliiBabkin/sedrava/pull/44). The earlier [0.11.0rc1](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1) ([PyPI](https://pypi.org/project/sedrava/0.11.0rc1/)) and previous stable [0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) ([PyPI](https://pypi.org/project/sedrava/0.10.0/)) remain available.

Install inside a Python 3.10+ virtual environment:

```sh
python -m pip install --upgrade sedrava==0.11.0
sedrava --version
```

## Implemented

- Responsive multi-page sites: `sedrava build site`, reusable checked components, styles and local assets.
- Typed interactive browser applications: `sedrava build webapp`, state/actions, pure functions, bounded collections, routes, forms, tables and dialogs.
- Validated bounded HTTP GET/POST/PUT/PATCH/DELETE *clients*; servers and API credentials are external.
- Four bundled examples: platform_site, platform_tasks, platform_catalog and platform_crm.
- Legacy application/Web/Android generators remain supported for tested schemas; Android versionCode `11002` (RC: 11001; stable 0.10: 10003).

## Actual release evidence

- 36 of 36 exact-source CI checks successful, followed by 11 green checks on the main merge commit.
- Clean wheel and sdist audit and independent verification of exact distributed file hashes.
- Actual PyPI 0.10.0 → 0.11.0 → 0.10.0 and 0.11.0rc1 → 0.11.0 → 0.11.0rc1 Python install/rollback checks.
- Chromium, Firefox, WebKit and Android API35 debug APK upgrade/data-retention tests.
- Published exact artifacts (wheel SHA-256 `5780c3cb14f33b95689c518809254e269a3396bb02720e88f9407b9abbd24626`; sdist `453096116a9da834c4db9023069962cc0d5bf18acb88e403994ad61a339ef70b`).
- [Published release workflow](https://github.com/VasiliiBabkin/sedrava/actions/runs/41951910157) succeeded via PyPI Trusted Publishing.

## Limits

The language is still experimental, not production certified. No generated trusted backend, SQLite/PostgreSQL, authentication, authorization, automatic migrations, physical-device certification or production Android downgrade guarantee. Experimental 0.12 namespaces/packages are not in 0.11. See [release acceptance](STABLE_RELEASE_GATES_011.md), [release train](RELEASE_TRACK_011.md) and [legacy compatibility](COMPATIBILITY_010.md).
