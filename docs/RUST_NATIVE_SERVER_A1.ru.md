# Sedrava Server A1 — экспериментальный нативный HTTP runtime

Первый ограниченный серверный режим Rust. Продолжение с состоянием:
[Server A2](RUST_NATIVE_SERVER_A2.ru.md). **Не предназначен для
публичного интернета и production**: нет TLS, аутентификации, БД,
устойчивого состояния, конкурентной обработки и исходящего HTTP.
Никаких разрешений Host файловой системы сервер не предоставляет.

## Программа и команды

Пример: [hello.sdr](../examples/native_server/hello.sdr).

```sedrava
server "Hello API"
route GET "/health":
    respond 200 { status: "ok", version: 1 }
route POST "/items":
    request name: text
    request quantity: int
    request available: bool
    respond 201 { name: request.name, quantity: request.quantity, available: request.available }
```

```sh
sedrava-native server check examples/native_server/hello.sdr
sedrava-native server run examples/native_server/hello.sdr \
    --port 0 --max-requests 32 --idle-ms 30000
```

Выводится `LISTENING http://127.0.0.1:PORT`. Порт 0 — выбор свободного
порта операционной системой. Для указания конкретного номера используйте
`--port 8081`. **Внешний адрес невозможно указать в CLI этого этапа.**
Сервер автоматически завершается после 1–10000 соединений или 500–120000
мс без активности. Значения по умолчанию: 32 соединения, 30 секунд.

Проверить запросы к порту 8081:

```sh
curl -sS http://127.0.0.1:8081/health
curl -sS -X POST http://127.0.0.1:8081/items \
  -H 'Content-Type: application/json' \
  --data '{"name":"молоко","quantity":2,"available":true}'
```

`/items` ничего не записывает, а только проверяет и возвращает входные
значения. Не используйте тестовый сервер для реальных персональных
данных и секретов.

## Поддержанный контракт

- Только отдельный `server` DSL с командами `route`, `request`,
  `respond`. Не `app`, не `webapp`; импортов и динамических вычислений
  на сервере пока нет.
- Методы GET, POST, PUT, PATCH, DELETE и точные ASCII-пути без query,
  percent-encoding, параметров и обхода каталогов. До 32 маршрутов.
- Поля запроса `int` (int32), `text` (до 1024 Unicode-символов),
  `bool` — до 16 обязательных полей. Запрещены лишние и
  повторяющиеся поля JSON, управляющие символы в строках и `null`.
- Ответ: обязательный `respond 200|201|202 { name: value }`,
  где значения — типизированный `request.field` или JSON-скаляр.
  Не более 32 полей. Никакого исполняемого кода/шаблонизации.
- HTTP/1.1 без keep-alive, пайплайнинга, HTTP/2, chunked и
  Transfer-Encoding. Один запрос на соединение, последовательная
  обработка, ограничение чтения и записи сокета.
- Заголовки до 8192 байт/32 штук, тело до 16 KiB. Обязателен
  корректный Host localhost/127.0.0.1 с настоящим портом (если задан).
  Дубли заголовков и Content-Length отклоняются.
- Запрос с телом требует точный Content-Type `application/json`.
  В ответе JSON, Content-Length, Connection: close, Cache-Control:
  no-store и X-Content-Type-Options: nosniff. CORS не выдаётся.
- Ошибки возвращаются JSON с `error.code`. Основные коды HTTP:
  400, 404, 405, 413, 415, 422, 431. Никакого сырого стека в ответе.

**Ограничения:** не реализованы TLS, авторизация, внешние адреса,
конкурентные транзакции, durable storage, HTTP JSON API из общего
app-domain, Host API, DB, server-side effects, роуты с параметрами,
стриминг и непрерывная production-служба. Для подключения к
SedravaSQL потребуется отдельный типизированный адаптер и политика
прав. В этом этапе никаких фоновых сервисов не устанавливается.

## Воспроизводимые тесты

```sh
cargo fmt --manifest-path rust/Cargo.toml --all -- --check
cargo test --manifest-path rust/Cargo.toml --locked --all-targets
cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava-native
python3 scripts/verify_native_server.py
```

Python — **только внешний тестовый клиент**. Rust-сервер исполняется
самостоятельно, без Python, npm или Rust на целевом VDS. Все тестовые
соединения идут к `127.0.0.1`, не к работающим сайтам.
