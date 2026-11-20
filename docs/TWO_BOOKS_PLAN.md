# Sedrava — plan for two complementary Russian-language textbooks

**Status:** editorial plan, not completed books. This file does not announce unsupported language features or a future release. Books should be published only after verifying the relevant code against the actual compiler version.

## Editorial principles shared by both books

- Core philosophy: **«Описал — получил»**. Explain what the reader can build, not only what keywords exist.
- **Never mix released and experimental features as if identical.** Each example has compiler version/SHA, target platform, expected output, limitations and a link to passing tests.
- Code listings come from runnable `.sdr` files in a separate versioned examples repository or `examples/books/`. Maintain a test harness that compiles every code sample during editorial CI; screenshots come from actual generated applications.
- No synthetic code excerpts falsely presented as supported. Proposed syntax appears only in explicitly marked roadmap appendices.
- Explain security boundaries: local browser state is not shared server storage; HTTP clients are not trusted backends; authentication/authorization must be server-validated.
- Keep plain, idiomatic Russian with minimal unnecessary Anglicisms; provide a short glossary when a technical term is essential. Show each example's result before discussing its implementation.
- Adopt an errata policy and release-specific editions: 0.10 stable, 0.11 experimental until published, later server support only after implementation.

## Book A — «Sedrava для программистов: язык, архитектура, приложения»

**Audience:** working developers (Python, JavaScript/TypeScript, Kotlin, PHP, etc.).  
**Promise:** map familiar concepts to Sedrava precisely, understand its declarative model, limitations, generated targets and safe application architecture.  
**Style:** concise technical explanations, complete verified examples, explicit edge cases, diagrams and implementation trade-offs.

### Proposed chapters

1. Mental model and design philosophy: declarative source, typed rules, generated targets.
2. CLI, project layout, packages, deterministic builds and installed toolchains.
3. Scalar types, Unicode, integer overflow, expressions, functions, diagnostics.
4. State, derived values, atomic actions, `require`, invariants and persistence.
5. Records, bounded collections, stable identities, filtering, sorting, map/find.
6. Components, state bindings, rendering model, forms and dialogs.
7. Static sites, responsive CSS, assets, SEO, local Markdown and accessible markup.
8. WebApp navigation, browser history, error and recovery states.
9. HTTP contracts, exact JSON schema checks, cancellation, failures and browser security boundaries.
10. Namespaces, module visibility, dependency graph and package lockfiles **after implementation**.
11. Server endpoints, SQLite transactions, auth, migrations and deployment **after implementation**.
12. Testing and differential conformance across Python/Web/Android, CI, rollback, source maps.
13. Performance and resource bounds, portability and supported targets.
14. Complete case study: real utility app, from design through tested deployment.

### What to include beyond prose

- Translation tables: Python/TS/PHP concepts ↔ Sedrava behavior (including non-equivalences).
- Threat-model examples for browser/server boundaries and transactional invariants.
- API reference generated/checked against compiler source, versioned compatibility matrix, small exercises with expected outputs.
- One professionally maintained example project and independent CI verification for each target used.

## Book B — «Программирование с нуля на Sedrava»

**Audience:** complete beginners, including people who have never used an IDE or terminal.  
**Promise:** the reader makes a working program very early, gains confidence incrementally, and understands the ideas without memorizing computer-science jargon up front.  
**Style:** plain conversational Russian, screenshots of actual interfaces, short lessons, frequent small achievements, prompts to experiment and useful troubleshooting.

### Proposed lessons

1. What a program actually is; what Sedrava does; seeing a running finished example.
2. Prepare the environment with copyable, verified installation instructions for the supported OS.
3. Create and open a first simple webpage from an `.sdr` file.
4. Add text, cards and buttons; change the look without changing logic.
5. Variables and counters: make a button increase a value.
6. Conditions: create helpful feedback and handle mistakes.
7. Your first keypad calculator (explain current integer-only math and division behavior).
8. Lists and records: build a personal to-do list.
9. Save the list locally and understand what a browser can and cannot remember.
10. Organize an app into multiple screens, navigate and return.
11. Reuse components; introduce namespaces/packages only when they are available.
12. Read public information from an API; handle a network failure without panic.
13. Publish a static application on a server; check that it really works on a phone.
14. Later edition: users, shared database and server-side app **only after the backend is stable**.
15. Final project: choose a personal problem, prototype it, test it, improve it and share it.

### Beginner teaching method

Each lesson follows: **«Что получится → Сделаем вместе → Почему работает → Попробуй сам → Если не получилось»**. Give one main idea per lesson, no code dumps without explanation. Define jargon the first time; use common-life comparisons sparingly and accurately. For every task, include a checked answer and what an error message looks like. Offer offline downloadable sample sources and a small glossary.

## Publishing and verification

1. Freeze the first edition's compiler commit or release and capture stable language behavior.
2. Write a compact versioned reference first; derive technical textbook chapters from verified reference contracts.
3. Run actual example builds and browser acceptance; capture original screenshots of generated interfaces.
4. Review all steps on a clean machine/environment; have a beginner follow Book B without unstated terminal knowledge.
5. Check consistency, technical accuracy, Russian style, accessibility, and copyright/licensing for images/fonts.
6. Publish digital books as PDF/EPUB or printable DOCX only after requested format and factual review; keep the source in Markdown so later language versions can be revised.

The two books must not be the same text with different levels of jargon: **Book A explains the language's guarantees and architecture; Book B teaches the reader to build useful things quickly**.
