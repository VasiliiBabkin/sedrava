# Sedrava — experimental lexical namespaces (0.12 Slice A)

**Status: experimental PR, not part of released 0.10.0, not a stable 0.12 release.**

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

- New `module org.name`, `export component/style/record/fn`, `import "file.sdr" as alias` and qualified `alias.Symbol`.
- Omitted `export` makes a module declaration internal; it can still be used from within the defining module.
- Colliding declaration names from independent modules are given distinct canonical IDs. Lexical-token rewrite leaves strings and comments unchanged before the original typed compiler validates results.
- Nested aliases, duplicate module IDs, alias conflicts, private access, symlinks, path traversal, cycles, size/depth bounds and duplicate physical imports are checked.
- Existing flat `import "file.sdr"` is preserved. No automatic global export or network access.
- Deterministic build manifests still record module input hashes.

## Not yet implemented

Full symbol-aware typed IR and accurate diagnostics for every original file/line, semver package manager, lockfile, re-exports, imported mutable state, stable public ABI, server/SQLite/PostgreSQL, authentication and permissions. Static sites support imported components/styles; WebApps support those plus checked functions/records, subject to existing target restrictions.

This is a **first tested lexical namespace implementation**, not completion of the entire architecture in [design PR #38](https://github.com/VasiliiBabkin/sedrava/pull/38). Next: preserve namespace identities in AST/IR, complete cross-file source maps, then packages and independent trusted server runtime.
