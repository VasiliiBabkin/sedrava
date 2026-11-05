# Sedrava bounded core A1 — experimental and unpublished

This is a **source-only PR**, not part of published 0.11.0 or the draft 0.12 namespace release. It extends strict, bounded portable semantics for Python/Web/Android.

## Unicode scalar indexing

Indexing is zero-based and measured in Unicode code points (not UTF-8 bytes, UTF-16 units or full grapheme clusters). The 1024-scalar text limit still applies; no implicit Unicode normalization, locale-dependent lowercasing or silent truncation is performed.

~~~sedrava
app "Unicode"
state text = "A😀Б"
derive emoji = text[1]
derive part = text[1:3]
derive position = text_index(text, "Б")
derive point = unicode_ord(emoji)
derive recreated = unicode_chr(point)
~~~

Functions text_at(text,index), text_slice(text,start,end), and text_index(text,needle) are available alongside square bracket forms. Index requires 0 <= index < scalar length. Slice is half open with 0 <= start <= end <= length; both ends must be specified, and steps/negative indices are prohibited. text_index returns -1 if missing and 0 for an empty needle. unicode_ord needs exactly one scalar. unicode_chr rejects surrogates, negative or >U+10FFFF. Error fails the whole action without a partial commit.

## Statically bounded loops

~~~sedrava
action calculate:
    repeat i in range(0, 5):
        total = total + i
~~~

The half-open range iterates 0..4; the upper bound is a literal 1..100. Loop indices are scoped immutable integers. No dynamic while, recursion, break, continue or unbounded iterations. The compiler calculates worst-case nested statement counts and rejects actions with more than 10,000 steps; the interpreter also counts executed steps.

## Bounded collections

The existing list-of-records limit remains 100 entries, with stable record identity and next_id. list_at(items,index) / items[index] returns a typed record at a zero-based positional index. list_slice(items,start,end) / items[start:end] returns a same-typed bounded list with stable IDs and next_id preserved. list_clear(items) empties the list without reusing issued IDs. Use the existing get(items,id) for lookup by stable record identity. There are still no unbounded maps or sets.

## Structured compiler diagnostics

Use: sedrava --diagnostics=json check examples/bounded_core_012.sdr

On failures, stderr contains one JSON object with fields code, phase, message and location (source, line, column). Unknown line/column is null, not guessed. Default human-readable CLI messages are preserved. Generic codes are SDR-E1001 (compile), SDR-E2001 (execute), SDR-E3001 (IO), SDR-E4001 (test). Internal typed SedravaError allows future error codes. This does not yet implement language-level try/catch or Result values.

## Verification and remaining limits

Must pass Python 3.10/3.12/3.13, real Chromium browser, generated Android Kotlin, existing regression matrix and clean wheel/sdist checks. Version tags, stable 0.11.0, experimental server PR #48/#49 and separate 0.12 package imports are unchanged. Still needed: language-level structured error handling, runtime-bounded iteration over collections, versioned normalization policy and broader collection types.
