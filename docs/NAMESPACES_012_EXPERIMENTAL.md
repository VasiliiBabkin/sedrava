# Sedrava — experimental lexical namespaces (0.12 Slice A)

**Status: experimental PR, not part of published stable 0.11.0, not a stable 0.12 release.**

## Actual source example

Module `examples/namespaces/first.sdr`:

```sedrava
module example.first
export component Panel:
    card:
        heading "First namespaced panel"
```

Usage in `examples/namespace_012_site.sdr`:

```sedrava
site "Namespace demonstration"
import "namespaces/first.sdr" as first
import "namespaces/second.sdr" as second
page home at "/":
    title "Namespace demonstration"
    heading "Two modules, one exported name"
    use first.Panel
    use second.Panel
```

Run this branch's compiler:

```bash
python -m sedrava_cli check examples/namespace_012_site.sdr
python -m sedrava_cli build site examples/namespace_012_site.sdr --output build/namespaced-site
python -m sedrava_cli check examples/namespace_012_webapp.sdr
python -m sedrava_cli build webapp examples/namespace_012_webapp.sdr --output build/namespaced-webapp
python -m unittest tests.test_namespaced_modules_012 -v
```

## Working capabilities

- New `module org.name`, `export component/style/record/fn/state/derive/action`, `import "file.sdr" as alias` and qualified `alias.Symbol`.
- Omitted `export` makes a module declaration internal; it can still be used from within the defining module.
- Colliding declaration names from independent modules are given distinct canonical IDs. Lexical-token rewrite leaves strings and comments unchanged before the original typed compiler validates results.
- Nested aliases, duplicate module IDs, alias conflicts, private access, symlinks, path traversal, cycles, size/depth bounds and duplicate physical imports are checked.
- Existing flat `import "file.sdr"` is preserved. No automatic global export or network access.
- Deterministic build manifests still record module input hashes.

## Not yet implemented

A native multi-file typed IR, re-exports, stable public ABI, remote registry/semver
resolution, server/SQL/authentication and permissions remain unimplemented.
The integrated branch now supports module-owned mutable state/actions/invariants,
original file/line/character provenance and local versioned SHA-256 locks.
See the current [EN integration contract](CORE_NAMESPACES_012.md) /
[RU](CORE_NAMESPACES_012.ru.md) and [package contract](PACKAGES_012_EXPERIMENTAL.md).
Old slice results describe their historical SHA, not current integration readiness.
