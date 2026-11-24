> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# Sedrava A5.1 — объединение лексических токенов и отступов

Дата: 23 ноября 2026. Исследование self-hosting на Sedrava;
**не полный лексер, не общий парсер, не компилятор на самом себе**.

## Реализация

Файл examples/self_host/parser_a51.sdr — отдельная версия A4,
не изменяет опубликованный Python Sedrava 0.11 или Rust-ядро.

Реализованы три последовательных действия на собственном языке:

1. scan: токены ограниченного A3-подмножества с Unicode-scalar
   offset/end, 1-based line/column и типом оператора.
2. scan_layout: строго 4-пробельные отступы с NEWLINE/INDENT/DEDENT
   и уровнем вложенности, как в эксперименте A4.
3. merge_tokens: упорядочивает оба потока по начальной позиции.
   При совпадающем offset layout-токен располагается перед обычным,
   чтобы INDENT/DEDENT предшествовал первому токену строки.
   Результат — list<UnifiedToken> с kind, lexeme, offset, end,
   line, column, level. Для layout-токенов lexeme пустой,
   end равен offset (нулевая длина).

merge_tokens проверяет, что оба обхода завершили весь текст
и итоговый список первоначально пуст. Чтение исходных коллекций
выполняется по устойчивым ID записей, которые равны 1..N лишь
в первом свежем запуске без удаления записей.

## Проверки на VDS

    source "$HOME/.sedrava-dev/env.sh"
    sedrava_target
    cd "$HOME/.sedrava-dev/sedrava"
    "$CARGO_TARGET_DIR/debug/sedrava-native" check examples/self_host/parser_a51.sdr
    "$CARGO_TARGET_DIR/debug/sedrava-native" test examples/self_host/parser_a51.sdr
    SEDRAVA_NATIVE_BIN="$CARGO_TARGET_DIR/debug/sedrava-native" \
      python3 -B scripts/verify_selfhost_parser_a51.py

Независимый Python oracle берёт ожидаемые результаты от A3 и A4,
но actual merge выполняет Sedrava native CLI.
Результат: 91 допустимый / 10 отклонённых входов, точное
сравнение kind,lexeme,offset,end,line,column,level;
детерминированный повторный запуск и отказ при пропуске scan.

Также 81 Rust unit тест PASS, нативный компилятор сгенерировал
Kotlin/Android из A5.1, Gradle 8.11.1 успешно собрал настоящий
debug APK, подпись Android v2 проверена. SHA-256 APK:
3955bc76df109fe12797cde2894672c0751983eea8998cf91fdeba4898a28a72.
**На физическом смартфоне A5.1 ещё не проверялся.**

## Ограничения

- Один свежий тройной проход scan, scan_layout, merge_tokens.
  Пока это НЕ однопроходный лексер Rust и не эквивалентный ему поток.
- Максимальная длина исходника 256 Unicode-скаляров; итоговый
  поток до 100 токенов. Превышение должно отклоняться.
- Во время scan_layout нельзя TAB, CR, кавычки в коде.
  Поэтому строки и произвольные Unicode-идентификаторы здесь
  не объединяются с отступами; внутри комментариев действуют
  только ограниченные правила A4.
- Нет грамматики функций/типов/блоков, общего AST, диагностики
  ошибок компилятора, повторного reset, инкрементального ввода,
  recovery от синтаксических ошибок и самокомпиляции.
- А4 parse_binary остаётся отдельным экспериментом над A3 tokens,
  а не парсером нового UnifiedToken потока.

## Следующее

A5.2 — объединённый поток как единственный вход парсера,
строгое правило ID vs индекс, синтаксические узлы блоков и
выражений, дифференциальная проверка по Rust AST; затем A6.
