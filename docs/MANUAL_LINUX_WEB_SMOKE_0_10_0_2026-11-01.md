# Sedrava 0.10.0 — manual Linux + Web smoke test (2026-11-01)
# Ручная проверка Sedrava 0.10.0 на Linux и в браузере

**Result / Результат:** PASS for the exact CLI and Web smoke scenarios listed below.
**Evidence type / Источник:** terminal screenshots provided by the tester in conversation, followed by explicit user confirmation that the browser application worked. These screenshots are **not** attached to this Git repository; commands were not independently rerun by the maintainers on the tester's host.

## Tested artifact and environment / Проверенная среда

| Field | Observed / Наблюдение |
| --- | --- |
| Test date | **2026-11-01** (local date visible in terminal output; after midnight) |
| Published distribution | `sedrava==0.10.0` installed from the public PyPI index |
| Distribution file | `sedrava-0.10.0-py3-none-any.whl` (pip output showed a wheel download) |
| CLI version | `sedrava 0.10.0` |
| OS / shell | Linux shell with Bash; exact distribution and version not recorded |
| Python | Virtual-environment package path showed `.venv/lib/python3.13/site-packages`, consistent with **Python 3.13**; exact `python3 --version` output not recorded |
| pip | Updated to `26.2.2` in the virtual environment |
| Web test | Generated local HTML, served by `python -m http.server` at `127.0.0.1:8000`; browser model/version not recorded |
| Repository checkout | Not required for the smoke program `hello.sdr`; the package was installed through pip |

The first installation attempt failed because the host did **not** expose the `python` command before a virtual environment was activated (`-bash: python: команда не найдена`). After an environment was successfully created and activated, `python`, `pip` and `sedrava` worked. Thus Linux onboarding should prefer `python3 -m venv .venv` before using `python` inside the activated environment.

## Source used for the manual test / Исходная программа

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

## Observed commands and results / Команды и результаты

| Check | Command or action | Observed result |
| --- | --- | --- |
| PyPI installation | `python -m pip install sedrava==0.10.0` | `Successfully installed sedrava-0.10.0` |
| Package identification | `sedrava --version` | `sedrava 0.10.0` |
| CLI entry point | `sedrava --help` | Subcommands `check`, `run`, `test`, `build` listed |
| Parser/type checking | `sedrava check hello.sdr` | `OK: hello.sdr` |
| Embedded tests | `sedrava test hello.sdr` | `PASS: 1 Sedrava tests` |
| Interpreter | `sedrava run hello.sdr add add` | `{"count": 2}` |
| Web build | `sedrava build web hello.sdr --output build/web/index.html` | Generated `build/web/index.html` (approximately **7.4 KB** reported by `ls -lh`) |
| Local serving | `python -m http.server 8000 --bind 127.0.0.1 --directory build/web` | Server reported listening on `127.0.0.1:8000` |
| Browser interaction | Open generated page and test counter/Add | Tester explicitly confirmed **«Всё работает»**; no independent browser trace or screenshot was supplied |

## Scope and limitations / Границы подтверждения

- The results are **manual smoke-test evidence** from a real Linux Python 3.13 environment, **not** new CI evidence, a compatibility certification, or proof of all supported features.
- A successful generated HTML file and an HTTP server listening do not alone prove browser operation; the browser check is recorded as **tester-confirmed**, not instrumented.
- No Web error log, DOM trace, screenshot of the rendered page, file checksum, or exact browser version was collected for this run.
- The test did **not** exercise Android builds or a physical Android device, record collections, multi-screen navigation, persistence/reload, or security properties. The [0.10 physical-device acceptance checklist](PHYSICAL_DEVICE_010.md) remains **open**.
- The already published [release tag v0.10.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) and [PyPI artifacts](https://pypi.org/project/sedrava/0.10.0/) are **unchanged**. This report records later post-publication validation in repository documentation.

**Conclusion / Вывод:** installation from PyPI, CLI check/test/run and HTML generation were directly supported by the terminal evidence; browser usability was confirmed by the tester. No broader platform acceptance is inferred.
