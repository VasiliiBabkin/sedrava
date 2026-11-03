# Web and Android builds / Сборка приложений

Install Sedrava using the [Quick Start](QUICKSTART.md). Run commands from the checkout root. `build` generates source, not a production signing/distribution pipeline.

## Web

```sh
sedrava test examples/reference_09.sdr
sedrava build web examples/reference_09.sdr --output "build/web/index.html"
python -m http.server 8000 --directory build/web
```

Open http://localhost:8000. The HTML contains all application code; no CDN or network service is needed. HTTP is recommended because `file:` storage behavior varies by browser. Browser storage is scoped to origin/path and app name. Never store secrets in it.

Real Chromium checks (separate from Node-based conformance):

```sh
python -m pip install playwright
python -m playwright install --with-deps chromium
python scripts/test_web_browser.py
```

Set `SEDRAVA_CHROMIUM` to an installed Chromium executable if needed. Browser traces are saved under `build/browser`. The browser suite fails if Playwright/Chromium is missing; it is not silently skipped. On Python 3.10 install test-only TOML support with `python -m pip install ".[test]"`. Node.js is required to run differential conformance tests in the unit suite; CI installs it explicitly.

## Android debug APK

Use a **full JDK** (17 recommended), Android SDK platform 35, build-tools 35.0.0 and **Gradle 8.11.1**. A JRE without `javac` cannot compile. The generated project pins Android Gradle Plugin 8.9.2, Kotlin/Compose compiler plugin 2.0.21 and Compose BOM 2024.12.01. Minimum Android API is 26; target/compile API is 35. Dependencies are downloaded on the first build. Android Studio can install the SDK/JDK or import the generated directory.

Install the official command-line SDK tools and configure `ANDROID_HOME` to the SDK path (not `cmdline-tools`). On Windows use `sdkmanager.bat`.

```sh
java -version
javac -version
gradle --version
sdkmanager --licenses
sdkmanager "platforms;android-35" "build-tools;35.0.0" "platform-tools"
sedrava test examples/reference_09.sdr
sedrava build android examples/reference_09.sdr --output "build/reference-09-android"
gradle -p "build/reference-09-android" --no-daemon :app:assembleDebug :app:lintDebug
```

APK: `build/reference-09-android/app/build/outputs/apk/debug/app-debug.apk`.
Lint: `build/reference-09-android/app/build/reports/lint-results-debug.html`.
A Gradle wrapper is not bundled; install the specified Gradle version or use the pinned version in GitHub Actions.

Verify/install with SDK tools (replace `$ANDROID_HOME` syntax with your shell's equivalent):

```sh
"$ANDROID_HOME/build-tools/35.0.0/apksigner" verify --verbose build/reference-09-android/app/build/outputs/apk/debug/app-debug.apk
"$ANDROID_HOME/build-tools/35.0.0/aapt" dump badging build/reference-09-android/app/build/outputs/apk/debug/app-debug.apk
"$ANDROID_HOME/build-tools/35.0.0/aapt" dump permissions build/reference-09-android/app/build/outputs/apk/debug/app-debug.apk
adb install -r build/reference-09-android/app/build/outputs/apk/debug/app-debug.apk
# Read PACKAGE from build/reference-09-android/sedrava-android.json:
adb shell am start -n PACKAGE/.MainActivity
```

Generated sources request no permissions. SDK/AndroidX may contribute manifest metadata; inspect the merged APK rather than assuming source manifest is the full result. Debug APKs are test artifacts, not production signing keys. Generated examples have title-derived IDs; explicit IDs are supported. See the identity guides below. Follow [device checklist](REFERENCE_09.md) for input, actions, persistence, rotation and recovery. APK compilation does **not** constitute a UI test.

## CI artifacts and repeatability

[Alpha checks](../.github/workflows/alpha.yml) run unit/conformance/example/documentation/package and Chromium tests; [reference Android workflow](../.github/workflows/reference-09-android.yml) builds the Lab APK and Lint report. The compatibility Android workflow also emits `sedrava-09-compatibility-build` containing wheel, sdist, APK, Web ZIP and `SHA256SUMS`; reproduce it with `python scripts/prepare_release.py --apk PATH_TO_CHECKED_APK` after building distributions. Download artifacts from the Actions run for the **same commit** as the source. Dependencies and toolchain versions are pinned directly; transitive dependency byte-for-byte reproducibility and release-signed APK reproducibility are not claimed.

Русский: генератор Android создаёт проект, который затем собирается Gradle. Используйте полный JDK с `javac`, SDK 35 и Gradle 8.11.1. При отсутствии устройства APK можно проверить подписью, `aapt` и Lint, но это не проверяет интерфейс. Состояние и ограничения описаны в [справочнике](LANGUAGE_0_9.md).

## Released 0.10 feature references / Возможности 0.10

Sedrava 0.10.0 is published on [PyPI](https://pypi.org/project/sedrava/0.10.0/) and [GitHub](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0). Unicode text, records/collections and guarded multi-screen navigation are included. See [text](LANGUAGE_0_10_TEXT.md), [records](RECORDS_COLLECTIONS_010.md), [navigation](NAVIGATION_010_CONTRACT.md), and [Android identity](ANDROID_ID.en.md). RC reports describe historical stages only. Android APK builds are separate from Python package publication; final physical-device 0.10 acceptance remains unconfirmed.

## Experimental Web UI 0.11 / Экспериментальный Web UI 0.11

Source-branch feature, separate from published RC2. Режим из этой ветки, отдельно от опубликованного RC2.

```sh
sedrava check examples/web_ui_011_landing.sdr
sedrava build site examples/web_ui_011_landing.sdr --output build/site
python -m http.server 8000 --directory build/site
```

13 static primitives, responsive layouts and safe assets; no deployment. 13 статических компонентов, адаптивность и безопасные ресурсы; без публикации сайта. [English](WEB_UI_011.en.md) · [Русский](WEB_UI_011.ru.md). Existing application commands are unchanged. Команды приложений не изменены.
