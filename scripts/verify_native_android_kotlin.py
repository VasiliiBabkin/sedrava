#!/usr/bin/env python3
"""Compile actual generated Android domain sources with Kotlin/JVM and compare Python."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
from android_codegen_v03 import quoted
from navigation_cases import SOURCE, steps, trace
from sedrava_core import parse, resolve, transition
from sedrava_records import fingerprint, plain


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def navigation_test():
    program = parse(SOURCE)
    lines = ["internal fun verifyNavigation() {", "    var session = Session()"]
    for index, (step, expected) in enumerate(zip(steps(), trace())):
        mode, *args = step
        if mode == "command":
            statement = f"dispatch(session, {quoted(args[0])})"
        elif mode == "input":
            statement = f"edit(session, {quoted(args[0])}, {quoted(args[1])})"
        elif mode == "select":
            statement = f"select(session, screens.getValue(\"main\").widgets.filterIsInstance<Widget.Rows>().single(), {args[2]})"
        elif mode == "recreate":
            statement = "restoreConfiguration(restoreSnapshot(snapshot(session.state)), snapshot(session.state, full = true), session.stack)"
        else:
            statement = "Session(restoreSnapshot(snapshot(session.state)))"
        wire = compact({"schema": 1, "signature": fingerprint(program), "state": expected["state"]})
        stack = ", ".join(quoted(value) for value in expected["stack"])
        accepted = str(expected["accepted"]).lower()
        lines += [
            f"    val next{index}: Session? = {statement}",
            f'    check((next{index} != null) == {accepted}) {{ "Acceptance at navigation step {index}" }}',
            f"    session = next{index} ?: session",
            f'    check(snapshot(session.state, full = true) == {quoted(wire)}) {{ "Domain at navigation step {index}" }}',
            f'    check(session.stack == listOf({stack})) {{ "Stack at navigation step {index}" }}',
        ]
    lines += [
        '    val row = screens.getValue("main").widgets.filterIsInstance<Widget.Rows>().single()',
        '    session = checkNotNull(select(session, row, 3))',
        '    repeat(30) { session = checkNotNull(dispatch(session, "open_details")) }',
        '    check(session.stack.size == 32)',
        '    check(dispatch(session, "open_details") == null)',
        '    check(restoreSession(session.state, listOf("unrecognized")).stack == listOf("main"))',
        '    val raw = snapshot(session.state)',
        '    val savedStack = session.stack',
        '    val bundle = snapshot(session.state, full = true)',
        '    check(restoreConfiguration(restoreSnapshot(raw), bundle, savedStack) == session)',
        '    check(restoreConfiguration(defaultState, bundle, savedStack) == Session())',
        '    check(restoreConfiguration(restoreSnapshot(raw), "invalid", savedStack).stack == listOf("main"))',
        '    check(restorePythonPreferences(mapOf("snapshot" to raw)) == restoreSnapshot(raw))',
        r'    for (bad in listOf(raw.replace("\"schema\":1", "\"schema\":1,\"schema\":1"),',
        r'            raw.replace("\"next_id\":4", "\"next_id\":3"),',
        r'            raw.replace("\"next_id\":4", "\"next_id\":4.0"),',
        r'            raw.replace("\"next_id\":4", "\"next_id\":2147483648"),',
        r'            raw.replace("\"next_id\":4", "\"next_id\":" + "[".repeat(40) + "0" + "]".repeat(40)),',
        r'            raw + "trailing", raw.replace("Cold launch", "\\ud800"), "x".repeat(200001))) {',
        '        check(validated { restoreSnapshot(bad) } == null) { "Accepted corrupted snapshot: " + bad.take(140) }',
        '    }',
        r'    val duplicateRow = raw.replace("\"items\":[{", "\"items\":[{\"id\":3,")',
        '    check(validated { restoreSnapshot(duplicateRow) } == null)',
        '    var full = Session()',
        '    repeat(100) { index ->',
        '        full = checkNotNull(edit(full, "new_title", "Task " + index))',
        '        full = checkNotNull(dispatch(full, "add_task"))',
        '    }',
        '    full = checkNotNull(edit(full, "new_title", "Too many"))',
        '    check(dispatch(full, "add_task") == null)',
        '    val list = full.state.getValue("tasks") as SdrList',
        '    check(list.nextId == 101 && list.rows.map { it.id } == (1..100).toList())',
        '    println("ANDROID_SNAPSHOT=" + raw)',
        '    println("PASS navigation: Python oracle steps, stack bound, corruption, recreation and cold restore")',
        "}",
    ]
    return "\n".join(lines)


def query_test(source):
    program = parse(source.read_text(encoding="utf-8"))
    state = program.states
    for action in ("add_one", "add_two"):
        state, accepted = transition(program, state, action)
        assert accepted
    expected = compact({key: plain(value) for key, value in resolve(state, program.derived).items()})
    return f'''internal fun verifyQueries() {{
    var session = Session()
    for (command in listOf("add_one", "add_two")) session = checkNotNull(dispatch(session, command))
    check(encodeJson(resolve(session.state)) == {quoted(expected)})
    check(((resolve(session.state).getValue("mapped") as SdrList).rows.map {{ it.id }}) == listOf(1, 2))
    println("PASS queries: Python oracle, typed selectors, IDs and map")
}}'''


def scalar_test():
    return r'''internal fun verifyScalars() {
    val start = Session()
    check(dispatch(start, "reject") == null)
    check(dispatch(start, "intermediate") == null)
    check(dispatch(start, "underflow") == null)
    check(dispatch(start, "minimum") == null)
    check(edit(start, "count", "1") == null)
    check(edit(start, "count", Int.MAX_VALUE) == null)
    check(edit(start, "label", Char(0xd800).toString()) == null)
    check(edit(start, "label", "😀".repeat(1025)) == null)
    val boundary = checkNotNull(edit(start, "label", "😀".repeat(1024)))
    check(resolve(boundary.state)["scalars"] == 1024)
    val toggled = checkNotNull(edit(boundary, "enabled", false))
    val ok = checkNotNull(dispatch(toggled, "reject"))
    check(resolve(ok.state)["doubled"] == 10)
    check(resolve(ok.state)["tomorrow"] == "2024-02-29")
    check(restoreSnapshot(snapshot(ok.state)) == ok.state)
    val legacy = restorePythonPreferences(mapOf("count" to 2, "enabled" to false, "label" to "legacy"))
    check(restoreSnapshot(snapshot(legacy)) == legacy)
    check(validated { restorePythonPreferences(mapOf("count" to "wrong")) } == null)
    check(validated { restorePythonPreferences(mapOf("count" to -1)) } == null)
    val folder = java.nio.file.Files.createTempDirectory("sedrava-store").toFile()
    try {
        val file = java.io.File(folder, "snapshot.json")
        val store = SnapshotStore(file) { mapOf("count" to 2, "enabled" to false, "label" to "legacy") }
        check(store.load() == legacy)
        store.save(snapshot(ok.state))
        check(SnapshotStore(file) { emptyMap<String, Any>() }.load() == ok.state)
        file.writeText("{bad")
        try {
            store.save(snapshot(legacy))
            error("Overwrote changed data")
        } catch (_: java.io.IOException) {}
        val damaged = SnapshotStore(file) { emptyMap<String, Any>() }
        check(validated { damaged.load() } == null)
        check(validated { damaged.save(snapshot(legacy)) } == null)
        check(file.readText() == "{bad")
        file.writeBytes(byteArrayOf(0xff.toByte()))
        try {
            damaged.load()
            error("Accepted malformed UTF-8")
        } catch (_: java.nio.charset.CharacterCodingException) {}
        check(file.readBytes().contentEquals(byteArrayOf(0xff.toByte())))
        check(folder.listFiles()!!.size == 1)
    } finally {
        folder.deleteRecursively()
    }
    println("PASS scalars: checked arithmetic, validation, Unicode, atomic files and migration of Python preferences")
}'''


def execute(command, **kwargs):
    return subprocess.run(command, check=True, text=True, timeout=420, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", type=Path, default=ROOT / "rust/target/debug/sedrava-native")
    parser.add_argument("--gradle", type=Path, required=True)
    parser.add_argument("--gradle-user-home", type=Path)
    args = parser.parse_args()
    native = str(args.native.resolve())
    env = os.environ.copy()
    if args.gradle_user_home:
        env["GRADLE_USER_HOME"] = str(args.gradle_user_home.resolve())
    nav = ROOT / "examples/task_manager_navigation.sdr"
    queries = ROOT / "tests/rust_cases/native_web_queries.sdr"
    scalar = ROOT / "tests/rust_cases/native_android_runtime.sdr"
    configs = [(nav, "navigation", navigation_test()),
               (queries, "queries", query_test(queries)),
               (scalar, "scalars", scalar_test())]
    with tempfile.TemporaryDirectory(prefix="sdr-android-jvm-") as temporary:
        work = Path(temporary)
        sources = work / "src/main/kotlin"
        for source, name, code in configs:
            package = "org.sedrava." + name
            project = work / name
            execute([native, "build", "android", str(source), "--output", str(project),
                     "--application-id", package], cwd=ROOT)
            src = project / "app/src/main/java" / package.replace(".", "/")
            group = sources / name
            group.mkdir(parents=True)
            for file in ("Program.kt", "Domain.kt", "Collections.kt", "Navigation.kt", "Snapshots.kt", "Storage.kt"):
                shutil.copy2(src / file, group / file)
            (group / "Verification.kt").write_text(f"package {package}\n\n{code}\n", encoding="utf-8")
        (sources / "Main.kt").write_text(
            "fun main() {\n"
            + "".join(f"    org.sedrava.{name}.verify{name.title()}()\n" for _, name, _ in configs)
            + "}\n", encoding="utf-8")
        (work / "settings.gradle.kts").write_text(
            'pluginManagement { repositories { mavenCentral(); gradlePluginPortal() } }\n'
            'rootProject.name = "NativeSedravaKotlin"\n', encoding="utf-8")
        (work / "build.gradle.kts").write_text(
            'plugins { kotlin("jvm") version "2.0.21"; application }\n'
            'repositories { mavenCentral() }\n'
            'application { mainClass.set("MainKt") }\n', encoding="utf-8")
        process = execute([str(args.gradle.resolve()), "-p", str(work), "--no-daemon", "--console=plain", "run"],
                          env=env, stdout=subprocess.PIPE)
        print(process.stdout)
        raw, = [line.removeprefix("ANDROID_SNAPSHOT=") for line in process.stdout.splitlines()
                if line.startswith("ANDROID_SNAPSHOT=")]
        state_file = work / "state.json"
        state_file.write_text(raw, encoding="utf-8")
        py = execute([sys.executable, str(ROOT / "sedrava_cli.py"), "run", str(nav),
                      "--state-file", str(state_file)], stdout=subprocess.PIPE)
        rs = execute([native, "run", str(nav), "--state-file", str(state_file)], stdout=subprocess.PIPE)
        assert json.loads(py.stdout) == json.loads(rs.stdout)
        print("PASS: generated Kotlin schema-1 snapshot restores in Python and Rust")


if __name__ == "__main__":
    main()
