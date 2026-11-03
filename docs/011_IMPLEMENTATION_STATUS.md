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
