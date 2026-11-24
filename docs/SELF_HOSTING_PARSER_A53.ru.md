> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# Sedrava A5.3 — AST арифметических выражений из объединённого потока токенов

Дата: 24 ноября 2026. Статус: экспериментальный шаг к self-hosting, **не полноценный компилятор**.

## Реализовано

Программа examples/self_host/parser_a53.sdr расширяет A5.2 и содержит
написанное **на Sedrava** действие parse_expression_program.
Оно потребляет настоящий массив UnifiedToken, полученный другими
Sedrava-действиями scan, scan_layout и merge_tokens, и создаёт:

- ProgramExpression: name, expression_id, depth, line, start/end;
- ExprNode: kind (integer/binary), lexeme, operator, left_id,
  right_id, start/end;
- сохранение стабильных ID AST-узлов и полуоткрытых диапазонов
  символов (Unicode scalar offsets).

Узкая грамматика одного присваивания: имя, знак равенства и
**1–3 целочисленных литерала**, разделённых операторами
+ - * /. Пример: result = 2 + 3 * 4. Умножение и деление
имеют приоритет перед сложением и вычитанием; одинаковый
приоритет обрабатывается **слева направо**. Расстановка
скобок, унарные знаки, вызовы функций, переменные RHS,
произвольное число операндов и полная грамматика
Sedrava пока не реализованы.

Сохраняется экспериментальное правило 4 пробела на уровень
INDENT/DEDENT, комментарии и пустые строки. Для вложенности
прототип ещё не требует корректного action/if/route-заголовка:
это НЕ проверка блоков реального языка.

Ограничения: вход до 256 Unicode-скаляров, объединённый поток
до 100 токенов, до 100 узлов выражений, до 16 операторных
присваиваний, глубина layout не выше 8. Операция
parse_expression_program запрещена до завершения слияния
и повторно в той же сессии.

## Как проверить

    source "$HOME/.sedrava-dev/env.sh"
    sedrava_target
    cd "$HOME/.sedrava-dev/sedrava"
    "$CARGO_TARGET_DIR/debug/sedrava-native" check examples/self_host/parser_a53.sdr
    SEDRAVA_NATIVE_BIN="$CARGO_TARGET_DIR/debug/sedrava-native" \
      python3 -B scripts/verify_selfhost_parser_a53.py

В Python строится только независимый oracle ожидаемых
токенов, AST-узлов, приоритетов и исходных позиций;
**все четыре действия выполняются именно на Sedrava**
нативным Rust-интерпретатором.

VDS: 37 принятых / 23 отклонённых программ PASS.
Проверены AST и порядок дочерних ID, left-associativity,
арифметический приоритет, отступы, позиции Unicode-скаляров,
совпадение UnifiedToken с A5.1 oracle и отказ от ошибочных
конструкций. Rust Sedrava: 83 unit tests PASS.

## Что дальше

A5.4: убрать фиксированное ограничение трёх операндов,
добавить скобки, AST заголовков блоков и структурированные
диагностики, не ослабляя детерминированность. Создание
stage 1/2/3 компилятора на Sedrava НЕ выполнено; Android APK
не собирался. Bootstrap всё ещё использует Rust; самокомпиляция
не объявляется достигнутой.
