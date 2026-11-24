> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# Sedrava A3 — позиции токенов и первый AST-узел

Дата: 23 ноября 2026. Экспериментальный этап, **не самокомпиляция**.

## Реализация в исходном Sedrava

examples/self_host/lexer_a3.sdr — независимая копия A2, где:
- Token содержит kind, lexeme, offset, end, line, column.
- offset: индекс начального Unicode-скаляра, считая с нуля.
- end: исключающая правая граница в Unicode-скалярах.
- line и column: номера строки и столбца, начиная с единицы.
  LF начинает новую строку; CR и TAB считаются по одному символу,
  не как экранная ширина с табуляцией.
- Пунктуация разделена на kind=operator (+-*/=<>! и
  составные ==, !=, <=, >=, ->) и kind=punct (скобки, запятая).
- Strings, escapes, комментарии, лимиты из A2 сохранены.
  Строки содержат исходные escape-последовательности в lexeme,
  не декодированный runtime text.

Отдельный action parse_assignment реализован на самой Sedrava:
он проверяет ровно три токена с паттерном
identifier = integer и добавляет один типизированный AST-узел
Assignment(name, literal, start, end).

Важно: get(tokens, K) принимает **устойчивый ID записи**, а не
индекс массива. Здесь ID 1,2,3 гарантируются только для первого
свежего scan, и не являются API произвольного AST-парсера.
Нет многократного reset, сканирования потоков, полноценного
парсера выражений, построения Rust AST/IR, проверки типов,
генерации кода или самосборки.

## Проверка на VDS

    source "$HOME/.sedrava-dev/env.sh"
    sedrava_target
    cd "$HOME/.sedrava-dev/sedrava"
    "$CARGO_TARGET_DIR/debug/sedrava-native" check examples/self_host/lexer_a3.sdr
    "$CARGO_TARGET_DIR/debug/sedrava-native" test examples/self_host/lexer_a3.sdr
    SEDRAVA_NATIVE_BIN="$CARGO_TARGET_DIR/debug/sedrava-native" python3 -B scripts/verify_selfhost_lexer_a3.py

Независимый внешний oracle из A2 используется лишь для проверки
исходного набора токенов. Позиции вычисляются независимо по
Unicode-индексам в Python. Реальное сканирование и построение AST
делает Sedrava через Rust native CLI; Python не вычисляет результат
для приложения.

Результат: 112 принятых и 19 отвергнутых входов;
6 принятых и 9 отвергнутых присваиваний AST;
строгое сравнение kind/lexeme/offset/end/line/column,
повторяемость, транзакционный отказ при ошибках.
Регрессии A1 и A2 — PASS, 81 Rust unit тест — PASS.

### Android source acceptance на VDS

Нативный Rust CLI сгенерировал Android проект из
examples/self_host/lexer_a3.sdr. Gradle 8.11.1 / Kotlin 2.0.21
/ Android SDK 35 выполнил assembleDebug: BUILD SUCCESSFUL.
Подпись отладочного APK проверена Android Build Tools. SHA-256:
9eaca2f75e1794d590cbb4e70d49ff27f29bd63f62f8824585389cd8e392098b.
Это НЕ проверка исполнения лексера A3 на реальном смартфоне;
проект для теста на VDS, не релиз для магазина.

## Ограничения

- Максимум 256 Unicode-скаляров и 100 токенов.
- Только ASCII идентификаторы и целые литералы в assignment AST.
- Нет полного лексера грамматики Sedrava, Unicode-идентификаторов,
  значимых отступов и токенов NEWLINE/INDENT/DEDENT.
- Нет обобщённых выражений, проверок операндов/типов, вложенных AST,
  ошибок с диагностикой span для компилятора.
- Поведение на реальном Android должно проверяться отдельно,
  даже если генерация/компиляция APK прошла.

## Следующая цель A4

Разделение сканера/парсера на повторно используемые компоненты,
токены NEWLINE/INDENT/DEDENT, полноценная span-диагностика,
собственные AST выражений и независимые тесты семантической
эквивалентности с действующим Rust-компилятором.
Это ещё НЕ реализовано.
