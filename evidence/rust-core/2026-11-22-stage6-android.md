# Sedrava Rust migration #65 — initial native Kotlin/Compose generator

**Date:** 2026-11-22. **Status:** experimental scalar Android generator,
not an Android APK or production-compatible replacement. Python remains
the default Android backend.

## Implemented

- Rust-only typed scalar Android project generation from Sedrava app input;
  no Python subprocess for actual code generation.
- Android Gradle / Kotlin Compose source, AndroidManifest, strings.xml,
  metadata (four-field identity schema compatible with Python identity checks).
- Scalar int32/bool/text state, action/require/if/let, derived values,
  state rules, text/int inputs and basic Compose widgets.
- Kotlin exact checked integer arithmetic and rejection of invalid transitions.
- Output must be a fresh directory. The project is first staged in a
  same-parent temporary directory and then published by rename; unsupported
  features / invalid app IDs reject before output creation.
- Explicit app ID argument; prevents accidental project identity changes.
- Unsupported collections, persist, navigation, pure functions and
  advanced UI explicitly reject. No silent feature erasure.

## Verification in local development worktree

Machine: Ubuntu Linux x86_64, Rust 1.100.0, Python 3.12.3, Node 20.20.2,
JDK 17 and Gradle 8.11.1 with Kotlin JVM plugin 2.0.21.

Commands:

    cargo fmt --manifest-path rust/Cargo.toml --all -- --check
    cargo test --manifest-path rust/Cargo.toml --locked --all-targets
    cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava-native
    python3 scripts/verify_native_android.py
    python3 scripts/verify_native_android_kotlin.py --gradle /path/to/gradle
    python3 scripts/verify_native_web.py
    python3 scripts/verify_rust_core.py --random-cases 24
    python3 -m unittest discover -s tests -q
    python3 scripts/check_docs.py

Initial verification of standalone Rust Android generator:
- 40 Rust unit tests PASS.
- Structure and metadata: PASS on examples/counter.sdr and
  tests/rust_cases/native_android_scalar.sdr.
- Deterministic output: 8 files with byte-for-byte identical contents
  between two generated project directories.
- Real Kotlin compiler caught an invalid expression-body early return;
  fixed before publication.
- **Kotlin JVM compilation and reflective state-machine smoke test PASS**
  using **test stubs for Android and Jetpack Compose**. The tested Kotlin
  domain actions correctly increment, decrement and reject underflow
  and arithmetic overflow.

Other development-worktree checks:
- Python/Rust differential: **390 comparisons, 0 observed mismatches** on
  the supported interpreter subset; negative cases compare only rejection
  status ([raw JSON](2026-11-22-stage6-parity.json)).
- Existing Python regression: **274 tests run, 5 skipped, zero failures**.
- Python/Rust schema-1 snapshots: **14 checks passed**
  ([raw JSON](2026-11-22-stage6-snapshot.json)).
- Existing Rust-generated Web/Node mock-DOM and import tests: PASS.
- Documentation checker: PASS (60 current files/links).

This proves Kotlin compilation with mocks, **not Android/Compose APK
compilation, installation, compatibility or runtime correctness**. The
VDS initially had no Android SDK, ADB or real device for this work.

## Not migrated

- Kotlin/Compose app persistence, typed collections, pure function
  codegen, navigation, WebApp and Site, HTTP/Host API.
- Actual Gradle Android Plugin build, Android Lint, APK signing,
  simulator/device runs, install/uninstall/migration tests.
- Cross-OS native binary release acceptance.

Issue #65 therefore remains OPEN. This stage only establishes a tested
starting point for the Android backend without modifying the published
Python compiler or breaking user projects.

Before merging, re-run against the exact GitHub source SHA and record it.
