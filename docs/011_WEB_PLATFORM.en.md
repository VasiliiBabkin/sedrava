# Sedrava 0.11 Web platform integration guide

**Experimental integration preview, not a released 0.11.0.** The package version remains the published 0.10.0 while this branch is reviewed. See [actual status](011_IMPLEMENTATION_STATUS.md). Do not install the published 0.10 wheel expecting these additions. The integration does not operate a production server, authentication service or database.

## Build and preview

From the integration checkout, with Python 3.10 or later:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install .
sedrava check examples/platform_site.sdr
sedrava build site examples/platform_site.sdr --output build/platform/site
sedrava build webapp examples/platform_tasks.sdr --output build/platform/tasks
sedrava build webapp examples/platform_catalog.sdr --output build/platform/catalog
sedrava build webapp examples/platform_crm.sdr --output build/platform/crm
python -m http.server 8000 --directory build/platform
```

Open `/site/`, `/tasks/` or `/crm/`. The catalog client needs an independently provided `/api/products` HTTP endpoint; the ordinary static server returns a visible HTTP error. The acceptance suite supplies a real loopback HTTP fixture, not a production backend. Build output is never edited manually.

`site` creates static HTML per page and local resources, with no JS runtime. `webapp` creates a client application (`index.html`, `app.js`, `app.css` and local assets). Existing `app`, `build web`, `build android`, `check`, `run` and `test` semantics are retained. Presentation modes support check/build; they do not pretend to run in the terminal interpreter.

## Shared syntax and domain logic

Programs use indentation, quoted text, exact types and checked int32 arithmetic. Records have scalar named fields; lists have declared record types and capacities 1–100. IDs are positive, stable and never reused. The following is a complete compiling source:

```sdr
webapp "Counter"
fn incremented(value: int) -> int = value + 1
state count = 0
persist count
derive doubled = count * 2
rule count >= 0
action increment:
    let previous = count
    count = incremented(previous)
view main:
    container max 960 padding 24:
        column gap 16:
            heading "A typed counter"
            value count label "Count"
            value doubled label "Twice"
            button "Increment" action increment
```

Pure `fn name(parameter: int|text|bool|Record, ...) -> Type = expression` declarations precede state. Earlier pure functions may be called; recursion, forward references, mutable captures, host execution and implicit conversions are rejected. Up to 32 functions, 8 parameters each. Calls evaluate arguments exactly once, left to right, even unused arguments; errors abort the enclosing action. Immutable `let` bindings have lexical block scope and cannot shadow state. `a if condition else b` requires a boolean condition and identical branch types and evaluates only the chosen branch. Existing action `if/else`, `require` and final invariants retain atomic rollback. A rejected intermediate checked expression cannot be hidden by a later assignment.

Deterministic operations: `text_length` counts Unicode scalar values; `trim` removes only ASCII space/tab/CR/LF; `lower_ascii` deliberately changes only A–Z; `contains`, `concat` retain checked text limits. `is_date`, `date_days`, `date_add` use valid proleptic Gregorian `YYYY-MM-DD`, years 0001–9999; days are measured from 1970-01-01. Invalid dates and overflow reject. There is no implicit clock, timezone or locale-dependent sort.

### Collection expressions

`filter`, `find`, `any`, `all`, `sort`, `sum` accept a known field literal or pure function. A function's first parameter is the collection's record type; remaining arguments are explicit. `map` requires a function returning a declared record. Examples from tested fixtures:

```sdr
fn matches(task: Task, query: text) -> bool = contains(lower_ascii(task.title), lower_ascii(query))
derive visible_tasks = filter(tasks, matches, search_text)
derive active_count = count(filter(contacts, "active", true))
```

These declarations belong in programs defining the corresponding types/state; see the complete [tasks](../examples/platform_tasks.sdr) and [CRM](../examples/platform_crm.sdr) sources. `find(list,"field",value)` returns the first stable ID or 0; `any/all` return bool (empty all is true). `sum(list,"integer_field")` checks every int32 accumulation. `sort(list,"field")` is stable ascending, Unicode-codepoint order for text. Filter/map/sort preserve IDs, next_id and capacity. Map does not mint identities, even if it changes the record type. No implicit coercion or substring semantics for field predicates. Selectors can instead be typed functions; no arbitrary lambdas are executed by the compiler.

Physical AST expressions are bounded to 256 nodes; expanded expression/function/collection work to 4096. Source, depth, collections, text and snapshot limits from 0.10 remain. A high-capacity query with an expensive selector can fail compilation rather than freeze the browser.

## Modules and UI composition

`import "assets/ui.sdr"` is a compile-time local import. Files must stay under the entry source directory, cannot be symlinks, and may export records, pure functions, styles and components. At most 32 files and depth 16; cycles, duplicate names and excessive expanded source reject. Paths resolve relative to the importing file. Imports have one flat namespace and are not npm/Python package loading. Imported state/actions and native plugins are unsupported. Expanded errors currently use expanded line positions; a complete cross-file source map is a known limitation.

```sdr
component Panel(title: text):
    card:
        column gap 16:
            heading $title level 2
            slot
```

Instantiate inside a page/view with `use Panel title "Overview":` and indented children. Parameters are exact compile-time text/int/bool literals, substituted outside string literals. One explicit slot; recursive templates reject. Component instances lower into the same registry-driven checked UI AST. State bindings inside templates refer to the application's declared state. Runtime component props, named/multiple slots and instance-local state are not implemented.

## UI reference

Static and application layouts share `container`, `row`, `column`, `grid`, `card`, `callout`, `heading`, `paragraph`, `code`, `link`, `image`, `spacer`, `divider`, `navbar`, `footer`. See [static component reference](WEB_UI_011.en.md) for property ranges. Static `button "Label" to "/page/"` is a link; WebApp `button "Label" action action_name` invokes an atomic action. `class "project-class"` supplies checked local CSS hooks. Each page/view requires exactly one level-one heading. Images require meaningful alt text.

Application widgets:

| Source | Meaning |
|---|---|
| `value key label "Name"` | Checked state or derived output |
| `input key label "Name" kind text` | Mutable scalar editor; kinds text/textarea/email/url; default textarea |
| `checkbox key label "Enabled"` | Mutable bool editor |
| `select key label "Mode":` / `option "One" value "one"` | Exact typed choice; no string-to-bool/int coercion |
| `form action save:` / `submit "Save"` | Native submit/Enter with checked domain action |
| `when flag:` | Bool-controlled visibility |
| `dialog id confirm label "Confirmation":` | Native modal dialog with keyboard behavior |
| `open "Open" to confirm` / `close "Cancel" to confirm` | Dialog controls; Escape closes |
| `navigate "Details" to details` / `back "Back"` | Checked route transition/history |
| `list tasks select selected title title status done` | Stable-ID selection, safe rendered record text |
| `table contacts select selected title name fields "name email" label "Contacts"` | Semantic table/caption/selection |
| `each tasks select selected title title:` | Custom typed row template |

Lists/each/tables accept `search search_text`, `sort title`, `where done equals filter_done active filter_enabled`, `empty "No matching tasks"` and `label`. Search is presentation filtering; domain `filter` is available for reusable logic. IDs never become indices. Within `each`, arbitrary layouts, `field title label "Task"`, `row-when done:`, `pick "Select"` and named action buttons are supported. Fields use safe text nodes. Row action selection and action run on a private candidate and commit together. Nested row scopes, inline row editors and capability controls in templates are explicitly rejected.

Invalid draft editors block action/form/navigation/request submission until corrected. Accepted state remains valid. Draft text is not a persistence promise. Forms do not create a server validation boundary. Modal close does not roll back already accepted edits; use an explicit draft state/action if needed. There is no custom tab/sidebar primitive yet; ordinary layouts and route controls compose these patterns.

## Routes, lifecycle and storage

`view main:` is the unguarded initial `/` route. Additional declarations can use `view details at "/tasks/:selected" when chosen:` with an existing mutable int parameter and bool guard. Targets and duplicate route/view names are checked. URLs use hashes (`#/tasks/1`) so direct links and reload work on an ordinary static host. Back/Forward are browser history, not a second invented router stack. Navigation depth is bounded to 32. Transition focuses the new h1; ordinary keyboard controls retain visible focus.

Route parameters are edited on a private typed candidate before evaluating the guard. Unknown/missing/deleted records display an error or return to main without corrupting state. Deleting the selected record closes the now-inactive view/dialog. Service requests are aborted when their view is left and on pagehide; sequence tokens suppress stale completion. No promise of arbitrary route string parameters or path-rewrite SPA routing is made.

`persist name` uses the existing exact schema fingerprint and atomic restore validation. Corrupt/incompatible originals are retained and subsequent saves blocked, rather than replacing them with defaults. No automatic migration. A schema/application-title/served-path change can affect compatibility or storage identity; preserve projects and export storage independently before changes. Browser storage is local per origin and path, is not encrypted, and may be removed by the user/browser. Offline means accepted local state and optional public GET cache; there is no service worker ensuring a cold offline page download.

## Typed HTTP API

Full [catalog source](../examples/platform_catalog.sdr) declares all five methods. A service block is root-level:

```sdr
service catalog:
    origin self
    path "/api/products"
    method GET
    auto true
    cache true
    timeout 1000
    max-bytes 16384
    max-items 100
    response many:
        id int32
        title text
        available bool
```

`origin self` is an explicit same-origin capability; otherwise use a bare public HTTPS origin. Integer `:state` path parameters are checked. GET auto-load/cache are optional. POST/PUT/PATCH require a `body DeclaredRecord(field=state, ...)` matching scalar field types. DELETE has no body. `response one/many` is an exact record schema with int32/text/bool fields. `request "Refresh" service catalog`, `cancel "Cancel" service catalog`, `remote catalog title title search search_text label "Catalog"` connect UI. Remote states are explicit idle/loading/success/error with last accepted data retained; they are not unchecked writes into domain state. Empty 204 is accepted for a many response only.

The connector checks HTTP status, JSON shape, duplicate keys, nesting, UTF-8, text/int32/item/byte bounds. Timeout 100–30000ms; WebApp response max 200000 bytes, default 65536. Requests use `credentials: omit`, reject redirects and respect CORS/CSP. No API-key/custom-secret-header mechanism, CORS bypass, authentication or arbitrary JS source. Optional GET cache is public data only; an accepted cache hit is shown until explicit refresh. Bad cached data is retained and not overwritten. Cancellation/retry are explicit; a timed-out mutation may already have happened at the server, so there is no distributed rollback guarantee.

## Styling, resources and static SEO

Project `theme:` supplies tokens background/surface/foreground/accent/gold/muted/border. Named `style panel:` holds reusable checked spacing/radius/shadow properties; use `style panel`. WebApp named `theme light:`/`theme dark:` with `theme-state theme_mode` uses mutable persisted text state; allowed palette names become a core invariant. Unsupported palette edits reject, including restore.

`stylesheet "assets/brand.css"` loads author-trusted local CSS (up to eight sheets, 256KiB each). CSS/font/image references are root-confined, bounded and content-addressed; symlinks, remote URLs, CSS imports/escapes and legacy executable expressions reject. CSS is a constrained author stylesheet format, not a full sanitizer for untrusted third-party CSS. Font support is local WOFF/WOFF2 with signature checks; provide the appropriate font license. Image validation is shared with static sites. Total presentation assets are bounded to 16MiB. Custom styling cannot grant script or HTTP capabilities. Breakpoint-prefixed properties and CSS media queries support responsive design; baseline styles respect reduced motion and keyboard focus. Accessibility still depends on author content and contrast choices.

Static sites use several `page name at "/path/":` blocks, each with title/description/lang metadata, shared imported components and local images. With `origin "https://your-reviewed-host.example"`, generation emits canonical/OpenGraph URLs, sitemap.xml and robots.txt; `robots false` disables indexing. Optional `favicon "assets/icon.svg"` and `social-image "assets/cover.svg"` are copied safely. `robots` requires an explicit origin. WebApp rejects static-only metadata rather than silently pretending SEO routing. No hosting/deployment happens at compile time.

## Deployment, upgrades and trust boundaries

Review and upload the generated site directory to an ordinary static host. For WebApp, serve the directory over HTTP(S); hashes need no special rewrite rules. Keep the same origin/path/name to retain the storage namespace. Provide API endpoints independently, with server-side authorization, validation, rate limiting, logging and secret storage. Browser constraints do not protect a server from a hostile client.

Extensions currently mean controlled compile-time `.sdr` libraries, local presentation resources and declared public HTTP capabilities. A future native/server adapter must have a separately versioned capability contract covering routes, typed requests/responses, error/cancel/resource limits, server transactions, storage migrations, standard authentication/authorization, secret injection and dependency auditing. None is automatically authorized by a client declaration. Arbitrary third-party executable modules, SQL adapters, server-side business logic and authentication are not implemented in this preview. Never embed secrets in generated source. See [security policy](SECURITY.md).

Upgrading existing 0.9/0.10 programs does not require syntax changes: use their original app targets. Keep published artifacts and saved data backups separate. The new root modes and imports do not migrate old state. Install branch builds in a separate virtual environment; remove it and return to your previous pinned version for compiler rollback. Rolling back the compiler is not automatic storage migration.

## Actual support and verification

| Area | Integration preview | Android |
|---|---|---|
| 0.9/0.10 app semantics and navigation | Existing Web target retained | Existing Compose target retained |
| Pure functions, lets, conditionals, bounded query/date/text IR | Python + JS | Kotlin backend / JVM oracle |
| Static multi-page site, composition, CSS/fonts, SEO | site target | Not a site target |
| Responsive WebApp forms/tables/templates/dialogs/hash routes/themes | webapp target | Not translated to Compose |
| Typed bounded HTTP connector | Browser public capabilities | No new Android HTTP target |
| Backend/auth/database/native executable plugins | Unsupported | Unsupported |

The four sources are acceptance clients, not evidence of every requested future platform scenario. Tests compare complete Python/JS/Kotlin states, run real Chromium with real loopback HTTP, six widths 320/360/390/768/1024/1440 and axe-core. See status/CI for exact counts at each SHA. Passing four initial-screen axe checks is not accessibility certification. Cross-file source maps, namespaced modules, richer runtime component props, timezone/clock/format libraries, server adapters, service workers and broader browser proof remain release work. **NO-GO for a 0.11.0 release until the documented gates are met.**
