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
Each type has 1..16 variants, each has 0..16 distinct int/text/bool fields; at most
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
