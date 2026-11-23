# Native 0.12.0-alpha.1 — release gates

Status: LOCAL Linux pre-release candidate, NOT a published stable release.

| Gate | Status | Evidence |
| --- | --- | --- |
| Rust CLI --version / Cargo match | PASS | 0.12.0-alpha.1 |
| Native unit tests | PASS | 81 tests, locked offline |
| Differential Python/Rust subset | PASS | 390 original main checks; **898 more checks against published 0.11.0 tag**, 0 mismatches; not total parity |
| Native smoke | PASS | 7 scenarios including parser rejection |
| Trusted Host smoke | PASS | scoped permissions and rollback |
| Server A6 regression | PASS | 46 HTTP writes, replay, four crash windows |
| Archive reproducibility | PASS | same compiled binary gives identical archives |
| Offline installer | PASS | no Python/Rust PATH; fails on invalid hash/overwrite |
| Kotlin/JVM execution | PASS | Generated Kotlin compiled and executed by Gradle Kotlin 2.0.21; navigation, types, persistence |
| Android APK/device | NOT TESTED | JVM acceptance and Android source emission do not imply APK |
| Windows/macOS | NOT TESTED | no native build/installation |
| Full Python 0.11 language coverage | INCOMPLETE | chosen subset only |
| Web DOM and generated assets | PASS (subset) | Seven published-stable Site/WebApp dual builds, Node VM checks, 4 jsdom interactive cases |
| Real Chromium/Firefox/WebKit | BLOCKED | Browser download ECONNRESET; no real-browser result claimed |
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

## Published 0.11.0 parity supplement (2026-11-23)

[Russian evidence and reproduction](NATIVE_012_STABLE011_PARITY.ru.md):
exact release tag c9cde75..., 297 Git objects verified; 898 comparisons,
666 accepted + 232 rejected, no mismatch by limited criteria; 7
published-stable site/WebApp build comparisons; generated Kotlin/JVM
execution PASS with Gradle/Kotlin. Web Node and jsdom tests PASS but
real browser execution and Android APK remain blocked.


### Android APK build addendum (23 Nov 2026)

Android SDK 35 Build Tools/Platform retained on VDS. A real generated
`app-debug.apk` was built and independently inspected with aapt,
apksigner and ZIP CRC verification. The first physical phone smoke is
pending. See [reproduction](NATIVE_012_ANDROID_APK_SMOKE.ru.md).
