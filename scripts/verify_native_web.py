#!/usr/bin/env python3
"""Build native Web UI without Python codegen and verify generated JS using Node.

This verifies only the supported scalar subset and mock DOM semantics,
not Chromium/Firefox/Android browser compatibility.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--native", type=Path,
                    default=ROOT/"rust/target/debug/sedrava-native")
    args=ap.parse_args()
    binary=args.native.resolve()
    with tempfile.TemporaryDirectory(prefix="sdr-native-web-") as directory:
        output=Path(directory)/"index.html"
        source=ROOT/"tests/rust_cases/native_web_ui.sdr"
        subprocess.run([str(binary),"build","web",str(source),"--output",str(output)],
                       cwd=ROOT,check=True,timeout=40)
        assert "<script>" in output.read_text(encoding="utf8")
        subprocess.run(["node",str(ROOT/"scripts/verify_native_web_node.js"),str(output)],
                       cwd=ROOT,check=True,timeout=20)
        invalid=ROOT/"examples/platform_crm.sdr"
        reject=subprocess.run([str(binary),"build","web",str(invalid),
                               "--output",str(output)],
                              cwd=ROOT,text=True,capture_output=True,timeout=30)
        assert reject.returncode!=0
        assert reject.stderr.strip()

        nav_source=ROOT/"examples/task_manager_navigation.sdr"
        nav_output=Path(directory)/"navigation.html"
        nav_file=Path(directory)/"navigation.json"
        subprocess.run([str(binary),"build","web",str(nav_source),
                        "--output",str(nav_output)],cwd=ROOT,check=True,timeout=40)
        subprocess.run(["node",str(ROOT/"scripts/verify_native_web_navigation_node.js"),
                        str(nav_output),str(nav_file)],cwd=ROOT,check=True,timeout=20)

        queries_source=ROOT/"tests/rust_cases/native_web_queries.sdr"
        queries_output=Path(directory)/"queries.html"
        subprocess.run([str(binary),"build","web",str(queries_source),
                        "--output",str(queries_output)],cwd=ROOT,check=True,timeout=40)
        query_node=subprocess.run(
            ["node",str(ROOT/"scripts/verify_native_web_queries_node.js"),str(queries_output)],
            cwd=ROOT,check=True,capture_output=True,text=True,timeout=20)
        query_json=__import__("json").loads(next(line[12:] for line in query_node.stdout.splitlines()
                                                 if line.startswith("RESULT_JSON ")))
        rust_query=subprocess.run([str(binary),"run",str(queries_source),"add_one","add_two"],
                                  cwd=ROOT,check=True,capture_output=True,text=True,timeout=30)
        python_query=subprocess.run([__import__("sys").executable,str(ROOT/"sedrava_cli.py"),
                                     "run",str(queries_source),"add_one","add_two"],
                                    cwd=ROOT,check=True,capture_output=True,text=True,timeout=30)
        assert query_json==__import__("json").loads(rust_query.stdout)
        assert query_json==__import__("json").loads(python_query.stdout)
        print("PASS: native Web collection queries match both Rust and Python")

        collections_source=ROOT/"examples/task_manager.sdr"
        collections_output=Path(directory)/"collections.html"
        collections_file=Path(directory)/"collections.json"
        subprocess.run([str(binary),"build","web",str(collections_source),
                        "--output",str(collections_output)],cwd=ROOT,check=True,timeout=40)
        subprocess.run(["node",str(ROOT/"scripts/verify_native_web_collections_node.js"),
                        str(collections_output),str(collections_file)],
                       cwd=ROOT,check=True,timeout=20)
        item_file=Path(str(collections_file)+".withrow")
        rust_rows=subprocess.run([str(binary),"run",str(collections_source),
                                  "--state-file",str(item_file)],
                                 cwd=ROOT,check=True,capture_output=True,text=True,timeout=30)
        python_rows=subprocess.run([__import__("sys").executable,
                                    str(ROOT/"sedrava_cli.py"),"run",
                                    str(collections_source),"--state-file",str(item_file)],
                                   cwd=ROOT,check=True,capture_output=True,text=True,timeout=30)
        assert __import__("json").loads(rust_rows.stdout)==__import__("json").loads(python_rows.stdout)
        print("PASS: browser record/list snapshot restores identically in Rust/Python")

        functions_source=ROOT/"tests/rust_cases/native_web_functions.sdr"
        functions_output=Path(directory)/"functions.html"
        subprocess.run([str(binary),"build","web",str(functions_source),
                        "--output",str(functions_output)],cwd=ROOT,check=True,timeout=40)
        subprocess.run(["node",str(ROOT/"scripts/verify_native_web_functions_node.js"),
                        str(functions_output)],cwd=ROOT,check=True,timeout=20)

        persistent_source=ROOT/"examples/reference_09.sdr"
        persistent_output=Path(directory)/"persistent.html"
        state_file=Path(directory)/"snapshot.json"
        subprocess.run([str(binary),"build","web",str(persistent_source),
                        "--output",str(persistent_output)],cwd=ROOT,check=True,timeout=40)
        for scenario in ("write","read"):
            subprocess.run(["node",str(ROOT/"scripts/verify_native_web_persist_node.js"),
                            str(persistent_output),str(state_file),scenario],
                           cwd=ROOT,check=True,timeout=20)
        rust=subprocess.run([str(binary),"run",str(persistent_source),
                             "add","--state-file",str(state_file)],
                            cwd=ROOT,capture_output=True,text=True,timeout=30)
        assert rust.returncode==0,rust.stderr
        rust_state=__import__("json").loads(rust.stdout)
        assert rust_state["progress"]==2
        subprocess.run(["node",str(ROOT/"scripts/verify_native_web_persist_node.js"),
                        str(persistent_output),str(state_file),"read"],
                       cwd=ROOT,check=True,timeout=20)
        subprocess.run(["node",str(ROOT/"scripts/verify_native_web_persist_node.js"),
                        str(persistent_output),str(state_file),"conflict"],
                       cwd=ROOT,check=True,timeout=20)
        valid=__import__("json").loads(state_file.read_text(encoding="utf8"))
        bad_cases=[
            '{"schema":1,"schema":1,"signature":"dup","state":{}}',
            __import__("json").dumps({**valid,"state":{**valid["state"],
                                "goal":5.5}},ensure_ascii=False),
            __import__("json").dumps({**valid,"signature":"wrong"},ensure_ascii=False),
            __import__("json").dumps({**valid,"state":{**valid["state"],
                                "goal":2147483648}},ensure_ascii=False)
        ]
        for raw in bad_cases:
            state_file.write_text(raw,encoding="utf8")
            subprocess.run(["node",str(ROOT/"scripts/verify_native_web_persist_node.js"),
                            str(persistent_output),str(state_file),"reject"],
                           cwd=ROOT,check=True,timeout=20)
        print("PASS: malformed/doubled browser snapshot keys and invalid values are rejected")
    print("PASS: native app-mode Web codegen, persistence, collection queries, navigation")

if __name__=="__main__":
    main()
