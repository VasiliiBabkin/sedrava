# Sedrava 0.12.0a1 — proposed experimental alpha notes

**Unpublished experimental 0.12.0a1 source.** The current stable release is [0.11.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0) ([PyPI](https://pypi.org/project/sedrava/0.11.0/)), with historical [0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) and [0.11.0rc1](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1) still available. Experimental alpha source is reconciled on a stable 0.11 baseline in `integration/012-alpha1-stable-base`; no `v0.12.0a1` tag, PyPI artifact or GitHub Release is claimed. Read-only candidate acceptance passed on exact SHA `14951a74e57929777560003aa52a425391bc41b2` ([run 42371782797](https://github.com/VasiliiBabkin/sedrava/actions/runs/42371782797)); the three-engine browser/Android-domain matrix passed on that PR head ([run 42371782882](https://github.com/VasiliiBabkin/sedrava/actions/runs/42371782882)). Two HTTP-browser tests were skipped in the candidate job because Playwright was not installed there; the HTTP API-specific E2E passed on the unchanged Host/Core parent SHA #57 ([run 42343889050](https://github.com/VasiliiBabkin/sedrava/actions/runs/42343889050)). This is not a single-job full-suite claim. These results apply to the cited SHA only; this documentation update requires fresh exact-head checks before release.

## Implemented in the candidate's source

- `module company.name`, explicit `export` of components/styles/records/pure functions, `import "relative.sdr" as alias` and qualified `alias.Symbol`.
- Private declarations are inaccessible from another module; names may safely collide across independent imported modules.
- Compile-time alias lowering uses checked lexical token transformations and maintains old flat imports. It is not yet a full symbol-aware typed IR.
- Original source file and line are retained for common nested import/component errors. Full rewritten column-level source spans are not available.
- Offline `sedrava.toml` dependencies must be vendored under `vendor/`, with exact versions and canonical SHA-256 `sedrava.lock` content.
- `sedrava lock` and `sedrava verify` check local integrity, cycles, directory traversal, symlinks and bounded dependency sizes; normal check/build verifies when a manifest is present.

## Additional typed Core and trusted Host A3 candidate features

- `error closed/open` variants with typed payloads and stable identities; contextual `Result<T,E>`, exhaustiveness-checked `match`, and compatibility with legacy `Result<T,Error>`.
- Experimental `effects pure` contracts and transitive checked pure-function graphs. The manifest is not an authorization token or complete system-wide effect analysis.
- Explicit-permission, trusted POSIX Host A1–A3 operations, scoped text/JSON I/O, `try_read` returning Core `Result<text,HostReadError>`, plus catchable expected file errors. Policy violations remain noncatchable.
- Versioned HostExecutionResult v1 with four statuses, phase tracking and conservative unknown-commit-state errors.
- Cross-target Python/JS/Android and Host tests have been executed on the stacked experimental sources. This **does not** certify untrusted script execution, production isolation or privileged server use.

## Explicit missing capabilities

No online package registry, automatic dependency download, semver range resolution, package-qualified imports, stable ABI, guaranteed source trust from SHA-256, generated trusted server, SQLite/PostgreSQL or authentication.

## Release boundary

The original alpha stack [#39–43](https://github.com/VasiliiBabkin/sedrava/pull/43) was based on an old experimental Web branch. The new alpha integration is based on **published stable 0.11.0**, without changing that stable release. Keep 0.10 and RC history, verify candidate file digests and obtain separate owner authorization before any alpha tag, release or PyPI upload.

[Russian notes](RELEASE_NOTES_0_12_0a1.ru.md) · [Alpha gates](RELEASE_TRACK_012_ALPHA.md) · [Namespace reference](NAMESPACES_012_EXPERIMENTAL.md) · [Offline packages](PACKAGES_012_EXPERIMENTAL.md).
