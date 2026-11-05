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
- Source metadata exists only during compilation. The generated applications do not embed developer paths or require extra permissions. Python runtime expressions retain their checked original origins.
- The compiler still checks all import path/symlink/cycle/private-export boundaries.

**Current integration:** lexical replacements and component substitutions now carry
character maps. App/site/WebApp compile diagnostics and Python runtime errors use
original paths, lines and scalar columns. Nested imported-call and template-column
regressions execute the actual compiler. This remains lexical lowering, not a
native multi-file typed-IR debug symbol table; some whole-program errors have only
a declaration/file location. Local package locks are implemented separately and
included in the integration; no remote registry, SQL, server or authentication.
See [EN](CORE_NAMESPACES_012.md) / [RU](CORE_NAMESPACES_012.ru.md).
Historical slice counts above are not final integration evidence. No merge,
publication or deployment is authorized by this document.
