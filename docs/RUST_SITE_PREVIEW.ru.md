# Экспериментальный нативный Site DSL на Rust

**Статус:** исходники подготовлены в рамках задачи #65, но сборка и тесты этого изменения ещё НЕ выполнялись в текущей среде. Это **частичный перенос**, а не совместимый генератор Sedrava Site 0.11.

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

В последней доступной нам среде нет Rust/Cargo, поэтому нельзя честно отметить проверки PASS, пока они не будут выполнены на точном коммите. GitHub Actions для этого изменения не запускались намеренно.

**Приёмка:** при первом прогоне исправить ошибки компиляции и тестов, сверить вывод на независимой копии и зафиксировать конкретный SHA, затем продолжать расширение Site/WebApp; задачу #65 не закрывать.
