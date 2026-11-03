# Coding-agent benchmark: independent trial protocol

The goal is to measure model-assisted software creation, not the runtime speed
of the programming languages. Baseline code and baselines CI are NOT agent trials.

## Fair conditions

- Compare Sedrava with TypeScript on Web, and Sedrava with Kotlin on Android.
  Never merge Web and Android results into a single language ranking.
- Pin the same model, agent harness, reasoning settings, timeout, token budget,
  revision budget, task text, starting environment, and test version.
- Allow language-specific references, but record their complete content hashes,
  token lengths, and allowed file lists. Do not show checked-in solutions from
  benchmarks/agent/baselines/ to the coding agent.
- Create a new isolated checkout/workspace for every trial; no previous
  agent solution or local storage should persist.
- Use seed values 1 through 5 for each comparable language/target combination,
  if the agent exposes seed control. If it does not, record "not exposed".
- Save the exact prompt, tool transcript, source diff, build logs, test evidence,
  measured token usage and tool calls, and real billed cost when available.
- Do not mark a build as a behavioral pass. Evaluate generated artifacts with
  the separate browser or Android device evaluator after agent execution.
- An agent unavailable for a language is "unsupported"; a failed agent run is
  "failed"; an emulator outage or invalid environment is "infrastructure_error".
  The schema's sample row is not evidence of any measured trial.

## Frozen input bundle

Use prepare_trial_bundle.py to create an immutable source input bundle.
Example, after substituting the pinned 40-character Git SHA and actual toolchain:

    python benchmarks/agent/prepare_trial_bundle.py \
      --target web --language sedrava \
      --commit FULL_GIT_SHA --trial-id sedrava-web-001 \
      --model MODEL_ID --agent AGENT_VERSION --seed 1 \
      --toolchain "Python 3.12; Chromium 141" \
      --seconds 600 --tokens 20000 --attempts 3 \
      --starter benchmarks/agent/starters/empty-v0.md \
      --reference benchmarks/agent/references/sedrava-web-v0.md \
      --output build/agent-trials/sedrava-web-001

This script copies the specified files, hashes the references and task, emits a
frozen prompt and manifest, and explicitly marks the trial "not_run". It never
calls the model. Provide the corresponding TypeScript/Kotlin starter and
references for those conditions, without prewritten solutions.

## Evaluation

For Web: build the candidate, serve its files on localhost and use the
framework-neutral Playwright counter evaluator. For Android: build its APK, run
the same ADB/UIAutomator counter evaluator used by the reference applications,
and record the device's fingerprint/API level.

After a *genuine* coding-agent run, attach the frozen manifest and agent logs to
the trial JSON. The current result schema cannot independently prove a trial
was autonomous: verify provenance before including records in public reports.
Generate at least five independent trials per condition before comparing
success rates. Where token usage or cost is unavailable, record null.
