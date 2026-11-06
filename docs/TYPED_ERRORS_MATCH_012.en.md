# Typed errors, Result and exhaustive match — experimental A1

Dependent on Effects A1. This document specifies the implementation in this branch,
not a stable release or a Host capability contract.

```
error closed ArithmeticError id "example.ArithmeticError":
    IntOverflow:
        left: int
        right: int
error open ReadTextError:
    FileNotFound:
        path: text
    InvalidEncoding:
        path: text
        encoding: text
```

`error closed|open Name [id "stable.identifier"]:` precedes functions/state.
Names use `[A-Za-z][A-Za-z0-9_]*`. Error type names cannot shadow the built-in
type names int/text/bool/list/Result/Error. Each type has 1..16 variants, each has 0..16 distinct int/text/bool fields; at most
16 types. Variant/field names are at most 64 ASCII identifier characters; IDs at most
128. Empty variants use `Name:` without a body. Constructors require exact
named fields: `ArithmeticError.IntOverflow(left=x, right=y)`. No coercion,
mutation, arbitrary class construction or engine exception interception exists.
Engine fault names BudgetExceeded/PolicyViolation/CapabilityDenied/CompilerError/
InternalError are reserved for the non-catchable engine boundary.

IDs default to `entry.Name` in an entry source, `module.identity.Name` in modules;
explicit IDs survive renaming. IDs must be unique in a compilation. Variant IDs
append `.Variant`. They do not depend on Python/JS/Kotlin class names, import
aliases, paths, declaration order or display titles. Keep IDs stable when moving
code; use a new versioned ID for incompatible payload changes. Values are ephemeral
in A1: no persisted error/Result states, JSON decoding or migrations are promised.

```
fn checked(x: int) -> Result<int, ArithmeticError> effects pure = Ok(x) if x < 100 else Err(ArithmeticError.IntOverflow(left=x, right=1))
```

`Ok(value)` / `Err(typed_variant)` require a contextual Result type (function return
or parameter). User error pairs currently accept scalar int/text/bool successes.
No general user generics or implicit error conversions. The legacy
`Result<T, Error>` and try_add/try_chr/try_at remain unchanged; `Error` is opaque,
not a user-declared type. `result_ok` / `result_or` work on either family;
`result_code` is legacy-only. Explicitly match a legacy Result and construct a new
typed Err to adapt it; no automatic engine-fault-to-Result adapter exists.

```
action inspect:
    let result = checked(100)
    match result:
        Ok(value):
            total = value
        Err(IntOverflow { left, right: addend }):
            total = left + addend
```

Match evaluates once. Every Result must handle Ok. Closed errors require all
variants or a remaining `Err(error)`; open/legacy errors require a final
`Err(error)`. Duplicate variants, unreachable arms, unknown fields and binders
shadowing visible names are compile errors. A pattern may select a subset of
fields. `field: local` renames a binding; shorthand binds the same name. Bindings
are immutable and scoped to the arm. `error_id(error)` returns the stable
variant identifier without granting access to fields of an unknown variant.
Match is an action statement, not an expression or a multi-line function body.

Match uses the shared action IR, type checker, step/fuel budget and atomic
candidate-state transition. Static work takes the maximum branch; runtime reserves
selection plus expression cost and then charges executed statements. Imported
functions, payload construction and Unicode operations retain existing limits.
No file/network/Host/Server operation or Android permission is introduced.

Compiler JSON diagnostics retain the existing envelope and original locations.
New passes use SDR-E1201 (error type/constructor), SDR-E1202 (typed Result),
SDR-E1203 (match); message prefixes are E_ERROR_TYPE / E_RESULT / E_MATCH.
Other preexisting diagnostics keep their existing codes. Engine execution faults
remain execution diagnostics rather than Result payloads.

For Host A3, introduce separately reviewed typed adapters that translate only
registered expected faults; validate untrusted payloads and preserve the fatal
budget/policy/capability boundary. Server requires its own adapters, transport
codec and security tests. Stable IDs alone neither grant authority nor implement
a wire format. No Host/Server PR is integrated by this slice.

In A1 every wildcard Err arm is final, including closed errors. Constructors
evaluate named payload expressions in declaration-field order on all targets.

Compatibility of names: legacy user functions/record constructors named Ok, Err
or error_id retain lexical priority. New intrinsic calls require those names not
to be shadowed; a non-callable value/parameter binding is never silently ignored.
Pattern Ok/Err tags are grammar, not function calls. Existing primitive/value/
record naming rules are otherwise unchanged.

Effects resolves checked operation metadata before comparing user-function names;
a later legacy Ok/Err/error_id declaration cannot retroactively change an earlier
builtin binding. Malformed operation metadata is rejected, not assumed pure.

Core records the checked root type of each expression. WebApp consumes those value
types without re-resolving earlier bindings against later declarations. See the
real modular WebApp at examples/typed_errors_modules_012/site.sdr.

CLI `run` can print ephemeral derived Error/Result values as diagnostic JSON:
errors use `{id, variant, fields}`, typed success uses `{value, code:"", error:null}`,
typed failure `{code:"", error:{...}}`; legacy errors retain `{code:"INT_OVERFLOW"}`.
This projection mirrors the generated JS value carriers, not Python class names.
It is not a persistent/transport schema or a decoder: snapshots still contain only
declared persistent state, and Result/error state declarations remain unsupported.
