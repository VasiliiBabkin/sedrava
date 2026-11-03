# Multi-screen task manager — Sedrava 0.10.0

Use Python 3.10+ and Sedrava 0.10.0. Run the example from a repository checkout:

```sh
python -m pip install '.[test]'
sedrava check examples/task_manager_navigation.sdr
sedrava test examples/task_manager_navigation.sdr
sedrava run examples/task_manager_navigation.sdr
sedrava build web examples/task_manager_navigation.sdr --output build/navigation-web/index.html
python -m http.server 8000 --directory build/navigation-web
```

Open http://localhost:8000. Add a title, open its card, edit the task title and
Save, toggle completion, then return with the app button or browser Back.
Forward reopens the screen against current shared data; it does not undo edits.
Delete removes the selected stable ID and returns to the list. Empty, missing-ID,
capacity and invalid-input failures leave the whole accepted session unchanged.
The new-task input and task editor are separate declared text states.

Screens are named declarations; `navigation: initial main` chooses the root.
`action open_details -> details using prepare_details` atomically runs the named
domain action and pushes a screen. `action back -> pop` pops, with a successful
no-op at root. `screen details when chosen:` uses a bool guard; a missing selected
record rejects opening. Deleting it while the screen is active pops invalid views.
See [syntax, types and limits](NAVIGATION_010_CONTRACT.md).

A card can select and open atomically:
`list tasks select selected open open_details title title status done`.
The title field must be text; the completion status must be bool. `display`
accepts a scalar expression and `input title label "Task title"` labels an editor.
No author-written JavaScript, Kotlin or generated-file edits are needed.

Refresh and a cold Android launch open the declared initial screen and restore
only `persist` domain fields. Browser history stores screen stacks, not task
snapshots. Back at the first browser entry may leave the page. Android system
Back at root belongs to Android; explicit `pop` remains a no-op. Rotation and
Activity recreation retain the full accepted domain state and stack together.
Invalid drafts may be discarded. Unsaved record edits are explicitly reset by
`prepare_details` when a task is reopened; Save commits the title to the record.

Android requires JDK 17, SDK 35 and Gradle 8.11.1 ([build setup](BUILD.md)):

```sh
sedrava build android examples/task_manager_navigation.sdr --output build/navigation-android
python scripts/prepare_navigation_android_tests.py build/navigation-android
python scripts/prepare_navigation_ui_tests.py build/navigation-android
gradle -p build/navigation-android --no-daemon :app:assembleDebug :app:testDebugUnitTest :app:lintDebug :app:assembleDebugAndroidTest
# With a running emulator:
bash scripts/test_navigation_emulator.sh
```

Test-preparation scripts add test sources/dependencies, not application Kotlin.
The emulator scenario uses system Back, rotates/recreates the Activity, force-stops
and restarts the app, checks the real preferences and captures the restored UI.
Current Android builds use independent deterministic IDs; see [identity settings](ANDROID_ID.en.md).

Run `python -m unittest discover -s tests -v` and
`python scripts/test_web_browser.py` (Playwright/Chromium). CI and measured evidence
are recorded in the [report](NAVIGATION_010_REPORT.md) and PR #15.
