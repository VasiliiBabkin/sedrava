> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# Sedrava Server A10 — согласованный снимок нескольких ключей SedravaSQL

Дата: 24 ноября 2026. Экспериментальная возможность локального сервера Sedrava, не полноценный SQL и не production.

## Что изменилось

В исходнике языка остаются привычные выражения:

    route GET "/pair":
        respond 200 {
            left: db_get("public_notes/left"),
            right: db_get("public_notes/right"),
            left_revision: db_revision("public_notes/left"),
            right_revision: db_revision("public_notes/right")
        }

Теперь Sedrava сначала собирает все разные namespace/key из ответа GET,
а затем выполняет ОДИН вызов SedravaSQL Database::read_snapshot.
Он читает 1–16 разных ключей в одной транзакции SQLite WAL.
Если между чтениями внешний процесс фиксирует B6/A9-пакет записи,
данные ответа всё равно относятся к одной зафиксированной версии БД.

Для одного ключа значение и ревизия также остаются согласованными.
Существующие GET-программы A7/A8/A9 используют новый механизм
без изменения своего исходного синтаксиса.

### Интерфейс и ошибки

- Ключи должны быть статическими литералами: обычные правила
  ASCII namespace/key, префикс sedrava_native запрещён.
- Отсутствующий или удалённый хотя бы один нужный ключ:
  HTTP 404 DB_KEY_NOT_FOUND, без публикации частичного результата.
- Ошибка чтения или значение вне ограничений scalar text:
  HTTP 503 DB_READ_FAILED с блокировкой последующей работы сессии.
- Ревизия, которая не помещается в int32:
  HTTP 503 DB_REVISION_RANGE, без обрезания числа.
- Чтение не меняет БД, не добавляет таблиц, не исполняет
  пользовательский SQL и не предоставляет новые права.
- Собственная память Sedrava Server (например, state.counter)
  НЕ входит в эту транзакцию чтения. Если два процесса сервера
  работают одновременно, один может иметь устаревшее state в
  памяти; поэтому нельзя считать комбинацию state и DB полей
  одним атомарным снимком. Гарантия относится только к SQL-ключам
  внутри ОДНОГО GET, а не между несколькими HTTP-запросами.

## Версии и воспроизведение

В Cargo.toml и Cargo.lock языка закреплён конкретный проверенный
коммит SedravaSQL B7: 225bf90576ff911b05304fd7bf971fcc21b9e67d.
Это не автоматическое обновление зависимостей.

    source "$HOME/.sedrava-dev/env.sh"
    sedravasql_target
    SQL="$CARGO_TARGET_DIR/debug/sedravasql"
    sedrava_target
    cd "$HOME/.sedrava-dev/sedrava"
    cargo test --manifest-path rust/Cargo.toml --locked --offline --all-targets
    cargo build --manifest-path rust/Cargo.toml --locked --offline --bin sedrava-native
    "$CARGO_TARGET_DIR/debug/sedrava-native" server check examples/native_server/sqlite_a10_snapshot.sdr
    SEDRAVA_A6_BIN="$CARGO_TARGET_DIR/debug/sedrava-native" SEDRAVASQL_CLI="$SQL" \
      python3 -B scripts/verify_native_server_coherent_read_a10.py

Все данные создаются в приватной TemporaryDirectory.
Два отдельных сервера слушают только адрес 127.0.0.1.

### Результаты на VDS

- 81 успешное B6/A9 обновление двух ключей с общим commit и
  сохранением серверного состояния, аудита и квитанций.
- 242 согласованных HTTP GET /pair; при параллельных записях
  в тесте встречены все 81 версии; ни разу не смешаны ревизии.
- Сверены legacy audit/receipts и managed_batch_receipts.
- Удаление одного ключа через независимый SedravaSQL CLI даёт
  404 для всего парного ответа.
- Принудительно изменённая на 2^31 ревизия тестовой записи
  приводит к 503 без отдачи некорректной пары.
- Существующие регрессии A6, A7, A8 и A9 остаются обязательными.

## Ограничения

Это только SQLite-backed путь, а не собственный NativeLog.
Не реализованы произвольные SELECT/SQL/таблицы, API для публичных
клиентов, общая транзакция записи и чтения через HTTP, согласованная
транзакция state+GET-ключей, свободный выбор ключей из request,
многопользовательская авторизация и гарантированное восстановление
после реального отключения питания.

Системные ограничения компактного Server DSL остаются действующими.
