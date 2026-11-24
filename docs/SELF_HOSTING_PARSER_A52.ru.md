> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# Sedrava A5.2 — разбор программ из объединённых токенов

Дата: 24 ноября 2026. Экспериментальный этап self-hosting.

## Реализация

Файл examples/self_host/parser_a52.sdr содержит написанный на
Sedrava новый action parse_program. Он работает после Sedrava
scan → scan_layout → merge_tokens, получает настоящий массив
UnifiedToken A5.1 и строит ProgramAssignment AST.

Каждый узел сохраняет name и literal, depth (текущий уровень
INDENT/DEDENT, 0..8), line (номер исходной строки от 1),
start/end (полуоткрытые границы в Unicode-скалярах).

Грамматика намеренно узкая: последовательность строк с
ASCII-идентификатором и целочисленным литералом вида name = 123,
пустые строки, комментарии и четырёхпробельные отступы.
Для вложенности здесь пока НЕ требуется заголовок блока
action/route/if: это лишь прототип layout-aware AST, а не
валидатор полной грамматики Sedrava.

Лимиты: не более 256 Unicode-скаляров исходника, не более
100 объединённых токенов, не более 32 AST-присваиваний,
не более 8 уровней. Неполные строки, лишние операторы,
неправильные отступы и INDENT до первой строки отвергаются.
parse_program также отвергает запуск без завершённого scan/merge
и повторное построение AST в том же состоянии.

Важно: get(list,id) использует стабильный ID записи, а не
индекс массива. Поэтому проверяется свежий объединённый поток
из одного запуска с ID записей 1..N.

## Воспроизведение

    source "$HOME/.sedrava-dev/env.sh"
    sedrava_target
    cd "$HOME/.sedrava-dev/sedrava"
    "$CARGO_TARGET_DIR/debug/sedrava-native" check examples/self_host/parser_a52.sdr
    SEDRAVA_NATIVE_BIN="$CARGO_TARGET_DIR/debug/sedrava-native" \
      python3 -B scripts/verify_selfhost_parser_a52.py

Python — только независимый оракул ожидаемых AST и токенов.
Фактическое выполнение всех четырёх action происходит внутри
нативного Sedrava Rust-интерпретатора на исходнике Sedrava.

VDS: 30 допустимых + 22 недопустимых программы PASS.
Проверены поля AST, точные позиции Unicode-скаляров,
паритет объединённых токенов с A5.1 oracle,
детерминизм, правильные ID и отказ до merge/при повторе.
83 Rust unit tests Sedrava PASS.

## Ограничения

Не реализованы полная грамматика, диагностика по точным кодам,
произвольные выражения, типизация, AST функций, модульная
система, IR, генератор компилятора, self-hosting stage 1/2/3.
Android APK из A5.2 не создавался и не проверялся.
Это не публикация стабильной Sedrava 0.12.
