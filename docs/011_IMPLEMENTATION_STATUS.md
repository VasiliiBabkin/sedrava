# Sedrava 0.11 integration — actual implementation status

Status: **NO-GO for 0.11.0 release; integration in progress.** No release/tag/package/site deployment authorized.

Base: PR #35 `4a5021acdbd61fb31717b9458ec9385a885ba95b`, branch `feature/webapp-011-b1-collections`; includes #34 → #33 → #22. Integration branch: `feature/011-web-platform-integration`.

Merged without squashing: #29 light-theme fix; #30 roadmap and current published 0.10 baseline; #31 API0 declarations/browser connector. CLI targets and package modules are unioned; published-version docs retained alongside experimental UI docs. Native Android semantics are not rewritten.

Checkpoints: `42d02ef` merges current baseline/roadmap; `6c849c5` merges API0 preserving site/webapp. No claim that all requested platform features exist.

## Verified capabilities inherited from source

- app: strict scalar/record/list actions, invariant rollback, persistence, Web/Compose navigation.
- site: responsive semantic static components, local checked assets, named styles, multiple pages; integrated light palette correction.
- webapp: core-generated atomic state/actions, scalar forms, selected collection CRUD; one view only at baseline.
- API0: explicit HTTPS read-only service/schema and fetch adapter, separate experimental CLI targets; not yet arbitrary WebApp binding or mutation methods.

## Work still required for release

Reusable composition/imports/functions; typed collection transforms; multi-view routes/history; arbitrary list templates; select/forms/dialogs; bounded mutating HTTP and runtime binding; custom CSS/fonts/theme configuration; full four-app acceptance; static SEO assets; server adapter boundaries and documentation; full compatibility/browser/package CI.

A browser bundle is not a trusted backend. Authentication, authorization, database and secret handling are not implemented and must not be advertised.

## Verification log

Integration Python/browser and packaging results will be appended after actual execution. CI links and final immutable SHA will be in the integration PR; generated artifact receipts bind their actual checkout SHA.

## Resume

Use this integration branch. Inspect `sedrava_webapp.py`, `sedrava_http*.py`, `sedrava_site.py`, `site_codegen.py`. Preserve prior modes and private-data protection. Continue in tested increments and update this file at every published checkpoint. Do not interpret a green existing suite as proof that the release requirements are met.

## Composition checkpoint

Added `sedrava_modules.py`: typed text/int/bool component parameters, one explicit slot, recursive expansion bounds, deterministic relative `.sdr` imports restricted to components/styles, cycle/traversal/symlink checks. Both presentation modes lower into the existing typed component AST. Imported state/actions are intentionally not supported yet. Diagnostics for expanded templates use expanded line positions (full cross-file source maps remain a release gap).

Added three unit tests for actual composition in both modes and negative import/recursion/type cases. API0 browser tests can select a real installed Chromium in container environments; no test is skipped or weakened by this change.

## Routing/forms/query checkpoint

Implemented typed multi-view hash routes (`:int_state`), guarded deep-link resolution, Back/Forward, reload restore, bounded navigation and focus changes using a tested Python route model. Domain actions still come from the existing core generator. Added native dialog/open/close, forms/submit and typed select/option. Added list search, bool filtering and stable Unicode-codepoint sorting, compared Python/JavaScript with complete row identity/order.

`examples/platform_tasks.sdr` now performs offline create/select/rename/complete/delete with search/filter, guarded detail route and confirmation dialog. Real Chromium: 2 integration scenarios pass, screenshots at 320/360/390/768/1024/1440; prior scalar 5/5 and collection 5/5 scenarios pass. Full Python at this checkpoint: 245 tests, no failures. Reload initially reset the deep route before restoration; this was found by E2E and corrected. Empty list status appears only when explicitly requested, preserving prior list behavior.

## Typed HTTP checkpoint

Added `sedrava_web_services.py` on top of API0 `ApiService`/`JsonResponse`: WebApp service blocks, explicit same-origin/public HTTPS capabilities, GET/POST/PUT/PATCH/DELETE, typed record request bodies using the shared expression compiler, exact JSON response schemas, bounded streaming UTF-8/JSON, cancellation/timeout/stale-response suppression, request/remote/cancel UI and checked optional public GET cache. Shared strict JSON parser is factored from the existing persistence runtime; it rejects duplicate keys and excessive depth. Request credentials are omitted; no secret or CORS bypass mechanism is provided.

`examples/platform_catalog.sdr` generates the full client. Chromium integration now has 3 passing scenarios, including a real localhost server exercising all five methods, request bodies, invalid schema/duplicate keys/oversize/status errors, timeout/cancel/retry, XSS, cached reload and six viewport widths. Full Python: 248 tests pass. Original API0 CLI targets remain available. HTTP status/data are deliberately outside domain state and cannot silently bypass invariants. A timed-out mutation can still have reached the server; no distributed rollback is promised.

Limits: same-origin server endpoints must be supplied independently; no backend/auth/database adapter. Integer path parameters only; no arbitrary custom headers. WebApp response limit is at most 200000 bytes to share strict parsing bounds. API cache is public data and never a secret store. No general functions or domain modules are claimed yet.

## Four-client / expression checkpoint

Four source projects now compile: `platform_site.sdr` (three static pages, light palette, SEO, shared components, local SVG/CSS/Inter font), `platform_tasks.sdr` (offline CRUD, guarded details, custom typed each/field row templates), `platform_catalog.sdr` (typed public JSON HTTP client) and `platform_crm.sdr` (related company/contact collections, forms/email validation, tables, modal edit, preferences and persisted light/dark palettes).

Added author-controlled local CSS and safe class hooks; local URL resources are bounded, root-confined and hash-copied. CSS imports/escapes and remote URLs are intentionally unsupported. Inter 5.2.8 assets from @fontsource/inter are OFL-licensed; `examples/assets/INTER_LICENSE.txt` is included. WOFF signatures are checked, not a full font decoder. Static metadata includes canonical/OpenGraph, sitemap/robots for an explicit HTTPS publishing origin. No site was deployed.

Pure typed expression `fn`, immutable action `let`, conditional expressions, bounded function cost and deterministic text/civil-date operations share the existing IR. JS and Kotlin backends emit the same model; no extra action interpreter. Python/JS complete-state and actual Kotlin/JVM comparisons cover eager unused-argument overflow, scope, atomic rollback, Unicode, date bounds and conditional evaluation. CRM consumes a reusable record-transforming function from a local module.

Last local full run: 258 Python tests pass. Real Chromium: six integration scenarios pass across all four projects, each photographed at 320/360/390/768/1024/1440; axe-core 4.10.3 WCAG2A/AA/2.1AA checks have zero violations on the four initial screens. This is not full accessibility certification. Empty-list ARIA was corrected after axe detected an invalid role. Additional each templates are read-only fields/named atomic actions; nested row scopes, inline row editors and capability controls inside templates are rejected explicitly.

Remaining release gaps include broader collection transformations/aggregation in domain expressions, module namespacing/source maps, clocks/timezones and richer formats, reviewed runtime extension/backend contracts, Firefox/WebKit verification where possible, final packaging and whole CI proof. Status remains NO-GO; these clients do not establish secure server/auth/database support.

## Bounded collection algebra checkpoint

Added typed domain `filter/map/find/any/all/sort/sum`, field selectors or pure record functions with explicit extra arguments. Maps preserve IDs/next_id/capacity; stable sort uses Unicode codepoints on all backends. Work is charged against the expression budget. Tasks use core-filtered derived collections; CRM exposes an aggregate. Full states after 13 actions (including overflow, failed deletion and rollback) match Python, Node and compiled Kotlin. Added three regression tests. Metadata for the wrong mode is rejected rather than ignored; output manifests include imported module/asset hashes. HTTPS capability origins are normalized before runtime comparison.

Local complete suite before the final metadata test: 261 passing; subsequent metadata test: 4/4 passing. Chromium integration: 6/6 passing after domain-query integration. The next full run will include that added test. New read-only `platform-011.yml` builds the four clients, runs the six browser/axe scenarios, archives screenshots and actual SHA/file hashes, and separately builds a common-IR APK/JVM oracle/Lint. Clean wheel/sdist checks now cover all four installed projects and all compiler modules.

Previous checkpoint `2a312dc14ff984a765bd411b5abc139ef0f5d803` has successful CI for Python, packaging, WebApp, static site, API0, legacy APK, records and text Android. Those results do not certify the next commit. Integration PR: https://github.com/VasiliiBabkin/sedrava/pull/36 (draft). Remaining release gaps in prior sections still apply; no release readiness claim.

## Acceptance and documentation checkpoint

At `9d75a60e00789aced1d4aeaec1e031e737411396`, the new acceptance workflow [41720781040](https://github.com/VasiliiBabkin/sedrava/actions/runs/41720781040) completed successfully: four generated clients, Chromium/axe evidence, common-IR APK, JVM oracle and Android Lint. These are actual CI results, not predictions for the following commit.

Subsequent local checks: 262 full Python tests passed; 25 focused platform tests passed after extending the domain fixture with cross-record map, local scopes, civil dates and Unicode conditionals. Existing Chromium scenarios passed: 26 legacy app, 8 static site, 5 scalar WebApp and 5 collection WebApp. A previous legacy launch run failed while the CRM source was temporarily malformed during editing; the corrected source passed the complete 26-scenario rerun. The local generated Android common-IR project built APK/JVM/Lint successfully; final extended fixture is also compiled by differential Kotlin tests and will be rebuilt in CI.

CRM now supports company rename/deletion, rejects deletion while related contacts exist, and retains state on that expected failure. The browser test now targets each named dialog rather than assuming only one dialog exists.

Found and fixed a real HTTP lifecycle defect: parameterized services previously reused cached/accepted data across different path parameter values. Cache keys now include served path and resolved endpoint path; parameter changes cancel the old request, invalidate stale completions and restore/reload only the matching cache. A real-server browser regression switches IDs during an in-flight response, then restores both cached records independently offline. Chromium acceptance now passes **7 scenarios**. No distributed mutation rollback is promised.

Added complete RU/EN integration guides (syntax/domain/UI/components/styles/API/modules/deployment/migration/support matrix), current links in canonical docs, and explicit historical-slice notices. Static SEO metadata is rejected in WebApp and mutable theme-state is rejected in site. New CI browser matrix will test Chromium/Firefox/WebKit where their hosted runners can install supported engines; local Firefox/WebKit executables are absent and their download CDN is outside the managed network allowlist. Local Firefox/WebKit success is not claimed.

Release status remains **NO-GO**: runtime component props/instance state, namespaced modules/full cross-file source maps, richer formats/clocks/timezones and executable/server adapter contracts are not complete. Browser clients do not implement auth, database or safe server-side business logic. No change to published package version, release artifacts, production site, tags or main.
