# IR 1.0 Candidate.1 — проверяемый первый срез

**Статус: экспериментальный, НЕ стабильный публичный ABI.**

Этот PR вводит отдельный контракт для скалярного одноэкранного app-mode.
Полная Sedrava остаётся за пределами текущего IR. Задача: #65.

## Команды

    sedrava-native ir-candidate examples/counter.sdr
    sedrava-native build web-ir examples/counter.sdr --output /tmp/counter.html

Прежние команды ir и build web не меняют поведения.
Новый Web consumer использует только структурированный JSON IR
(schema, version, coverage, program, diagnostics), не обращаясь к AST.

JSON Schema: schemas/ir/app-1.0-candidate.1.schema.json.
Golden: tests/ir_candidate/counter.json.
Проверка: python3 scripts/verify_ir_candidate.py --binary PATH.

## Включено

- Состояния int32, bool, text с явными типами и начальным значением.
- Атомарные действия assign и require; общие инварианты rule.
- Выражения: literal/reference/unary/binary/conditional.
- Экран с text, value и button.
- Частичная карта мест в исходнике для верхнеуровневых объявлений.

## Не включено

derive, persist, чистые функции, records/collections, вызовы функций,
навигация, несколько экранов, let/branch/match, расширенный UI, Site,
WebApp, Android, Host и Server. Каждая неподдерживаемая конструкция
отвергается явной ошибкой E_IR_CANDIDATE_UNSUPPORTED. Действующий
генератор build web продолжает работать напрямую с Program.

## Порядок эволюции

1. Candidate-версии допускают ломающие изменения и требуют нового golden.
2. Смысловая часть IR отделена от диагностики. Source spans отдельных
   выражений будут добавлены, не меняя смысловое представление.
3. Потребители обязаны проверять schema/version/coverage и неизвестные узлы.
4. JSON Schema описывает формат, а не типовую согласованность или
   семантическую корректность программы. Web-генератор первого этапа
   принимает только IR из проверенного компилятора Rust.
5. Затем: нормализованные записи/коллекции, source spans выражений,
   перенос существующего Web-генератора на IR и перенос Android.

## Приёмка

- cargo fmt --check; cargo test --locked.
- Сверка golden и детерминированного JSON.
- Проверка JSON Schema, если установлен Python jsonschema.
- Рабочая сборка web-ir и явные отказы на неподдерживаемом примере.
- Устаревшие команды и сборки не должны менять поведения.
- Не запускать дорогостоящие GitHub Actions на промежуточной работе.

