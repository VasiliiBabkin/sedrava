# Android application identity (Sedrava 0.10.0)

The display title is the `.sdr` `app "…"` declaration. Android installation identity is a build setting; it does not change language semantics.

```sh
sedrava build android examples/task_manager_navigation.sdr --output build/daybook
sedrava build android examples/task_manager.sdr --output build/tasks
# Choose and keep your own identity for an app that may change its title:
sedrava build android examples/task_manager_navigation.sdr --application-id com.example.daybook --output build/my-daybook
gradle -p build/daybook --no-daemon :app:assembleDebug :app:lintDebug
```

Default: `org.sedrava.app.a` followed by the first 32 hexadecimal SHA-256 digits of the **exact UTF-8 app title**. No normalization, trimming, filenames, paths, source-code hashes, random values or timestamps. Rebuilding/editing actions with the same title preserves identity. Different titles (including case, whitespace, punctuation and canonically different Unicode) get different hashes; identical titles deliberately share identity. A 128-bit digest is collision resistant, not a global registry. Choose distinct explicit IDs for distinct apps with identical titles, and do not reuse another application's ID.

`--application-id` is accepted only for Android. The portable subset is 2 or more dot-separated lowercase ASCII segments, each starting with a letter followed by letters, digits or underscores; maximum 255 characters overall. Java/Kotlin keywords are rejected. Bad IDs fail before creating a project. Python API: `android_codegen_v03.generate(source, output, application_id="com.example.daybook")`.

Resolved application ID, Gradle namespace and Kotlin package are identical. `sedrava-android.json` records identity/title/schema; source paths follow the package. Tests and permission audits read this identity. Reusing an output directory with a different identity fails; choose another directory. For projects generated before identity metadata existed, regenerate in a fresh output directory. Generated code is disposable; keep the `.sdr` source.

Android keeps private data by application ID. An update preserves data when ID, signing certificate and compatible storage schema are unchanged, and Android accepts its version code. Debug builds use the local Android debug keystore; another machine can have a different key. This RC uses development `versionCode=10001` (older builds used 1) and `versionName=0.10.0rc1`; it is not a production app-version strategy. `adb install -r` supports local repeated debug updates. Explicit identity allows title changes without moving storage. Changing ID installs a separate app; no automatic data migration. To update an old shared-package experimental app, opt in to `--application-id org.sedrava.generated` with its original signing key; do not install multiple apps using this legacy ID.

Display names are escaped Android string resources, independent of namespace. Names may contain Unicode, `@`, `?`, quotes and whitespace. No extra device permissions are needed. Web remains a self-contained offline HTML file; its storage scope is URL pathname plus title, so renaming/moving it starts a separate snapshot.

Inspect and launch the actual generated package:

```sh
python -c "import json; print(json.load(open('build/daybook/sedrava-android.json'))['application_id'])"
adb install -r build/daybook/app/build/outputs/apk/debug/app-debug.apk
# Replace PACKAGE with the printed value:
adb shell am start -n PACKAGE/.MainActivity
```

Separate installation identities are implemented; encrypted storage, automatic schema migration, release signing, Gradle wrapper and a general design/layout API remain unavailable. [Russian guide](ANDROID_ID.ru.md).
