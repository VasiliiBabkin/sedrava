# Effects A1 recovery / Восстановление Effects A1

Base: 8d677b8c62d994ff8ff0a6f2b5af94a7ae7ec3cb (PR #55).
The failing fixtures called user functions in state initializers and used an
unsupported block test declaration. Corrected to literal initial state, function
calls in actions, and `test name: actions -> condition`. No grammar expansion.
Added negative regressions for both legacy and `effects pure` initializers and
block tests. Existing effect graph tests remain enabled. Final CI is recorded in
PR #55; its old red runs are preserved, not represented as successful.

Ошибочные примеры исправлены по действующему контракту: вызовы функций выполняются
в действиях, тесты используют `test name: actions -> condition`. Грамматика не
изменена. Проверки запрещённых инициализаторов и блочных тестов добавлены явно.
