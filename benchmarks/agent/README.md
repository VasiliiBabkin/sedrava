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

## Candidate runner (no model invocation)

`run_candidate.py` executes a pre-existing candidate's build command and, only
if that succeeds, its behavioral test command. It records exit status, elapsed
time, and separate build/test logs. Commands are argv vectors executed **without
a shell**. Run only trusted build/test commands in an isolated environment.

Example (replace the scripts with real commands and the SHA with the tested
commit):

```bash
python benchmarks/agent/run_candidate.py \
  --task counter-v0 --language sedrava --target web \
  --model manual-baseline --commit "$(git rev-parse HEAD)" \
  --cwd . --build python -m compileall -q sedrava.py \
  --test python -m unittest tests.test_core -v \
  --output /tmp/sedrava-trial.json
python benchmarks/agent/analyze.py /tmp/sedrava-trial.json
```

The example above is **only a runner demonstration**: it is not a valid
cross-language behavioral comparison. A real benchmark must use task-specific
acceptance tests and agent-produced candidate source. Token usage and cost
remain `null` until independently recorded. A run marked `manual-baseline`
must never be presented as an autonomous agent trial.

## Browser acceptance evaluator (counter-v0)

The standalone Playwright evaluator in
`acceptance/counter_web_browser.py` executes cases C01–C08 against an
**already running local HTTP Web app**. It does not inspect source or
application storage keys. Supply the CSS selector for the displayed count
and the visible accessible button labels for each candidate. Example:

```bash
python -m pip install playwright
python -m playwright install chromium
python benchmarks/agent/acceptance/counter_web_browser.py \
  --url http://127.0.0.1:8000/index.html \
  --value-selector 'output[data-state="count"]' \
  --increment-label Add --decrement-label Subtract --reset-label Reset \
  --output /tmp/counter-acceptance.json
```

Start the local server separately and point it at the **built** candidate.
The selector above is illustrative; inspect each implementation's public
UI and record the mapping before running. The evaluator rejects non-local
URLs, uses a fresh browser context per invocation, and writes a JSON report.
A passed result establishes the observed Web counter behavior only, not
language-wide agent success. Keep each candidate's build logs and trial
metadata alongside the browser report. No benchmark agent runs are bundled.


## Android baseline acceptance (not agent trials)

The native Kotlin reference implementation is hand-written in
baselines/kotlin-android/MainActivity.kt. The separate
prepare_kotlin_android_baseline.py builds only an Android Gradle project
around that source. Sedrava Android is generated from
baselines/sedrava/counter.sdr. Both APKs are tested using the same
acceptance/counter_android_device.py script against emulator API 35.

The Android suite covers A01–A08: fresh install, increment, decrement,
reset, multiple operations, process death/relaunch, home/reopen, and persisted
reset. It reads displayed UI text through ADB/UIAutomator, not storage or
application internals. GitHub Actions uploads both JSON evidence files and
APKs. Android CI builds and baseline passes are *not* model performance data.

## Reproducible agent trial inputs

See prompts/experiment-protocol-v0.md and prepare_trial_bundle.py.
The bundle builder freezes each starter, reference and task with SHA-256,
and emits the exact coding-agent prompt plus a manifest with outcome not_run.
It has no access to an AI model and does not generate success measurements.
The first agent trials must be executed by an actual coding-agent harness,
followed by independent browser/Android acceptance and measured telemetry.

## First Web measurement attempt (2026-11-03)

[Execution report / отчёт](reports/counter-web-2026-11-03.md): **0 actual agent trials**.
The real Codex CLI preflight was blocked by the managed proxy (HTTP CONNECT 403);
model access was not verified. There is no measured Sedrava-versus-TypeScript
pass rate, generation time, token consumption or cost.

`prepare_web_experiment.py` creates five neutral frozen bundles per language
through the existing bundle builder, an explicit not-run comparison, scheduling
order and evaluator hashes. Prepared directories are not isolated executions.
`evaluate_web_candidate.py` serves built candidates and invokes the independent
C01–C08 evaluator; keep its output outside the served directory. The agent must
never see the evaluator, baselines or prior candidates. Real runs additionally
need an authorized model endpoint, a budget-enforcing adapter and fresh isolated
containers; see the report for exact requirements and commands.

The evaluator now rejects hidden count displays, monitors errors on every tab,
retains partial failure evidence, and validates local URLs structurally.
`test_web_evaluator.py` exercises three deliberately broken baseline variants;
these controls are not coding-agent measurements. Existing baseline jobs and
all eight behavioral cases remain enabled.
