# FAQ / Вопросы о Sedrava 0.11.0

**Current stable release:** [GitHub 0.11.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0), [PyPI](https://pypi.org/project/sedrava/0.11.0/). Previous stable [0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) ([PyPI](https://pypi.org/project/sedrava/0.10.0/)) remains available. The language is experimental, not production-certified.

**What can I build?** Local applications with int32, bool, Unicode text, typed records, bounded lists, invariants, atomic actions, tests, persistence and multiple screens. [Examples](../examples/README.md).

**Does `run` open an app?** No. It interprets actions and prints JSON state. Use `build web` for standalone HTML or `build android` for Kotlin/Compose **source**, not an APK.

**Does `check` execute tests?** No. Use `test`; `build` also runs embedded checks.

**Why was an action rejected?** An invalid value, final `rule`, arithmetic or type constraint may reject it. Accepted state remains unchanged. Input drafts can remain visible until corrected.

**Do strings, lists and navigation work in 0.10.0?** Yes. Text is capped at 1024 Unicode scalars, lists at 100 items, navigation at 32 stack entries. See [text](LANGUAGE_0_10_TEXT.md), [records](RECORDS_COLLECTIONS_010.md), [navigation](NAVIGATION_010_CONTRACT.md).

**Does sedrava build site work in 0.10.0?** No. Site and WebApp generation are available in [stable 0.11.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0) ([PyPI](https://pypi.org/project/sedrava/0.11.0/)); the historical experimental [0.11.0rc1](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1) ([PyPI](https://pypi.org/project/sedrava/0.11.0rc1/)) included them as well. The official documentation site uses [Astro/Starlight](https://github.com/VasiliiBabkin/sedrava-site).

**sedrava: command not found?** Create and activate a Python virtual environment, then run `python -m pip install sedrava==0.11.0`; check `python -m pip show sedrava`. On Debian/Ubuntu, do not bypass the externally-managed-environment protection; use python3-venv instead. Source checkouts can use `python -m pip install .`.

**Android compiler/SDK errors?** Use a full JDK 17, Android SDK platform 35 and Gradle 8.11.1. See [BUILD.md](BUILD.md); do not disable TLS validation.

**Persistence problems?** Check `persist`, browser origin, Android application ID and signing key. No automatic migrations; rejected snapshots should be backed up before manual reset. Storage is unencrypted and unsuitable for secrets. [Compatibility](COMPATIBILITY_010.md).

**Are 0.9 and Intent 0.7 current?** No. Both are historical project baselines. Stable 0.11.0 is published.

**Как начать?** Установите `sedrava==0.11.0`, следуйте [быстрому старту](QUICKSTART.md) и [ограничениям](KNOWN_LIMITATIONS.md). APK собирается отдельно от Python-пакета.
