# Sedrava WebApp 0.11 — B1 Scalar Vertical Slice

> Historical slice scope / исторический срез. Current integration adds routes, composition, typed HTTP, custom assets and domain queries. See [English guide](011_WEB_PLATFORM.en.md), [русское руководство](011_WEB_PLATFORM.ru.md) and [actual status](011_IMPLEMENTATION_STATUS.md). Statements below about missing features describe the original slice, not the complete integration branch.


**Status:** experimental branch implementation, not part of the released 0.10 language. This is a limited, stateful Web application mode, distinct from static site mode and the existing 0.10 app mode.

## Quick start

    python -m sedrava_cli check examples/webapp_011_counter.sdr
    python -m sedrava_cli build webapp examples/webapp_011_counter.sdr --output build/webapp
    python -m http.server 8000 --directory build/webapp

Open http://127.0.0.1:8000/. The generated directory contains index.html, external app.js, app.css, and a checked sedrava-webapp.json manifest. No framework or mandatory server-side runtime.

## Declarative source example

    webapp "My WebApp"
    state count = 0
    state caption = "Ready"
    state show_caption = true
    persist count
    persist caption
    persist show_caption
    derive doubled = count * 2
    action add: count = count + 1
    view main:
        container max 960:
            column gap 16:
                heading "A stateful app"
                value count label "Count"
                value doubled label "Twice"
                button "Add" action add
                input count label "Edit the count"
                input caption label "Caption"
                checkbox show_caption label "Show caption"
                when show_caption:
                    paragraph "Caption appears below"
                    value caption label "Caption"

Scalar state/action/derive/rule/persistence is type-checked by the same Sedrava 0.10 core. The runtime is extracted from the existing Web backend. No duplicate action interpreter is introduced.

## UI catalog and validation

Layouts: container, row, column, grid, card, callout.
Static elements: heading, paragraph, code, spacer, divider.
Dynamic: value key with optional label; input key label "Text"; checkbox bool_key label "Text"; when bool_key: with children; button "Text" action action_name.

Bindings to derived states are read-only. Text inputs enforce the 1024 Unicode-scalar limit; number inputs validate signed int32 and any declared rules. Rejected drafts do not mutate accepted state and block action buttons until corrected or focus leaves the editor. Checkbox state and conditional visibility follow committed domain state.

Each document requires one h1. User-supplied content is written as escaped HTML or DOM text, never as executable HTML. No arbitrary JS or event-handler attributes. The generated Content-Security-Policy allows only local external scripts and CSS, and disallows network requests. Existing invalid local storage is never silently overwritten.

## Compatibility and omissions

The explicit top-level webapp document and build webapp target do not reinterpret existing app, build web, build android, site, or build site sources.

Supported on the stacked experimental collections branch: typed 0.10 records, bounded lists, selectable row UI and CRUD via existing named actions. See [collections WebApp guide](WEBAPP_011_COLLECTIONS.md).

Still not supported: navigation and history, HTTP APIs, live server data, multi-page views, module imports, custom scripts, arbitrary expressions inside UI attribute values, multi-user data, or Android output for webapp.

Next: full navigation and editable record-bound UI, followed by typed HTTP from API0. Each requires independent acceptance tests.

## Evidence

Unit tests: python -m unittest discover -s tests -p 'test_webapp*.py' -v

Browser tests: python scripts/test_webapp_browser.py and python scripts/test_webapp_collections_browser.py with Playwright and Chromium.

Required independent browser acceptance: actual rendering at 360/768/1440 widths, persistence across reload/new page, rejected actions, invalid input, conditional display, XSS regression, corrupt saved data, CSP and keyboard use.

Managed build directories are hash-verified, staged before replacement, and refuse to overwrite unmanaged or modified content.
