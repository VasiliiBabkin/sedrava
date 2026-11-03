"""Run the same browser acceptance checks on two independently built baselines.

Preconditions: TypeScript compiler and Playwright Chromium installed.
This is a toolchain/evaluator smoke test, NOT an AI-agent benchmark trial.
"""
import functools
import http.server
import json
import pathlib
import subprocess
import sys
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parents[3]
BENCH = ROOT / "benchmarks/agent"
sys.path.insert(0, str(ROOT))
from web_codegen import generate


class SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def run_case(name, directory, selector, report_dir):
    handler = functools.partial(SilentHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    report = report_dir / (name + ".json")
    try:
        cmd = [
            sys.executable, str(BENCH / "acceptance/counter_web_browser.py"),
            "--url", f"http://127.0.0.1:{server.server_port}/index.html",
            "--value-selector", selector,
            "--increment-label", "Add", "--decrement-label", "Subtract",
            "--reset-label", "Reset", "--output", str(report),
        ]
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                timeout=120)
        print(name, result.stdout, result.stderr, flush=True)
        if result.returncode:
            raise RuntimeError(f"{name} browser acceptance failed: {report.read_text() if report.exists() else result.stderr}")
        data = json.loads(report.read_text(encoding="utf-8"))
        if not data["passed"] or len(data["observations"]) != 8:
            raise RuntimeError(f"{name}: incomplete browser evidence")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def main():
    report_dir = ROOT / "build/agent-benchmark-baselines"
    report_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="sedrava-benchmark-") as tmp:
        root = pathlib.Path(tmp)
        sedrava_dir = root / "sedrava"
        sedrava_dir.mkdir()
        source = (BENCH / "baselines/sedrava/counter.sdr").read_text(encoding="utf-8")
        (sedrava_dir / "index.html").write_text(generate(source), encoding="utf-8")
        run_case("sedrava", sedrava_dir, 'output[data-state="count"]', report_dir)
        typescript_dir = BENCH / "baselines/typescript"
        if not (typescript_dir / "counter.js").is_file():
            raise RuntimeError("TypeScript baseline not compiled: run tsc first")
        run_case("typescript", typescript_dir, "#count", report_dir)
    print("Both non-agent baselines passed independent browser acceptance.")


if __name__ == "__main__":
    main()
