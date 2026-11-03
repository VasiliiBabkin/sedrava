# Sedrava 0.10 UI status / Состояние интерфейсов

Historical 0.10 UI implementation record. The capabilities described below are included
in the published [0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0).
This document describes the pre-release implementation status and is retained for provenance.
More general site layout and themes are explored separately in the draft 0.11 Web UI PR.

## Implemented / Реализовано

- Named screens with explicit initial screen, shared domain state and guarded entry.
- Bounded push/pop stack in the Python core and generated JavaScript/Kotlin.
- Atomic domain-action-plus-navigation bindings; stable collection selection.
- Browser Back/Forward and Compose system Back, with defined root behavior.
- Responsive Web cards and native Compose surfaces, labeled inputs, focus handling.
- One two-screen [task manager](../examples/task_manager_navigation.sdr).

Use the [normative navigation syntax](NAVIGATION_010_CONTRACT.md),
[English guide](NAVIGATION_QUICKSTART.en.md) or
[русское руководство](NAVIGATION_QUICKSTART.ru.md).
Measured results belong to [NAVIGATION_010_REPORT.md](NAVIGATION_010_REPORT.md).

## Remaining / Осталось

Deep links, route parameters, tabs, general reusable layout components, animations,
custom themes, nested data schemas and physical-device accessibility acceptance
are separate work. No natural-language interpretation or generated host callbacks
are required or promised. Existing 0.9 and records/text examples retain their syntax.

Русский: экраны и переходы описываются в `.sdr`, семантика проверяется в ядре.
Текст, записи и списки уже реализованы. Полный набор тем, компонентов и глубоких
ссылок пока отсутствует. Успешный APK не заменяет проверку UI; отчёт разделяет
JVM, эмулятор и физическое устройство. Релиз 0.10.0 опубликован; испытания конечного APK на физическом устройстве остаются неподтверждёнными.
