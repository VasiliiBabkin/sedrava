> Historical reference; not a current release or installation guide. [Current Rust documentation](README.ru.md).

# First public Alpha engineering audit / Инженерный аудит

Date: 2026-10-29. Baseline: [`08fd020`](https://github.com/VasiliiBabkin/sedrava/commit/08fd020dfd111238aea619c9e0b6684f2be8b25e), actual `main` at checkout. Work branch: `alpha/0.9.0a1-engineering`. Candidate version remains **0.9.0a1** (unreleased). No PyPI upload, release tag or public release is implied by this document.

## Audit coverage and architecture

Reviewed both parsers, CLI, shared AST/evaluator, Web/Android generators, packaging, all existing tests/workflows, README/roadmap/0.9 status, reference app and Android acceptance findings, plus recent PRs [#6](https://github.com/VasiliiBabkin/sedrava/pull/6), [#7](https://github.com/VasiliiBabkin/sedrava/pull/7), [#8](https://github.com/VasiliiBabkin/sedrava/pull/8).

The working core remains in place. `sedrava_core.py` is the 0.9 typed AST/interpreter; Web and `android_codegen_v03.py` consume it. `sedrava.py` and `android_codegen.py` retain historical subset compatibility; the latter supplies the compatible Gradle scaffold using a fixed harmless source. No application semantics pass through the old parser in the current CLI. Retaining these modules avoids breaking existing users/tests; they are documented as compatibility tools, not the normative 0.9 API. No architecture rewrite or 0.10 feature expansion was needed.

Actual features: int32/bool state, checked +/−/*, pure derives, typed sequential actions/if/else, final invariants, embedded independent tests, one screen, numeric input, static text/value/button/conditional text, accepted-state persistence in generated UIs. Strings as state, clocks, lists, toggles, cards, navigation and editor self-hosting remain future work. Static labels are not string fields. See [normative reference](LANGUAGE_0_9.md).

## Defects found and corrected

| Finding | Correction and regression evidence |
| --- | --- |
| `run` absent from CLI | Deterministic JSON interpreter with action sequence, failure codes and paths-with-spaces test |
| Minimum int32 literal rejected while oversized literals survived in unused expressions | Normalize signed minimum and validate every literal; boundary regression tests |
| Invalid initial derives could compile and crash UI startup | Validate all initial derives, even without rules |
| Python evaluated unused derives differently from generated runtimes | Check all derives after each assignment and before final/input/restored acceptance; 720-step Python/Node suite |
| Web/Android action arithmetic could escape callbacks | Atomic rejection and visible error; Chromium verifies no unhandled exception or partial update |
| Saved values restored without invariant validation; Android wrong-type prefs could throw | Per-field fallback plus whole-snapshot semantic validation; browser corruption tests and JVM validation tests |
| Kotlin `$` labels interpolated; names collided with generated locals | Escape dollar signs, prefix all generated user variables; regression tests |
| App names could terminate an HTML script | Script-safe JSON encoding; real-browser injection regression |
| JS prototype-like derived identifiers failed | Null-prototype derived maps and computed action keys; browser boundary test |
| Duplicate screens, indentation tabs, derive expansion and deep blocks insufficiently guarded | Reject duplicate screens/tabs, bound expansion/nesting and reserve literal/keyword state names |
| Activity recreation discarded accepted transient state | `rememberSaveable`; generation verified, new device rotation check remains unperformed |
| Source archives omitted guides/examples/scripts | Explicit manifest, stronger archive audit and clean-install tests |

## Measured local results

- Baseline: **78 tests passed**.
- Updated Python unit/integration/conformance/example suite: **88 tests passed**, no skips in the local run. Node differential suite includes 720 deterministic steps over 9 UI/boundary programs in addition to prior Workflow/rejection suites.
- Actual Chromium through Playwright: **7 tests passed**. All UI examples launch; input ranges/relational constraints, correction, empty draft, derived overflow, atomic action overflow, persistence/reload, malformed saved data, script injection and prototype/minimum-integer cases covered. Browser traces are emitted under `build/browser`.
- Android: full JDK 17.0.17 (Temurin), Gradle 8.11.1, SDK platform 35, build-tools 35.0.0 installed during this pass. Initial build using the environment's Java 21 JRE failed because `javac` was missing; this is a toolchain issue, not a passed gate. Final APK/JVM/Lint results are recorded below when completed.
- `adb devices`: **no attached devices**. `/dev/kvm`: **absent**. No local emulator, installation, UI instrumentation, logcat/rotation or new physical-device acceptance is claimed.
- Historical manual Android 16 results remain unchanged in [ANDROID_09_ACCEPTANCE.md](ANDROID_09_ACCEPTANCE.md). They refer to a previous binary and are not attributed to these new changes.
- Distribution, clean-checkout and CI final results are recorded below when completed. No claim of exhaustive semantic equivalence or complete transitive CVE coverage.

## Security, dependencies and licenses

No Python runtime dependencies, source `eval`/`exec`, shell execution from application source, telemetry, accounts, advertising or cloud runtime added. Inputs are bounded and typed. Generated source manifests declare no permissions; actual merged permissions must be inspected with SDK tools. No secrets belong in source or local storage. See [security review and audit boundaries](SECURITY.md) and [known limitations](KNOWN_LIMITATIONS.md). Direct Android dependencies are pinned; a complete transitive advisory/SBOM audit and bit-identical APK reproducibility remain unclaimed.

## Release decision

A reviewable PR and reproducible candidate are the objective. A public release is allowed only after the exact final commit passes mandatory CI/package/Web/Android gates. No version change is warranted: this is the first unpublished 0.9 alpha and the fixes repair its intended contract. Newly stricter rejection affects malformed/unsafe candidates, not a published stable language.

For next steps use the [publication checklist](RELEASE_NOTES_0_9_0a1.md), [build guide](BUILD.md) and [0.10 architecture](PLAN_0_10_UI.md). Complete device revalidation remains explicitly separate from successful builds.

## Completed build/package checks

- First local reference APK and Android Lint build: **PASS**, JDK 17/Gradle 8.11.1, 46 tasks executed. A second clean build using the final generator plus JVM tests is also required and recorded in the follow-up results.
- Wheel and sdist: **built successfully**, `twine check` passed, archive/license/metadata audit passed. Clean virtual environment installs `sedrava 0.9.0a1` with no runtime dependency packages.
- Current documentation checker validates 11 guide files and their local links.

The first implementation commit is [`1565170`](https://github.com/VasiliiBabkin/sedrava/commit/15651705cdfc64afb8382affb3dd98b05901b198). Final PR/CI artifact evidence is added after the corresponding run exists; no placeholder URL is evidence of success.

## Final local Android result and first CI feedback

- **PASS:** clean reference build, `assembleDebug`, `lintDebug`, `testDebugUnitTest`; 52 tasks executed, 2 JVM tests, 0 failures/errors/skips. JVM tests execute generated snapshot/input invariant validation, not Compose UI callbacks.
- **PASS:** separate Countdown Android APK build (35 tasks), without modifying generated application code.
- **PASS:** SDK `apksigner verify` (v2 signature), `aapt dump badging`, `aapt dump permissions`. The merged APK has only AndroidX's own `org.sedrava.generated.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION` (signature protection), no Internet/storage/camera/location or other dangerous permission. Lint: 0 errors, 5 `UseKtx` style warnings and 3 informational boxing suggestions.
- **PASS:** separate clean Git worktree at `2323256`: unit/conformance/example suite, documentation links, wheel/sdist build and metadata/archive audit; wheel installation and CLI check/test/run/both targets from outside the source directory, including output paths with spaces. Source-archive installation also checked.
- The first expanded CI run exposed an existing test-only Python 3.10 incompatibility (`tomllib` is standard only from 3.11). Fixed with the test-only `tomli` extra/backport, without raising the supported runtime Python version or skipping the test. CI now disables matrix fail-fast and checks out the exact PR head for alpha/reference gates.
- PR: [#9](https://github.com/VasiliiBabkin/sedrava/pull/9). First CI run: [40890956733](https://github.com/VasiliiBabkin/sedrava/actions/runs/40890956733) (not green; Python 3.10 test import failure). Final passing runs must be used for publication.

## Additional consistency gates

Final source checks also bound total action statements at parse time (so generated runtimes cannot bypass the interpreter step ceiling), enforce uniform widget indentation and reject oversized CLI files before reading them fully. The reference Android workflow enforces an actual APK permission allowlist and produces a release-candidate bundle with wheel, sdist, debug APK, Web examples and SHA-256 checksums, without publishing.
