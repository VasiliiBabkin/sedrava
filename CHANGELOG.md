# Changelog

## 0.12.0a1 — experimental alpha integration (NOT published)

- Preserve stable published 0.11.0 baseline and add checked namespaced module exports and alias visibility, source-provenance diagnostics and deterministic offline package locks from the original #39–#43 experiments.
- Exact-version local vendored dependencies, SHA-256 lock integrity and bounded resolver checks; no hosted registry, unrestricted foreign libraries or backend/database/auth.
- Experimental branch only: no alpha tag, PyPI publication or production website claims. New CI on the post-0.11 source SHA is required.

## 0.11.0 — stable released on GitHub and PyPI (2026-11-05)

- [GitHub release](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0) and [PyPI](https://pypi.org/project/sedrava/0.11.0/) published from exact audited source `c9cde75e3d2e2c7eafeeaec10c73fec627816e68`. Web-platform scope matches [0.11.0rc1](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1); Android versionCode 11002 exceeds RC 11001.
- Exact-head release CI succeeded (36/36); main merge CI succeeded (11/11), as did real PyPI 0.10 → 0.11 → 0.10 and RC → 0.11 → RC installation checks, Chromium/Firefox/WebKit and Android API35.
- Published verified wheel/sdist via PyPI Trusted Publishing (workflow 41951910157). No automatic schema migrations, trusted backend, SQLite/auth or experimental 0.12 namespace/lockfile code is included.

## 0.11.0rc1 — experimental prerelease published on 2026-11-04

- Published the tested integration line as an experimental [GitHub prerelease](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1) and [PyPI package](https://pypi.org/project/sedrava/0.11.0rc1/); 0.10.0 remains available.
- Candidate scope: responsive multi-page sites; stateful WebApps; components, reusable functions, forms, routes, typed collection queries, local styling and bounded public HTTP client requests.
- Preserve existing app/Web/Android targets and explicitly exclude 0.12 namespaced modules, package locks, trusted server, databases and authentication.
- Read-only candidate distribution/compatibility CI, published 0.10 upgrade/rollback checks and RU/EN website release documentation were completed before/after the approved RC publication.


## Unreleased — Web UI 0.11 Slice A

- Add experimental `site` presentation AST and `sedrava build site`, preserving 0.10 application semantics and package identity.
- Implement 13 primitives, named styles, typed properties, responsive layouts and amethyst/gold dark defaults.
- Validate links, headings and bounded local assets; escape HTML; stage deterministic outputs with protected rebuilds.
- Include two-page source example, RU/EN reference, clean-package checks and actual Chromium screenshots/keyboard/contrast evidence.
- No release, production-site change or deployment.



## 0.10.0 — released on GitHub and PyPI (2026-10-31)

- [GitHub release](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) and [PyPI wheel/sdist](https://pypi.org/project/sedrava/0.10.0/); publishing workflow completed successfully. Version 0.10.0 / Android versionCode 10003. In-place Android updates require identical ID and signing key.
- Dedicated GitHub Actions PyPI Trusted Publishing: exact production tag v0.10.0, manual TestPyPI only, separate build and publish jobs.
- Release notes and physical-device checklist. Final 0.10 physical Android acceptance remains unconfirmed; release success does not imply hardware certification.
- Historic rc1/rc2 artifacts remain immutable. No automatic data migrations or production workload guarantees.

## Historical: 0.10.0rc2 preparation (pre-stable)

- Retain all stability audit fixes; no language/schema or Android ID changes.
- Version 0.10.0rc2 and Android 10002; strict actual rc1 upgrade/corruption evidence.
- Bind tested APK bytes and complete boundary corpus to the immutable RC2 kit.
- Include dedication in distributions; separate bilingual RC2 notes/rollback guides.
- No stable-release, tag, index publication or deployment authorization.

## Unreleased stability audit / Аудит стабильности

- Preserve rejected saved data on Web/Android instead of overwriting it with defaults or new edits.
- Accept int32 minimum in all expression positions; retain overflow rejection.
- Write CLI Web outputs atomically and protect source/output collisions.
- Give repeated scalar editors separate accessible error messages.
- Add bounded Python/JavaScript/Kotlin differential evidence and rc1-source update checks.
- No version, schema or Android identity change; rc1 artifacts unchanged. Recommend rc2.

## Historical: 0.10.0.dev0 text increment

- First-class immutable text state, derived aliases/booleans, exact equality, assignments, rules/tests and CLI JSON.
- Strict escaped literals shared by expressions and UI labels; bounded Unicode scalar values and rejection of invalid surrogates.
- Inferred validated multiline input, accepted-state persistence and atomic mixed-type actions on Web and Android.
- Pure generated Kotlin state adapters shared by Compose and JVM conformance; hostile-string fixture and text profile example.
- Expanded Python/JavaScript/browser/JVM tests, Android APK/Lint workflow and normative text guide.
- Explicit label-backslash migration and native HTML textarea line-ending boundary, both tested. No full 0.10 milestone, tag or publication.

The historical 0.9.0a1 release/tag/assets remain unchanged. Notes below preserve the status *at the time* and do not override the published 0.10.0 status.


## 0.9.0a1 — unreleased first Sedrava public alpha candidate

- Shared restricted typed AST for integer/boolean state, derived values, sequential atomic actions, rules and embedded tests.
- Numeric input, accepted-state persistence and conditional text on Web and Android.
- Added `sedrava run FILE [ACTION ...]` with deterministic JSON output alongside check/test/build commands.
- Fixed signed-minimum integer literals; reject oversized literals even in short-circuited expressions.
- Reject initially overflowing derives; validate all derived values after every assignment and before input/restored-state acceptance.
- Handle action overflow and invariant rejection visibly without partial state updates in generated interfaces.
- Validate restored snapshots, recover from wrong-type Android preferences and preserve accepted state across Activity recreation.
- Escape HTML script content and Kotlin dollar interpolation; namespace generated Kotlin variables to avoid collisions; support prototype-like identifiers safely on Web.
- Bound nested blocks and expanded derived expressions; reject duplicate screens, tab indentation and reserved state names; allow initial-state tests with an empty action sequence.
- Added full manual countdown example, browser regression suite, example/determinism tests, normative language reference and installation/build/troubleshooting guides.
- Source distributions now include examples, documentation and validation scripts; CI prepares downloadable candidate artifacts without PyPI publishing.

This is Sedrava's first candidate; historical Intent 0.7 and abandoned Sedrava 0.7.1 proposals are not releases of this version. No stable-language compatibility promise is made.

## Historical: 0.10 records integration / Записи и коллекции

- `.sdr` record declarations, bounded list state, typed constructors, lookup and immutable mutations.
- Stable monotonic IDs, atomic actions and `require`, strict versioned whole-state snapshots.
- Generated selectable lists in Web and Compose; offline task manager from one source file.
- Python/JS/Kotlin oracle, Chromium CRUD and Android test harnesses; see
  [measured results](docs/COLLECTIONS_010_REPORT.md). No release or publication.

## Historical: 0.10 navigation / Многоэкранность

- Named screens, explicit initial screen, bounded push/pop stack and bool guards.
- Atomic navigation bindings with domain actions; selected stable ID preserved;
  missing/deleted records cannot leave an invalid details screen active.
- Web Back/Forward, keyboard focus and responsive cards; native Compose Back and
  complete accepted-session recreation. Cold launch/reload start at initial.
- One two-screen task manager source, shared Python/JS/Kotlin oracles, browser and
  emulator harnesses. [Measured evidence](docs/NAVIGATION_010_REPORT.md).
- Навигация реализована в ядре и генераторах; 0.10 не выпущена.

## Historical: 0.10 release readiness / Подготовка RC

- Deterministic Android identity and validated `--application-id`; matching namespace, Kotlin package, tests and permission audit. Независимая установка приложений, стабильные ID и строковые ресурсы названия.
- Responsive long titles/cards, larger fonts, stronger secondary-text contrast, accessible status descriptions and invalid-draft action blocking in navigation apps; pure navigation remains available.
- CLI validates generated Web before creating output directories; project identity collisions reject before changing files.
- Wheel bundles documentation/examples/license; clean wheel and sdist checks run outside checkout.
- Side-by-side emulator installation and update-data-retention checks; 0.10 remains unreleased.

- Resource escaping also covers XML-illegal Unicode scalars; duplicate Compose editors track errors independently. Эмулятор подтвердил совместную установку двух APK и сохранение данных при повторной установке; [готовность RC](docs/RELEASE_READINESS_010_REPORT.md) измерена без публикации.

## 0.10.0rc1 — prepared, not published / Подготовлено, не опубликовано

- Single `sedrava_version.VERSION` for package/CLI/generated Android; Android test code 10001, unchanged IDs.
- Pinned build backend/tools/actions, read-only workflows without publication rights/steps; bounded archive/credential/integrity checks.
- Same-SHA immutable RC kit with wheel/sdist/two debug APKs/Web/test evidence, actual manifests/checksums and post-upload delivery identity.
- Clean installs cover 0.9, text, records/collections/navigation; published 0.9 wheel -> separate RC -> original environment tested. Real same-key Android development-to-RC update gate added.
- RU/EN release notes, installation/rollback, physical-device limitations and separate owner approval instructions. No tag, release, merge, index upload or deployment.


## Unreleased 0.11 integration preview (not a version announcement)

- Preserve merge history of Web UI, WebApp scalar/collections, light theme and API0 work.
- Add bounded local modules, typed components/slots, pure functions/local bindings/conditionals and portable text/date/collection expressions.
- Add guarded hash routing/history, native forms/select/dialogs, stable-ID tables and typed custom row templates.
- Add public bounded typed HTTP mutations/cancel/cache, local CSS/fonts/themes and static SEO assets.
- Add four source-driven clients and real Chromium/axe/common-IR differential checks. Server/auth/database adapters remain unsupported; release status is NO-GO pending remaining gates.
- Руководства RU/EN описывают фактическую поддержку и ограничения; production-сайт и опубликованные артефакты не изменялись.

### Unpublished 0.12 integration experiment

- Integrate bounded A1/A2 types, loops, Unicode 15 and Result with namespaces.
- Add isolated module-owned state/actions, shared budgets and original columns.
- Harden lock schemas/vendor imports and protect imported sources from outputs.
- RU/EN contract: docs/CORE_NAMESPACES_012.md / CORE_NAMESPACES_012.ru.md.
