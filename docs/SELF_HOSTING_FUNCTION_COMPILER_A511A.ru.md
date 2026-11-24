# A5.11a — while loops and mutable locals

Extends the separate self-hosted A5.10d source compiler with four-space function bodies and eight-space single-level `while` bodies. Conditions use one integer comparison `<` or `==`; bodies contain assignments to previously declared locals only. Parameters are read-only, no shadowing, declarations inside loops, nested loops, break/continue or early return inside loops. The compiler emits a conditional forward jump and backward jump, with the same stack VM and global 256-instruction limit. Assignments also work outside loops. A5.10d recursive functions and conditional returns are retained. Scope and source budgets remain experimental; not the main Rust frontend or a full type-system upgrade.

VDS: 6 valid source programs including summation, iterative factorial and sequential loops; 7 invalid programs; infinite loop stops with STEP_BUDGET. Test: `scripts/verify_selfhost_function_compiler_a511a.py` using SEDRAVA_NATIVE_BIN.

VDS: 83 Rust tests and all A10–A21/B15a server/database regressions PASS against SedravaSQL 49fbaf5240b3fd3c63e6ce3c828ea280b46ff3a7.
