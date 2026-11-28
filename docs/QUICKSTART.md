# Быстрый старт / Quickstart

**Описал — получил.**

Sedrava — декларативный язык программирования. Основная и единственная развиваемая реализация — Rust. Текущая линия **0.12.0-alpha.4**: экспериментальная, не для промышленной эксплуатации.

[Загрузить Linux x86-64](https://sedrava.virtreal.ru/downloads/0.12.0-alpha.4/) · [Релиз GitHub](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.12.0-alpha.4) · [Официальный сайт](https://sedrava.virtreal.ru/ru/) · [English](README.en.md).

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


[English guide](README.en.md) · [Distribution](DISTRIBUTION_NATIVE.ru.md) · [Examples](../examples/README.md).

**Format 2 / формат 2:** [A39 installation and domain example](PLATFORM_RELEASE_A39.ru.md) · [A37 model](SERVICE_DOMAIN_A37.ru.md) · [A38 qualification](QUALIFICATION_A38.ru.md). Experimental A33–A37 databases are incompatible with A38 semantic migration names; use new private test data.
