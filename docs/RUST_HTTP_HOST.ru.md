> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# Нативные HTTP-возможности WebApp и файловый Host

Python 0.11 остаётся эталоном WebApp. Файловый Host сверяется с
экспериментальным Python A3 из отдельной ветки. [Спецификация A3](https://github.com/VasiliiBabkin/sedrava/blob/9cff547310747c107be4b840bea4cf171fe48c34/docs/HOST_013_A3.en.md)

## HTTP в WebApp

Компилятор проверяет `service`, `request`, `cancel` и `remote`, включая
шаблоны строк и условия `row-when`. Поддерживаются GET, POST, PUT, PATCH
и DELETE, целочисленные параметры пути и типизированное record-тело для
POST, PUT и PATCH. Схема ответа явно задаёт `one` или `many` и поля
`int32`, `bool`, `text`. Успешный 204 принимается для `many` как пустой
список. Ответ проверяется до попадания в панель или кэш.

- Допустим `origin self`. Адресом назначения служит HTTP(S)-origin,
  с которого загружена страница. CSP разрешает соединения только с
  этим origin. Fetch запрещает редиректы, не отправляет credentials и
  Referer. Внешние origin и неоднозначные URL-пути, включая percent
  encoding, явно отклоняются. Нативный компилятор не подключается к сети.
- Браузерный origin является границей полномочий. Компилятор не
  разрешает DNS и не предоставляет DNS pinning. При публикации
  безопасность origin, HTTP-обработчиков, прокси и окружения браузера
  контролирует оператор. Локальный loopback разрешён как origin самой
  тестовой страницы.
- Тайм-аут от 100 до 30 000 мс охватывает получение тела. Поток читается
  с ограничением декодированных байтов. Максимум 200 000 байт на запрос
  и ответ, 1000 строк, 32 поля на схему, глубина JSON 32. На вкладку
  действует бюджет 60 попыток за скользящую минуту и не более одного
  активного запроса на декларацию. Компилятор также ограничивает
  максимальное разворачивание панелей 20 000 условных DOM-узлов.
- Смена параметра и отмена инвалидируют незавершённый запрос. Поздний
  ответ не обновляет новую панель. Последний валидный ответ для того же
  пути при сетевой ошибке сохраняется. Автозагрузка и кэш доступны GET.
  Невалидный кэш сохраняется без перезаписи, при этом панель может
  загрузить свежий ответ. Формат ключа кэша собственной нативной сборки
  может отличаться от Python.
- HTTP-ответы живут в состоянии HTTP-панели. Они не изменяют состояние
  Sedrava и не обходят проверку атомарных действий. Отмена браузерного
  запроса не гарантирует откат операций на сервере.

## Файловый Host

На POSIX поддерживаются отдельный документ `host`, аргументы
`text|int|bool`, чистый `let`, `read`, один отложенный `write` и
финальный `emit`. Необходимые эффекты определяются по инструкциям.
`--trusted`, каталог `--root`, независимые grants `--allow-read` /
`--allow-write` и области `--read-scope` / `--write-scope` задаёт
оператор. `host check` проверяет исходник без файловых эффектов.

Пути открываются относительно дескрипторов каталогов с запретом
следования по symlink. Допустимы обычные файлы с одной hard link.
Ограничения составляют 16 аргументов, 64 инструкции, 8 чтений,
1 запись, 4096 байт на файл и 1024 Unicode-скаляра на текст.
Все вычисления и успешный `emit` предшествуют публикации файла.
Публикуется новый файл с правами не шире 0600 через эксклюзивный
временный файл и атомарную операцию без замены назначения. В отличие
от Python A3, перезапись существующего файла отклоняется с `FILE_EXISTS`.

Стандартный вывод `host run` содержит `sedrava.host.execution.v1` с
`success`, `failed`, `fault` или `rejected`. При отказе после начала
публикации `commit_state` равен `unknown`. Коды ошибок не содержат
путей машины. Автоматическое повторение не разрешено. Native CLI по
умолчанию выдаёт v1 и принимает явный `--result-protocol v1`.

Host рассчитан на доверенный исходник и рабочий каталог. В границу
доверия входят предки корня, точки монтирования и отсутствие враждебных
переименований. Дескрипторы ограничивают разрешение путей, но не
предоставляют OS sandbox или тайм-аут потенциально блокирующего
файлового вызова. Host-сеть, Host A2 JSON и операции каталогов, A3
`try_read`/`match`, полная карта Effects и исполнение недоверенного
кода пока отклоняются или отсутствуют. Экспериментальная спецификация
A3 сама исключает Host-сеть и исполнение недоверенного кода.

## Воспроизведение на изолированной Linux-машине

Используйте чистый checkout SHA из PR, локальные Chromium, Node,
Python Playwright и Rust. Для браузерного сервиса тестовый сценарий
автоматически поднимает сервер на loopback со случайным портом.

~~~sh
cargo fmt --manifest-path rust/Cargo.toml --all -- --check
cargo build --manifest-path rust/Cargo.toml --locked
cargo test --manifest-path rust/Cargo.toml --locked --all-targets
npm install --prefix build/platform-a11y --no-audit --no-fund axe-core@4.10.3
python3 scripts/test_platform_browser.py
SEDRAVA_NATIVE="$PWD/rust/target/debug/sedrava-native" python3 scripts/test_platform_browser.py
python3 scripts/verify_native_web_011.py
python3 scripts/verify_native_web.py
python3 scripts/verify_native_site.py
python3 scripts/verify_rust_core.py --random-cases 24
python3 scripts/verify_rust_snapshot.py
python3 scripts/verify_native_host.py
python3 -m unittest discover -s tests -q
~~~

Для проверки без Python на Linux можно использовать отдельный mount
namespace с Bubblewrap. В нём доступны только динамические библиотеки,
нативный бинарник и входные файлы.

~~~sh
testroot=$(mktemp -d)
printf 'host "Test"\nread original from "input"\nwrite "report" = original\nemit original\n' > "$testroot/host.sdr"
printf hello > "$testroot/input"
bwrap --die-with-parent --unshare-all --ro-bind /lib /lib --ro-bind /lib64 /lib64 \
  --bind "$testroot" /work --ro-bind "$PWD/rust/target/debug/sedrava-native" /sedrava-native \
  --ro-bind "$PWD/examples/platform_catalog.sdr" /catalog.sdr --clearenv \
  /sedrava-native build webapp /catalog.sdr --output /work/catalog
bwrap --die-with-parent --unshare-all --ro-bind /lib /lib --ro-bind /lib64 /lib64 \
  --bind "$testroot" /work --ro-bind "$PWD/rust/target/debug/sedrava-native" /sedrava-native \
  --clearenv /sedrava-native host run /work/host.sdr --root /work --trusted --allow-read --allow-write
test -s "$testroot/catalog/app.js"
test "$(cat "$testroot/report")" = hello
~~~

Для прямого сравнения Host возьмите отдельный checkout
`9cff547310747c107be4b840bea4cf171fe48c34` из ветки
`security/host-a3-release-audit` и вызовите
`python3 scripts/verify_native_host.py --python-host /path/to/a3/sedrava_cli.py`.
Полная карта покрытия приведена в [плане миграции](RUST_FULL_MIGRATION.ru.md).
