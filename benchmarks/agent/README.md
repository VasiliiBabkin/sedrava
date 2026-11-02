# Sedrava Agent Benchmark (experimental v0)

This benchmark evaluates how reliably a coding agent produces **working** programs from the same functional requirements in Sedrava, TypeScript, and Kotlin. It is not a language popularity ranking.

## Protocol

1. Pin repository commit, compiler/toolchain versions, model identifier, agent settings, system prompt, and test harness.
2. Give each language the same behavior specification, but language-specific syntax references and starter scaffolding. Report reference token counts.
3. Run at least five independent trials per language and task. Use identical time, attempt, and token budgets. Do not reuse generated code across trials.
4. Permit documentation and compiler/test feedback equally; record every attempt and correction. No hidden human edits.
5. Evaluate build success separately from behavioral tests. A successful build is not a successful task.
6. Record wall time, input/output tokens, tool calls, build/test attempts, and any externally billed cost. If unavailable, record null; never estimate it as measured.
7. Publish raw JSON results, toolchain versions, tests, and failures. Report sample size and uncertainty; avoid conclusions from a single run.

## Tasks

- `counter-v0`: increment/decrement, reset, and persistence after reload/restart.
- `records-v0`: create, edit, delete, and reject invalid entries without losing previously saved data.
- `navigation-v0`: two screens, back navigation, and preservation of state.
- `http-cards-v0`: read-only HTTPS JSON cards, loading/empty/error states, safe rendering, and retry. **Sedrava 0.11 experimental Web only**; do not compare with stable Sedrava 0.10.

Cross-language tests must implement the same *observable* behavior, not require identical UI markup. Record unsupported tasks as unsupported, not as agent failures. Android and Web results must be reported separately.

## Result format

See `result.schema.json` and `sample-result.json`. A trial is one model/task/language/seed combination. The schema requires an explicit outcome and disallows silently filling missing measurements with zero.

## Interpretation

Report pass rate with numerator and denominator, median attempts/time/tokens where measured, and confidence intervals when sample size permits. Disclose agent access to examples and any prior knowledge of the language. A language-specific reference supplied to an agent is a treatment condition, not a neutral constant.
