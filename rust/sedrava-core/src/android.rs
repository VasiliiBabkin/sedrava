//! Native Kotlin/Compose generator for the Rust app-mode model.

mod program;

use crate::model::{fail, Program, Result};
use std::collections::BTreeMap;

pub struct AndroidProject {
    pub files: BTreeMap<String, Vec<u8>>,
    pub application_id: String,
}

fn kotlin_string(value: &str) -> String {
    let mut result = String::from("\"");
    for c in value.chars() {
        match c {
            '"' => result.push_str("\\\""),
            '\\' => result.push_str("\\\\"),
            '\n' => result.push_str("\\n"),
            '\r' => result.push_str("\\r"),
            '\t' => result.push_str("\\t"),
            '$' => result.push_str("\\$"),
            x if (x as u32) < 32 || matches!(x, '\u{2028}' | '\u{2029}') => {
                result.push_str(&format!("\\u{:04x}", x as u32))
            }
            x => result.push(x),
        }
    }
    result.push('"');
    result
}
fn xml(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}
fn android_resource_string(value: &str) -> String {
    let mut escaped = String::new();
    for c in value.chars() {
        match c {
            '\\' => escaped.push_str("\\\\"),
            '"' => escaped.push_str("\\\""),
            '\'' => escaped.push_str("\\'"),
            '\n' => escaped.push_str("\\n"),
            '\r' => escaped.push_str("\\r"),
            '\t' => escaped.push_str("\\t"),
            '@' => escaped.push_str("\\@"),
            '?' => escaped.push_str("\\?"),
            c if (c as u32) < 32 || matches!(c, '\u{fffe}' | '\u{ffff}') => {
                escaped.push_str(&format!("\\u{:04x}", c as u32))
            }
            c => escaped.push(c),
        }
    }
    xml(&escaped)
}

const RESERVED:&str=" abstract as assert boolean break byte case catch char class const continue default do double else enum extends false final finally float for fun goto if implements import in instanceof int interface is long native new null object package private protected public return short static strictfp super switch synchronized this throw throws transient true try typealias typeof val var void volatile when while record sealed permits yield by constructor delegate dynamic field file get init param property receiver set setparam where actual annotation companion crossinline data expect external infix inline inner internal lateinit noinline open operator out override reified suspend tailrec vararg value ";

pub fn validate_application_id(value: &str) -> Result<()> {
    if value.len() > 255
        || value.len() < 3
        || value
            .chars()
            .any(|ch| !ch.is_ascii_lowercase() && !ch.is_ascii_digit() && ch != '_' && ch != '.')
    {
        return fail("Android application ID must be lowercase ASCII identifier");
    }
    let parts = value.split('.').collect::<Vec<_>>();
    if parts.len() < 2 {
        return fail("Android application ID must contain at least two segments");
    }
    for part in parts {
        if part.is_empty()
            || !part.as_bytes()[0].is_ascii_lowercase()
            || RESERVED.contains(&format!(" {part} "))
        {
            return fail("Android application ID contains empty, invalid or reserved segment");
        }
    }
    Ok(())
}
pub fn generate(program: &Program, application_id: &str) -> Result<AndroidProject> {
    validate_application_id(application_id)?;
    if program.screens.is_empty() {
        return fail("Android requires at least one app screen");
    }
    if !crate::runtime::valid_state(program, &program.states) {
        return fail("Invalid initial Android state");
    }

    let package_dir = application_id.replace('.', "/");
    let mut files = BTreeMap::new();
    let generated = program::generate(program)?;
    for (name, content) in [
        ("Program.kt", generated.as_str()),
        ("Domain.kt", include_str!("android/Domain.kt")),
        ("Collections.kt", include_str!("android/Collections.kt")),
        ("Navigation.kt", include_str!("android/Navigation.kt")),
        ("Snapshots.kt", include_str!("android/Snapshots.kt")),
        ("Storage.kt", include_str!("android/Storage.kt")),
        ("MainActivity.kt", include_str!("android/MainActivity.kt")),
    ] {
        files.insert(
            format!("app/src/main/java/{package_dir}/{name}"),
            format!("package {application_id}\n\n{content}").into_bytes(),
        );
    }
    files.insert("settings.gradle.kts".into(),
        b"pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\ndependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral() } }\nrootProject.name=\"SedravaNativeApp\"\ninclude(\":app\")\n".to_vec());
    files.insert("build.gradle.kts".into(),
        b"plugins { id(\"com.android.application\") version \"8.9.2\" apply false; id(\"org.jetbrains.kotlin.android\") version \"2.0.21\" apply false; id(\"org.jetbrains.kotlin.plugin.compose\") version \"2.0.21\" apply false }\n".to_vec());
    files.insert(
        "gradle.properties".into(),
        b"org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8\nandroid.useAndroidX=true\n".to_vec(),
    );
    files.insert("app/build.gradle.kts".into(),format!(
        "plugins {{ id(\"com.android.application\");id(\"org.jetbrains.kotlin.android\");id(\"org.jetbrains.kotlin.plugin.compose\") }}\nandroid {{ namespace=\"{application_id}\";compileSdk=35\n defaultConfig {{applicationId=\"{application_id}\";minSdk=26;targetSdk=35;versionCode=1;versionName=\"0.1-native-preview\" }}\n buildFeatures {{compose=true}}\n compileOptions {{sourceCompatibility=JavaVersion.VERSION_17;targetCompatibility=JavaVersion.VERSION_17}}\n kotlinOptions {{jvmTarget=\"17\"}}\n}}\ndependencies {{implementation(platform(\"androidx.compose:compose-bom:2024.12.01\"));implementation(\"androidx.activity:activity-compose:1.9.3\");implementation(\"androidx.compose.material3:material3\");implementation(\"androidx.compose.ui:ui\");implementation(\"androidx.compose.foundation:foundation\");implementation(\"androidx.lifecycle:lifecycle-viewmodel-ktx:2.8.7\")}}\n"
    ).into_bytes());
    files.insert("app/src/main/AndroidManifest.xml".into(),
        b"<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\"><application android:allowBackup=\"false\" android:label=\"@string/sedrava_app_name\" android:theme=\"@android:style/Theme.Material.Light.NoActionBar\"><activity android:name=\".MainActivity\" android:exported=\"true\"><intent-filter><action android:name=\"android.intent.action.MAIN\"/><category android:name=\"android.intent.category.LAUNCHER\"/></intent-filter></activity></application></manifest>\n".to_vec());
    files.insert(
        "app/src/main/res/values/strings.xml".into(),
        format!(
            "<resources><string name=\"sedrava_app_name\">\"{}\"</string></resources>\n",
            android_resource_string(&program.name)
        )
        .into_bytes(),
    );
    files.insert(
        "sedrava-android.json".into(),
        (serde_json::to_string_pretty(&serde_json::json!({
            "schema":1,"application_id":application_id,"namespace":application_id,
            "title":program.name
        }))
        .unwrap()
            + "\n")
            .into_bytes(),
    );
    Ok(AndroidProject {
        files,
        application_id: application_id.to_owned(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parse;

    #[test]
    fn generates_split_compose_project_for_app_contract() {
        for source in [
            include_str!("../../../examples/counter.sdr"),
            include_str!("../../../examples/task_manager_navigation.sdr"),
            include_str!("../../../tests/rust_cases/native_web_queries.sdr"),
        ] {
            let p = parse(source).unwrap();
            let generated = generate(&p, "org.sedrava.demo").unwrap();
            let dir = "app/src/main/java/org/sedrava/demo";
            for file in ["Program.kt", "Domain.kt", "Snapshots.kt", "MainActivity.kt"] {
                assert!(generated.files.contains_key(&format!("{dir}/{file}")));
            }
            let metadata: serde_json::Value =
                serde_json::from_slice(&generated.files["sedrava-android.json"]).unwrap();
            assert_eq!(metadata["namespace"], "org.sedrava.demo");
            assert_eq!(metadata["title"], p.name);
        }
    }

    #[test]
    fn rejects_unsafe_application_ids() {
        for value in [
            "org..name",
            "org.class",
            "com.Example",
            "com/escape",
            "org",
            "../x",
        ] {
            assert!(validate_application_id(value).is_err());
        }
    }
}
