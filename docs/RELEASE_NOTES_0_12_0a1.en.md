# Sedrava 0.12.0a1 — proposed experimental alpha notes

**Unpublished source candidate.** Latest verified published version remains [0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0). The 0.11.0rc1 source candidate is under separate review in [PR #42](https://github.com/VasiliiBabkin/sedrava/pull/42). This document does not assert any `v0.12.0a1` tag, PyPI artifact or GitHub Release exists.

## Implemented in the candidate's source

- `module company.name`, explicit `export` of components/styles/records/pure functions, `import "relative.sdr" as alias` and qualified `alias.Symbol`.
- Private declarations are inaccessible from another module; names may safely collide across independent imported modules.
- Compile-time alias lowering uses checked lexical token transformations and maintains old flat imports. It is not yet a full symbol-aware typed IR.
- Original source file and line are retained for common nested import/component errors. Full rewritten column-level source spans are not available.
- Offline `sedrava.toml` dependencies must be vendored under `vendor/`, with exact versions and canonical SHA-256 `sedrava.lock` content.
- `sedrava lock` and `sedrava verify` check local integrity, cycles, directory traversal, symlinks and bounded dependency sizes; normal check/build verifies when a manifest is present.

## Explicit missing capabilities

No online package registry, automatic dependency download, semver range resolution, package-qualified imports, stable ABI, guaranteed source trust from SHA-256, generated trusted server, SQLite/PostgreSQL or authentication.

## Release boundary

This 0.12 source alpha currently builds on the **unmerged experimental 0.11** integration line and must be reconciled with a reviewed/released 0.11 baseline before any public alpha publication. Preserve the stable 0.10 history, run full exact-SHA CI and obtain owner approval for immutable bytes/destination.

[Russian notes](RELEASE_NOTES_0_12_0a1.ru.md) · [Alpha gates](RELEASE_TRACK_012_ALPHA.md) · [Namespace reference](NAMESPACES_012_EXPERIMENTAL.md) · [Offline packages](PACKAGES_012_EXPERIMENTAL.md).
