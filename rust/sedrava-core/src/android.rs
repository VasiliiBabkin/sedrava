//! Experimental native Android Compose generator for a bounded scalar app
//! subset. No Python calls; no claim of complete Android compiler parity.

use crate::model::{fail, Binary, Expr, Kind, Program, Result, Stmt, Unary, Value, Widget};
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
fn kotlin_type(k: &Kind) -> Result<&'static str> {
    match k {
        Kind::Int => Ok("Int"),
        Kind::Bool => Ok("Boolean"),
        Kind::Text => Ok("String"),
        _ => fail("Android scalar generator does not support record/list types"),
    }
}
fn literal(v: &Value) -> Result<String> {
    match v {
        Value::Int(x) => Ok(x.to_string()),
        Value::Bool(x) => Ok(x.to_string()),
        Value::Text(x) => Ok(kotlin_string(x)),
        _ => fail("Android generator supports scalar state only"),
    }
}
fn emit_expr(e: &Expr, scope: &BTreeMap<String, String>) -> Result<String> {
    Ok(match e {
        Expr::Int(n) => n.to_string(),
        Expr::Bool(v) => v.to_string(),
        Expr::Text(s) => kotlin_string(s),
        Expr::Ident(name) => scope.get(name).cloned().ok_or_else(|| {
            crate::model::Error(format!("Unknown Kotlin expression name: {name}"))
        })?,
        Expr::Unary(Unary::Neg, e) => format!("Math.negateExact({})", emit_expr(e, scope)?),
        Expr::Unary(Unary::Not, e) => format!("!({})", emit_expr(e, scope)?),
        Expr::Binary(op, a, b) => {
            let a = emit_expr(a, scope)?;
            let b = emit_expr(b, scope)?;
            match op {
                Binary::Add => format!("Math.addExact({a},{b})"),
                Binary::Sub => format!("Math.subtractExact({a},{b})"),
                Binary::Mul => format!("Math.multiplyExact({a},{b})"),
                Binary::Eq => format!("({a} == {b})"),
                Binary::Ne => format!("({a} != {b})"),
                Binary::Lt => format!("({a} < {b})"),
                Binary::Le => format!("({a} <= {b})"),
                Binary::Gt => format!("({a} > {b})"),
                Binary::Ge => format!("({a} >= {b})"),
                Binary::And => format!("({a} && {b})"),
                Binary::Or => format!("({a} || {b})"),
            }
        }
        Expr::Conditional(c, a, b) => format!(
            "(if ({}) {} else {})",
            emit_expr(c, scope)?,
            emit_expr(a, scope)?,
            emit_expr(b, scope)?
        ),
        Expr::Call { .. } | Expr::Attr(..) => {
            return fail("Android generator does not yet translate calls and record fields")
        }
    })
}
fn state_property(name: &str) -> String {
    format!("sdr_{name}")
}
fn state_scope(program: &Program, receiver: &str) -> BTreeMap<String, String> {
    let mut result = BTreeMap::new();
    for name in program.states.keys() {
        result.insert(name.clone(), format!("{receiver}.{}", state_property(name)));
    }
    result
}
fn emit_statements(
    body: &[Stmt],
    scope: &BTreeMap<String, String>,
    depth: usize,
    count: &mut usize,
    output: &mut String,
) -> Result<()> {
    let mut scope = scope.clone();
    let pad = " ".repeat(depth);
    for stmt in body {
        match stmt {
            Stmt::Assign(name, expr) => {
                let expr = emit_expr(expr, &scope)?;
                let target = scope
                    .get(name)
                    .ok_or_else(|| crate::model::Error(format!("Unknown Android state: {name}")))?;
                output.push_str(&format!("{pad}{target} = {expr}\n"));
            }
            Stmt::Let(name, expr) => {
                *count += 1;
                let local = format!("_local_{count}");
                output.push_str(&format!(
                    "{pad}val {local} = {}\n",
                    emit_expr(expr, &scope)?
                ));
                scope.insert(name.clone(), local);
            }
            Stmt::Require(expr) => {
                output.push_str(&format!("{pad}require({})\n", emit_expr(expr, &scope)?));
            }
            Stmt::Branch(cond, yes, no) => {
                output.push_str(&format!("{pad}if ({}) {{\n", emit_expr(cond, &scope)?));
                emit_statements(yes, &scope, depth + 2, count, output)?;
                output.push_str(&format!("{pad}}}"));
                if !no.is_empty() {
                    output.push_str(" else {\n");
                    emit_statements(no, &scope, depth + 2, count, output)?;
                    output.push_str(&format!("{pad}}}"));
                }
                output.push('\n');
            }
        }
    }
    Ok(())
}
fn verify_app(program: &Program) -> Result<()> {
    if program.states.is_empty() {
        return fail("Native Android preview requires at least one state");
    }
    if program.has_navigation || program.screens.len() != 1 || !program.screens.contains_key("main")
    {
        return fail("Native Android generator supports only one unguarded screen");
    }
    if !program.persistent.is_empty() {
        return fail("Native Android state persistence not implemented");
    }
    if !program.functions.is_empty() {
        return fail("Native Android pure function codegen is not implemented");
    }
    for name in program.states.keys() {
        kotlin_type(
            program
                .types
                .get(name)
                .ok_or_else(|| crate::model::Error("Unknown state kind".into()))?,
        )?;
    }
    for widget in &program.screens["main"].widgets {
        if matches!(widget, Widget::List { .. }) {
            return fail("Native Android list widgets require Android record adapter");
        }
    }
    Ok(())
}

pub fn generate(program: &Program, application_id: &str) -> Result<AndroidProject> {
    validate_application_id(application_id)?;
    verify_app(program)?;
    let mut body = String::new();
    body.push_str(&format!("package {application_id}\n\n"));
    body.push_str(
        r#"import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

"#,
    );
    body.push_str("internal data class SdrState(\n");
    for (n, (name, value)) in program.states.iter().enumerate() {
        let separator = if n + 1 < program.states.len() {
            ","
        } else {
            ""
        };
        body.push_str(&format!(
            "    val {}: {} = {}{separator}\n",
            state_property(name),
            kotlin_type(&value.kind())?,
            literal(value)?
        ));
    }
    body.push_str(")\n");
    body.push_str("private fun validState(state:SdrState):Boolean = try {\n");
    let scope = state_scope(program, "state");
    for (name, value) in &program.states {
        if let Value::Text(_) = value {
            body.push_str(&format!(
                "    require(state.{}.codePointCount(0,state.{}.length) <= 1024)\n",
                state_property(name),
                state_property(name)
            ));
        }
    }
    let mut names = scope.clone();
    for (name, expr) in &program.derives {
        let compiled = emit_expr(expr, &names)?;
        let local = format!("_derived_{name}");
        body.push_str(&format!("    val {local} = {compiled}\n"));
        names.insert(name.clone(), local);
    }
    for rule in &program.rules {
        body.push_str(&format!("    require({})\n", emit_expr(rule, &names)?));
    }
    body.push_str("    true\n} catch (_:ArithmeticException) {false} catch (_:IllegalArgumentException) {false}\n");
    body.push_str(
        "private fun transition(current:SdrState, action:String):SdrState {\n    return try {\n",
    );
    for name in program.states.keys() {
        body.push_str(&format!(
            "    var {}=current.{}\n",
            state_property(name),
            state_property(name)
        ));
    }
    body.push_str("    when(action) {\n");
    let mut local: BTreeMap<String, String> = program
        .states
        .keys()
        .map(|n| (n.clone(), state_property(n)))
        .collect();
    for (name, expr) in &program.derives {
        let translated = emit_expr(expr, &local)?;
        local.insert(name.clone(), format!("({translated})"));
    }
    let mut count = 0;
    for (name, stmts) in &program.actions {
        body.push_str(&format!("        {} -> {{\n", kotlin_string(name)));
        emit_statements(stmts, &local, 12, &mut count, &mut body)?;
        body.push_str("        }\n");
    }
    body.push_str("        else -> return current\n    }\n");
    body.push_str("    val next=SdrState(");
    body.push_str(
        &program
            .states
            .keys()
            .map(|name| state_property(name))
            .collect::<Vec<_>>()
            .join(","),
    );
    body.push_str(")\n    if(validState(next)) next else current\n");
    body.push_str(
        "} catch (_:ArithmeticException) {current} catch (_:IllegalArgumentException) {current}\n}\n",
    );

    body.push_str(
        r#"
class MainActivity:ComponentActivity() {
    override fun onCreate(savedInstanceState:Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { MaterialTheme { SedravaScreen() } }
    }
}
@Composable
fun SedravaScreen() {
    var state by remember { mutableStateOf(SdrState()) }
    Column(modifier=Modifier.fillMaxSize().padding(24.dp),
           verticalArrangement=Arrangement.spacedBy(16.dp)) {
"#,
    );
    let mut view = state_scope(program, "state");
    for (name, expr) in &program.derives {
        let compiled = emit_expr(expr, &view)?;
        let local = format!("render_{name}");
        body.push_str(&format!("        val {local} = {compiled}\n"));
        view.insert(name.clone(), local);
    }
    for widget in &program.screens["main"].widgets {
        match widget {
            Widget::Text(s) => {
                body.push_str(&format!("        Text({})\n", kotlin_string(s)));
            }
            Widget::Value(name) => {
                let source = view
                    .get(name)
                    .ok_or_else(|| crate::model::Error(format!("Unknown UI value {name}")))?;
                body.push_str(&format!(
                    "        Text({} + {source}.toString())\n",
                    kotlin_string(&format!("{name}: "))
                ));
            }
            Widget::Show { condition, label } => {
                let expr = view.get(condition).ok_or_else(|| {
                    crate::model::Error(format!("Unknown UI condition: {condition}"))
                })?;
                body.push_str(&format!(
                    "        if({expr}) Text({})\n",
                    kotlin_string(label)
                ));
            }
            Widget::Input { state: name, label } => {
                let kind = program
                    .types
                    .get(name)
                    .ok_or_else(|| crate::model::Error("Unknown Android input".into()))?;
                let stateval = format!("state.{}", state_property(name));
                match kind {
                    Kind::Text=>body.push_str(&format!(
                        "        OutlinedTextField(value={stateval},onValueChange={{ value -> if(value.codePointCount(0,value.length)<=1024) {{val next=state.copy({} = value);if(validState(next))state=next}} }},label={{Text({})}})\n",
                        state_property(name),kotlin_string(label)
                    )),
                    Kind::Int=>body.push_str(&format!(
                        "        OutlinedTextField(value={stateval}.toString(),onValueChange={{ raw -> val number=raw.toIntOrNull();if(number!=null){{val next=state.copy({}=number);if(validState(next))state=next}} }},label={{Text({})}})\n",
                        state_property(name),kotlin_string(label)
                    )),
                    _=>return fail("Native Android only supports text/int inputs")
                }
            }
            Widget::Button { label, action } => {
                body.push_str(&format!(
                    "        Button(onClick={{state=transition(state,{})}}){{Text({})}}\n",
                    kotlin_string(action),
                    kotlin_string(label)
                ));
            }
            Widget::Display(expr) => {
                body.push_str(&format!(
                    "        Text(({}).toString())\n",
                    emit_expr(expr, &view)?
                ));
            }
            Widget::List { .. } => return fail("Android list widget is not yet implemented"),
        }
    }
    body.push_str("    }\n}\n");

    let segments = application_id.split('.').collect::<Vec<_>>();
    let package_dir = segments.join("/");
    let mut files = BTreeMap::new();
    files.insert(
        format!("app/src/main/java/{package_dir}/MainActivity.kt"),
        body.into_bytes(),
    );
    files.insert("settings.gradle.kts".into(),
        b"pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\ndependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral() } }\nrootProject.name=\"SedravaNativeApp\"\ninclude(\":app\")\n".to_vec());
    files.insert("build.gradle.kts".into(),
        b"plugins { id(\"com.android.application\") version \"8.9.2\" apply false; id(\"org.jetbrains.kotlin.android\") version \"2.0.21\" apply false; id(\"org.jetbrains.kotlin.plugin.compose\") version \"2.0.21\" apply false }\n".to_vec());
    files.insert(
        "gradle.properties".into(),
        b"org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8\nandroid.useAndroidX=true\n".to_vec(),
    );
    files.insert("app/build.gradle.kts".into(),format!(
        "plugins {{ id(\"com.android.application\");id(\"org.jetbrains.kotlin.android\");id(\"org.jetbrains.kotlin.plugin.compose\") }}\nandroid {{ namespace=\"{application_id}\";compileSdk=35\n defaultConfig {{applicationId=\"{application_id}\";minSdk=26;targetSdk=35;versionCode=1;versionName=\"0.1-native-preview\" }}\n buildFeatures {{compose=true}}\n compileOptions {{sourceCompatibility=JavaVersion.VERSION_17;targetCompatibility=JavaVersion.VERSION_17}}\n kotlinOptions {{jvmTarget=\"17\"}}\n}}\ndependencies {{implementation(platform(\"androidx.compose:compose-bom:2024.12.01\"));implementation(\"androidx.activity:activity-compose:1.9.3\");implementation(\"androidx.compose.material3:material3\");implementation(\"androidx.compose.ui:ui\")}}\n"
    ).into_bytes());
    files.insert("app/src/main/AndroidManifest.xml".into(),
        b"<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\"><application android:label=\"@string/sedrava_app_name\" android:theme=\"@android:style/Theme.Material.Light.NoActionBar\"><activity android:name=\".MainActivity\" android:exported=\"true\"><intent-filter><action android:name=\"android.intent.action.MAIN\"/><category android:name=\"android.intent.category.LAUNCHER\"/></intent-filter></activity></application></manifest>\n".to_vec());
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
    use crate::parser::parse;
    #[test]
    fn creates_android_scaffold_from_existing_counter() {
        let p = parse(include_str!("../../../examples/counter.sdr")).unwrap();
        let result = generate(&p, "org.sedrava.demo").unwrap();
        let kotlin = String::from_utf8(
            result
                .files
                .iter()
                .find(|(name, _)| name.ends_with("MainActivity.kt"))
                .unwrap()
                .1
                .clone(),
        )
        .unwrap();
        assert!(kotlin.contains("Math.addExact"));
        assert!(kotlin.contains("Button(onClick"));
        assert!(kotlin.contains("private fun validState"));
        assert_eq!(result.files.len(), 8);
        let metadata: serde_json::Value =
            serde_json::from_slice(&result.files["sedrava-android.json"]).unwrap();
        assert_eq!(metadata.as_object().unwrap().len(), 4);
        assert_eq!(metadata["namespace"], "org.sedrava.demo");
    }
    #[test]
    fn rejects_unsafe_id_and_unsupported_navigation() {
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
        let p = parse(include_str!(
            "../../../examples/task_manager_navigation.sdr"
        ))
        .unwrap();
        assert!(generate(&p, "org.sedrava.demo").is_err());
    }
}
