# Sedrava documentation — English (0.10.0)

**Published:** [GitHub release](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) and [PyPI](https://pypi.org/project/sedrava/0.10.0/), 31 October 2026. The language is experimental, not a production framework.

## Install

Python **3.10+**:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install sedrava==0.10.0
sedrava --version
```

For Windows PowerShell use `.venv\Scripts\Activate.ps1`. To develop from source, clone the repository and use `python -m pip install .`.

## Documentation

- [Quick Start](QUICKSTART.md) — first program and CLI.
- [Text semantics](LANGUAGE_0_10_TEXT.md), [records and collections](RECORDS_COLLECTIONS_010.md), [multi-screen navigation](NAVIGATION_010_CONTRACT.md).
- [Examples](../examples/README.md), [task-manager guide](RECORDS_QUICKSTART.en.md), [navigation example](NAVIGATION_QUICKSTART.en.md).
- [Build Web and Android](BUILD.md), [Android identifiers](ANDROID_ID.en.md).
- [FAQ](FAQ.md), [compatibility](COMPATIBILITY_010.md), [known limitations](KNOWN_LIMITATIONS.md), [security notes](SECURITY.md).
- [Roadmap](ROADMAP.md), [0.10 release notes](RELEASE_NOTES_0_10_0.md), and the [historical 0.9 reference](LANGUAGE_0_9.md).

`sedrava check FILE` validates, `sedrava test FILE` runs embedded tests, `sedrava run FILE ACTION...` prints JSON state, and `sedrava build web/android FILE --output PATH` generates platform output. Android generation yields sources, **not a compiled APK**.

0.10.0 includes signed int32, bool, Unicode text, typed records and bounded lists, atomic actions, invariants, persistence and navigation. No data migrations, encrypted storage, modules, automatic timers or production API compatibility guarantee. The [draft 0.11 Web UI work](https://github.com/VasiliiBabkin/sedrava/pull/22) is not in this release. The [Astro/Starlight site](https://github.com/VasiliiBabkin/sedrava-site) is independent.

**Evidence boundary:** [final 0.10 physical-device acceptance](PHYSICAL_DEVICE_010.md) remains unconfirmed; passing emulator tests do not prove phone compatibility.


**Linux release smoke test:** [manual verification on 1 November 2026](MANUAL_LINUX_WEB_SMOKE_0_10_0_2026-11-01.md) (PyPI installation, CLI and Web). Physical Android acceptance is separate.

## Experimental Web UI 0.11 / Экспериментальный Web UI 0.11

Source-branch feature, separate from published RC2. Режим из этой ветки, отдельно от опубликованного RC2.

```sh
sedrava check examples/web_ui_011_landing.sdr
sedrava build site examples/web_ui_011_landing.sdr --output build/site
python -m http.server 8000 --directory build/site
```

13 static primitives, responsive layouts and safe assets; no deployment. 13 статических компонентов, адаптивность и безопасные ресурсы; без публикации сайта. [English](WEB_UI_011.en.md) · [Русский](WEB_UI_011.ru.md). Existing application commands are unchanged. Команды приложений не изменены.
