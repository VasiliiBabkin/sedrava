# Agent trial instructions — counter-v0 / Web

This is a reproducible **prompt template**, not evidence of a completed trial.
For each trial replace the bracketed values, start from a fresh checkout,
and record the exact prompt text and agent configuration.

## Assignment

Implement a Web application satisfying the complete requirements in
`benchmarks/agent/tasks/counter-v0.md` using **[LANGUAGE]**.

Use the existing language toolchain and starter scaffold in **[STARTER_PATH]**.
You may read the supplied documentation under **[REFERENCE_PATH]** and run
the available build and test commands. Do not change the acceptance tests.
Do not use an external service, network persistence, or a second language
to implement the application's core behavior.

Deliver source code in **[CANDIDATE_PATH]**, a short README with exact build
and run commands, and a note identifying any unmet requirements.

## Conditions (fill before each run)

- Repository commit: **[40_CHARACTER_SHA]**
- Language: **[sedrava|typescript]**
- Model and agent version: **[MODEL_AND_AGENT_VERSION]**
- Toolchain and runtime: **[VERSIONS]**
- Starter scaffold hash: **[SHA256]**
- Reference documentation hash: **[SHA256]**
- Time / token / tool-call budget: **[BUDGET]**
- Seed / temperature (if exposed): **[SETTINGS]**
- Trial identifier: **[TRIAL_ID]**

## Independent evaluation

A separate evaluator (not the coding agent) checks the observable behavior:
fresh count 0; increment; decrement into negatives; reset; sequential
operations; persistence across reload. The evaluator must test the built
artifact, not just inspect code. Record exact commands, versions, test logs,
and failures. Do not give the agent the private evaluator implementation.
Run at least five independent trials per comparable condition.

**Important:** This template does not invoke a model, and it does not claim
that any implementation has passed.
