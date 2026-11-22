# Native Rust: Effects & Targets A1 (экспериментальный этап)

Этот этап переносит **ограниченный контракт типизированных чистых функций**
из экспериментальной Python 0.12, PR #55. Манифест не даёт полномочий
процессу или программе: это сведения о проверенном **app-domain**,
а не сертификат безопасности для браузера, Android, Host, сервера или БД.

## Синтаксис и команда

Обычные функции `fn ... -> TYPE = expression` продолжат работать.
Дополнительно принимается декларация верхней границы для чистых функций:

```sedrava
fn increment(x: int) -> int effects pure = x + 1
fn double_step(y: int) -> int = increment(increment(y))
```

Единственная разрешённая на данном этапе аннотация — `effects pure`.
`effects { host.fs.read }`, `effects all` и другие варианты
**отклоняются**; у пользовательского кода пока нет способа запрашивать
нечистые операции внутри `fn`.

```sh
cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava-native
./rust/target/debug/sedrava-native check examples/native_effects_a1/pure.sdr
./rust/target/debug/sedrava-native test examples/native_effects_a1/pure.sdr
./rust/target/debug/sedrava-native effects examples/native_effects_a1/pure.sdr --target web
```

`effects` принимает `--target app|web|android`, по умолчанию `app`.
В stdout выводится канонический JSON схемы `sedrava.effects.v1`.
Сортировка ключей/функций и отсутствие временных меток позволяют
сравнивать результаты. `source_sha256` — хеш **развёрнутого и
предварительно проверенного** исходника, включая допустимые локальные
импорты; импортированные пакеты `vendor/` проходят проверку `sedrava.lock`.

Пример формы вывода (хеш ниже не приводится, поскольку зависит от байтов
развёрнутого исходного текста):

```json
{
  "schema": "sedrava.effects.v1",
  "kind": "app-domain",
  "target": "web",
  "effective": [],
  "functions": [
    {"name": "double_step", "declared": null, "effective": []},
    {"name": "increment", "declared": [], "effective": []}
  ]
}
```

Фактический JSON дополнительно содержит `source_sha256`.
Поля сериализуются в стабильном лексикографическом порядке без пробелов.

## Семантика и ограничения

Нативный анализатор обходит типизированное дерево выражения и строит
ограниченный граф вызовов (до 32 функций, до 256 call-узлов на тело).
Прямые вызовы, в том числе чистые функции-селекторы коллекций, учитываются
в транзитивном наборе эффектов. Циклы, неучтённые/динамические вызовы,
неверные сигнатуры и превышение объявленной верхней границы отклоняются.

Версионированные *имена будущих эффектов*:
`host.fs.read`, `host.fs.write`, `host.fs.list`, `host.fs.mkdir`,
`host.fs.rmdir`, `server.db.read`, `server.db.write`, `server.http`,
`web.api`. Наличие имени в анализаторе не подключает соответствующую
операцию, не отменяет policy и не создаёт сетевое или файловое разрешение.
Политика `target` хранит допустимые верхние границы; реальное исполнение
всё равно должно проверять свои полномочия отдельно.

Полноценные возможности остаются **неперенесёнными**: Effects для
Web UI, браузерного хранилища, Host, HTTP/server/DB runtime,
типизированные `Result<T,E>` и `match`, эффекты экспортированных
namespace API, полные source spans и стабильный типизированный IR,
реальные capability grants для пользовательских эффектных функций.
Никакой production security-manifest этим этапом не обещается.

## Приёмка

```sh
cargo test --manifest-path rust/Cargo.toml --locked --all-targets
python3 scripts/verify_native_effects.py
python3 scripts/verify_rust_core.py --random-cases 24
python3 -m unittest discover -s tests -q
```

Пример расположен во вложенном каталоге, поскольку стабильная
Python 0.11 пока не знает синтаксиса `effects pure`.
Python 0.11 остаётся основной реализацией до полной миграции.
