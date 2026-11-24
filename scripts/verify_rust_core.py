#!/usr/bin/env python3
"""Differential checks: restricted Rust native core vs authoritative Python core.

Python standard library only. Compare actual JSON state for accepted runs and
success/rejection for invalid runs; error wording is intentionally not compared.
No automatic substitution of Rust into production commands.
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from legacy_reference import legacy_root

CASES = {
    "examples/counter.sdr": ["increment", "decrement", "reset"],
    "examples/reference_09.sdr": ["add", "subtract", "reset", "restore"],
    "examples/text_profile.sdr": ["rename", "reset", "reject_blank"],
    "tests/rust_cases/scalars.sdr": ["add", "toggle", "rename", "reset"],
    "tests/rust_cases/overflow.sdr": ["overflow"],
    "tests/rust_cases/require.sdr": ["guarded", "negative"],
    "tests/rust_cases/escaped.sdr": ["change"],
    "examples/task_manager.sdr": ["add", "complete", "rename", "delete"],
    "tests/rust_cases/records_lists.sdr": ["add", "finish", "delete"],
    "tests/rust_cases/functions_queries.sdr": ["add", "update"],
    "examples/task_manager_navigation.sdr": ["add_task", "prepare_details", "open_details", "delete_and_back", "$back", "toggle_task"],
    "tests/rust_cases/navigation.sdr": ["open", "back", "$back", "step", "disable"],
    "tests/rust_cases/lazy_queries.sdr": ["prepare"],
}


def execute(prefix: list[str], command: str, source: str, actions: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(
        prefix + [command, source, *actions],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def equivalent(command: str, original: tuple[int, str, str], native: tuple[int, str, str]) -> bool:
    if (original[0] == 0) != (native[0] == 0):
        return False
    if original[0] != 0:
        return True  # Both reject; error text and reason still need deeper review.
    if command == "run":
        try:
            return json.loads(original[1]) == json.loads(native[1])
        except json.JSONDecodeError:
            return False
    if command == "test":
        return original[1] == native[1]
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--native",
        type=Path,
        default=ROOT / "rust" / "target" / "debug" / "sedrava",
    )
    ap.add_argument("--seed", type=int, default=90210)
    ap.add_argument("--random-cases", type=int, default=32)
    ap.add_argument("--report", type=Path, default=None)
    opts = ap.parse_args()
    if opts.random_cases < 0 or opts.random_cases > 500:
        ap.error("random-cases must be from 0 to 500")
    executable = opts.native.resolve()
    if not executable.is_file():
        ap.error(f"native binary is missing: {executable}; build with cargo first")

    python = [sys.executable, str(legacy_root() / "sedrava_cli.py")]
    rust = [str(executable)]
    rng = random.Random(opts.seed)
    mismatches = []
    total = 0
    accepted = 0
    rejected = 0

    for source, choices in CASES.items():
        candidates = [
            ("check", []),
            ("test", []),
            ("run", []),
            *[("run", [name]) for name in choices],
        ]
        for _ in range(opts.random_cases):
            candidates.append(("run", [
                rng.choice(choices) for _ in range(rng.randrange(0, 8))
            ]))
        for command, actions in candidates:
            original = execute(python, command, source, actions)
            native = execute(rust, command, source, actions)
            total += 1
            if original[0] == 0:
                accepted += 1
            else:
                rejected += 1
            if not equivalent(command, original, native):
                mismatches.append({
                    "source": source,
                    "command": command,
                    "actions": actions,
                    "python": {"exit": original[0], "stdout": original[1], "stderr": original[2][-1000:]},
                    "rust": {"exit": native[0], "stdout": native[1], "stderr": native[2][-1000:]},
                })
                if len(mismatches) >= 20:
                    break
        if len(mismatches) >= 20:
            break

    catalog_supported = execute(rust, "check", "examples/platform_catalog.sdr", [])[0] == 0
    if not catalog_supported:
        mismatches.append({"source": "examples/platform_catalog.sdr", "problem": "native HTTP catalog failed to check"})

    summary = {
        "schema": "sedrava-rust-differential-v1",
        "seed": opts.seed,
        "random_cases_per_source": opts.random_cases,
        "comparisons": total,
        "python_accepted": accepted,
        "python_rejected": rejected,
        "native_http_catalog_accepted": catalog_supported,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
         "note": "Comparable outcomes are limited to listed scalar, record, collection, pure function, standard library and navigation examples; same rejection does not prove identical failure semantics.",
    }
    output = json.dumps(summary, indent=2, ensure_ascii=False)
    if opts.report:
        opts.report.parent.mkdir(parents=True, exist_ok=True)
        opts.report.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 1 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
