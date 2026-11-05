# Bounded core + namespaces integration (experimental 0.12)

Unpublished 0.12.0a1, Android versionCode 12001. Based on #47, retaining the history
and contracts of #50/#51. No stable release, server adapter or package publication.
[Русский](CORE_NAMESPACES_012.ru.md) · [Evidence](CORE_NAMESPACES_012_STATUS.md).

## One checked language

`examples/modules_core_012/main.sdr` builds an app for Web and Android. Its sibling
`site.sdr` is the WebApp presentation of the same imported model. Neither needs
manual HTML/JS/Kotlin changes. Existing site, app, WebApp and legacy imports remain.

```sdr
module sample.counter
export state numbers: list<int>(max=4) = [3, 1, 2]
export state total = 0
persist numbers
persist total
export action scan:
    total = 0
    for index, value in numbers:
        total = total + value
        numbers = list_replace_at(numbers, index, value * 2)
```

An entry imports this file with `import "counter.sdr" as counter`, then uses
`value counter.total` and `button "Scan" -> counter.scan` in an app screen. WebApp
uses `value counter.total` and `button "Scan" action counter.scan` in a view.
`sedrava run main.sdr counter.scan` resolves the same explicit public action.

Modules now declare record/fn/component/style **and state/derive/action**. Any
symbol is private unless marked export. `persist name` refers to an owned state.
Module actions/derived expressions may use their own symbols or explicit public
imports, never capture entry-app state. Functions remain pure checked expression
functions; their bodies do not acquire a separate statement interpreter. Bounded
loops are in ordinary actions. There is no implicit action execution on import.

Parameter/local/loop bindings are hygienically lowered, with scoped lifetime.
Adding an unrelated entry state cannot capture a module parameter or let variable.
Shadowing a module declaration/import alias is rejected. Module import graphs are
acyclic, deduplicated and topologically ordered. Imported state/derive/action
blocks are scheduled at the domain declaration boundary without legitimizing an
invalid ordering in the entry file. Forward function calls/recursion remain
unsupported. All definitions are checked, including private and unused ones.

Every imported function uses the same types: exact-capacity scalar/record lists,
nominal records, primitive types and ephemeral `Result<T, Error>`. The first-order
Result and list restrictions from [A2](CORE_012_A2.md) remain; modules do not add
nested collections, arbitrary errors or persistence of Result.

## Limits and stable storage

The shared core checks the entire expanded program: function/record/state counts,
source and AST limits, nested loops, callback/function expansion and invariant
costs. There is no per-module reset of the action budget. The 1,000,000 work-unit
and 10,000 statement limits apply across nested imported calls. Unicode 15 tables,
1024-scalar text limits and exact int32 operations are shared by all targets.
Namespace graphs additionally allow at most 32 modules/depth 16, with 100,000
aggregate source characters and 100,000 characters after lowering/instantiation.
These conservative bounds can reject a program smaller in its current state.

The stable symbol identity comes from the declared module identity and symbol,
not its entry alias. Renaming an alias preserves the storage fingerprint and IDs;
renaming a module/state/record or changing type/capacity can reject saved state.
No automatic migration. Rejected bytes remain protected from subsequent writes.
Private names control source resolution, not confidentiality: browser code and
local storage are observable. No secrets/authentication guarantee is added.

## Diagnostics and trust boundaries

Each lowering replacement carries a character map to the original file. Type,
syntax and Python execution failures refer to the actual nested module path,
line and scalar character column, including after long mangled names, typed
parameter signatures and component substitutions. JSON diagnostics preserve the
original location and compile/execute phase. Unknown-identifier matching excludes
quoted literals, field labels and comments. A failure inside an imported function
reports that function body rather than inventing a caller location.

Some whole-program errors have only a declaration/file location; this is lexical
lowering, not a native multi-file typed-IR debug symbol table. Generated applications
show controlled runtime error messages rather than embedding local developer paths.
Internal M_/L_ generated identifiers cannot be supplied in namespaced source or
CLI action arguments. Non-ASCII identifier tokens reject instead of silently
normalizing to a private ASCII symbol; Unicode text literals are unaffected.

## Locked local packages

No remote registry or code execution by import. Only reviewed local packages in
vendor/ with exact versions and SHA-256 locks are supported. Verification precedes
compilation. A vendor import must be covered by the verified lock, and the actual
source bytes read are checked again against its captured digest. Traversal,
symlinks, cycles, extra/unlocked package files and reserved-name access reject.
Bool/float/NaN are not integer lock schema values. Oversized lock generation fails
before replacing the old file. SHA-256 is content pinning, not an author signature;
`sedrava lock` is an explicit review/update operation, not a trust oracle.

## Reproduce

```
sedrava check examples/modules_core_012/main.sdr
sedrava test examples/modules_core_012/main.sdr
sedrava run examples/modules_core_012/main.sdr model.scan
sedrava build web examples/modules_core_012/main.sdr --output build/modules/index.html
sedrava build android examples/modules_core_012/main.sdr --output build/modules-android
sedrava build webapp examples/modules_core_012/site.sdr --output build/modules-webapp
```

Output paths cannot replace imported inputs or contain source directories. Installed
wheel/sdist include both this modular project and the locked package example.
Tests run actual generated JS, compiled Kotlin, three browsers and API35 Compose;
consult the evidence journal/PR for exact SHA and actual results, not assumptions.
