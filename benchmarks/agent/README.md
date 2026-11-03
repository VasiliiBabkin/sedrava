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
