"""Validate and summarize Sedrava Agent Benchmark trial JSON files.

Standard library only. This validates recorded metadata, not the truth of
agent-generated measurements or the behavioral correctness of a program.
"""
import argparse
import json
import pathlib
import re
import statistics
import sys

TASKS = {"counter-v0", "records-v0", "navigation-v0", "http-cards-v0"}
LANGUAGES = {"sedrava", "typescript", "kotlin"}
TARGETS = {"web", "android"}
OUTCOMES = {"passed", "failed", "unsupported", "infrastructure_error"}
REQUIRED = {"schema_version", "task", "language", "target", "trial_id",
            "repository_commit", "model", "outcome", "build_passed",
            "behavior_passed", "attempts", "wall_seconds", "input_tokens",
            "output_tokens", "tool_calls", "cost_usd", "notes"}


def validate(record):
    if type(record) is not dict:
        raise ValueError("Trial must be a JSON object")
    if set(record) != REQUIRED:
        raise ValueError("Missing/extra fields: " + repr(sorted(REQUIRED ^ set(record))))
    if record["schema_version"] != "0.1":
        raise ValueError("Unsupported schema version")
    for key, allowed in (("task", TASKS), ("language", LANGUAGES),
                         ("target", TARGETS), ("outcome", OUTCOMES)):
        if type(record[key]) is not str or record[key] not in allowed:
            raise ValueError("Invalid " + key)
    for key in ("trial_id", "model"):
        if type(record[key]) is not str or not record[key].strip():
            raise ValueError("Invalid " + key)
    if not re.fullmatch("[0-9a-f]{40}", str(record["repository_commit"])):
        raise ValueError("Invalid repository_commit")
    if type(record["notes"]) is not str:
        raise ValueError("Invalid notes")
    for key in ("build_passed", "behavior_passed"):
        if record[key] is not None and type(record[key]) is not bool:
            raise ValueError("Invalid " + key)
    for key in ("attempts", "input_tokens", "output_tokens", "tool_calls"):
        value = record[key]
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("Invalid " + key)
    if record["attempts"] is None:
        raise ValueError("attempts must be measured")
    for key in ("wall_seconds", "cost_usd"):
        value = record[key]
        if value is not None and (type(value) not in (int, float) or
                                  not 0 <= value < float("inf")):
            raise ValueError("Invalid " + key)
    if record["outcome"] == "passed" and (record["build_passed"] is not True or
                                            record["behavior_passed"] is not True):
        raise ValueError("Passed requires successful build and behavior")
    if record["outcome"] in ("unsupported", "infrastructure_error") and (
            record["build_passed"] is not None or record["behavior_passed"] is not None):
        raise ValueError("Unsupported/infrastructure outcomes cannot claim test results")
    if record["outcome"] == "failed" and record["behavior_passed"] is True:
        raise ValueError("Failed trial cannot pass behavioral tests")
    return record


def summarize(records):
    groups = {}
    for record in records:
        key = (record["task"], record["target"], record["language"], record["model"])
        groups.setdefault(key, []).append(record)
    output = []
    for key, trials in sorted(groups.items()):
        evaluated = [r for r in trials if r["outcome"] in ("passed", "failed")]
        passed = sum(r["outcome"] == "passed" for r in evaluated)
        def median(field):
            values = [r[field] for r in evaluated if r[field] is not None]
            return statistics.median(values) if values else None
        output.append({"task": key[0], "target": key[1], "language": key[2],
                       "model": key[3], "trials": len(trials),
                       "evaluated": len(evaluated), "passed": passed,
                       "pass_rate": passed / len(evaluated) if evaluated else None,
                       "unsupported": sum(r["outcome"] == "unsupported" for r in trials),
                       "infrastructure_errors": sum(r["outcome"] == "infrastructure_error" for r in trials),
                       "median_attempts": median("attempts"),
                       "median_wall_seconds": median("wall_seconds"),
                       "median_input_tokens": median("input_tokens"),
                       "median_output_tokens": median("output_tokens"),
                       "median_cost_usd": median("cost_usd")})
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    records = []
    ids = set()
    try:
        for path in args.files:
            data = json.loads(path.read_text(encoding="utf-8"))
            for item in data if type(data) is list else [data]:
                record = validate(item)
                if record["trial_id"] in ids:
                    raise ValueError("Duplicate trial_id: " + record["trial_id"])
                ids.add(record["trial_id"])
                records.append(record)
        result = {"schema_version": "0.1", "total_trials": len(records),
                  "groups": summarize(records)}
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("Benchmark validation error: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
