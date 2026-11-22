# Rust Core verification evidence — 2026-11-22

This report documents a **restricted scalar Sedrava native prototype**, not
full language parity, native code generation, Web/Android speed, safety
certification or production readiness.

## Exact revisions

- Rust build, rustfmt, unit tests and differential tests: Sedrava
  commit 31250bee938863bca60ce7f23bb6a00140516f5a.
- CLI benchmark: source commit 20066cb93240e101ccdc5cf8f6c7dedd7bb30efa;
  the later commit applies rustfmt only to Rust implementation and adds docs/lockfile.
- Script inputs: scripts/verify_rust_core.py and
  scripts/benchmark_rust_core.py in this branch.

## Environment

- Linux 6.8.0-147-generic x86_64, virtualized Intel Xeon Skylake
  (IBRS), 2 available logical CPUs, about 7.8 GiB memory.
- Python 3.12.3.
- rustc 1.100.0 (0ef1bc386 2026-11-09).
- Cargo 1.100.0 (3acc79c0c 2026-11-05).
- Isolated user-local Rust toolchain and work directory; no system-wide
  package upgrade or production service restart.
- Dependency resolution recorded by rust/Cargo.lock; Cargo commands used
  --locked against the lockfile.

## Commands and results

From a checkout at the test revision:

    cargo fmt --manifest-path rust/Cargo.toml --all -- --check
    cargo test --manifest-path rust/Cargo.toml --workspace --all-targets --locked
    cargo build --manifest-path rust/Cargo.toml --bin sedrava-native --locked
    python3 scripts/verify_rust_core.py --random-cases 32
    python3 -m unittest discover -s tests -q
    python3 scripts/check_docs.py

Observed:
- rustfmt check: PASS
- Rust unit tests: **13 passed, 0 failed**
- Native CLI build: PASS
- Python/Rust differential: **263 comparisons, 0 mismatches**;
  167 accepted and 96 rejected by Python, matching Rust success/rejection.
- Unsupported records/collections sample: explicitly rejected by Rust.
- Existing Python suite: **274 tests, 0 failures, 5 skipped**
- Documentation checker: **60 documents / local links checked, PASS**

The differential program compares actual JSON output on successful runs.
For failures it compares only the **fact of rejection**, not its cause or
error string. It is not evidence for unsupported language constructs.

Raw reproducible aggregate results:
- [Differential parity](2026-11-22-parity.json)
- [CLI benchmark measurements including every individual sample](2026-11-22-benchmark.json)

## Scoped CLI latency benchmark

Benchmark command:

    python3 scripts/benchmark_rust_core.py --repeats 30 --seed 23042

The script performs five warm-up calls per engine and scenario, then
interleaves 30 subprocess calls for each engine with a deterministic seed.
Results are **end-to-end command latency**: process launch, interpreter
startup, source loading and parsing, plus command execution.

| Scenario | Python median (ms) | Rust median (ms) | Python/Rust |
| --- | ---: | ---: | ---: |
| check reference_09.sdr | 219.8026 | 4.3487 | 50.544 |
| run reference_09.sdr (two actions) | 233.2650 | 3.7184 | 62.733 |
| run text_profile.sdr (Unicode action) | 217.9399 | 3.4160 | 63.800 |
| test reference_09.sdr | 233.3806 | 4.6002 | 50.733 |

**Important:** This is a comparison of startup-heavy short CLI commands
on one VDS and a narrow shared subset of Sedrava. It does NOT establish a
50–64x speedup for compiler algorithms, long-running programs, generated
Web/Android code, or arbitrary user programs. Hardware load, cache behavior
and workload choice can change these numbers substantially.

## Limitations and required follow-up

- Native Rust currently rejects records, collections, navigation, pure
  functions, modules, host effects, site/webapp and code generation.
- No native persistence, database API or Android packaging.
- Regression suite and differential harness are samples, not a language
  equivalence proof.
- No separate audit of runtime security, fuzzing, Windows/macOS CI,
  concurrency or end-user acceptance.
- GitHub Actions checks were **not** used as evidence for the Rust results
  above; the listed checks ran directly on the Linux VDS.

This report is an engineering record, not a release certificate.
