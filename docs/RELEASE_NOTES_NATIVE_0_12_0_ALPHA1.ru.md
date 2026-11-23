# Sedrava Native 0.12.0-alpha.1 — предварительный кандидат

Дата: 23 ноября 2026. Статус: проверенный на VDS Linux x86_64
экспериментальный кандидат, НЕ опубликованная стабильная версия.

Стабильный продукт по-прежнему Sedrava 0.11.0 (Python, PyPI).
Rust-продукт использует отдельную команду sedrava-native и версию
0.12.0-alpha.1. Команда sedrava не меняется.

## Что уже реализовано в нативном Rust

Парсер/типизация, действия, тесты, записи, ограниченные коллекции,
функции, навигация, экспериментальные Web/Site/WebApp/Android
генераторы, ограниченный файловый Host API, loopback Server A6 с
SQLite/SedravaSQL и read-only db_get. В самом языке есть экспериментальные
Unicode text_at и ограниченный while для собственного лексера A1.
Это не означает полной совместимости с Python 0.11.

## Как собрать

    cargo build --manifest-path rust/Cargo.toml --locked --release --bin sedrava-native
    ./rust/target/release/sedrava-native --version

Из исходников можно упаковать Linux preview:

    python3 scripts/package_native_preview.py --binary rust/target/release/sedrava-native --output build/native-previews

Формат имени архива: sedrava-native-VERSION-RUST_HOST.tar.gz.
Версия проверяется по фактическому ответу бинарника и Cargo.toml.
Только архив, собранный из ЧИСТОГО зафиксированного коммита,
может рассматриваться для выдачи.

Установка уже готового, независимо скачанного архива с проверенным SHA:

    sh scripts/install_native_preview.sh /absolute/file.tar.gz REAL_SHA256 "$HOME/.local"
    "$HOME/.local/bin/sedrava-native" --version

На машине установки не нужны Python, pip, Rust или Cargo; нужен только
совместимый готовый бинарник, POSIX shell и стандартные утилиты.

## Подтверждённые проверки на VDS

Ubuntu Linux x86_64, rustc/cargo 1.100.0, Python 3.12 как тестовый
инструментарий:

- Rust unit: 81/81 PASS.
- Дифференциальные сравнения 13 подобранных программ:
  390 запусков, из них 227 допустимых, 163 отклонённых,
  0 расхождений (только сравниваемая часть языка).
- Семь приёмочных сценариев: app, внутренний лексер,
  ошибочные программы, Site, WebApp, Android КОД, server check — PASS.
- Отдельные Host проверки и A6: 46 HTTP записей, replay,
  CAS, 4 debug crash windows и db_get — PASS.
- Release build Linux и офлайн-установка без Python/Rust,
  повторяемая упаковка одного бинарника, отказ при неверном хэше,
  постороннем файле/симлинке и перезаписи — PASS.

## Что НЕ готово

Нет подтверждённой установки APK и Android device acceptance.
Нет сборок и тестов Windows/macOS. Нет полной матрицы совместимости
Python 0.11 и Rust, охвата браузеров и подтверждения production Host/DB.
Архив не подписан. Конкретный SHA и опубликованные release assets
должны определяться отдельно после чистой сборки.

Стабильный выпуск 0.12.0, замена бинарника sedrava, изменение
PyPI и автоматическое переключение работающих проектов НЕ разрешены
данными результатами.

[Матрица](NATIVE_012_ALPHA_ACCEPTANCE.md) ·
[Перенос Rust](RUST_FULL_MIGRATION.ru.md) ·
[Распространение](DISTRIBUTION_NATIVE.ru.md).
