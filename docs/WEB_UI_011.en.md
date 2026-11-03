# Web UI 0.11 — experimental Slice A

Implemented in the `feature/web-ui-011-slice-a` source branch, not a published 0.11 release. The canonical package version remains 0.10.0rc2; an already published RC2 package does **not** contain this development feature. Existing application syntax and `build web` / `build android` retain their meaning. [Русская версия](WEB_UI_011.ru.md).

## Build and preview

From a checkout of this branch, install `python -m pip install .`, then:

```sh
sedrava check examples/web_ui_011_landing.sdr
sedrava build site examples/web_ui_011_landing.sdr --output build/site
python -m http.server 8000 --directory build/site
```

Open `http://localhost:8000/`. The output includes HTML for each page, `site.css`, a favicon, hashed local images and `sedrava-site.json` with file checksums. It needs no JavaScript, network fonts, framework or build-time Node dependency. The bundled example has two pages and works independently of the production Sedrava site. No deployment is performed.

`check` validates the complete site, including local images and cross-page links, without writing outputs. `run`, `test`, `build web` and `build android` reject site documents explicitly; sites have no application state or action tests. Use the separate browser checks described below.

## Syntax

```text
site "My site"
theme:
    accent "#B59BFF"
    gold "#F3D087"
style feature:
    padding 28
    radius 24
    shadow soft
page home at "/":
    title "My site — welcome"
    description "A small independent site"
    lang "en"
    container max 1160 padding 24 md-padding 40:
        column gap 32:
            heading "Describe it. Make it real."
            paragraph "One source. No hand-written HTML." variant lead
            row gap 16 wrap:
                button "See features" to "#features"
                link "Source" to "https://github.com/VasiliiBabkin/sedrava" target blank
            grid id features columns 3 md-columns 2 gap 20:
                card style feature:
                    heading "Shared foundations" level 2
                    paragraph "Typed properties and safe defaults."
```

Four spaces per level; tabs are errors. Container components require `:` and children; leaves cannot have children. Parameters are whitespace-separated `name value` pairs, with a positional quoted string where shown. `wrap` is also a bare true flag; `wrap false` disables it. Strings use the existing Sedrava text decoder (`\n`, `\r`, `\t`, `\"`, `\\`), at most 1024 Unicode scalars per literal. Source limit: 100,000 characters; nesting limit: 32. Diagnostics contain source line and column. Full-line `#` comments are supported; inline comments are not.

At least one root page `/` is required. Other routes use `/components/` form, with ASCII safe segments and a trailing slash. Names and paths must be unique. `title` is required; `description` and `lang` are optional (default `en`). Each page must have exactly one h1. If `level` is omitted, the first heading becomes h1 and subsequent headings h2. Explicit levels 1–6 cannot skip a level. IDs are unique within a page; `content` is reserved for the generated keyboard skip target. Internal routes and fragments must exist.

## Component catalog

| Component | Content and parameters | Output |
| --- | --- | --- |
| `page` | Named route, title, description, lang, children | HTML document and main landmark |
| `container` | Children; `max` defaults to 1160 | Centered bounded block |
| `row` | Children; `gap` 16, `wrap` true | Wrapping flex row |
| `column` | Children; `gap` 16 | Flex column |
| `grid` | Children; `columns` 1–12 (default 3), `gap` 20 | Responsive grid |
| `heading "text"` | `level`, variant default/display | h1–h6 |
| `paragraph "text"` | variant default/lead/eyebrow/muted/brand | Paragraph |
| `link "text"` | Required `to`, target self/blank, variant default/quiet | Anchor |
| `button "text"` | Required `to`, target self/blank, variant primary/secondary/ghost | Button-styled **anchor** |
| `card` | Children; padding 28, radius 24; variant default/highlight/muted | Article |
| `image "assets/picture.svg"` | Required `alt` (empty for decorative image) | Lazy decoded image |
| `spacer` | `size` 0–4096 (default 24) | Hidden decorative space |
| `divider` | Shared visual properties | Horizontal rule |

All component nodes share `id`, `label` (ARIA label), `style`, `gap`, `padding`, `margin`, `width`, `max`, `height`, `size` (font size), `radius`, `color`, `background`, `align`, `justify`, `text-align`, `weight`, `shadow`. These do not apply to page metadata. Sizes are integer CSS pixels: gap/padding/margin/height 0–4096, width/max 1–4096, font size 10–160, radius 0–256. Width also accepts `auto` or `full`. Width and padding are bounded to fit their parent; padding caps at 10% and margin at 5%. `align`: start/center/end/stretch; `justify`: start/center/end/between/around/evenly; `text-align`: start/center/end/left/right; `weight`: normal/medium/semibold/bold; `shadow`: none/soft/glow. Layout properties affect elements according to their native CSS layout, e.g. `align` is useful on flex/grid containers.

Theme tokens: background, surface, foreground, accent, gold, muted, border. Theme definitions accept opaque quoted `#RGB` or `#RRGGBB`; component colors accept these or an unquoted token. No arbitrary CSS values are accepted. Named styles contain one property per line; they cannot set id, label or another style. Component-specific values are checked against the component using the style.

Precedence: built-in defaults → named style → inline properties. Prefix visual/layout properties with `sm-` (640px), `md-` (768px), `lg-` (1024px) for minimum-width overrides. Responsive overrides apply after base values. Semantic properties (text, to, src, alt, level, id, label, style, variant) are not responsive. A grid defaults to one column below 768px, min(2, columns) from 768px, and the requested columns from 1024px. Explicit breakpoint columns replace that automatic value. A larger breakpoint replaces an earlier breakpoint for the same property.

## Safety and build contract

Text and attributes are escaped. Links allow checked HTTP/HTTPS, mailto (without headers), tel, declared site routes and anchors. Credentials, protocol-relative URLs, traversal and unsafe schemes are rejected. New-tab anchors receive `noopener noreferrer`. Remote images require HTTPS and are not downloaded or verified at build time. They compromise offline availability; the reference example uses only local assets.

Local image paths resolve relative to the `.sdr` file, not the current working directory. Symlinks and paths outside that directory are rejected. Allowed formats: PNG, JPEG, WebP (signature checks, not full image decoding), and a restricted UTF-8 SVG subset (basic shapes/text; no scripts, styles, external references, entities or animation). Maximum 2 MiB per asset and 16 MiB for unique assets. Output has a restrictive CSP, no inline script and no user-authored CSS. Custom colors remain the author's contrast responsibility.

Builds are byte-deterministic for the same source, asset bytes and compiler. Output manifests contain no timestamp or absolute path. A new/empty directory is accepted; rebuilding requires the previous exact, unmodified generated file inventory. Unknown or edited output files are protected by refusing the build. Validation and staging precede replacement; replacement failures restore the previous directory. This is an ordinary filesystem failure guarantee, not a power-loss or concurrent-publisher protocol. Do not use the output directory for user files. Source and asset/output collisions are rejected.

## Architecture and verification

`sedrava_frontend.parse_document` dispatches by the first declaration. Both modes use shared source bounds/line validation, text decoding and source spans. Sites have a typed presentation AST because application action widgets cannot represent static layout. `sedrava_site.COMPONENTS` registers tags, properties, child policy and variants; adding an ordinary primitive does not require another parser or renderer branch. `site_codegen` owns CSS mapping, safe assets and transactional output. Advanced widgets may still require semantics and tests.

The natural syntax from PR #21 is retained. The contract now explicitly defines `style`, page metadata, breakpoints, strict internal links, heading rules and bounded assets. `button` means a navigation anchor with a required target; inert buttons or arbitrary click handlers would promise unimplemented behavior. `spacer` and `divider` complete the requested foundation. There is no second expression/action language.

Run `python -m unittest discover -s tests -v` and `python scripts/test_site_browser.py` (requires Playwright 1.62.0 and Chromium). The latter records full-page screenshots at 360/768/1440, traces, focus, semantics and computed default text contrast under `build/site-evidence`. It tests actual navigation, Back/Forward, keyboard, reduced motion, layout overrides, Unicode and escaped markup, with no page errors or failed HTTP responses. These checks are not a full WCAG certification or screen-reader/device audit. The dedicated read-only GitHub workflow uploads `sedrava-web-ui-011` with the site and actual SHA/hash receipt; it never deploys.

Next components are **planned**, not implemented: semantic navbar/footer, badge/callout, code block, documentation navigation; later accessible forms, accordion, tabs and dialog. State bindings, reusable author components, arbitrary JS/CSS, site-to-Android and production-site replacement are outside Slice A.

## Slice B additions (development branch only)

The additive Slice B branch provides `navbar`, `footer`, `callout`, and
`code` components. This is **not** a published language release.

| Component | Authoring syntax | Semantics |
| --- | --- | --- |
| `navbar` | `navbar label "Primary navigation":` with child links/rows | One top-level `<nav>`, before the main landmark |
| `footer` | `footer:` with children | One top-level `<footer>`, after the main landmark |
| `callout` | `callout variant warning:` with children | `<aside>` notice, variants default/info/warning |
| `code` | `code "state x = 0\npersist x"` | Escaped `<pre><code>` with local horizontal scrolling |

`navbar` and `footer` are optional. When used, the navbar must be the first
top-level element and footer the last. Neither is allowed inside a nested
container. This keeps navigation and footer landmarks outside the generated
`<main>`. All other nested content remains in `<main>`. Code is static text
without evaluation or HTML injection. The existing site-mode text-literal
length limit applies. The original Web/Android application modes are unchanged.
