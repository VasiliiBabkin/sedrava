# FAQ / Вопросы о Sedrava 0.10.0

**Current release:** [GitHub 0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0), [PyPI](https://pypi.org/project/sedrava/0.10.0/). Experimental, not production-certified.

**What can I build?** Local applications with int32, bool, Unicode text, typed records, bounded lists, invariants, atomic actions, tests, persistence and multiple screens. [Examples](../examples/README.md).

**Does `run` open an app?** No. It interprets actions and prints JSON state. Use `build web` for standalone HTML or `build android` for Kotlin/Compose **source**, not an APK.

**Does `check` execute tests?** No. Use `test`; `build` also runs embedded checks.

**Why was an action rejected?** An invalid value, final `rule`, arithmetic or type constraint may reject it. Accepted state remains unchanged. Input drafts can remain visible until corrected.

**Do strings, lists and navigation work in 0.10.0?** Yes. Text is capped at 1024 Unicode scalars, lists at 100 items, navigation at 32 stack entries. See [text](LANGUAGE_0_10_TEXT.md), [records](RECORDS_COLLECTIONS_010.md), [navigation](NAVIGATION_010_CONTRACT.md).

**Does `sedrava build site` work in 0.10.0?** No. It is experimental in [draft PR #22](https://github.com/VasiliiBabkin/sedrava/pull/22). The separate documentation site uses [Astro/Starlight](https://github.com/VasiliiBabkin/sedrava-site).

**`sedrava: command not found`?** Activate your Python venv and use `python -m pip install sedrava==0.10.0`; verify `python -m pip show sedrava`. Use `python -m pip install .` for source checkouts.

**Android compiler/SDK errors?** Use a full JDK 17, Android SDK platform 35 and Gradle 8.11.1. See [BUILD.md](BUILD.md); do not disable TLS validation.

**Persistence problems?** Check `persist`, browser origin, Android application ID and signing key. No automatic migrations; rejected snapshots should be backed up before manual reset. Storage is unencrypted and unsuitable for secrets. [Compatibility](COMPATIBILITY_010.md).

**Are 0.9 and Intent 0.7 current?** No. Both are historical project baselines. 0.10.0 is published.

**Как начать?** Установите `sedrava==0.10.0`, следуйте [быстрому старту](QUICKSTART.md) и [ограничениям](KNOWN_LIMITATIONS.md). APK собирается отдельно от Python-пакета.
