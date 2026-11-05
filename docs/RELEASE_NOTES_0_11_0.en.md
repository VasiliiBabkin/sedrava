# Sedrava 0.11.0 — stable release candidate notes

**Not published.** The current stable package is [0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) ([PyPI](https://pypi.org/project/sedrava/0.10.0/)). The experimental [0.11.0rc1 prerelease](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1) is published on [PyPI](https://pypi.org/project/sedrava/0.11.0rc1/). This is a source-only *stable candidate* awaiting final checks and owner approval.

## Candidate scope

- Responsive multi-page sites via `sedrava build site`, checked local assets and reusable typed components.
- Interactive browser applications via `sedrava build webapp`: typed state/actions, pure functions, bounded collections, routes, forms, dialogs and tables.
- Validated bounded public HTTP GET/POST/PUT/PATCH/DELETE clients; APIs/servers are independently provided.
- Four reproducible example projects: site, tasks, catalog and CRM; legacy `app`, Web and Android targets retained.
- VersionName `0.11.0`; Android versionCode `11002` (published RC: 11001).

## Known limits and release status

No generated trusted backend, SQLite/PostgreSQL, authentication/authorization, automatic migrations, namespaces/packages, physical Android certification or production-signed downgrade guarantee. An HTTP client alone cannot implement a backend.

Final exact-source Python/Web/Android CI, clean wheel/sdist install and both real PyPI 0.10 and RC upgrade/rollback tests must pass before approval. **Do not use `pip install sedrava==0.11.0` as installation guidance until the version is actually published.** [Gates](STABLE_RELEASE_GATES_011.md) · [Release train](RELEASE_TRACK_011.md) · [Legacy compatibility](COMPATIBILITY_010.md).
