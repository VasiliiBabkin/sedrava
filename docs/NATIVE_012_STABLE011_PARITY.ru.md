> Historical milestone / Исторический этап. The current primary implementation is Rust. See [current guide](README.ru.md) and [history](HISTORY.md).

# Sedrava Native 0.12: проверка относительно опубликованной Python 0.11.0

Дата: 23 ноября 2026.
Статус: **пройдены ограниченные проверки совместимости Linux; стабильный 0.12 остаётся NO-GO**.

## Проверяемые исходники

- Строго опубликованный Python 0.11.0: тег v0.11.0, коммит
  c9cde75e3d2e2c7eafeeaec10c73fec627816e68.
- Версия нативного Rust CLI: 0.12.0-alpha.1, основа
  0abae76cf027b536fb2b29dc053182b9e92aceb2.
- Бинарник Linux x86_64, SHA-256:
  623e4d0f78ba688156247a20dd5f73628e3a96fdaad3baa3989acf4387d3e7f3.
- Перед сравнением проверен полный commit SHA тега и **297 файлов**
  эталонных исходников по Git object SHA1. Намеренно изменённый
  sedrava_cli.py был отклонён ещё до запуска тестов.

## Совместимость языка — PASS в ограниченном объёме

Скрипт scripts/verify_native_stable011.py использует два *разных*
процесса: реальный Python 0.11.0 из архива точного тега и
экспериментальный Rust CLI. Нет обращения к Python-эталону
из изменяющегося current main.

- 11 приложений, 7 Site/WebApp-примеров из опубликованного тега.
- 75 воспроизводимых псевдослучайных последовательностей действий
  на каждое app (seed 12011) плюс check/test/пустой run и
  отдельные actions.
- **898 сравнений: 666 успешных по Python, 232 отклонены Python;
  расхождений с Rust 0** по принятой проверке.
- Для успешного run сравниваются разобранные JSON-состояния;
  для test — точный stdout; для check — код принятия;
  для ошибок — только факт успешности/отказа обеими реализациями.

Одинаковый отказ не доказывает одинаковые классы ошибок или
смысл неуспеха. Тест не является proof of equivalence
для полного языка Python 0.11 и всех способов исполнения.

## Генерация Web — PASS без браузерного движка

scripts/verify_native_stable011_web.py для двух компиляторов
строит 7 реальных примеров опубликованного тега:
platform_site, web_ui_011_landing, platform_catalog,
platform_crm, platform_tasks, webapp_011_counter,
webapp_011_tasks.

Подтверждены локальные HTML/CSS/JS/шрифты, корректные пути
ресурсов, синтаксис сгенерированного JavaScript командой
node --check, идентичная повторная сборка Native и отказ
перезаписывать созданные файлы.

Дополнительно штатный scripts/verify_native_web.py прошёл
Node.js DOM-stub тесты состояния, правил, инпутов, списка,
навигации, сохранения, ошибок/повреждённых снимков.

Для более реалистичной модели событий установлен jsdom 27.2.0
в отдельный каталог VDS, и
scripts/verify_native_stable011_dom.js проверил четыре сценария:
счётчик и CRUD задач **в каждом** из двух WebApp-движков
(старый Python и новый Rust). Проверены клики, ошибки ввода,
выбор, переименование, удаление.
Это **не** настоящий Chromium/Firefox/WebKit.

Скрипт scripts/verify_native_stable011_browser.py подготовлен
для реального браузера с функциями прежнего теста
scripts/verify_native_web_011.py, но **НЕ запускался**.
Playwright удалось установить на VDS; загрузка самого
Chromium оборвалась по ECONNRESET на CDN.
Попытка передать статический комплект для теста на
отдельной изолированной машине также не завершилась
из-за ограничений передачи. Browser gate остаётся BLOCKED.

## Настоящий Kotlin/JVM — PASS, Android APK — NOT TESTED

Использован ранее сохранённый на VDS Gradle 8.11.1,
Kotlin/JVM plugin 2.0.21. Скрипты
scripts/verify_native_android_kotlin.py и
scripts/verify_native_android_typed_result.py действительно
скомпилировали и исполнили Kotlin-код, сгенерированный Rust.

- Navigation, query, scalar/Unicode, проверка сохранения и
  восстановления состояния; сериализация передаётся в Rust и
  Python без расхождения.
- Типизированные Result/Error, правила payload, ошибки и
  атомарный откат успешно исполняются в Kotlin/JVM.

Android SDK и эмулятор на этом VDS не были доступны, поэтому
**не** заявлена сборка APK, установка на телефон или проверка Compose.

## Воспроизведение

Пример Linux с текущим git main и rustc/cargo:

    git fetch origin refs/tags/v0.11.0:refs/tags/v0.11.0
    mkdir -p /tmp/sedrava-published-011
    git archive v0.11.0 | tar -xf - -C /tmp/sedrava-published-011
    cargo build --manifest-path rust/Cargo.toml --locked --release --bin sedrava-native
    python3 scripts/verify_native_stable011.py --stable-root /tmp/sedrava-published-011 --native rust/target/release/sedrava-native --seed 12011 --random-cases 75
    python3 scripts/verify_native_stable011_web.py --stable-root /tmp/sedrava-published-011 --native rust/target/release/sedrava-native --keep-output /tmp/sedrava-web011-fixtures
    npm install --prefix /tmp/sedrava-dom-tooling --no-save --ignore-scripts jsdom@27.2.0
    SEDRAVA_JSDOM_PATH=/tmp/sedrava-dom-tooling/node_modules/jsdom node scripts/verify_native_stable011_dom.js /tmp/sedrava-web011-fixtures

Для настоящего браузера (если локально установлен Chromium
и Python Playwright) существует отдельный раннер:

    python3 scripts/verify_native_stable011_browser.py --root /tmp/sedrava-web011-fixtures --chromium /usr/bin/chromium

Раннер — подготовленное испытание; по итогам текущей проверки его
успешное прохождение **не** утверждается.

## Машинные отчёты

- [898 сравнений с опубликованной 0.11](../evidence/native-012/stable011-parity.json)
- [7 проверок сборок Site/WebApp](../evidence/native-012/stable011-web-builds.json)
- [Лог четырёх jsdom-сценариев](../evidence/native-012/jsdom-webapp-smoke.txt)

Все проверки выполнялись на временных данных. Эти отчёты
подтверждают только перечисленные сценарии; каждый новый релиз
должен проверяться заново.

## Релизный вывод

Rust можно использовать в качестве самостоятельного экспериментального
компилятора в указанных проверенных режимах.
Официальным стабильным релизом пока остаётся Python 0.11.0.

До решения о native 0.12 beta/stable остаются:

1. Настоящий Chromium, Firefox и WebKit на итоговых Site/WebApp.
2. Генерация APK, JVM/Compose, установка, обновление/откат на
   совместимых Android-устройствах.
3. Windows и macOS нативные сборки и независимые smoke tests.
4. Остальные конструкции языка, диагностика ошибок, миграция
   пользовательских проектов и полная матрица 0.11 совместимости.
5. Security-review Host/Server/DB, воспроизводимые релизные
   артефакты и отдельное утверждение публикации.

Все эти ограничения — действующие NO-GO для стабильного 0.12.
GitHub Actions не запускались. Работающие VDS-сервисы не менялись.
