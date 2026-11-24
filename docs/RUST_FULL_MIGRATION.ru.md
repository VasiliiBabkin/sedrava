> Historical milestone / Исторический этап. The current primary implementation is Rust. See [current guide](README.ru.md) and [history](HISTORY.md).

# Sedrava → Rust: полный перенос языка

**Статус документа: 22 ноября 2026 г.** Это карта миграции, не объявление
готовности компилятора. Рабочая версия Python (Sedrava 0.11.0) остаётся
доступной и не заменяется автоматически. Собранный бинарник Rust пока
предназначен исключительно для экспериментов и конформанс-тестов.

## Цель

Создать самостоятельную реализацию *всего* действующего контракта Sedrava на
Rust: парсер, типы, интерпретатор, генераторы Web/Android и серверные
режимы, модули, ресурсы, безопасные эффекты и инструменты разработки.
Отдельная СУБД SedravaSQL продолжит развитие после окончания этой миграции.

**Принцип приёмки:** возможность есть только тогда, когда она реализована,
проверена на релевантных примерах и имеет явные ограничения.

## Карта покрытия

| Возможность | Native Rust | Ограничения |
| --- | --- | --- |
| UTF-8, int32, bool, text, базовые выражения | Реализовано | Выборочные совместимые примеры |
| Unicode scalar limits и переполнение int32 | Реализовано | Нужны дополнительные property/fuzz-тесты |
| state, derive, let, require, rule, action, test | Реализовано | Пока без source spans уровня Python |
| Типизированные records | Реализовано | Поля int/bool/text, до 16 полей |
| Коллекции record и стабильные ID | Реализовано | max 1..100, без общего хранилища |
| append/get/has/update/remove/count/next_id | Реализовано | Проверки лимитов и типов |
| filter/find/any/all/sort/sum/map | Реализовано | Селектор: поле или чистая функция |
| Чистые функции с аргументами и возвращаемыми типами | Реализовано | Порядок объявлений и лимит параметров |
| text_length/trim/lower_ascii/contains/concat | Реализовано | Экспериментальный API |
| is_date/date_days/date_add | Реализовано | Диапазон дат 0001..9999 |
| Условные выражения и короткое вычисление | Реализовано | Выборочная проверка с Python |
| Несколько экранов, guards, навигация, pop/back | Реализовано | Модель переходов; не UI |
| Физическое сохранение/восстановление state | Реализовано экспериментально | Python 0.11 ↔ Rust схема 1; не проверены отказ питания и конкурирующие писатели |
| Специальные UI-описания и темы приложения | Частично | Темы, именованные стили и адаптивные свойства Site/WebApp проверены в Chromium на выбранных примерах |
| Расширенная диагностика исходника (source spans) | Частично | Карта строк/колонок только для верхнеуровневых объявлений |
| Типизированный промежуточный IR | Экспериментальный JSON v1 | Команда `ir FILE`, схема нестабильна и нет генераторов | 
| Локальные импорты/пакеты, компоненты, стили | Частично | Проверяемые offline vendor locks и SHA-256 на Rust, компоненты Site; пространства имён и полные импорты Python 0.12 не перенесены |
| Site и WebApp, layout, виджеты, маршруты | Экспериментальная реализация | Многостраничный Site, локальные ресурсы, WebApp с параметризованными маршрутами, формами, списками, таблицами диалогами и типизированными same-origin HTTP-виджетами |
| Web-генератор JavaScript/HTML | Экспериментальная реализация | Site/WebApp проверены в Chromium на шести примерах; app-mode проверен через Node mock DOM, Firefox и WebKit остаются вне матрицы Rust |
| Android-генератор Kotlin/Compose | Экспериментальное подмножество | Нативный app-mode с коллекциями, проверяемыми действиями, навигацией, schema-1 и Compose; аппаратная валидация остаётся отдельной |
| HTTP-сервисы WebApp | Экспериментальная реализация | Same-origin GET/POST/PUT/PATCH/DELETE, проверка JSON, кэш, отмена и тайм-ауты. Внешние origin и прочие HTTP-цели ожидают переноса |
| Host API и Effects | Экспериментальное подмножество | POSIX Host A2 и его отдельные разрешения; Rust Effects A1: аннотация чистой fn, ограниченный транзитивный граф, манифест app-domain. Типизированные Result/match, эффекты Host/сервера и изоляция недоверенного кода ещё не перенесены |
| Нативные бинарники для Windows/macOS | Не проверено | cargo install и preview-архив проверяются на Linux x86_64; Windows/macOS ещё нет |
| Совместимость всех существующих .sdr-программ | Не доказана | Нужна матрица по режимам/платформам |
| Новый стабильный релиз на Rust | Нет | Стабильный движок — Python |

### Проверяемая часть

Из корня репозитория, с установленным Rust и Cargo:

    cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava-native
    cargo test --manifest-path rust/Cargo.toml --locked --all-targets
    cargo fmt --manifest-path rust/Cargo.toml --all -- --check
    python3 scripts/verify_rust_core.py --random-cases 24
    python3 scripts/verify_rust_snapshot.py
    python3 scripts/verify_native_site.py
    python3 scripts/verify_native_web_011.py

Примеры, выполняемые на Rust:

    ./rust/target/debug/sedrava-native test examples/task_manager.sdr
    ./rust/target/debug/sedrava-native test examples/task_manager_navigation.sdr
    ./rust/target/debug/sedrava-native test tests/rust_cases/functions_queries.sdr
    ./rust/target/debug/sedrava-native run tests/rust_cases/navigation.sdr open '$back'

Приведённые команды предназначены для Linux/macOS и не являются подтверждением
работоспособности на других ОС. Каждую проверку следует запускать на конкретном
SHA и сохранять окружение, выходные коды и ошибки. Код доступен под Apache-2.0.

## Следующие этапы без пропусков

1. **Семантика и восстановление**: snapshot codec/schema-1 совместим в
   проверенных сценариях; далее нужны конкуренция писателей, аварии/диск,
   cross-OS тесты и resource/fuzz-проверки.
2. **Модули и интерфейсы**: imports, typed packages, source spans, версия IR,
   специальные объявления Site/WebApp, компоненты, темы, маршрутизация и UI DSL.
3. **Генерация**: Web HTML/JS, Android Kotlin/Compose, HTTP API, проверка
   совпадения поведения с действующим компилятором на общих примерах.
4. **Host и безопасность**: контролируемые эффекты, лимиты, host-error taxonomy,
   сетевые/файловые права, fuzz/property/crash/concurrency-проверки.
5. **Выпуск**: установки Windows/Linux/macOS, документация пользователю,
   миграция с PyPI, дифференциальные тесты, полная регрессия и совместимые пакеты.

## Критерии переключения на Rust по умолчанию

- Все поддерживаемые режимы Sedrava либо повторяют публичный контракт, либо
  несовместимость отдельно оформлена и протестирована.
- Достигнуты реальные browser/JVM/Android/device acceptance, а не только
  синтаксическая проверка и генерация исходников.
- Покрыты восстановление, ошибки, лимиты ресурсов, непротиворечивость IR,
  откат транзакционных действий и безопасность Host IO.
- Выпущены воспроизводимые артефакты и документация для сторонних пользователей.
- Python-реализация убирается из цепочки только после подтверждения покрытия.
- Перед стабильным релизом — отдельный контрольный review.

Отдельный проект [SedravaSQL](https://github.com/VasiliiBabkin/sedravasql)
пока не блокирует перенос и не встраивается в компилятор без строгого API.

История решения: [ADR_RUST_CORE.md](ADR_RUST_CORE.md).

Воспроизводимые результаты второго этапа: [отчёт](../evidence/rust-core/2026-11-22-stage2.md).

### Экспериментальный Rust snapshot/IR (следующая ревизия)

Для локального испытания с отдельными тестовыми данными:

    ./rust/target/debug/sedrava-native run tests/rust_cases/persistent_records.sdr add --state-file demo-state.json
    ./rust/target/debug/sedrava-native run tests/rust_cases/persistent_records.sdr complete --state-file demo-state.json
    ./rust/target/debug/sedrava-native ir tests/rust_cases/persistent_records.sdr

`--state-file` читает/пишет только разрешённые состояния (`persist`).
Перед сохранением проверяются схема, типы, правила и завершение всех действий.
Запись производится через временный файл и замену в том же каталоге.
Это не обещание безусловной сохранности данных при сбое питания или конкуренции
пишущих процессов. Пользовательские данные для тестов не требуются.
Структура `ir` версионирована для исследований и пока НЕ является стабильным ABI.


Подробный протокол [сохранений и экспериментального IR](RUST_NATIVE_PERSISTENCE.ru.md).


Проверяемые прототипы [импортов и Web](RUST_WEB_SCALAR.ru.md) и [распространения](DISTRIBUTION_NATIVE.ru.md).


Подробности экспериментального [Android-подмножества](RUST_ANDROID_GENERATOR.ru.md).


Покрытие экспериментальных Site и WebApp, известные различия и browser-проверки описаны в [RUST_SITE_PREVIEW.ru.md](RUST_SITE_PREVIEW.ru.md).

Контракт нативных HTTP-виджетов и ограниченного файлового Host описан в [RUST_HTTP_HOST.ru.md](RUST_HTTP_HOST.ru.md).


## Дополнение: Host A2 и offline packages на Rust

Реализованы и проверяются отдельно:
[Host JSON/каталоги](RUST_HOST_A2.ru.md) и
[локальные пакеты с lock-файлами](RUST_LOCKED_PACKAGES.ru.md).
Эти возможности не означают переноса всего Python Core 0.12,
в частности typed errors/Result/match, Effects A1/Targets,
серверного runtime и всех пространств имён.


### Следующий перенос: Effects & Targets A1

Нативный Rust проверяет необязательные аннотации чистых функций
и создаёт экспериментальный манифест:
[описание контракта](RUST_EFFECTS_A1.ru.md).
Важная граница: это **только** типизированный app-domain, не полноценная
модель эффектов и разрешений для браузера, Host, HTTP или базы данных.
Следом остаются Result/closed-open errors/exhaustive match,
namespace API и типизированные эффекты всех целевых сред.


### Следующий перенос: Core typed errors/Result/match A1

Реализовано экспериментальное подмножество номинальных ошибок и
скалярных Result, исчерпывающий match в действиях, генерация
нативного Web JS и сравнение с Python 0.12 PR #56.
Подробности и ограничения (Android, legacy try_*, импортированные
ошибки): [Core + Web A1](RUST_TYPED_ERRORS_A1.ru.md).
Issue #65 остаётся открытым.


### Kotlin/Android для скалярных типизированных ошибок

Нативный Rust генератор получил экспериментальное
[отображение Error/Result/match в Kotlin](RUST_TYPED_ANDROID.ru.md).
Полная совместимость с не выпущенными Python 0.12 API не является
целью; вместо неё — строгая проверяемая модель Rust и
независимая Kotlin/JVM и APK-валидация. Issue #65 остаётся открытым.


### Namespace imports — Rust native experimental

Новый строго локальный `import "module.sdr" as alias` для app-mode
позволяет использовать одноимённые fn/record из нескольких модулей,
а также явно идентифицированные error-типы без Python runtime.
Результат разворачивания детерминирован; проверяются неизвестные
экспорты, коллизии и запрещённые пути.

[Контракт и ограничения](RUST_NAMESPACE_IMPORTS.ru.md). Это не полная
поддержка пространств имён Python 0.12, Site/WebApp или source maps.
Issue #65 остаётся открытым.


### Native preview installer — offline Linux trial

Для экспериментального TAR.GZ существует ограниченный
[офлайн-установщик с явным SHA-256](DISTRIBUTION_NATIVE.ru.md).
Пользователю preview-бинарника не нужны pip, Python или Rust;
публикация, подписи и мультиплатформенная валидация пока не завершены.
Python 0.11 остаётся стабильной версией.


### Native Server A1 — loopback-only HTTP

[Экспериментальный сервер](RUST_NATIVE_SERVER_A1.ru.md) добавляет
отдельный статически проверяемый server DSL, строгий JSON-контракт
и нативный Rust HTTP/1.1 runtime, слушающий только loopback. Это не
публичная серверная платформа: DB, Host/network effects, авторизация,
транзакции, TLS и длительная эксплуатация остаются не реализованы.
Issue #65 остаётся открытым.


### IR 1.0 Candidate.1 — первый отдельно проверяемый контракт

[Экспериментальный скалярный app-IR](IR_CANDIDATE.ru.md) имеет
опубликованную JSON Schema, golden и первый независимый потребитель
для Web. Это не полный стабильный IR и не заменяет генераторы.
Issue #65 остаётся открытым.

### Server A2 — типизированное состояние и закрытый state-dir

[Server A2](RUST_NATIVE_SERVER_A2.ru.md) добавляет `set`/`require`,
`int`/`bool`/`text` и опциональные JSON-снимки в доверенном Unix-каталоге.
Откат проверен для ошибочных вычислений и записи до commit.
Нет exactly-once, гарантированного восстановления после сбоя
питания, серверных Host effects, SQLite или SedravaSQL.


### Server A3 — ограниченные транзакционные квитанции

[Экспериментальный Server A3](RUST_NATIVE_SERVER_A3.ru.md) вводит
`--transactional` и JSON-снимок состояния с невытесняемым журналом
32 ключей идемпотентности, глобальной ревизией и CAS-заголовком.
Повтор подтверждённого запроса не исполняет обработчик повторно
после штатного рестарта. **Не** является промышленным хранилищем
или реализацией SedravaSQL, не гарантирует power-loss durability.


### Native Server A4 — append-only redo journal

[Ограниченный Server A4](RUST_NATIVE_SERVER_A4.ru.md) реализует
отдельный opt-in режим хранения с одноразовыми записями
подтверждённых транзакций и строго проверяемой цепочкой SHA-256.
Это **не** production WAL: нет checkpoint/компактизации,
power-loss доказательства и сетевой многопользовательской БД.
Issue #84 остаётся открытым.

### Server A5 — SedravaSQL SQLite storage

[Server A5](RUST_NATIVE_SERVER_A5_SQLITE.ru.md) добавляет opt-in
`--sqlite-state` через **реальную внешнюю Rust-библиотеку SedravaSQL**
(pinned commit b5831d7...). Подтверждённые операции записываются
в SQLite WAL с атомарным аудитом и квитанциями. Старые режимы
не меняются, серверный лимит 32 квитанций пока остаётся.
Это первая работающая интеграция языка и независимой СУБД,
не полный SQL/ORM API и не production.

### Server A6 — persistent SQL receipts and read-only DSL lookup

[Документация A6](RUST_NATIVE_SERVER_A6_SQLITE.ru.md): автономный
Rust-сервер с отдельными SQL-квитанциями запросов вместо общего
ограниченного JSON-списка (неограниченное число ключей без автоматической
очистки); первая read-only операция из Sedrava:
`db_get("namespace/key")` для GET-ответа, под управлением SedravaSQL.
A1–A5 остаются неизменными. Нет произвольного SQL, DB-write DSL,
power-loss гарантий и готовности к production.
