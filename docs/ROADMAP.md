# Sedrava — Roadmap / Дорожная карта

**Released / Опубликовано:** [Sedrava 0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) and [PyPI](https://pypi.org/project/sedrava/0.10.0/), 31 October 2026.
**Status:** an experimental public release, not a 1.0 compatibility commitment or a production certification. Final 0.10 Android physical-device acceptance is still not documented.
**In development:** [Web UI 0.11](https://github.com/VasiliiBabkin/sedrava/pull/22) is a draft PR, not released. Its experimental `build site` command is separate from the Astro/Starlight documentation site.

## Vision / Видение

Describe the application; get the application. / Опиши приложение — получи приложение. State, actions, invariants, tests and UI are described without copying platform boilerplate. Python and generated Web/Android semantics are tested against bounded scenarios; no universal equivalence is claimed.

## Milestones / Этапы

| Version | Scope / Направление | Status / Статус |
| --- | --- | --- |
| **0.9** | Checked integers, actions, rules, basic Web/Android | Historical GitHub alpha |
| **0.10** | Unicode text, records, bounded lists, multi-screen navigation | **Released** on GitHub and PyPI |
| **0.11** | Extended Web UI, responsive sites, experimental read-only HTTP API0 and declarative data presentation | **Draft PRs #22 and #31**, not in released CLI |
| **0.12+** | Module imports and reuse, library SDK, versioned packages; device capabilities, editors and desktop | Proposed, not committed |
| **1.0** | Versioned specification, compatible storage and support policy | Long-term goal |

Version numbers are planning milestones, **not release dates**. / Номера — ориентиры, а не сроки.

## Planned sequence after HTTP API0 / Порядок следующих работ

1. **Finish 0.11 Web HTTP API0** ([draft PR #31](https://github.com/VasiliiBabkin/sedrava/pull/31)): bind validated read-only JSON to explicitly declared UI fields and components; handle loading, empty results, errors and retry; preserve isolation from local persistent state. Keep the initial scope Web-only and GET-only.
2. **Build a representative one-file Web demo** with a remote JSON collection, cards, status handling and no handwritten JavaScript. Document browser CORS constraints and reproducible Chromium tests.
3. **Stabilize 0.11**: review security and resource limits, validate installed wheel/sdist, maintain regression coverage, align docs with the separately maintained `sedrava-site`. Release only after explicit approval and evidence.
4. **Design a typed module/import system**: namespaces, deterministic dependency resolution, platform capability declarations, compatibility checks and diagnostics. A possible `use` keyword is only a proposal, not current language syntax.
5. **Create a library extension SDK** that allows independently developed reusable components without changing the compiler for each feature; define sandbox/security and target-runtime contracts.
6. **Add a versioned package manager** with lockfile, integrity verification and reproducible offline-capable builds, followed by official Web/Android component libraries and third-party packages. Do not assume arbitrary Python/JavaScript libraries are portable.
7. **Benchmark real utility** against a conventional TypeScript/Web implementation and a native Android baseline where applicable: measure end-to-end time, handwritten source size, defects, and change-request turnaround. No speedup factor is claimed before reproducible measurement.

These are **ordered planning goals, not implemented features or guaranteed version commitments**. Do not expand 0.11 API0 into POST, authentication or Android networking before its Web contract is validated.

## Principles / Принципы

- Predictable, atomic state transitions with typed values and explicit invariants.
- Offline-first where practical; safe resource bounds.
- Comparable semantics across target runtimes with transparent platform-specific limitations.
- Source builds, test evidence and documentation before release.
- Separate experiments, historical records and published features.

## 0.10 release evidence / Проверки 0.10

Release tag `v0.10.0` resolves to commit `688a320025a0d38235eb90c780362ec26b0708e2`. The [release workflow](https://github.com/VasiliiBabkin/sedrava/actions/runs/41237159326) published wheel/sdist on PyPI with digital attestations. Main CI, Android build and text conformance succeeded. [RC1](RC_010_REPORT.md), [RC2](RC2_010_REPORT.md) and [stability audit](STABILITY_AUDIT_010.md) reports describe historical states and are retained unchanged.

**Still open:** [final 0.10 physical-device acceptance](PHYSICAL_DEVICE_010.md). Do not imply all Android devices are supported or that the source contains automatic migrations, encrypted persistence or security certification. See [limitations](KNOWN_LIMITATIONS.md) and [compatibility](COMPATIBILITY_010.md).

[Documentation website repository](https://github.com/VasiliiBabkin/sedrava-site) · [issues](https://github.com/VasiliiBabkin/sedrava/issues).
