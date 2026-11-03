# Sedrava 0.10 text semantics / Строковое ядро Sedrava 0.10

Sedrava **0.10.0** includes immutable text in the shared AST, Python interpreter/CLI, Web and Android generators. It is [published on PyPI](https://pypi.org/project/sedrava/0.10.0/) and [GitHub](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0). The [0.9 reference](LANGUAGE_0_9.md) remains historical; this page specifies exact text semantics.

## Describe → Get

```sedrava
app "Text profile"
state name = "Guest"
persist name
derive named = name != ""
action rename: name = "Алиса 😀"
rule named
test rename: rename -> name == "Алиса 😀"
screen main:
    input name
    value name
    show named : text "Name accepted"
    button "Rename" -> rename
```

`input name` is inferred from the declared type: multiline text editor for text, numeric editor for int32. `value`, `derive`, action assignments, tests, comparisons and persistence use genuine typed values; authors write no callbacks or target code. An empty text value is legal unless a rule forbids it. This example deliberately starts with a valid nonempty name.

## Grammar and scalar values

A text expression is a **double-quoted** literal, a text state, or a previously declared text derive. Exactly five escapes are supported: `\\`, `\"`, `\n`, `\r`, `\t`. Invalid escapes, unclosed quotes, single quotes, Python raw/f strings and implicit adjacent-literal concatenation are rejected. Real newlines/CR cannot occur inside source literals; use escapes. Literal `true`/`false` inside quotes remains text. Static `app`, `text`, `show … : text` and button labels use the same escape-aware decoder.

The maximum is **1024 Unicode scalar values**, not UTF-16 code units, bytes or user-perceived grapheme clusters. Thus 1024 emoji `😀` fit; 1025 do not. Combining marks each count separately. Unpaired surrogates are rejected at source, input and persistence boundaries. A valid UTF-16 pair on JavaScript/JVM represents one scalar. UTF-8 decoding is strict. No normalization, trimming, case folding, implicit conversions or truncation applies to accepted text. Equality compares the exact scalar sequence: `"é" != "é"` and `"Name" != "name"`.

Text supports `==`/`!=` with text operands, and assignment to text state. It does **not** support ordering, concatenation, interpolation, indexing, regex, numeric conversion or a string-length operation. Empty checks use `name == ""` / `name != ""`. Integer and boolean semantics remain unchanged. JSON `run` returns strings as JSON strings, preserving accepted scalar values.

## Atomicity, drafts and restoration

An action computes a candidate; all derives are checked after each assignment and rules against the final candidate. Mixed text/int32/bool updates commit together or are all rejected. Generated callbacks and the Android JVM conformance suite call the same emitted pure state functions. Failures leave accepted state unchanged and display an error.

A text draft commits immediately only if scalar/length/type/derived/rule checks pass. Invalid drafts remain editable with accessible error feedback. Empty drafts are validated too: they commit if allowed, otherwise remain rejected drafts. Whitespace-only text remains nonempty; the runtime does not trim it. There is no `maxlength` truncation in HTML or Compose. Accepted Android state uses `rememberSaveable`; rejected drafts are not promised to survive recreation.

Only `persist` fields are saved. Wrong-type, oversized or surrogate-containing fields individually use defaults. The resulting snapshot is then checked as a whole; a rule/derive failure restores all defaults. Unknown keys are ignored, nonpersistent fields start from defaults, malformed Web JSON is ignored. Android uses the typed contents of `SharedPreferences.all`; malformed preference XML recovery belongs to Android itself. Storage is local, unencrypted and best effort as in 0.9. Generated apps use deterministic per-title Android IDs; explicit overrides are supported.

## Explicit compatibility and platform boundaries

- **Escaped legacy labels:** 0.9's regex labels treated backslashes literally. One uniform escape grammar is necessary to avoid contradictory meanings of the same literal in state and UI. In this development increment, labels containing backslashes must escape them: `text "C:\\temp"` displays `C:\temp`; `text "line\nnext"` now displays a newline. All published 0.9 examples retain their behavior. Migration is covered by `test_legacy_label_backslash_migration_is_explicit`; invalid escapes fail instead of being silently reinterpreted. No 0.9 tag or artifact is changed.
- **Native editor line endings:** HTML textarea normalizes CR and CRLF in the *draft* to LF, per browser behavior. The runtime adds no additional normalization. Source/action/model/persisted strings retain CR, LF and exact equality; their display in an editor follows the platform's editor behavior. A Chromium conformance test checks both the native draft normalization and exact model acceptance of CR. This boundary is disclosed rather than claiming byte-identical native editing.
- Android compilation, JVM state tests, signature checks and Lint do not establish Compose UI/rotation/device acceptance. See the [work report](TEXT_010_REPORT.md) for measured coverage.
- Records and bounded lists are implemented in main since PR #14; see [syntax](RECORDS_COLLECTIONS_010.md). Named screens, responsive task cards and Back are implemented in the [navigation increment](NAVIGATION_010_CONTRACT.md). Per-app package identity is implemented; general toggles and custom themes/layout components remain separate milestones. The full [Describe → Get target](DESCRIBE_GET_010.md) is not yet implemented.

## Reproduce / Повторить

```sh
python -m pip install ".[test]"
sedrava --version
sedrava check examples/text_profile.sdr
sedrava test examples/text_profile.sdr
sedrava run examples/text_profile.sdr rename
sedrava build web examples/text_profile.sdr --output build/text-web/index.html
python -m http.server 8000 --directory build/text-web
```

Open http://localhost:8000. Enter a Unicode name, reload, try an empty name and correct it; the invalid draft must not change accepted state. The “Try rejected blank action” button also attempts to change counters/flags, demonstrating rollback of the whole action.

For an APK, install JDK 17, SDK 35 and Gradle 8.11.1 as in [BUILD.md](BUILD.md):

```sh
sedrava build android examples/text_profile.sdr --output build/text-android
python scripts/prepare_text_android_tests.py build/text-android
gradle -p build/text-android --no-daemon clean :app:assembleDebug :app:lintDebug :app:testDebugUnitTest
python scripts/verify_apk.py build/text-android/app/build/outputs/apk/debug/app-debug.apk
```

The test-preparation script adds only test sources; generated application code is unchanged. APK: `build/text-android/app/build/outputs/apk/debug/app-debug.apk`. The [text Android CI](../.github/workflows/text-010.yml) builds both the profile and hostile-string fixture with the same process, uploading APKs, Web output and evidence. Full Python/Node and Chromium suites remain mandatory.

Русский: строка — полноценное неизменяемое значение, а не только элемент интерфейса. Тип редактора выводится из состояния; проверка, сохранение и обработчики генерируются. Лимит — 1024 Unicode scalar values; emoji считается одним значением, составной графемный кластер может содержать несколько. Нет автоматической нормализации и усечения. Некорректный ввод не меняет принятое состояние; отказ действия отменяет все связанные изменения. Это реализованный промежуточный шаг, а не выпуск всей версии 0.10.

Collection programs use strict whole-snapshot restoration; scalar-only programs retain
the text restoration contract above. See [collection specification](RECORDS_COLLECTIONS_010.md).

## Release engineering / История проверки перед выпуском

Independent deterministic Android IDs and `--application-id` are implemented.
Независимые Android-приложения собираются с постоянным ID; название отделено от пакета.
[English identity/build guide](ANDROID_ID.en.md) · [Русская инструкция](ANDROID_ID.ru.md).
Wheel/sdist include examples, documentation and license under `sys.prefix/share/sedrava`.
Дистрибутив 0.10.0 опубликован на PyPI; исходные отчёты проверки относятся к подготовке.
