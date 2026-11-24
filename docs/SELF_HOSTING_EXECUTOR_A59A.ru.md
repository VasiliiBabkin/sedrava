> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# A5.9a — исполнитель собственного IR

`examples/self_host/executor_a59a.sdr` — Sedrava-authored extension of A5.8a/b, preserving previous example. Runs scan/layout/merge/declarations/validation/AST/typecheck/lowering/execute_flat inside Sedrava runtime. Registers are the emitted Instruction records with int/bool values; symbol table stores scalar initializer and current value. Executes one flat action, sequential assignments, int32 checked arithmetic + - *, unary minus/not, comparisons and group aliases. Each subsequent assignment sees previous changes. Integer literal conversion rejects out-of-range input before multiplication. Runtime rejects overflow and invalid program; no successful execution result for rejected run. Explicitly rejects branches, calls, short-circuit and/or, text and multiple actions; not a full backend or independent executable compiler. Limits inherited from A5.8. Future A5.9b control-flow and scoped function execution.

VDS: 5 accepted programs compared with independent expected state; 7 overflow/unsupported programs rejected; 2 execution guards PASS. Run scripts/verify_selfhost_executor_a59a.py with SEDRAVA_NATIVE_BIN pointing to native release binary.
