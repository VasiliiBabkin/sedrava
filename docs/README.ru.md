# Sedrava — язык и инструментарий на Rust

**Описал — получил.**

Sedrava — декларативный язык программирования. Основная и единственная развиваемая реализация — Rust. Текущая линия **0.12.0-alpha.2**: экспериментальная, не для промышленной эксплуатации.

[Загрузить Linux x86-64](https://sedrava.virtreal.ru/downloads/0.12.0-alpha.2/) · [Релиз GitHub](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.12.0-alpha.2) · [Официальный сайт](https://sedrava.virtreal.ru/ru/) · [English](README.en.md).

## Установка и первая программа

Готовый бинарник **sedrava** работает без установки Python или Rust. На Linux x86-64 GNU проверен Ubuntu 24.04. Установщик проверяет SHA-256 и не перезаписывает существующий файл. Windows/macOS не проверены.

Создайте UTF-8 файл hello.sdr:

~~~text
app "Hello Sedrava"
state count = 0
action add: count = count + 1
rule count >= 0 and count <= 10
test once: add -> count == 1
screen main:
    text "Hello Sedrava"
    value count
    button "Add" -> add
~~~

~~~sh
sedrava check hello.sdr
sedrava test hello.sdr
sedrava run hello.sdr add add
sedrava build web hello.sdr --output build/hello.html
sedrava build android hello.sdr --output build/hello-android --application-id org.example.hello
~~~

Android-команда создаёт Kotlin/Compose-проект; для APK нужны JDK, SDK и Gradle. См. [сборку](BUILD.md). Для новых проектов используйте отдельные тестовые данные и новые выходные каталоги.

## Сборка из исходников

~~~sh
git clone https://github.com/VasiliiBabkin/sedrava.git
cd sedrava
cargo build --manifest-path rust/Cargo.toml --locked --release --bin sedrava
./rust/target/release/sedrava --version
cargo test --manifest-path rust/Cargo.toml --locked --all-targets
~~~

## Что поддерживается

- Типизированное состояние, действия, инварианты, записи, ограниченные списки, функции, навигация, Unicode, импорты и локальные пакеты.
- Генерация автономного Web, Site, WebApp и поддерживаемых Android-приложений.
- Ограниченный trusted Host, локальный HTTP, типизированный SQL API A21 с ролями, квитанциями и последовательными транзакциями.
- [SedravaSQL](https://sql.virtreal.ru/): NativeLog SQL; страничное B+Tree B25 пока отдельный эксперимент.
- Self-host A5.11b — отдельный эксперимент собственного компилятора, не основной компилятор.

Не все конструкции поддерживаются всеми целевыми генераторами. Полная матрица браузеров/устройств, Windows/macOS, совместимость старых проектов и промышленная безопасность не установлены.

[Быстрый старт](QUICKSTART.md) · [Распространение](DISTRIBUTION_NATIVE.ru.md) · [Заметки к выпуску](RELEASE_NOTES_0_12_0_ALPHA2.md) · [Дорожная карта](ROADMAP.md) · [Примеры](../examples/README.md) · [Измерения](BENCHMARK_2026_11_24.ru.md) · [История](HISTORY.md).

Посвящение: [Геннадию Ивановичу Смирных](../DEDICATION.md). Лицензия Apache-2.0.

**Контрольная точка:** [состояние B31 и отчёты](DEVELOPMENT_STATUS.ru.md). В main — NativeLog SQL B28; B31 — отдельная исследовательская ветка. Публичные выпуски не изменены.
