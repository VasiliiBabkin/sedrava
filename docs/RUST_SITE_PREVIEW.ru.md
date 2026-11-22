# Экспериментальные Site и WebApp на Rust

Нативный генератор поддерживает многостраничный Site и автономный WebApp из
Sedrava 0.11. Python 0.11 остаётся эталоном совместимости. Для каждого
запуска генератора укажите новый каталог назначения.

~~~sh
cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava-native
./rust/target/debug/sedrava-native check examples/platform_site.sdr
./rust/target/debug/sedrava-native build site examples/platform_site.sdr --output build/native-site
./rust/target/debug/sedrava-native check examples/webapp_011_tasks.sdr
./rust/target/debug/sedrava-native build webapp examples/webapp_011_tasks.sdr --output build/native-tasks
python3 -m http.server --bind 127.0.0.1 --directory build 8080
~~~

Сервис раздаёт `/native-site/index.html` и `/native-tasks/index.html` по
loopback HTTP для проверки в браузере. Для WebApp это даёт нормальный origin
для загрузки скрипта и работы `localStorage`. Компиляция обеих целей выполняется
в нативном бинарнике.

## Что входит в срез

- Site с темами, именованными стилями, адаптивными свойствами, семантическими
  элементами, относительными ссылками, проверяемыми якорями, изображениями,
  локальными CSS/шрифтами, лицензиями, метаданными, sitemap и robots.
- Локальные импорты компонентов и стилей, в WebApp также функций и типов record.
  Компоненты разворачиваются с типизированными аргументами и одним слотом.
  Импорты ограничены исходным каталогом. Symlink, циклы и выход за корень
  отклоняются.
- WebApp с проверяемым состоянием, вычисляемыми значениями, действиями, вводом,
  флажками, списками, шаблонами строк, таблицами, формами, диалогами и
  именованными темами. Маршруты поддерживают целочисленные параметры,
  булевы guards, переходы назад и прямые ссылки по fragment URL.
- WebApp использует общий с app-mode генератор логики и код схемы 1. Состояние
  изменяется после проверки типов, правил и, при наличии `persist`, записи
  сохранения. Ошибка записи или повреждённое сохранение блокируют изменение.
  HTML, CSS, JavaScript и локальные ресурсы записываются в отдельные файлы.
  Генерация завершает проверку до публикации каталога.

## Границы совместимости

Для `platform_catalog.sdr` доступен [нативный same-origin HTTP](RUST_HTTP_HOST.ru.md).
Пакеты, locks, сетевой импорт, полный Android и диагностика уровня Python
остаются за пределами этого переноса. Для нативного CLI требуется новый каталог.
Управляемая перегенерация и файлы-манифесты Python пока отсутствуют.

Нативный WebApp использует собственный ключ `localStorage` и для скалярных
программ пишет схему 1. Автоматическая миграция браузерных данных Python
отсутствует. Сравнение старого значения перед записью обнаруживает изменения
из другой вкладки, но не обеспечивает атомарную многовкладочную транзакцию.
Проверки файлового ввода и публикации выполнены в Linux. Для macOS,
Windows, Firefox и WebKit требуется отдельная приёмка.

## Проверки

~~~sh
cargo fmt --manifest-path rust/Cargo.toml --all -- --check
cargo test --manifest-path rust/Cargo.toml --locked --all-targets
cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava-native
python3 scripts/verify_native_site.py
python3 scripts/verify_native_web.py
python3 scripts/verify_native_web_011.py
python3 scripts/verify_rust_core.py --random-cases 24
python3 scripts/verify_rust_snapshot.py
python3 -m unittest discover -s tests -q
~~~

Для `verify_native_web_011.py` нужны установленный Python Playwright и
Chromium. При необходимости путь к браузеру задаётся через
`SEDRAVA_CHROMIUM`. Скрипт собирает оригинальные примеры обоими
компиляторами, поднимает loopback HTTP и проверяет один набор ожидаемых
результатов для обеих сборок. Включены адаптивные сетки, переходы,
встроенный шрифт, отказ правила, CRUD, сохранение, формы, таблицы,
модальные диалоги, смена темы и отрицательные сценарии безопасности.

Полная матрица остаётся в [карте миграции](RUST_FULL_MIGRATION.ru.md).
