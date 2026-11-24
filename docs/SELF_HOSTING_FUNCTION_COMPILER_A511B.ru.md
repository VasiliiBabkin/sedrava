# A5.11b — вложенные циклы и условные блоки

Experimental self-hosted compiler extends A5.11a with up to two nested control blocks (`while` and `if`), using four-space indentation increments. Conditions use a single integer comparison `<` or `==`; assignments target existing mutable locals. Each active block stores a branch patch, entry PC and nonempty-body flag; dedentation emits a backward jump for while and patches the forward conditional jump. No declarations in nested blocks, statement else, break/continue, early return or nesting beyond two. Conditional return expressions and recursive calls from A5.10d remain supported. Existing source and 256 VM instruction budgets apply. Not the main frontend.

VDS: six valid programs, five invalid sources, nested infinite loop stopped with STEP_BUDGET. Test: scripts/verify_selfhost_function_compiler_a511b.py.
