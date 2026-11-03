# Quick Start / Быстрый старт — Sedrava 0.10.0

**Published release:** [GitHub v0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) · [PyPI](https://pypi.org/project/sedrava/0.10.0/). Sedrava remains experimental, not a production-support guarantee.

## Install / Установка

Requires Python **3.10+**. Use a virtual environment:

```sh
# Linux: use python3, since some distributions have no 'python' alias.
python3 -m venv .venv
. .venv/bin/activate
python -m pip install sedrava==0.10.0
sedrava --version
```

On Windows, create the environment with `py -3 -m venv .venv`, activate with `.venv\Scripts\Activate.ps1`, then run `python -m pip install sedrava==0.10.0`. To work from a repository checkout instead, use `python -m pip install .` after activation. If `python3 -m venv` is unavailable on Ubuntu/Debian, install the distro's `python3-venv` package.

## First app / Первое приложение

Create a UTF-8 file `hello.sdr`:

```text
app "Hello Sedrava"
state count = 0
action add: count = count + 1
rule count >= 0 and count <= 10
test once: add -> count == 1
screen main:
    text "Hello Sedrava"
    value count
    button "Add" -> add
```

```sh
sedrava check hello.sdr
sedrava test hello.sdr
sedrava run hello.sdr add add
sedrava build web hello.sdr --output build/web/index.html
python -m http.server 8000 --directory build/web
```

Open http://localhost:8000. The `run` command prints `{"count": 2}`; it is not a GUI. The Web generator produces a standalone HTML application.

## Text, records and navigation / Текст, записи и навигация

Included in **0.10.0**: [text](LANGUAGE_0_10_TEXT.md), [records and bounded lists](RECORDS_COLLECTIONS_010.md), [multi-screen navigation](NAVIGATION_010_CONTRACT.md). Clone the repository to use the checked-in examples:

```sh
git clone https://github.com/VasiliiBabkin/sedrava.git
cd sedrava
sedrava check examples/task_manager_navigation.sdr
sedrava test examples/task_manager_navigation.sdr
sedrava build android examples/task_manager_navigation.sdr --output build/tasks-android
```

`build android` generates Kotlin/Compose source, **not an APK**. Compile with JDK, Android SDK and Gradle per [BUILD.md](BUILD.md). Data migrations and encrypted persistence are not provided. Final 0.10 APK physical-device acceptance is not recorded.

`sedrava build site` is experimental in [draft PR #22](https://github.com/VasiliiBabkin/sedrava/pull/22), **not** part of the released CLI. [sedrava-site](https://github.com/VasiliiBabkin/sedrava-site) is a separate Astro/Starlight website.


## Post-release Linux smoke test / Ручная проверка Linux

Installation from PyPI, CLI `check`/`test`/`run`, HTML generation and tester-confirmed browser interaction passed on 2026-11-01 in a Linux virtual environment using Python 3.13. See the [evidence and scope](MANUAL_LINUX_WEB_SMOKE_0_10_0_2026-11-01.md). Physical Android acceptance is separate.

## Experimental Web UI 0.11 / Экспериментальный Web UI 0.11

Source-branch feature, separate from published RC2. Режим из этой ветки, отдельно от опубликованного RC2.

```sh
sedrava check examples/web_ui_011_landing.sdr
sedrava build site examples/web_ui_011_landing.sdr --output build/site
python -m http.server 8000 --directory build/site
```

13 static primitives, responsive layouts and safe assets; no deployment. 13 статических компонентов, адаптивность и безопасные ресурсы; без публикации сайта. [English](WEB_UI_011.en.md) · [Русский](WEB_UI_011.ru.md). Existing application commands are unchanged. Команды приложений не изменены.


## Experimental 0.11 integration / Экспериментальная интеграция

The integration preview adds shared composition, pure functions, bounded collection queries, forms/tables/dialogs, hash routes, local styling and typed public HTTP. It is not a published 0.11.0 or a backend/auth/database service.

Реализованные возможности, сборка четырёх проектов и ограничения: [English guide](011_WEB_PLATFORM.en.md), [руководство](011_WEB_PLATFORM.ru.md), [actual status](011_IMPLEMENTATION_STATUS.md). Existing published 0.10.0 instructions above remain applicable to their original targets.
