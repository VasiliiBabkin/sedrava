# Sedrava 0.12 B1 — offline local package locks

**Experimental draft only. No registry, download/install manager, remote packages or released 0.12.0.** This slice stacks on [namespace PR #39](https://github.com/VasiliiBabkin/sedrava/pull/39) and [provenance PR #40](https://github.com/VasiliiBabkin/sedrava/pull/40). Published stable 0.11 remains unchanged. Current integration with A1/A2 is described in [EN](CORE_NAMESPACES_012.md) / [RU](CORE_NAMESPACES_012.ru.md).

## A real working vendored example

Run in the new branch:

```sh
python -m sedrava_cli lock examples/packages_012_demo
python -m sedrava_cli verify examples/packages_012_demo
python -m sedrava_cli check examples/packages_012_demo/site.sdr
python -m sedrava_cli build site examples/packages_012_demo/site.sdr --output build/locked-demo
```

Project-level `sedrava.toml`:

```toml
[package]
name = "example.locked.site"
version = "0.1.0"

[dependencies]
"example.cards" = { path = "vendor/example.cards", version = "1.0.0" }
```

Each declared dependency under the local `vendor/` directory must have its own `[package]` manifest with the matching exact version. Dependencies may declare transitive dependencies with root-relative paths under `vendor/`. No remote fetching is implemented.

Ordinary checked imports still work: `import "vendor/example.cards/panel.sdr" as cards`. This slice **does not** implement `pkg:` URLs, import-path rewriting or a package registry.

`sedrava lock` hashes all regular files in each vendored package, fixes the exact package versions and transitively records the dependency graph in canonical JSON `sedrava.lock` without timestamps or host-specific paths. `sedrava verify` recomputes the graph and refuses stale, modified, corrupted or unreviewed content. CLI `check`/`build`/`run`/`test` check the lock automatically when project metadata exists beside the entry file; generated site/WebApp manifests hash the manifest and lock as inputs.

Security constraints: root-confined `vendor/` paths, no symlinks, hidden files or unexpected file types, exact version/name checks, cycle/conflict rejection, up to 32 packages, 256 files and 8 MiB per package, duplicate-key rejection in lock JSON, atomic lockfile replacement. Imported `.sdr` is processed by the existing checked compiler, **not** executed as Python or arbitrary JavaScript.

## What this does not yet provide

No online registry, semver-range solver, downloadable dependency resolution, arbitrary host plugins, ABI compatibility guarantee, package-qualified import or shared server/auth/database. Builds with no `sedrava.toml` still use existing behavior. The project manifest must be next to the `.sdr` entry file in this first slice. On Python 3.10 package-locking users must explicitly install `sedrava[packages]` to obtain `tomli`; on 3.11+ it uses built-in `tomllib`. No dependency is added to the default Sedrava installation, preserving offline install/rollback compatibility for existing users.

The lockfile is a **content-integrity pin**, not a signature or an assertion that third-party source is safe. Review vendored source before locking. Later stages must add actual package namespaces/import resolution, source origin mapping for packages, API/ABI checks, and a trusted server target. Do not merge or release without CI and owner review.
