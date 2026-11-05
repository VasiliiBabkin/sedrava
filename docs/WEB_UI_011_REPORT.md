# Web UI 0.11 Slice A — implementation evidence / Результаты

Experimental implementation in PR [#22](https://github.com/VasiliiBabkin/sedrava/pull/22), branch `feature/web-ui-011-slice-a`. Not a published 0.11 release. No production-site repository or deployment changes. Исходники экспериментальны; рабочий сайт и его репозиторий не изменены.

## Implemented / Реализовано

- `sedrava build site examples/web_ui_011_landing.sdr --output build/site`, with shared frontend dispatch, source validation, text literals and spans; separate typed presentation AST.
- Page plus 12 component primitives, registry-driven nesting/properties, theme tokens, named styles, responsive overrides and strict semantic diagnostics. No language of arbitrary HTML/CSS/JavaScript.
- Multi-page portable HTML/CSS, dark amethyst/gold defaults, adaptive grids, focus/skip navigation, reduced motion and escaped content. Static buttons are honest navigation anchors.
- Checked links and local assets; reject UTF-16 SVG/entity declarations before XML parsing and bound reads even if an asset grows during the build; bounded safe SVG, hash-named images, restrictive CSP. Deterministic manifests; validation/staging and protected rebuild/rollback.
- Working two-page example including local illustration; RU/EN references and source/wheel/sdist inclusion. Existing application examples remain in their original regression suites; sites have dedicated tests.

## Local evidence / Локальные проверки

- Python 3.12: **183 tests passed**, including **18 new site tests**. The legacy candidate packager now selects app documents through the shared frontend rather than feeding static sites into the app parser, with a regression test for mixed examples. Node differential application traces remain enabled; no action test is applied to a static site.
- Existing application Chromium suite: **26 tests passed**.
- Site Chromium suite: **7 tests passed**. Both pages photographed at 360/768/1440, no horizontal overflow, actual keyboard navigation and Back/Forward, visible focus, reduced motion, text contrast, long Unicode text, escaped hostile markup, no script/page errors or HTTP failures. Screenshots inspected visually, including mobile rendering.
- File generation tests cover determinism, typed-property/style errors, unsafe URLs/SVG, symlinks and oversized assets, unknown/edited output protection, and rollback after an injected replacement failure.

CI and artifact evidence is bound to the actual checkout SHA by workflows, not a manually predicted hash: `sedrava-web-ui-011/site-evidence/BUILD.json` contains the Git SHA, run URL and SHA-256 inventory; `toolchain.json` records actual Chromium/Playwright versions. The same artifact contains `site/` plus screenshots, accessibility snapshot and browser traces. Python, package, application browser and Android workflows remain enabled. The RC kit collector is scoped to release branches/manual runs; it must not reassemble a previously published RC from a UI feature branch. This does not disable any regression job.

## Limits / Ограничения

Only static presentation is implemented; no state/action bindings, forms, reusable author components or site-to-Android. Remote HTTPS images are not fetched or checked; offline availability requires local assets. Raster signature checks are not full decoding. Custom theme contrast requires author verification. Browser checks do not establish full WCAG conformance or physical screen-reader/device acceptance. Directory replacement protects ordinary validation/filesystem failures, not power loss or concurrent writers. Output directories are generated-only.

Android remains an application target; no Kotlin UI was introduced for sites. Local Android emulator/physical-device checks are unavailable (no KVM/device); applicable existing Android CI supplies JVM/APK/Lint/emulator regression evidence, and only its actual final results may be claimed. Physical-device testing is not claimed.

Next catalog candidates: semantic navbar/footer, badge/callout, code block and documentation navigation; later accessible forms, accordion, tabs, dialog. These remain planned.

[English reference](WEB_UI_011.en.md) · [Русская справка](WEB_UI_011.ru.md). Final commit/check/artifact links are maintained in PR #22; each artifact receipt provides immutable build identity without a self-referential source commit field.
