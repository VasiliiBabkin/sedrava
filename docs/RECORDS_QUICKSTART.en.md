# Build an offline task manager (Sedrava 0.10.0)

Use Python 3.10+ and the published Sedrava 0.10.0 package; clone the repository for example files:

```sh
git clone https://github.com/VasiliiBabkin/sedrava.git
cd sedrava
python -m pip install '.[test]'
sedrava check examples/task_manager.sdr
sedrava test examples/task_manager.sdr
sedrava run examples/task_manager.sdr
sedrava run examples/task_manager.sdr --state-file build/tasks-state.json
sedrava build web examples/task_manager.sdr --output build/tasks-web/index.html
python -m http.server 8000 --directory build/tasks-web
```

Open http://localhost:8000. Enter a title and Add. Select a row; Complete toggles
completion, Rename uses the current title input, Delete removes the selected ID.
The title input is cleared after successful add/rename. Empty title and missing
selection produce a rejection message. Whitespace is preserved. Reload to restore
tasks. Empty lists display a message. There are at most 100 tasks.

The [source](../examples/task_manager.sdr) is the complete app for both targets.
Records declare fields before state. List declarations specify capacity. Actions
assign immutable list results; `require` rejects an action before mutation.
`get` looks up an ID; it never interprets an ID as an index. `list … select …`
generates selection controls. No JavaScript/Kotlin edits are needed.
See the [normative syntax and types](RECORDS_COLLECTIONS_010.md).

For Android, configure JDK 17, Android SDK 35 and Gradle 8.11.1 as in
[BUILD.md](BUILD.md):

```sh
sedrava build android examples/task_manager.sdr --output build/tasks-android
python scripts/prepare_records_android_tests.py build/tasks-android
gradle -p build/tasks-android --no-daemon :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
adb install -r build/tasks-android/app/build/outputs/apk/debug/app-debug.apk
```

Select a task, change completion/title, rotate and relaunch. Accepted full state
is saved for recreation; only `persist` fields survive process relaunch. Invalid
drafts are not promised to survive recreation. Storage is local and unencrypted.
Current Android builds use independent deterministic IDs; see [identity settings](ANDROID_ID.en.md).

Validation: `python -m unittest discover -s tests -v`,
`python scripts/test_web_browser.py` (Playwright + Chromium). JVM oracle tests
exercise emitted Kotlin state functions; emulator tests additionally exercise
Compose. The [measured report](COLLECTIONS_010_REPORT.md) distinguishes these
from physical-device evidence. No 0.10 release is claimed.
