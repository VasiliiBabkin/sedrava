# Sedrava Server A8 — атомарная запись в SedravaSQL из языка

Дата: 24 ноября 2026. Статус: экспериментальный локальный Server DSL, **не публичный API, не SQL и не стабильный выпуск языка**.

## Что работает

Один объявленный ключ SedravaSQL можно изменять прямо из проверяемой программы Sedrava:

```sedrava
server "A8 SQL PUT"
state enabled: bool = true
route PUT "/note":
    request value: text
    db_put "public_notes/welcome" = request.value
    respond 200 { note: request.value, saved: true }
route GET "/note":
    respond 200 { note: db_get("public_notes/welcome"), revision: db_revision("public_notes/welcome") }
```

Это полностью исполняемый пример `examples/native_server/sqlite_a8_put.sdr`, а не псевдокод. Действия в нём выполняет Rust-ядро Sedrava Server. Хранение предоставляет существующая независимая Rust-библиотека SedravaSQL через SQLite WAL, а не SQLite-free NativeLog.

`db_put "namespace/key" = request.FIELD` доступен только для **PUT** и строго одного объявленного `request FIELD: text`; ключ — строковый литерал с двумя частями 1..128 ASCII [A-Za-z0-9_.-]. Запрещён reserved namespace `sedrava_native`. Динамические ключи, SQL-операторы, запись в несколько записей, произвольные поля, GET/POST/PATCH/DELETE db_put, смешивание с `set` или `require`, обращение к `state` из ответа PUT и DB-выражения в таком ответе — отклоняются на этапе `server check`.

### HTTP-контракт

- Режим сервера: **только** `--transactional --sqlite-v2-state /ABSOLUTE/PRIVATE/managed.sqlite`; слушатель только 127.0.0.1.
- Запись: `PUT /note` с `Content-Type: application/json`, телом `{"value":"Привет"}`, `Idempotency-Key: ...` (12..64 ASCII символов [A-Za-z0-9_.-]) и **обязательным** `X-Sedrava-If-Revision: 0` для нового ключа.
- Ответ: HTTP 200, JSON `{"note":"Привет","saved":true}`, заголовок `X-Sedrava-KV-Revision: 1`. Он обозначает **ревизию ключа**, а не `X-Sedrava-Revision` состояния A6.
- GET-ответ предоставляет значение и ревизию того же ключа, прочитанные из одной строки. При GET заголовок `X-Sedrava-Revision` по-прежнему относится к состоянию A6, а не к ключу; для ключа используйте поле JSON `revision`.
- `X-Sedrava-If-Revision` на A8 PUT интерпретируется как **ожидаемая ревизия конкретного ключа** (не A6-состояния). Для нового ключа 0, для существующего — последнее полученное `db_revision`.
- Если ключ запроса уже использован с теми же методом, URL, телом и условием ревизии, возвращается сохранённый исходный ответ и `X-Sedrava-Replayed: true`. Это работает после перезапуска сервера и после других изменений в базе.
- Повтор того же Idempotency-Key с иным содержимым → 409; неправильная ревизия при новом ключе запроса → 412; отсутствие ключа или условия → 428; некорректный JSON → 400; несоответствие схемы → 422.
- Отказ в доступе к базе либо неопределённый исход SQLite commit → 503 `DB_PUT_UNCERTAIN` и остановка сервера для защиты от записи на базе устаревшего состояния. Ревизия, которая не помещается в int32 для следующего ответа, отвергается с 507.

### Атомарность и безопасность

**Одна** транзакция SedravaSQL `Database::mutate_with_response` атомарно сохраняет новое значение в `records`, запись `audit`, запись `receipts` и исходный полный HTTP-ответ в `application_response`. Обработчик Sedrava не возвращает успешный ответ до подтверждения SQLite commit. Запись в отдельный ключ никак не изменяет A6 state snapshot; смешанные транзакции «бизнес-ключ + серверное состояние» в A8 **не реализованы**.

Ключ идемпотентности изолирован по подписи Sedrava-программы, route, namespace и key; его исходный текст не передаётся в общую таблицу без этого контекста. Отсутствует истечение срока хранения или автоматическая очистка квитанций.

**Важно:** CAS, durable idempotency и SQLite WAL нельзя считать доказательством сохранности при настоящем отключении питания; физическая power-loss проверка, угрозы от другого процесса того же UID, аудит внешней авторизации, резервирование, квоты и эксплуатационный SLA не подтверждены. Публичный сетевой интерфейс и клиентская аутентификация НЕ реализованы.

## Самостоятельная проверка

На VDS, в отдельной директории, не подключаясь к пользовательским базам:

```bash
source "$HOME/.sedrava-dev/env.sh"
sedravasql_target
SQL="$CARGO_TARGET_DIR/debug/sedravasql"
sedrava_target
cd "$HOME/.sedrava-dev/sedrava"
cargo test --manifest-path rust/Cargo.toml --locked --offline --all-targets
cargo build --manifest-path rust/Cargo.toml --locked --offline --bin sedrava-native
"$CARGO_TARGET_DIR/debug/sedrava-native" server check examples/native_server/sqlite_a8_put.sdr
SEDRAVA_A8_BIN="$CARGO_TARGET_DIR/debug/sedrava-native" SEDRAVASQL_CLI="$SQL" \
  python3 -B scripts/verify_native_server_db_put_a8.py
```

Реальный интеграционный тест проверяет PUT/GET, CAS, изменённые payload и повторяемость, историю в SQLite (state/audit/receipts), обновление из независимого CLI, перезапуск сервера, два одновременно запущенных сервера, 11 синтаксически запрещённых сценариев, некорректные HTTP-условия и **четыре контролируемые debug-only остановки** SQLite-транзакции (до и после commit). Все тесты запускаются на 127.0.0.1 и временных приватных БД.

## Чего ещё нет

- Атомарного обновления нескольких отдельных ключей и A6 state в **одной** общей транзакции.
- SQL-таблиц/запросов/индексов, произвольного `db_put` с путём из запроса, операторов delete или insert для новых типов.
- Публичной аутентификации и авторизации. **Не открывайте сервер напрямую в интернет.**
- Подключения SQLite-free NativeLog к серверному режиму.
- Поддержки продакшена, миграций и гарантированной устойчивости к аппаратным сбоям.

Дальнейший этап A9 — спроектировать проверяемую атомарную batch-модель для нескольких ключей и серверного состояния, не ослабляя idempotency/CAS.
