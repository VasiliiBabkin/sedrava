> Historical reference; not a current release or installation guide. [Current Rust documentation](README.ru.md).

# Sedrava usefulness experiment

## Hypothesis

A declarative specification that combines application behavior, invariants, and executable examples can reduce authoring effort and regressions relative to direct Kotlin/Compose implementation for a defined class of small applications.

This is a hypothesis, not a measured outcome.

## Baselines

1. Native Kotlin/Compose implementation with conventional unit tests.
2. AI-assisted Kotlin/Compose implementation from the same natural-language requirements.
3. Sedrava specification compiled deterministically to Kotlin/Compose.

Keep the requirements, target SDK, UI acceptance criteria, developer experience, and test device identical. Count all compiler, runtime, generator, and specification fixes as engineering effort for the Sedrava arm.

## Trial applications

- Counter: increment, decrement, reset, nonnegative invariant.
- Timer: monotonic countdown, pause/resume, background and screen-lock behavior.
- Local notes: create, edit, delete, persistence, restart and migration.

## Measurements

- Human editing time and number of intervention rounds.
- Lines and concepts maintained by the human (not generated code).
- Static diagnostic accuracy and actionable error messages.
- Number of failing acceptance tests and regressions after requirement changes.
- Android cold start, binary size, and memory use on the same hardware.
- Build reproducibility and build time.
- Cross-platform semantic equivalence once a second backend exists.

## Acceptance gates

1. No false claim of formal verification: executable examples are tests, not proofs.
2. Generated projects must build in CI and APKs must pass device-level acceptance tests.
3. Every new language construct has parsing, typing, interpreter, and backend tests.
4. Never silently discard or reinterpret a source declaration.
5. Measure before claiming productivity, reliability, or portability advantages.

## Technical priorities

1. Typed AST with source locations and deterministic diagnostics.
2. Arithmetic transitions and multi-statement actions.
3. Predicate evaluation over *post-transition* state with invariant enforcement.
4. UI event binding to validated transitions.
5. Explicit time/event model (clock source, background policy, lifecycle).
6. Persistent state with versioned schema.
7. Second backend (web) and semantic conformance tests.
8. Optional AI authoring layer, with independent deterministic validation.

## Explicit non-goals for v0.2

- Replacing Kotlin for arbitrary Android development.
- Claiming complete application correctness.
- General-purpose arbitrary code execution in specifications.
