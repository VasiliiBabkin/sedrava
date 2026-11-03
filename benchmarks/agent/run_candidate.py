"""Run a candidate's build and behavioral checks and record an observed trial.

This runner does not call an AI model. Candidate source must already exist.
Use explicit commands and pass token/cost measurements only when observed.
"""
import argparse
import datetime
import json
import pathlib
import subprocess
import sys
import time
import uuid

from analyze import validate


def execute(command, cwd, timeout, log_path):
    started = time.monotonic()
    try:
        with log_path.open("w", encoding="utf-8") as log:
            result = subprocess.run(command, shell=False, cwd=cwd,
                                    stdout=log, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False)
        return result.returncode == 0, time.monotonic() - started, "exit " + str(result.returncode)
    except subprocess.TimeoutExpired:
        return False, time.monotonic() - started, "timeout"
    except OSError as exc:
        log_path.write_text(str(exc), encoding="utf-8")
        return False, time.monotonic() - started, "execution error"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--model", required=True, help="Model identifier, or 'manual-baseline'")
    parser.add_argument("--commit", required=True, help="40-character repository commit")
    parser.add_argument("--cwd", required=True, type=pathlib.Path)
    parser.add_argument("--build", required=True, nargs="+", help="Build command argv; use --build=PROGRAM")
    parser.add_argument("--test", required=True, nargs="+", help="Behavioral test command argv; use --test=PROGRAM")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--trial-id", default=None)
    parser.add_argument("--notes", default="")
    args = parser.parse_args(argv)
    if args.timeout < 1 or not args.cwd.is_dir():
        parser.error("timeout must be positive and cwd must exist")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    trial_id = args.trial_id or str(uuid.uuid4())
    start = time.monotonic()
    build_ok, _, build_status = execute(args.build, args.cwd, args.timeout,
                                        args.output.with_suffix(".build.log"))
    test_ok = None
    test_status = "not run"
    if build_ok:
        test_ok, _, test_status = execute(args.test, args.cwd, args.timeout,
                                          args.output.with_suffix(".test.log"))
    record = {
        "schema_version": "0.1", "task": args.task, "language": args.language,
        "target": args.target, "trial_id": trial_id,
        "repository_commit": args.commit, "model": args.model,
        "outcome": "passed" if build_ok and test_ok else "failed",
        "build_passed": build_ok, "behavior_passed": test_ok,
        "attempts": 1, "wall_seconds": round(time.monotonic() - start, 4),
        "input_tokens": None, "output_tokens": None, "tool_calls": None,
        "cost_usd": None,
        "notes": args.notes + " [build: " + build_status + "; behavior: " + test_status + "]"
    }
    validate(record)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(args.output)
    return 0 if record["outcome"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
