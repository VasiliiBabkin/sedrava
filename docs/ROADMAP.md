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
| **0.11** | Extended Web UI and responsive website generation | **Draft PR #22**, not in released CLI |
| **0.12+** | Device capabilities, module/reuse architecture, editors and desktop | Proposed, not committed |
| **1.0** | Versioned specification, compatible storage and support policy | Long-term goal |

Version numbers are planning milestones, **not release dates**. / Номера — ориентиры, а не сроки.

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

## Web UI 0.11 — Slice A / Срез A

Implemented experimentally in the feature branch: `build site`, 13 static primitives, typed styles, responsive HTML/CSS and checked local assets. Реализовано экспериментально в ветке: генерация сайтов, 13 статических компонентов, типизированные стили, адаптивность и проверка ресурсов. This does not announce a 0.11 release or change the production site. Это не выпуск 0.11 и не замена рабочего сайта.

[English reference](WEB_UI_011.en.md) · [Русская справка](WEB_UI_011.ru.md). Next: semantic navigation/footer, badges/callouts, code blocks and documentation navigation; interactive forms/tabs/dialogs require later contracts and tests. Далее: семантическая навигация/footer, badge/callout, code block; интерактивные компоненты требуют следующих контрактов и тестов.
