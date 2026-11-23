# Native 0.12.0-alpha.1 — release gates

Status: LOCAL Linux pre-release candidate, NOT a published stable release.

| Gate | Status | Evidence |
| --- | --- | --- |
| Rust CLI --version / Cargo match | PASS | 0.12.0-alpha.1 |
| Native unit tests | PASS | 81 tests, locked offline |
| Differential Python/Rust subset | PASS | 390 cases, zero observed mismatches |
| Native smoke | PASS | 7 scenarios including parser rejection |
| Trusted Host smoke | PASS | scoped permissions and rollback |
| Server A6 regression | PASS | 46 HTTP writes, replay, four crash windows |
| Archive reproducibility | PASS | same compiled binary gives identical archives |
| Offline installer | PASS | no Python/Rust PATH; fails on invalid hash/overwrite |
| Android APK/device | NOT TESTED | source emission does not imply APK |
| Windows/macOS | NOT TESTED | no native build/installation |
| Full Python 0.11 language coverage | INCOMPLETE | chosen subset only |
| Full browser parity | NOT TESTED THIS CANDIDATE | independent acceptance required |
| Security / physical power-loss | NO-GO | production claims excluded |
| Public tag/Release/PyPI | NOT PERFORMED | separate publication gate |
| Python stable replacement | BLOCKED | 0.11.0 remains stable |

Linux reproduction (assumes default rust/target or matching CARGO_TARGET_DIR):

    cargo fmt --manifest-path rust/Cargo.toml --all -- --check
    cargo test --manifest-path rust/Cargo.toml --locked --offline --all-targets
    cargo build --manifest-path rust/Cargo.toml --locked --offline --bin sedrava-native
    python3 scripts/verify_rust_core.py --native rust/target/debug/sedrava-native --random-cases 24
    python3 scripts/verify_native_alpha_012.py --native rust/target/debug/sedrava-native
    cargo build --manifest-path rust/Cargo.toml --locked --offline --release --bin sedrava-native
    python3 scripts/verify_native_alpha_012.py --native rust/target/release/sedrava-native
    python3 scripts/verify_native_preview_install.py

Security, browser, Android, cross-platform and full language-compatibility
gates remain explicit, even if the above commands pass. A release requires
immutable source SHA, verified artifacts and explicit publication decision.
