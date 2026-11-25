"""Create an independent Kotlin Android baseline project from checked-in Kotlin source.

The reference application is hand-written Kotlin; this script only supplies an
Android Gradle build scaffold. It does not invoke a coding agent.
"""
import argparse
from pathlib import Path
import shutil

PACKAGE = "org.sedrava.benchmark.kotlin"
HERE = Path(__file__).resolve().parent


def prepare(output: Path) -> None:
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError("Output directory must be empty: " + str(output))
    package_path = output / "app/src/main/java" / Path(*PACKAGE.split("."))
    package_path.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(HERE / "baselines/kotlin-android/MainActivity.kt",
                    package_path / "MainActivity.kt")
    (output / "settings.gradle.kts").write_text(
        'pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\n'
        'dependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); '
        'repositories { google(); mavenCentral() } }\n'
        'rootProject.name = "CounterKotlinBaseline"\ninclude(":app")\n',
        encoding="utf-8")
    (output / "build.gradle.kts").write_text(
        'plugins { id("com.android.application") version "8.9.2" apply false; '
        'id("org.jetbrains.kotlin.android") version "2.0.21" apply false }\n',
        encoding="utf-8")
    (output / "gradle.properties").write_text(
        'org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8\nandroid.useAndroidX=true\n',
        encoding="utf-8")
    (output / "app/build.gradle.kts").write_text(
        'plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }\n'
        'android { namespace = "' + PACKAGE + '"; compileSdk = 35\n'
        '  defaultConfig { applicationId = "' + PACKAGE + '"; minSdk = 26; '
        'targetSdk = 35; versionCode = 1; versionName = "1.0" }\n'
        '  compileOptions { sourceCompatibility = JavaVersion.VERSION_17; '
        'targetCompatibility = JavaVersion.VERSION_17 }\n'
        '  kotlinOptions { jvmTarget = "17" }\n}\n',
        encoding="utf-8")
    manifest = output / "app/src/main/AndroidManifest.xml"
    manifest.write_text(
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
        '<application android:label="Kotlin counter baseline" '
        'android:theme="@android:style/Theme.Material.Light.NoActionBar">'
        '<activity android:name=".MainActivity" android:exported="true">'
        '<intent-filter><action android:name="android.intent.action.MAIN"/>'
        '<category android:name="android.intent.category.LAUNCHER"/>'
        '</intent-filter></activity></application></manifest>\n',
        encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
