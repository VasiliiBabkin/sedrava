# Sedrava Web UI 0.11 — design proposal / Проект архитектуры

**Status:** proposal only. No new grammar, renderer, or component is implemented by this document. The published 0.10.0rc2 contract remains unchanged.

## Product goal / Цель

Describe a polished, responsive, accessible website using concise `.sdr` source. The first acceptance project is a **parallel rebuild** of the Sedrava website. Keep the current Astro website and deployment intact until feature parity and explicit approval for switching.

**Simple by default; flexible by composition.** A large standard component library is welcome. Complexity belongs in the renderer and reusable components, not in the everyday authoring syntax. Avoid requiring raw HTML/CSS/JS for ordinary layouts. Offer explicit advanced escape hatches where platform-specific behavior is genuinely necessary.

## Proposed author experience (illustrative, NOT valid 0.10 syntax)

```text
site "Sedrava"
theme:
    accent "#9270E8"
    surface "#11111A"
    text "#F5F3FA"

page home at "/":
    title "Sedrava — build apps by describing them"
    description "A declarative language for Web and Android"
    layout column gap 24 padding 32:
        hero:
            heading "Describe the app. Get the app."
            paragraph "One source, useful applications."
            button "Get started" link "/docs/"
        grid columns 3 responsive:
            card:
                heading "State"
                paragraph "Describe what matters."
            card:
                heading "Rules"
                paragraph "Protect valid state."
            card:
                heading "Build"
                paragraph "Generate your target."
```

This sample is a discussion aid. Names, indentation, style syntax, and compatibility must be specified and reviewed before implementation.

## Component architecture / Компоненты

Build a **small set of orthogonal primitives** and a **large catalog of composed components**, all following one property and event model.

1. **Structure:** page, section, container, row, column, grid, stack, spacer, divider, tabs, accordion.
2. **Typography and media:** heading, paragraph, rich text, code, image, icon, video, figure.
3. **Navigation:** link, navbar, menu, breadcrumbs, pagination, sidebar, footer.
4. **Content:** card, badge, callout, list, table, timeline, stats, hero, feature section.
5. **Interaction:** button, input, textarea, select, checkbox, radio, switch, dialog, drawer, tooltip, toast.
6. **Site composition:** reusable component, slots, layout, page metadata, assets, route, locale.
7. **Advanced web:** theme tokens, breakpoints, state variants, animation and transitions, custom CSS class or scoped CSS escape hatch, carefully bounded external integrations.

Component names above are **candidate API**, not promises. Components should be documented with examples, defaults, accessibility requirements, Web/Android applicability and fallback behavior. A component catalog may grow without making the core grammar more complicated.

## Non-negotiable semantics / Требования

- **Predictability:** explicit types; no implicit platform-specific effects; deterministic output for identical inputs.
- **Accessibility:** semantic HTML, keyboard navigation, focus, labels, contrast and reduced-motion support.
- **Responsive:** mobile-first defaults, named breakpoints, flexible sizing and layouts without manual CSS for common cases.
- **Styling:** tokens, themes, variants and local overrides with documented precedence; dark/light modes.
- **Composition:** components nest, accept parameters and slots; shared layouts and reusable definitions avoid duplication.
- **Static-first:** generate HTML/CSS for content and SEO; ship JavaScript only for interactions that need it.
- **Safety:** escaped content, safe URLs, explicit trusted-content boundary, no arbitrary script execution in ordinary text widgets.
- **Compatibility:** no silent change to 0.9/0.10 syntax or existing Web/Android behavior; new features gated and tested.
- **Portability:** Web-specific components are explicitly marked; Android generator gives clear diagnostics rather than pretending to support them.

## Vertical slices / Порядок разработки

**Slice A — visual landing page.** Implement only the primitives needed for a responsive Sedrava landing page: theme, typography, section, container, column, row, grid, card, button/link, image, breakpoints. Produce static HTML/CSS with no unnecessary JS. Compare mobile, tablet and desktop screenshots. Add accessibility and security tests.

**Slice B — documentation website.** Add routes, metadata, shared layouts, reusable components, code blocks, navigation, search integration and assets. Generate a parallel Sedrava website under a preview path or artifact; do not change production deployment.

**Slice C — rich component library.** Expand to interactive elements and patterns, including focus management, validation and reduced motion. Build a documented gallery with runnable examples and automated browser checks.

**Slice D — site migration gate.** Compare content, links, SEO, accessibility, responsiveness, load behavior and deployment/rollback. Switch production only with owner approval.

## Exit criteria for first implementation / Критерии приёмки

- A real `.sdr` landing page builds into standalone static assets.
- Layout works at 360px, 768px and 1440px; no unintended horizontal overflow.
- Navigation and keyboard focus work; reduced-motion preference is respected.
- Output is deterministic; HTML content and attributes are safely escaped.
- Existing 0.9 and 0.10 regression suites stay green.
- Both RU and EN documentation include a component reference and honest support matrix.
- No automatic production website switch, stable release or PyPI publication.

## Follow-on goals / Дальше

After practical website authoring: add APIs for a Sedrava-based code editor (syntax highlighting, diagnostics, file operations and preview), potentially embedding a proven editor component. Self-hosting the compiler is a **later optional research goal**, not a prerequisite for website or editor work.

## Documentation and website synchronization

The source repository is authoritative for language syntax and implementation status. The separate `sedrava-site` repository should mirror **only implemented, tested** features. A design proposal must never be described on the public site as a shipped capability.
