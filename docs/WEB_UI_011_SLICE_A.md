# Web UI 0.11 — Slice A implementation contract

**Status: implemented experimental source-branch Slice A; not a published 0.11 release.** This document complements [the proposal](WEB_UI_011_PROPOSAL.md) in PR #21. Published 0.10.0rc2 does not include this feature. See the normative [English](WEB_UI_011.en.md) / [Russian](WEB_UI_011.ru.md) references and the [implementation report](WEB_UI_011_REPORT.md).

## Goal

A single `.sdr` source generates a responsive, accessible, static landing page without hand-written HTML/CSS/JS. The first target is **not** a replacement for the existing interactive `sedrava build web` behavior. Prefer an explicit `sedrava build site` target, implemented alongside the application targets. Existing 0.9/0.10 programs must continue to parse and build unchanged.

## Authoring syntax

```text
site "Sedrava"
theme:
    background "#10101A"
    surface "#1C1A2B"
    foreground "#F7F4FF"
    accent "#B59BFF"

page home at "/":
    title "Sedrava — Describe the app. Get the app."
    description "Declarative language for Web and Android"
    container max 1120:
        column gap 32:
            heading "Build applications by describing them"
            paragraph "State, actions and rules — one source."
            row gap 16 wrap:
                link "Get started" to "https://github.com/VasiliiBabkin/sedrava/tree/main/docs"
                link "GitHub" to "https://github.com/VasiliiBabkin/sedrava"
            grid columns 3 gap 20:
                card:
                    heading "State"
                    paragraph "Describe your data."
                card:
                    heading "Rules"
                    paragraph "Protect valid state."
                card:
                    heading "Build"
                    paragraph "Generate the application."
```

The implementation uses one indentation-based grammar, typed property validation and a registry of components. Strict internal routes must resolve to a declared page. `button` is a navigation anchor with required `to`; spacer and divider are also implemented. See the references for style precedence, breakpoints and resource limits.

## Acceptance requirements

1. Static HTML5 and CSS; semantic landmarks and a single h1; no JavaScript for a static page.
2. Escaped text and attribute values; reject unsafe URL schemes and invalid colors; never interpolate user text into CSS or script.
3. Mobile-first layout with no horizontal scrolling at 360/768/1440px; reduced-motion and visible keyboard focus.
4. Theme tokens with accessible defaults; named component styles with documented override precedence.
5. Components in the first vertical slice: page, container, column, row, grid, heading, paragraph, link, button-link, card, image. Support nested composition.
6. Build determinism, invalid syntax diagnostics with line numbers, unit tests, browser screenshots and accessibility checks.
7. A dedicated example and RU/EN reference documentation; site content must distinguish *planned* from *implemented*.
8. Preserve the current `sedrava build web` and `sedrava build android` behavior; no silent grammar changes.
9. No production site deployment, merge to main, GitHub release, or PyPI publication without separate authorization.

## Growth path

Build primitives first, then a rich catalog: navbar, sidebar, footer, badges, callouts, tabs, accordions, forms, dialogs, responsive tables, code blocks, documentation navigation, transitions, and reusable components. Keep a shared property model, accessible defaults and clear Web-only support boundaries. The eventual goal is to build the entire Sedrava documentation site using Sedrava.
