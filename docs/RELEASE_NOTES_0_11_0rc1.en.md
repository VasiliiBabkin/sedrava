# Sedrava 0.11.0rc1 — prospective release-candidate notes

**Unpublished candidate.** The latest released version remains [0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0). The text below describes code on `release/011-rc1-preparation` and is not evidence of a GitHub/PyPI release.

## New in the candidate source

- `sedrava build site` produces responsive, multi-page static output with reusable checked components, styles, local resources, and controlled metadata.
- `sedrava build webapp` generates interactive browser applications with typed state/actions, derived expressions, bounded collections, forms, dialogs, tables and guarded hash routes.
- Pure functions, local bindings, bounded transformations and stricter cross-backend validation extend 0.10 domain logic.
- Checked HTTP GET/POST/PUT/PATCH/DELETE public client APIs with error, cancellation and response-schema constraints. API servers are external and independently trusted.
- Example sources `examples/platform_site.sdr`, `platform_tasks.sdr`, `platform_catalog.sdr`, `platform_crm.sdr`.

## Compatibility and limitations

- Published 0.10 remains unchanged; traditional `app`, Web and Android targets continue to work.
- Source imports use a flat module namespace; aliased namespace visibility and package locks belong to **experimental 0.12**, not this candidate.
- There is no generated backend, SQLite/PostgreSQL, authentication, authorization, server-side storage or multiuser protection.
- Browser storage is local; no schema migration guarantee, cold-offline service worker or universal component-instance state.
- Browser and Android behavior requires final same-commit CI acceptance; physical Android hardware is not certified.

## Status, installation and verification

Only use a reviewed checkout of the preparation branch for candidate testing. Do not claim `pip install sedrava==0.11.0rc1` or a `v0.11.0rc1` GitHub release is available until those destinations have been checked after publication.
See [Russian notes](RELEASE_NOTES_0_11_0rc1.ru.md), [full guide](011_WEB_PLATFORM.en.md) and [release gates](RELEASE_TRACK_011.md).


[Verified installation and rollback procedure](UPGRADE_0_11_0rc1.en.md); [independent audit and evidence contract](UPGRADE_AUDIT_011.md).
