"""Freeze one coding-agent experiment's inputs. Does NOT invoke an AI model.

Create one bundle for each independent trial, and give the agent only the
bundle's prompt and explicitly listed input files. Keep evaluator code private.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SUPPORTED = {("counter-v0", "web", "sedrava"),
             ("counter-v0", "web", "typescript"),
             ("counter-v0", "android", "sedrava"),
             ("counter-v0", "android", "kotlin")}


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative_file(value: str) -> Path:
    source = (REPO / value).resolve()
    if not source.is_relative_to(REPO) or not source.is_file():
        raise ValueError("Input must be an existing repository file: " + value)
    if source.stat().st_size > 2_000_000:
        raise ValueError("Input too large: " + value)
    return source.relative_to(REPO)


def freeze(paths, category, folder):
    recorded = []
    for path in sorted(set(paths)):
        relative = relative_file(path)
        source = REPO / relative
        target = folder / "inputs" / category / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        recorded.append({"path": (Path("inputs") / category / relative).as_posix(),
                         "sha256": checksum(source.read_bytes()),
                         "source_path": relative.as_posix()})
    return recorded


def prepare(args):
    if (args.task, args.target, args.language) not in SUPPORTED:
        raise ValueError("Unsupported language/target/task combination")
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        raise ValueError("A real 40-character commit SHA is required")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", args.trial_id):
        raise ValueError("Use a unique URL-safe trial ID")
    if args.seconds <= 0 or args.tokens <= 0 or args.attempts <= 0:
        raise ValueError("Budgets must be positive")
    if not args.starter or not args.reference:
        raise ValueError("At least one starter file and reference file are required")
    folder = args.output.resolve()
    folder.mkdir(parents=True, exist_ok=False)
    starters = freeze(args.starter, "starter", folder)
    references = freeze(args.reference, "reference", folder)
    task_source = (HERE / "tasks" / (args.task + ".md")).read_bytes()
    (folder / "task.md").write_bytes(task_source)
    manifest = {
        "protocol": "sedrava-agent-benchmark-v0",
        "trial_id": args.trial_id,
        "task": args.task, "target": args.target, "language": args.language,
        "repository_commit": args.commit,
        "model": args.model, "agent": args.agent, "seed": args.seed,
        "temperature": args.temperature, "toolchain": args.toolchain,
        "budgets": {"seconds": args.seconds, "tokens": args.tokens,
                    "attempts": args.attempts},
        "task_sha256": checksum(task_source), "starters": starters,
        "references": references,
        "outcome": "not_run"
    }
    (folder / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    starter_lines = "\n".join("- " + x["path"] for x in starters)
    reference_lines = "\n".join("- " + x["path"] for x in references)
    prompt = (
        "# Coding-agent task: " + args.task + "\n\n"
        "Implement the application described in task.md using " + args.language +
        " for " + args.target + ".\n\n"
        "Use only the supplied starter files and language references as a starting point. "
        "You may run compiler/build commands and fix your own source, within the declared budgets. "
        "Do not modify the task contract. The evaluator is independent and unavailable to you.\n\n"
        "Starter files:\n" + starter_lines + "\n\n"
        "Language references:\n" + reference_lines + "\n\n"
        "Deliver a runnable candidate, a short README with exact build/run instructions, "
        "and a statement of any unmet requirements. Do not use a different language "
        "for the core state or UI behavior.\n\n"
        "Trial ID: " + args.trial_id + "\n"
        "Commit: " + args.commit + "\n"
        "Agent: " + args.agent + "; model: " + args.model + "\n"
        "Budget: " + str(args.seconds) + " seconds, " + str(args.tokens) +
        " tokens, " + str(args.attempts) + " attempts.\n"
        "Seed: " + str(args.seed) + "; temperature: " + str(args.temperature) + "\n"
    )
    (folder / "prompt.md").write_text(prompt, encoding="utf-8")
    print(folder)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="counter-v0")
    parser.add_argument("--target", required=True, choices=["web", "android"])
    parser.add_argument("--language", required=True,
                        choices=["sedrava", "typescript", "kotlin"])
    parser.add_argument("--commit", required=True)
    parser.add_argument("--trial-id", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--temperature", default="not exposed")
    parser.add_argument("--toolchain", required=True)
    parser.add_argument("--seconds", type=int, required=True)
    parser.add_argument("--tokens", type=int, required=True)
    parser.add_argument("--attempts", type=int, required=True)
    parser.add_argument("--starter", action="append", required=True)
    parser.add_argument("--reference", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        prepare(args)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
