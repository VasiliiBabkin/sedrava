> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# Нативный Sedrava: offline lock-файлы локальных пакетов

Rust-компилятор экспериментально поддерживает **закреплённые локальные
пакеты** из `vendor/`, без сети, реестра или установки пакетов.
Схема `sedrava.lock` версии 1 и структура манифестов совместимы с
проверенным примером Python 0.12 из PR #52. Это контроль целостности байтов,
а не цифровая подпись или доверие к стороннему коду.

## Как пользоваться

См. `examples/native_locked_app` — обычное app-mode приложение с функцией
из пакета `example.math`. В каталоге находятся:

- `sedrava.toml` с `[package]` name/version и `[dependencies]`.
- `vendor/example.math/sedrava.toml` с точной версией.
- `vendor/example.math/math.sdr` с исходным кодом.
- `sedrava.lock` со списком SHA-256 для всех файлов пакетов.

```sh
./rust/target/debug/sedrava-native verify examples/native_locked_app
./rust/target/debug/sedrava-native check examples/native_locked_app/main.sdr
./rust/target/debug/sedrava-native test examples/native_locked_app/main.sdr

# Только после просмотра изменений в зависимостях:
./rust/target/debug/sedrava-native lock examples/native_locked_app
```

`lock` детерминированно создаёт/заменяет lock-файл через временный файл.
`verify` заново читает точные версии и байты каждого локального пакета.
Все команды `check`, `run`, `test`, `build web|android|site|webapp`
автоматически проверяют lock, если манифест или lock присутствует рядом
с входным `.sdr`-файлом. Отсутствующий, испорченный либо устаревший lock
вызывает отказ, а не автоматическую перезапись.

При обычных импортах Rust повторно сверяет SHA-256 импортированных
файлов из `vendor/` непосредственно после чтения их байтов.

## Ограничения и безопасность

- Только точные локальные зависимости под `vendor/`; транзитивные зависимости
  задаются там же root-relative путями.
- Максимум 32 пакета, 256 файлов и 8 МиБ на пакет, 1024 записи каталогов,
  глубина 16, длина относительного пути 1024 символа.
- Манифест до 32 КиБ, lock до 128 КиБ; строгий TOML и JSON без повторов ключей.
- Запрещены symlink, hardlink-файлы на POSIX, скрытые/специальные файлы,
  выход за корень, циклические и конфликтующие зависимости.
- Нет поиска пакетов, скачивания, semver-диапазонов, `pkg:`-URL,
  пространства имён в Rust app-mode и полного переноса Python 0.12
  экспортов модулей, содержащих state/actions.
- Совпадение lock не защищает от одновременной злонамеренной замены каталогов;
  проектная директория должна быть доверенной.
- Генераторы Site/WebApp проверяют lock при запуске, но повторное
  побайтовое сверение каждого их внутреннего импорта и непротиворечивая
  source map для всех форм `import ... as alias` ещё требуют проверки.

Для проектов **без** `sedrava.toml` и `sedrava.lock` сохраняется прежнее
поведение обычных локальных импортов, кроме запрещённых необозреваемых
импортов из `vendor/`.

Проверки:

```sh
cargo test --manifest-path rust/Cargo.toml --locked --all-targets
python3 scripts/verify_native_packages.py
```

Сопоставление с примером Python 0.12 проверило и чтение исходного
`sedrava.lock`, и **побайтовое совпадение** lock, повторно созданного Rust.
Ни полный переход всей версии 0.12, ни производственная готовность
этим не утверждаются.
