# Counter-v0 Web: execution readiness and blocked measurement / Готовность запуска

Date: 2026-11-03. PR: [#32](https://github.com/VasiliiBabkin/sedrava/pull/32).

**No autonomous counter trials completed. No language-quality comparison is available.**
**Испытания кодирующего агента не выполнены; сравнение качества языков пока невозможно.**

## Observed result / Фактический результат

| Condition / Условие | Planned / План | Completed / Выполнено | Success rate / Доля успеха | Agent time, tokens, cost |
| --- | --- | --- | --- | --- |
| Sedrava / Web / counter-v0 | 5 | 0 | unknown (`null`), not 0% | unavailable (`null`) |
| TypeScript / Web / counter-v0 | 5 | 0 | unknown (`null`), not 0% | unavailable (`null`) |

The successful original [workflow 41564473752](https://github.com/VasiliiBabkin/sedrava/actions/runs/41564473752), at `4253cce653eac4cc3c4de356dec831df8aa220a9`, establishes only reference controls: 8/8 Web cases per language and 8/8 Android cases for Sedrava/Kotlin. None is an agent-generated candidate. Baseline counts, unit fixtures, negative controls and prepared folders are excluded from the comparison.

## Actual attempted launch / Настоящая попытка запуска

The installed **codex-cli 0.159.0-alpha.3** reported `Logged in using ChatGPT`. A bounded, read-only, ephemeral CLI authorization probe in an empty directory requested **gpt-5.4**, reasoning **medium**, with a 45-second deadline. It was not given counter requirements or reference implementations. It received no model answer. The proxy rejected `wss://chatgpt.com/backend-api/codex/responses` with **HTTP CONNECT 403**; HTTPS requests to the ChatGPT backend also failed. Model metadata could not be fetched; availability of the requested model is unverified. The process exited **124** at the external deadline.

[Raw JSONL events](../evidence/2026-11-03-preflight/events.jsonl), [stderr](../evidence/2026-11-03-preflight/stderr.log), and [machine-readable probe](../evidence/2026-11-03-preflight/probe.json) preserve this evidence. No provider usage or bill was returned. We did not measure the probe wall time separately; the 45-second timeout is a configured limit, not a fabricated timing observation. The probe is not a failed coding trial and contributes no denominator to pass rate.

The managed environment has no configured API secret/outbound identity bindings, and its enforced allowlist excludes ChatGPT/model API hosts. Local CLI login status does not prove server authorization when the proxy rejects the connection before it reaches the service. No proxy bypass, secret extraction, new interactive login, or remote publication was attempted.

Проверена настоящая CLI-сессия, а не имитация ответа модели. Основной блокер — сетевой отказ 403 до обращения к модельному сервису. Авторизация на стороне сервера и доступность модели не подтверждены. Ошибка предварительной проверки не превращена в десять «неуспешных испытаний».

## Prepared implementation / Что подготовлено

- `prepare_web_experiment.py` calls the existing `prepare_trial_bundle.py` ten times, using only the same empty starter and each language's concise syntax/platform reference. No baseline solution is supplied. It checks actual HEAD and committed benchmark files, freezes prompts/input hashes and evaluator hashes, and emits `experiment.json` plus `comparison.json` with an explicit `not_run` status.
- Five unique directories per language, shuffled in a fixed order (order seed 20261103). Replicate IDs 1–5 do **not** claim provider seed control. Input token counts remain null until an actual provider-compatible tokenizer is recorded. The manifests record reasoning medium and unavailable temperature/seed controls explicitly.
- Proposed identical budgets: **600 seconds, 20,000 aggregate input/output tokens, 3 attempts per trial**. These are frozen future limits, **not claims of enforcement by the installed CLI**. Codex CLI help exposes no hard aggregate session-token or build-attempt ceiling. A compliant execution adapter must enforce and log these budgets before the study starts. An instruction in a prompt alone is insufficient.
- `evaluate_web_candidate.py` serves an already built candidate on a fresh localhost port and invokes the existing external Playwright acceptance. It does not call a model, supply a solution, repair source, or create a coding-agent result row. Keep the entire coding/build/browser process in fresh isolated containers when actual trials run; this HTTP helper alone is not a sandbox.
- C01–C08 retain the same behavioral requirements. Strengthening found that hidden counters could pass and that page errors on the second tab were not monitored. The evaluator now requires visible output, captures exceptions on every page, preserves partial observations after a failure, and rejects credential-bearing URLs masquerading as localhost.
- Three actual browser negative controls reject hidden output, lost persistence (C06), and an exception on the C07 page. These are intentionally broken reference mutations, **not agent samples**. Reporting tests cover bundle separation, hashes, unavailable telemetry, counterfeit SHA/dirty inputs and input-solution rejection.

The original baseline CI remains enabled. The benchmark workflow additionally prepares ten frozen bundles and uploads the explicit not-run comparison, and runs the browser negative controls. It never invokes a paid model on repository events. Final commit identity and CI links are recorded in PR #32 and the CI artifact manifests, avoiding a self-referential SHA in this source file.

## Requirements to execute / Точные условия реального запуска

1. Restore approved network access through the managed environment configuration: the existing ChatGPT-authenticated Codex path needs HTTPS/WSS to `chatgpt.com` (model metadata and `/backend-api/codex/responses`; disable unnecessary connectors for the study). Alternatively configure an explicitly authorized provider API credential and its permitted endpoint, such as `api.openai.com`. Never put credentials in Git, bundles, transcripts or agent-visible files. Do not send a key in chat.
2. Perform an external, non-task preflight that verifies the **same resolved model ID** is available for both languages. If gpt-5.4 is unavailable, select another actually available fixed model and regenerate **all** bundles before any trial. Record agent binary/version/hash, provider/model revision where exposed, reasoning settings, immutable container/toolchain versions, compiler revision, evaluator hashes and the experiment start time.
3. Provide an agent adapter enforcing the aggregate token cap, monotonic 600-second deadline and at most three recorded build/revision attempts. It must record every request/response/tool command and authoritative token usage, abort budget overruns, and expose no prior session memory. If these controls or their telemetry cannot be established, do not label the run protocol-compliant. Cost remains null unless a genuine billed measurement is available.
4. Run each of ten trials in a **new container/filesystem** containing only its frozen prompt/task/starter/reference and pinned compiler/toolchain. Do not mount the repository, `.git`, examples, baselines, evaluator, previous trial outputs or host credentials. Keep the provider-facing supervisor outside the tool-execution container. A directory or Git worktree with a readable parent repository does not establish isolation. Use the same CPU/memory/network policy in both conditions. Compiler internals necessarily provide language tooling; disclose those readable files and ship no example solution.
5. After the coding deadline, stop agent access, hash/archive all source, README, transcript, attempts and usage before evaluation. Determine the public UI mapping independently. Run the original eight-case contract outside the coding container, on the built artifact, using a fresh browser context in a separate evaluation container with external networking disabled (loopback HTTP remains available). C01–C08 alone do not certify absence of network dependencies or int32 boundary behavior; retain the original acceptance scope rather than claiming broader coverage. Keep each build command/log, acceptance JSON, source diff, attempt ledger, toolchain and provenance beside the result. Do not silently repair a candidate or retry after seeing private acceptance failures.
6. Admit only provenance-reviewed real trials to `analyze.py`. `run_candidate.py` measures build/evaluation duration and one evaluation cycle; its `attempts=1` and `wall_seconds` are **not** agent revision count or end-to-end agent generation time. Attach actual agent telemetry separately; never promote that runner's template fields to model measurements. Exclude baseline/sample/negative-control rows and infrastructure outages from language pass-rate denominators. Report 5 independent trials per condition and uncertainty; this small task cannot establish a general language ranking.

Для запуска нужны: разрешённый доступ к выбранному модельному сервису и действующая авторизация; подтверждённая модель; адаптер с настоящими ограничениями времени, суммарных токенов и попыток; десять новых изолированных сред; независимая проверка и полная телеметрия. Встроенные вспомогательные агенты текущего сеанса не подменяют эксперимент: они не предоставляют требуемых гарантий изоляции, бюджетов и измерений.

## Commands / Команды

Prepare inputs from a clean committed checkout (does not invoke an agent):

```sh
python benchmarks/agent/prepare_web_experiment.py \
  --commit "$(git rev-parse HEAD)" --model gpt-5.4 \
  --agent "codex-cli 0.159.0-alpha.3 (requested; not verified for execution)" \
  --toolchain "Record actual pinned toolchain before model execution" \
  --seconds 600 --tokens 20000 --attempts 3 \
  --output build/agent-web-experiment
```

Evaluate a genuine built candidate after agent completion and source capture; substitute its independently observed public UI mapping:

```sh
python benchmarks/agent/evaluate_web_candidate.py \
  --directory /isolated-evaluation/built-candidate --entry index.html \
  --value-selector 'output' \
  --increment-label Add --decrement-label Subtract --reset-label Reset \
  --output /isolated-evaluation/evidence/acceptance.json
```

Run reporting and evaluator controls (not coding trials):

```sh
python -m unittest discover -s tests -p 'test_agent_*.py' -v
python benchmarks/agent/run_baselines.py
python benchmarks/agent/test_web_evaluator.py
```

For the last two commands install the workflow's pinned TypeScript 5.9.3 and Playwright 1.56.0/Chromium, and compile the TypeScript baseline as documented in the workflow. `SEDRAVA_CHROMIUM` optionally selects a local Chromium executable for negative controls. Local supplemental validation used Python 3.12.14, Node 24.19.0, TypeScript 5.9.3, Playwright 1.62.0 and system Chromium; this is **not** the frozen prospective agent environment or a Node22/Playwright1.56 trial claim. CI uses the original pinned baseline versions.

**Conclusion / Вывод:** execution is blocked before the first real coding trial. No success rate, generation-time comparison, token-efficiency comparison or cost comparison can honestly be published yet. The prepared inputs and hardened evaluator are ready for an authorized, controlled runner; they do not establish that a compliant coding run occurred.
