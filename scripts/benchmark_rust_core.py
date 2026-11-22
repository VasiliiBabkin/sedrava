#!/usr/bin/env python3
"""End-to-end CLI latency comparison: Python Sedrava vs experimental Rust core.

This is NOT a benchmark of generated Web/Android apps, compiler backends,
general Sedrava programs, or language execution in a long-lived process.
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = [
    ("check-reference", "check", "examples/reference_09.sdr", []),
    ("run-reference", "run", "examples/reference_09.sdr", ["add", "add"]),
    ("run-unicode", "run", "examples/text_profile.sdr", ["rename"]),
    ("test-reference", "test", "examples/reference_09.sdr", []),
    ("run-records", "run", "tests/rust_cases/records_lists.sdr", ["add", "finish"]),
    ("run-functions", "run", "tests/rust_cases/functions_queries.sdr", ["add"]),
    ("run-navigation", "run", "tests/rust_cases/navigation.sdr", ["open", "$back"]),
]


def version(argv: list[str]) -> str:
    result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f"version command failed: {argv}: {result.stderr}")
    return result.stdout.strip()


def single(prefix: list[str], command: str, path: str, actions: list[str]) -> float:
    start = time.perf_counter_ns()
    child = subprocess.run(
        prefix + [command, path, *actions],
        cwd=ROOT,
        capture_output=True,
        timeout=30,
        check=False,
    )
    elapsed = (time.perf_counter_ns() - start) / 1_000_000
    if child.returncode:
        raise RuntimeError(
            f"command failed: {prefix[0]} {command} {path} "
            f"{actions}: {child.stderr.decode('utf-8', errors='replace')}"
        )
    return elapsed


def metrics(samples: list[float]) -> dict:
    ordered = sorted(samples)
    return {
        "n": len(samples),
        "median_ms": round(statistics.median(samples), 4),
        "p95_ms_nearest_rank": round(ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)], 4),
        "min_ms": round(ordered[0], 4),
        "max_ms": round(ordered[-1], 4),
        "samples_ms": [round(x, 4) for x in samples],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", type=Path, default=ROOT / "rust/target/debug/sedrava-native")
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--seed", type=int, default=23042)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 5 <= args.repeats <= 200:
        parser.error("repeats must be between 5 and 200")
    native = args.native.resolve()
    if not native.is_file():
        parser.error("native executable missing; cargo build --manifest-path rust/Cargo.toml --bin sedrava-native")

    python = [sys.executable, str(ROOT / "sedrava_cli.py")]
    rust = [str(native)]
    rng = random.Random(args.seed)
    measurements = []
    for name, command, source, actions in SCENARIOS:
        # Execute both runners in the same subprocess-based scenario.
        for _ in range(5):
            single(python, command, source, actions)
            single(rust, command, source, actions)
        results = {"python": [], "rust": []}
        order = ["python"] * args.repeats + ["rust"] * args.repeats
        rng.shuffle(order)
        for engine in order:
            results[engine].append(single(python if engine == "python" else rust, command, source, actions))
        a = metrics(results["python"])
        b = metrics(results["rust"])
        measurements.append({
            "name": name, "command": command, "source": source, "actions": actions,
            "python": a, "rust": b,
            "median_ratio_python_div_rust": round(a["median_ms"] / b["median_ms"], 3),
        })

    report = {
        "schema": "sedrava-rust-cli-benchmark-v1",
        "utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": version([sys.executable, "--version"]),
        "rust_binary": version([str(native), "--version"]),
        "repeats_each": args.repeats,
        "seed": args.seed,
        "scope": "new process start + CLI startup + source parse/type-check + indicated command",
        "caveats": [
            "Comparison only covers programs supported by experimental Rust scalar core.",
            "No backend generation or long-lived interpreter throughput measured.",
            "Measurements can be influenced by machine load, page cache and filesystem.",
            "Single machine/time sample does not prove a universal or architecture-wide speedup.",
            "Run conformance verification separately before citing benchmark results.",
        ],
        "scenarios": measurements,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
