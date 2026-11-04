# Sedrava 0.12 A2 — original-file diagnostics

**Status: experimental draft stacked on namespace PR #39 and WebApp PR #36. Not part of the published 0.10.0.**

## What actually changed

Before this slice, aliased modules were lowered into one combined stream, then reusable components were expanded. Parser errors often pointed to a misleading generated line number.

Now optional source provenance records the original checked file and line for every emitted line of nested aliased imports, old unqualified imports, and component template/slot expansion. Both `sedrava check` and `sedrava build site` / `build webapp` reuse it.

Example for a typo on line 2 of `math.sdr`:

```text
.../math.sdr:2:43: Unknown identifier: missing (expanded line 2)
```

The original `expand(source, path)` return contract remains `(source, dependencies)`. Call `expand(source, path, with_origins=True)` to additionally receive the immutable per-output-line `(Path, original_line)` provenance sequence.

## Evidence and boundaries

- 7 focused regression tests exercise nested namespace imports, legacy imports, component templates, main caller locations, build and check diagnostics, and no guessed locations.
- 11 existing namespace/legacy module tests also passed locally.
- Before publication to the PR, the reference namespaced site/WebApp generated **identical file hashes** with and without this change (four files each).
- Source metadata exists only during compilation. No runtime JS, extra permissions, or backend capabilities are added.
- The compiler still checks all import path/symlink/cycle/private-export boundaries.

**Remaining limitations:** This is reliable original **line** provenance for supported transformations, not complete column-level mappings for rewritten identifiers, every synthetic compiler pass, or a native typed-IR symbol table. Compiler errors without a checked line remain unchanged; mapping never guesses. Lexical symbol lowering remains experimental. No package manager, SQLite, server, or authentication is present.

Next steps: complete column/span mapping and canonical typed-IR symbol identity; then design and implement local versioned packages/lockfiles in a separate PR. This draft does not authorize merges, releases, or deployment.
