# Экспериментальный нативный Site DSL на Rust

**Статус:** проверенный экспериментальный фрагмент задачи #65 (см. [отчёт](../evidence/rust-core/2026-11-22-stage7-site.md)). На точном SHA 0c95a31 прошли Cargo fmt/build, 43 Rust-теста, Site CLI smoke и документационная проверка. Это **частичный перенос**, а не совместимый генератор Sedrava Site 0.11.

## Что добавлено

Экспериментальная команда:

~~~sh
cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava-native
./rust/target/debug/sedrava-native check examples/site_native_preview.sdr
./rust/target/debug/sedrava-native build site examples/site_native_preview.sdr --output build/native-site-preview
~~~

Только на новом, ранее не существовавшем каталоге output. Генератор не должен менять существующие файлы. Результат — index.html и guide/index.html с экранированными пользовательскими строками. Python для генерации HTML не вызывается.

Поддерживаемая **строгая ограниченная грамматика**:

- site "name" и page identifier at "/path/":; обязательный title, необязательный description.
- Блочные элементы container:, row:, column:, grid:, card:, navbar:, footer:, callout:. Отступы строго по 4 пробела.
- heading "...", paragraph "...", code "...", divider, link "..." to "/path/", button "..." to "/path/".
- Внутренние ссылки на страницы и якоря, внешние https://-ссылки; экранирование HTML в тексте и атрибутах.
- Неподдерживаемые параметры и директивы приводят к ошибке, а не к частичной невидимой потере содержимого.
- Ограничения на число страниц, глубину и размер исходника.

## Что не поддерживается

**Не компилирует** существующие полные примеры web_ui_011_landing.sdr или platform_site.sdr: ещё нет тем, стилей, компонентов/макросов, import, assets, изображений, метаданных origin/robots, markdown, responsive props, классов, форм, виджетов и продвинутых HTML-возможностей.

Это намеренное поведение: генератор никогда не должен притворяться совместимым, незаметно пропуская неподдерживаемые конструкции. Прежний Python Site остаётся эталоном.

## Проверки после установки Rust/Cargo

~~~sh
cargo fmt --manifest-path rust/Cargo.toml --all -- --check
cargo test --manifest-path rust/Cargo.toml --locked --all-targets
cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava-native
python3 scripts/verify_native_site.py
python3 scripts/verify_rust_core.py --random-cases 24
python3 -m unittest discover -s tests -q
~~~

Проверки выполнены 22.11.2026 на изолированной установке Rust/Cargo 1.100.0 на VDS Linux. Подтверждены 43 Rust-теста, 390 выборочных сравнений Python/Rust (без найденных расхождений), 14 snapshot-проверок и 274 Python-теста (5 skipped). Сравнения не доказывают полного соответствия языка. GitHub Actions не запускались намеренно.

**Дальнейшая приёмка:** проверить расширение Site/WebApp на оригинальных примерах 0.11 и реальных браузерах, провести независимую проверку безопасности. Не считать #65 закрытой.
