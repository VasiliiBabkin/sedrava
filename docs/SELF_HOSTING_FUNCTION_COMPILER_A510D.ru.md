> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# A5.10d — conditional returns and structured runtime fault subset

A5.10c block and expression bodies extended with one top-level `value if left < right else value` (or == comparison) in return expressions. Both arms are statically resolved and lowered, but only the selected arm executes. Comparison operands are int, result consumed only by branch; no general bool type, nested conditional, statement if/else, or conditional local initializer. Emit function-relative jz/jump and support terminating recursion within existing frame/instruction budgets. Structured runtime fault states `runtime_error`, `runtime_error_pc`, `runtime_error_function`, `finished=false` for CALL_DEPTH, INTEGER_OVERFLOW for add/sub, and STEP_BUDGET; not a complete diagnostic API. Multiplication overflow and other runtime guards still use inherited native failure behavior. Failed executions are not successful results; consumers must inspect finished/error, not just process exit. Experimental compiler, not main Rust frontend.

VDS: 5 valid source programs (factorial 5=120, selected branch only, locals and precedence), 3 structured fault cases, 7 invalid sources PASS. `scripts/verify_selfhost_function_compiler_a510d.py`.
