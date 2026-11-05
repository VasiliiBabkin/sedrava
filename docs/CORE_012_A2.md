# Experimental bounded core A2 — English

Source experiment stacked on PR #50; not a stable 0.11 feature or a release.
The existing primitive, record, record-ID and snapshot contracts remain unchanged.
See `examples/bounded_values_012.sdr` for a complete executable application.

## Lists and iteration

```sdr
state numbers: list<int>(max=4) = [3, 1, 2]
action double:
    for index, value in numbers:
        numbers = list_replace_at(numbers, index, value * 2)
```

`list<T>(max=N)` supports int, bool, text and existing record T; N is a literal
1..100. Scalar lists may have typed literals; record lists start empty and allocate
stable positive IDs. No implicit conversion, nested lists or inferred capacities.
Function parameters/results specify the exact capacity. Scalar lists serialize as
strict JSON arrays; bool/float are rejected for int. Existing record-list schema,
IDs, monotonic next_id and fingerprints are preserved. Changing element type or
capacity rejects the old snapshot; there is no automatic migration.

Operations: append, count, list_at, list_slice, list_clear, list_remove_at,
list_replace_at, list_index, list_capacity. Bracket indexes/slices are positional,
zero-based and require explicit valid bounds; negative indexes and slice steps
are rejected. `list_index` uses exact typed equality and returns -1 if absent.
Record replacement retains the ID; removal never reuses it. `list_identity(rows,i)`
returns the stable ID at position i. Existing get/update/remove/has use IDs.
Scalar lists additionally support list_sort (Unicode scalar lexicographic ordering
for text) and list_sum (int only, checked int32 after every addition).

`for value in collection:` and `for index, value in collection:` visit an immutable
entry snapshot, in order. Mutations do not change that iteration. Text iteration
visits Unicode scalars, not graphemes. Loop bindings are immutable and scoped;
shadowing existing names is rejected. `repeat i in range(start,end[,step]):` uses
signed int32 literals, exclusive end, nonzero step and at most 100 iterations.
Empty and descending ranges are permitted. No while or unbounded iteration.

## Resource and transaction contract

Nested loops, collection capacities, function calls, query callbacks, sort work,
derived expansion and invariants contribute to a conservative static bound.
Actions exceeding 1,000,000 work units reject; Python, JS and Kotlin reserve the
same fuel before each statement at runtime. The existing 10,000 statement and
nesting limits remain. Units bound visits/evaluations, not milliseconds. Text is
at most 1024 scalars; state/snapshot limits still apply. Failure, overflow, failed
invariant or fuel exhaustion commits no partial action. Fuel errors cannot be
caught as expected application errors.

## Unicode 15.0.0

`unicode_nfc`, `unicode_nfd`, `unicode_nfkc`, `unicode_nfkd` require text and return
text. Forms are explicit in operation names. `text_casefold` uses default full
case folding, without locale/Turkic special casing. All three targets use the
same pinned UCD 15.0.0 data and portable algorithm, including Hangul, canonical
ordering, blocking and composition exclusions. No host normalize()/Normalizer
calls. Surrogates reject; unassigned scalars are preserved. Output over 1024
scalars rejects the whole action. Intermediate decomposition is bounded at
18*1024 scalars; tables are generated from checked SHA-256 inputs. Normalization
reserves 65,536 work units and case folding 4,096. See unicode_data/15.0.0/manifest.json
and licenses/Unicode-Data-LICENSE.txt. Generated applications carry the notice.

Normalization is never implicit in storage/equality. Combine explicit normalization
and folding with text_index/contains for search. Indexes refer to transformed text
if a transformation was applied, never to original grapheme clusters. Grapheme
segmentation, locale collation and newer Unicode semantics are not implemented.

## Expected errors

```sdr
fn safe(x: int, y: int) -> Result<int, Error> = try_add(x, y)
action calculate:
    let outcome = safe(2147483647, 1)
    number = result_or(outcome, 0)
    message = result_code(outcome)
```

Result<T, Error> is an immutable ephemeral typed value for local bindings, derived
expressions and pure functions. `try_add(int,int)`, `try_chr(int)` and
`try_at(text-or-list,int)` return Result. Closed expected codes are INT_OVERFLOW,
INVALID_SCALAR and INDEX_BOUNDS. `result_ok`, `result_code` (empty on success) and
`result_or(result, same-typed-fallback)` handle outcomes explicitly. Arguments,
including fallback, evaluate eagerly. There is no implicit unwrap. Errors while
evaluating arguments, invariant failures and engine/resource faults are not
converted to Result. No exception-message matching or host exception payloads.
Result state/persistence, nested Result, user-defined error variants and exhaustive
pattern matching are not supported. This is a bounded first step, not unrestricted
algebraic data types. Map/Set remain deferred pending portable equality, key and
snapshot contracts. The standalone A2 branch required separate namespace reconciliation. The current
integration contract is [CORE_NAMESPACES_012.md](CORE_NAMESPACES_012.md);
server experiments remain separate.
