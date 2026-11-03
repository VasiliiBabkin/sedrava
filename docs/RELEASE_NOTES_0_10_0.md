# Sedrava 0.10.0 — заметки о стабильном выпуске / Release notes

**Релиз:** [GitHub v0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) · [PyPI 0.10.0](https://pypi.org/project/sedrava/0.10.0/).

**Описал приложение — получил приложение.** Sedrava позволяет описать небольшое приложение в одном `.sdr` и сгенерировать автономное Web-приложение или проект Android/Jetpack Compose.

## Возможности / Capabilities

- Строгие типы text (до 1024 Unicode scalar values), signed int32, boolean.
- Типизированные записи и упорядоченные списки (до 100 элементов) с устойчивыми ID.
- Атомарные действия с откатом, инварианты и встроенные тесты.
- Экраны, навигация с ограниченным стеком до 32 и guarded transitions.
- Web: история, восстановление сохранённых значений. Android: системный Back, сохранение принятого сеанса.
- CLI: `check`, `test`, `run`, `build web`, `build android`; Python >=3.10, без внешних runtime dependencies.

## Установка / Installation

```sh
python -m pip install sedrava==0.10.0
sedrava --version
```

Версия [опубликована на PyPI](https://pypi.org/project/sedrava/0.10.0/) 31 октября 2026 года. Команда `sedrava --version` сообщает установленную версию.

## Проверка / Verification

Для RC2 существуют отчёты Python/JavaScript/Kotlin/Chromium/Android emulator ([RC2 report](RC2_010_REPORT.md)). На финальном SHA `688a320025a0d38235eb90c780362ec26b0708e2` успешно прошли публикация wheel/sdist и применимые проверки CI, Android и текста ([workflow](https://github.com/VasiliiBabkin/sedrava/actions/runs/41237159326)). Успешное выполнение физического теста не подтверждено: см. [device checklist](PHYSICAL_DEVICE_010.md).

## Ручная проверка после релиза / Post-release manual smoke test

1 ноября 2026 года пользователь подтвердил установку `sedrava==0.10.0` с PyPI на Linux (виртуальное окружение Python 3.13), успешные `check`, `test` и `run`, генерацию HTML и работу приложения в браузере. Проверки CLI и генерации зафиксированы снимками терминала; браузерный результат сообщён тестировщиком. [Подробный отчёт и ограничения](MANUAL_LINUX_WEB_SMOKE_0_10_0_2026-11-01.md). Это не заменяет приёмку Android на реальном устройстве.

## Совместимость и ограничения / Compatibility and limitations

Android versionCode **10003** > rc2 **10002**. Обновление возможно лишь при совпадении application ID и подписи. Автоматических миграций нет; несовместимые данные отклоняются с сохранением оригинального снимка. При ошибке записи принятые изменения могут остаться только в памяти. Одновременные авторы записи не синхронизируются. Web storage зависит от origin; данные Android не шифруются самим Sedrava. Нет модулей, циклов, deep links и гарантии стабильного API. Подробности: [compatibility](COMPATIBILITY_010.md), [known limitations](KNOWN_LIMITATIONS.md), [Android IDs](ANDROID_ID.en.md).

**Назначение:** учебная и экспериментальная разработка, не production.

**English:** Sedrava 0.10.0 was publicly released on GitHub and PyPI on 31 October 2026 with text, records, bounded lists, atomic actions, invariants and navigation. The language remains experimental; final 0.10 physical Android acceptance is not yet documented.
