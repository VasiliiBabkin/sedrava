> Historical reference; not a current release or installation guide. [Current Rust documentation](README.ru.md).

# Sedrava 0.10 — String semantics contract (implementation prerequisite)

Status: **implemented on `feature/010-string-core`, unreleased development increment**. See [normative text reference](LANGUAGE_0_10_TEXT.md) and [measured work report](TEXT_010_REPORT.md). This is not acceptance of the whole 0.10 roadmap. Baseline: [0.9 language reference](LANGUAGE_0_9.md). Parent contract: [Describe → Get](DESCRIBE_GET_010.md).

## First increment

Add a first-class immutable `text` scalar to the common AST/type checker, evaluator, actions, rules, embedded tests, CLI JSON, Web generator and Android generator. Do not implement a string as a UI-only widget: it must be a genuine value with identical accepted-state semantics on all backends.

### Syntax decision to implement and test

- `state title = "Untitled"` declares a text state. A double-quoted literal is a text expression; `app "…"` and `text "…"` remain compatible.
- `derive is_named = title != ""` and `rule title != ""` are valid.
- `action rename: title = "New name"` is valid; `input title` produces validated text input; `value title` displays it.
- Text supports `==` and `!=` only, with text operands. No implicit conversion, ordering, indexing, concatenation, interpolation, regex or numeric parsing in this increment.
- JSON `run` includes strings as JSON strings; boolean and int32 values retain their existing representation.
- All 0.9 examples and commands must retain behavior.

### Source encoding and limits

Source remains UTF-8. String literals use double quotes and allow escaped `\\`, `\"`, `\n`, `\r`, `\t`; invalid escapes and unterminated literals fail with source locations. Reject unpaired surrogate code points and malformed UTF-8. Limit each text value to 1,024 Unicode scalar values, with the limit checked on input, assignments, derived expressions and restored persistence. Limit is in Unicode code points, not UTF-16 units or bytes; do not silently truncate. Preserve user-entered Unicode without normalization or case folding in 0.10, so equality is exact scalar sequence equality. An empty string is valid unless a `rule` forbids it.

### Atomicity and validation

All text edits follow the 0.9 draft/accepted-state model. An invalid edit preserves accepted state and shows an accessible error. All derived values remain evaluable after each assignment, and rules are checked against the final candidate. Failed validation never partially commits, including across text/int32/bool changes in one action.

### Persistence and safety

Only explicitly `persist`-marked text state is stored. Restore malformed, over-limit or type-mismatched snapshots using the same safe fallback rules as 0.9. Escape strings as data in HTML/JavaScript, Kotlin and JSON. Never interpolate text directly into generated source without backend-specific escaping. No secret storage or encryption promise.

### Conformance and acceptance

- Parser/type checker tests: valid literals, escapes, Unicode, empty text, wrong types, malformed literals, over-limit values.
- Interpreter: exact JSON output, action transitions, rejected rules, atomic multi-field action.
- Differential Web/JS tests: compare Unicode/escaping and rejected input to Python; run real Chromium scenarios including reload.
- Android generator: compile, JVM tests, Lint, restore and rotation tests if device/emulator available; explicitly report absent runtime UI coverage.
- Security regressions: `</script>`, Kotlin interpolation sequences, quotes, backslashes, control characters and Unicode edge cases.
- New `examples/text_profile.sdr` should declare and persist a title, validate nonempty input and display a derived boolean; build Web and Android without editing generated code.
- Do not label the feature complete unless all supported backends implement it and CI passes.

## Sequencing

Implement this increment before records/collections, then define stable identity and bounded collection mutations. Do not create a 0.10 tag or publish a package as part of the implementation PR.

## Resolved implementation boundaries

Static labels now share the escaped literal grammar; escape backslashes in legacy labels. HTML textarea performs native CR/CRLF-to-LF draft normalization, while accepted source/model/persisted strings retain exact scalar equality. Both boundaries have regression tests and are detailed in the [reference](LANGUAGE_0_10_TEXT.md). All published 0.9 examples remain covered.
