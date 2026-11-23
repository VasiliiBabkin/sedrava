# Sedrava Server A7 — согласованное чтение данных SedravaSQL

Дата: 24 ноября 2026. Статус: экспериментальный локальный серверный режим, не публичный API и не стабильная версия языка.

## Возможность

В Sedrava server DSL есть два проверяемых выражения для ответа GET:

    server "A7 SQL Metadata"
    state enabled: bool = true
    route GET "/note":
        respond 200 { note: db_get("public_notes/welcome"), revision: db_revision("public_notes/welcome"), enabled: state.enabled }

Полный пример: examples/native_server/sqlite_a7_metadata.sdr.

- db_get("namespace/key") возвращает text.
- db_revision("namespace/key") возвращает int32 с ревизией записи SedravaSQL.
- Для одного ключа в рамках одного HTTP-ответа оба поля берутся из единственного чтения записи.
- Путь только статический строковый литерал. Динамические request/state пути и служебные пространства sedrava_native запрещены.
- Только GET response и только локальный --transactional --sqlite-v2-state.
- Нет SQL-языка, произвольных таблиц, доступа на запись или публичной авторизации.

Это согласованность **одного ключа** внутри одного ответа, а не снимок всех разных ключей и не транзакция нескольких HTTP-запросов.

Отсутствующий или удалённый ключ даёт 404 DB_KEY_NOT_FOUND. Ошибка чтения, недопустимое содержимое или управляющие символы приводят к 503. Если ревизия не помещается в int32, сервер возвращает 503 DB_REVISION_RANGE без обрезания.

Ограничение значений: 1024 Unicode-скаляра, без управляющих символов.

## Реальная проверка VDS

    source "$HOME/.sedrava-dev/env.sh"
    sedrava_target
    cd "$HOME/.sedrava-dev/sedrava"
    cargo test --manifest-path rust/Cargo.toml --locked --offline --all-targets
    sedrava-native server check examples/native_server/sqlite_a7_metadata.sdr

Сценарий scripts/verify_native_server_db_revision_a7.py создаёт отдельную приватную SQLite-базу, изменяет её через **независимый процесс SedravaSQL CLI**, запускает Sedrava Server на 127.0.0.1 и проверяет GET:

- Начальное значение Привет + revision 1.
- Независимое обновление → новое значение + revision 2.
- Удаление → 404.
- Семь неправильных, dynamic, reserved и write-вариантов отвергнуты до сетевого bind.
- Ревизия 2^31 из тестовой базы приводит к 503.
- Старые тесты A6 с 46 записями HTTP, историей receipts, конфликтами и четырьмя SQL crash windows проходят.
- 82 Rust unit tests проходят.

Строгий Clippy в существующем ядре сообщил о ранее существовавших предупреждениях. Его полный PASS для этого SHA не заявляется.

## Границы

Sedrava 0.11 в опубликованной стабильной версии не включает эти экспериментальные серверные возможности. SedravaSQL здесь предоставляет SQLite-backed managed KV. Самостоятельный NativeLog остаётся отдельным прототипом и не подключается этим изменением к HTTP.

Нет авторизации внешних пользователей, публичного сервера, динамической SQL, произвольного доступа к БД, миграций, retention для receipts и полной crash/power-loss сертификации.

Следующий этап: отдельный контракт **атомарной серверной записи** с CAS по ключу и фиксированной схемой ответа, audit и durable receipt внутри одной транзакции SedravaSQL.
