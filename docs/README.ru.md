# Sedrava — документация (0.10.0)

**Опубликованная версия:** [GitHub 0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) и [PyPI](https://pypi.org/project/sedrava/0.10.0/), 31 октября 2026 года. Язык экспериментальный; это не гарантия готовности к промышленной эксплуатации.

## Состояние выпусков

Действующая стабильная версия — **0.10.0** (ссылки ниже). Экспериментальная [0.11.0rc1 опубликована на GitHub](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1) и [PyPI](https://pypi.org/project/sedrava/0.11.0rc1/). Стабильная **0.11.0 ещё не опубликована**; её исходники проходят отдельную проверку, Android versionCode 11002. [Критерии выпуска](STABLE_RELEASE_GATES_011.md) · [русские заметки](RELEASE_NOTES_0_11_0.ru.md).

В опубликованном кандидате и готовящейся стабильной версии есть `build site`, `build webapp`, типизированные Web-компоненты, функции и ограниченный HTTP-клиент. Нет встроенного сервера, SQLite, авторизации, миграций и пакетов с пространствами имён.

## Установка

Нужен Python **3.10+**:

```sh
python -m venv .venv
# Linux/macOS:
. .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install sedrava==0.10.0
sedrava --version
```

Для разработки из исходников можно клонировать репозиторий и выполнить `python -m pip install .`.

## Руководства

- [Быстрый старт](QUICKSTART.md), [список примеров](../examples/README.md).
- [Текстовые значения](LANGUAGE_0_10_TEXT.md), [записи и коллекции](RECORDS_COLLECTIONS_010.md), [многоэкранная навигация](NAVIGATION_010_CONTRACT.md).
- [Менеджер задач](RECORDS_QUICKSTART.ru.md), [двухэкранный пример](NAVIGATION_QUICKSTART.ru.md).
- [Сборка Web и Android](BUILD.md), [идентификаторы приложений](ANDROID_ID.ru.md).
- [FAQ](FAQ.md), [совместимость](COMPATIBILITY_010.md), [ограничения](KNOWN_LIMITATIONS.md), [безопасность](SECURITY.md).
- [Дорожная карта](ROADMAP.md), [описание релиза](RELEASE_NOTES_0_10_0.md), [исторический справочник 0.9](LANGUAGE_0_9.md).

Команды `check`, `test`, `run`, `build web` и `build android` доступны в 0.10.0. Последняя создаёт исходники Kotlin/Compose, **не APK**.

В 0.10.0 входят int32, bool, строки, типизированные записи, ограниченные коллекции, инварианты, атомарные действия и навигация. Не предусмотрены автоматические миграции хранилища, шифрование состояния или гарантии совместимости API 1.0.

**Граница проверки:** испытания конечного APK 0.10 на физическом телефоне [не подтверждены протоколом](PHYSICAL_DEVICE_010.md), хотя проверки на эмуляторе выполнялись. `sedrava build site` уже доступна в [опубликованной экспериментальной 0.11.0rc1](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1), а [сайт документации](https://github.com/VasiliiBabkin/sedrava-site) собирается отдельно через Astro/Starlight.


**Проверка релиза на Linux:** [ручной smoke-test 1 ноября 2026 года](MANUAL_LINUX_WEB_SMOKE_0_10_0_2026-11-01.md) (установка из PyPI, CLI и Web); испытания физического Android этим не подтверждаются.

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
