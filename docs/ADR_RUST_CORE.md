# ADR: Native Rust core for Sedrava

**Decision:** Introduce an experimental native Rust parser, type checker and
state interpreter in the existing Sedrava repository alongside Python.
Do not replace the published Python CLI automatically before verified parity.

**Motivation:** A standalone native CLI, controlled low-level integration and
measurable startup/compilation performance. No universal speedup assumed.

## Design constraints

- Keep the Sedrava source syntax and observed behavior as the contract.
- Preserve int32 overflow checking, Unicode scalar limits, strict escapes,
  atomic actions, and separate require vs rule rejection behavior.
- Safe Rust and bounded parsing/execution; no source evaluation or implicit IO.
- Reject unsupported constructs explicitly, including records and collections.
- The current Rust AST is internal; it is not yet a stable cross-target IR.
- Preserve published Python 0.11.0 artifacts, PyPI packages and source tags.
- Publish raw measurements and failures, not performance marketing claims.

## Alternatives

1. Rewrite everything in Rust immediately: high compatibility risk and hard to
   review; rejected.
2. Keep only Python: easy maintenance but no standalone native compiler;
   rejected as long-term-only direction.
3. Selected: native scalar subset with differential checks before expansion.

## Next milestones

1. Experimental typed JSON IR and top-level source spans now implemented;
   next complete expression-level spans and structured diagnostics.
2. Records, bounded lists and identity with cross-runtime conformance.
3. Pure functions implemented; still port modules, full budgets and Host Effects.
4. Connect existing Web/Android generators through versioned IR after parity.
5. Investigate native code generation separately.
6. Integrate SedravaSQL through explicit storage permissions and a stable API.

**Risk:** two-engine maintenance, semantic drift, more complex builds,
cross-platform distribution. No default engine switch without a reviewed
compatibility matrix.

[Russian technical guide](RUST_CORE_MIGRATION.ru.md).
