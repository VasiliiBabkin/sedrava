# Sedrava 0.11+ — From sites to complete Web applications

**Status: implementation plan, not shipped functionality.** Published 0.10 app mode and experimental 0.11 static site mode remain separate. The purpose is to join them without breaking existing `.sdr` programs or weakening invariants.

## Product contract

One declarative source describes **state + actions + rules + screens + UI bindings**. The compiler emits an offline-capable Web application; a later adapter adds explicitly declared network and server features. A generated site is not a full app merely because it has buttons.

### Current verified baseline

- 0.10: typed text/int32/boolean, bounded records/collections, stable IDs, atomic guarded actions, navigation and persistence for generated apps.
- 0.11 Slice A (PR #22): static site parser, responsive HTML/CSS, components and safe assets. It currently has **no state binding, forms or event handlers**.
- Light-theme fix is tracked separately in PR #29. Do not bypass that work with CSS patches in individual examples.

## Proposed integration boundaries

1. Preserve `sedrava build web` and `sedrava build android` behavior for all existing 0.10 examples. Keep `sedrava build site` for static publishing.
2. Introduce a new **explicit app UI mode** (exact grammar to be approved in a dedicated spec PR). Never silently reinterpret a `site` file as a stateful app.
3. Reuse the 0.10 interpreter/action semantics; UI events dispatch named actions through a generated adapter. No duplicate action evaluator in browser JavaScript.
4. Bind text, disabled state, value, list rows and validation messages using typed expressions. Escape all user content. Never turn user input into HTML or executable source.
5. UI observes **committed** state only. Failed validation or invariant checks must not alter rendered state, saved snapshots or navigation.
6. Use deterministic stable keys for list items. Enforce collection and text limits in UI and core; do not truncate silently.
7. Generated JS must be local, CSP-compatible and dependency-free for the first interactive slice. No inline event handlers, eval, remote scripts or runtime code generation.
8. Accessibility is part of the contract: explicit labels, focus and keyboard operation, live validation messages, reduced motion, contrast and touch targets.

## Extensibility: imports, services and platform bridges

A language that cannot integrate with other code and services is constrained to its built-in feature set. Extensibility is a **product requirement**, not evidence that any connector is implemented today.

- **M1: modules/imports.** Resolve local modules at compile time, deterministic dependency graph, explicit exports, cycle and duplicate-name diagnostics, reproducible builds. No arbitrary code execution during compilation.
- **M2: typed HTTP connector.** Explicit origins, methods, request/response schemas, bounded payloads, timeout/cancellation, safe error values and tests with mocked endpoints. Network effects are asynchronous and must never be disguised as atomic local mutations.
- **M3: platform bridges.** Explicit capability declarations for browser APIs and Android SDK integrations. Provide a safe generated adapter interface; unsupported targets must fail clearly, never silently drop behavior.
- **M4: packages and ecosystem.** Versioned dependency manifest, lockfile and provenance/integrity verification, then a public component/connector catalog. Package execution permissions and supply-chain risks need a separate review.
- **M5: server-side connectors.** Database drivers, authentication and private credentials only behind a trusted server boundary. Never bundle API secrets into client JavaScript.

**Proposed first end-to-end connector acceptance:** a task manager can fetch a typed public JSON endpoint (e.g. sample data), display loading/error/success, retain accepted local data if offline, and recover on retry. The demo must use a controlled mock endpoint in CI. No external service is required to run unit tests.

**Dependency:** ship the B1 state/event adapter before HTTP effects; specify module grammar alongside B0 so app structure is not locked to a single source file. Do not make arbitrary JavaScript injection the default escape hatch.

## API-first implementation priority (decision 2026-11-01)

The first interoperability need is **external services and HTTP APIs**, not arbitrary third-party JavaScript execution. Prioritize a minimal typed HTTP client immediately after the B1 state/event foundation, before expanding the decorative component catalog.

**API0 contract (specification and tests):**
- Explicit `service` declaration with HTTPS origin allowlist and fixed request paths.
- Start with GET + JSON, named response record schema, bounded depth/body/collection size, strict validation, typed failures.
- Asynchronous request state: idle/loading/success/error, cancellation, timeout, retry; network results are only committed via validated existing actions.
- Browser fetch follows CORS; never claim the compiler can bypass a third-party service's CORS policy.
- No API keys or tokens embedded in generated public JavaScript; private credentials require a server-side proxy/adapter in a later milestone.
- Mocked local endpoint in Chromium tests, plus negative tests for invalid JSON, bad status, oversized body, timeouts, rejected origin and offline mode.
- Clear diagnostic for unsupported endpoints or server-only capabilities. Keep existing 0.10 programs unchanged.

**API1 acceptance:** one Sedrava task-manager view loads public example records from a test API, renders a loading indicator, success and recoverable error, and preserves local tasks across a failed request. No dependency on third-party availability in CI.

**Non-goals for the first HTTP slice:** arbitrary JavaScript, OAuth, database credentials, unrestricted URLs, WebSockets, server-rendered secrets or production authentication.

## Delivery slices and gates

### B0 — contract and executable task-manager fixture

- Specify app UI syntax, binding types, action dispatch, validation, errors and persistence. Specify import/export grammar and module resolution contract without claiming runtime support.
- Add one task-manager fixture and golden diagnostics for unsupported constructs.
- Acceptance: syntax and safety review, 0.10 regressions unchanged.

### B1 — interactive state and forms (first real app)

- Components: input, textarea, checkbox, button(action), label, list, conditional, validation message.
- Bind to text/bool/int32 and bounded records/collections; CRUD uses existing 0.10 actions.
- Generate local JS adapter, event delegation, safe DOM updates and persistent state.
- Acceptance: create/edit/complete/delete tasks, invalid input rollback, reload persistence, keyboard-only flows, XSS regression tests, 360/768/1440 viewport checks.

### B2 — minimal typed HTTP API integration (API0/API1)\n\n- Implement the API-first contract above after B1, with deterministic mocked network tests.\n- Acceptance: public JSON endpoint, loading/success/error/retry, CORS-aware diagnostics, and preservation of committed local state.\n\n### B2b — app navigation and composition

- Reuse guarded multi-screen navigation with browser history/back.
- Reusable UI components, layout templates, empty/loading/error states, accessible dialog and responsive navbar.
- Acceptance: refresh/deep-link/back/forward and state restoration, no stale selected item.

### B3 — richer client data, modules and network

- Explicit `storage` selection, versioned data migrations, safe import/export and quota/error behavior.
- Explicit HTTP client with origin allowlist, typed response parsing, timeouts, cancellation, loading/error/retry.
- Acceptance: offline-first task app still works with network disabled; network errors never corrupt saved state.

### B4 — server-backed applications

- Separate server target and trusted runtime boundary. Authentication, authorization and secrets must **not** be embedded in browser bundles.
- Typed server routes, persistence adapter, schema migration, deployment and rollback strategy.
- Acceptance: independent security review and multi-user test app. Not part of the first 0.11 milestone.

## First acceptance application: Task Manager

- Add, edit, mark done, delete; search and filter (all/open/done).
- Persist across reload, including stable item identity.
- Reject empty/oversized text; show field-specific errors without losing prior accepted state.
- Work with keyboard and screen reader, 360px viewport, offline, no external JS.
- Test rejected mutations, malicious text, back/forward, concurrent clicks and corrupted storage.

## Engineering workflow

1. Implement B0 in its own PR; test parser and diagnostics.
2. Implement B1 behind an explicit new build mode; add Python/Chromium contract comparisons and accessibility checks.
3. Use `sedrava-site` only as the deployment and preview home for accepted demo builds. Keep current docs and production unchanged.
4. After CI and user acceptance, publish a task-manager demo on the **dev** site; do not replace the current showcase without approval.
5. Never claim server apps, network APIs or authentication are supported until the corresponding slice passes tests.

## Release gate

No 0.11 stable release until compiler outputs, docs, security checks, cross-platform regressions and representative application are verified. Maintain a public feature support matrix: designed / implemented / tested / released.
