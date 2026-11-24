> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# Sedrava A2 — расширенный лексер на собственном языке

Дата: 23 ноября 2026. Экспериментальный шаг к self-hosting,
**не самостоятельный компилятор, не релиз 0.12 beta**.

## Что работает

В файле examples/self_host/lexer_a2.sdr реализован один action scan
с внутренним ограниченным while и операциями text_at, concat,
типизированным списком Token(kind,lexeme,offset). Rust исполняет
код Sedrava, Python ничего не токенизирует внутри приложения.

По сравнению с A1 поддерживаются:

- ASCII идентификаторы и целые десятичные литералы;
- Unicode в строковых литералах, включая кириллицу и эмодзи;
- двойные кавычки с экранированием обратного слеша, кавычки, n/t/r;
- пробел, табуляция, CR, LF;
- однострочные комментарии # до LF (кроме кавычек);
- отдельные знаки (){}[],:.+-*/=<>!, а также ==, !=, <=, >=, ->;
- позиции в индексах Unicode-скаляров, а не UTF-8 байтах.

В A2 нет парсинга деревьев, AST, полноценного Unicode-идентификатора,
дробных/экспоненциальных чисел, тройных кавычек, интерполяции,
многострочных комментариев и полной грамматики Sedrava. Имена
токенов некоторых операторов остаются kind=punct. Отступы, границы
строк и комментарии пока не выдаются отдельными токенами.

## Ограничения

- Один scan на исходную строку длиной <= 256 Unicode-символов.
- Максимум 100 токенов; превышение вызывает отказ.
- Число, непосредственно после которого идёт ASCII-буква или _,
  считается ошибкой этого подмножества.
- Строковый escape допускает только n, t, r, двойную кавычку и слеш.
  Unicode escape-формат вида backslash-uXXXX пока не реализован.
- Только один запуск action scan из исходного начального состояния.
  Нет API многократного сброса/сканирования потока.
- Скрипт не доказывает полную эквивалентность Rust токенизатору;
  Python является *независимым проверочным алгоритмом* подмножества.

## Подтверждённые проверки

    source "$HOME/.sedrava-dev/env.sh"
    sedrava_target
    cd "$HOME/.sedrava-dev/sedrava"

    "$CARGO_TARGET_DIR/debug/sedrava-native" check examples/self_host/lexer_a2.sdr
    "$CARGO_TARGET_DIR/debug/sedrava-native" test examples/self_host/lexer_a2.sdr
    SEDRAVA_NATIVE_BIN="$CARGO_TARGET_DIR/debug/sedrava-native" python3 scripts/verify_selfhost_lexer_a2.py
    SEDRAVA_NATIVE_BIN="$CARGO_TARGET_DIR/debug/sedrava-native" python3 scripts/verify_selfhost_lexer_a1.py
    cargo test --manifest-path rust/Cargo.toml --locked --offline --all-targets

Результаты VDS: A2 — 68 положительных / 16 отрицательных
примеров, строгие token.kind/lexeme/offset и повторяемость.
A1 прежний golden corpus — PASS. Все 81 native Rust тест — PASS.
Android Kotlin generated source прошёл полноценную сборку
Gradle 8.11.1/AGP 8.9.2/Kotlin 2.0.21/SDK35:
assembleDebug PASS, подпись APK проверена.
Тест на реальном телефоне для A2 **не выполнялся**.

WebApp генератор здесь не проверяется: этот исходник представляет
собой app, а не webapp и не предназначен для преобразования в webapp
без дополнительной работы с типом проекта.

## Следующий этап

Строгое разделение token kind и source spans,
расширенная классификация Unicode, многострочный scanner,
токенизация отступов и полное соответствие Rust lexer; затем
AST/парсер на Sedrava. Это отдельные этапы с собственными тестами.
