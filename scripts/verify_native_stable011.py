#!/usr/bin/env python3
"""Conformance sampler against an *exact, published* Sedrava 0.11.0 source tree.

Unlike verify_rust_core.py this does NOT use Python code from current main.
This verifies restricted scalar/record/action behavior, not complete language
parity or identical human-readable error descriptions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STABLE_SHA="c9cde75e3d2e2c7eafeeaec10c73fec627816e68"
APPS=(
    "counter.sdr","reference_09.sdr","countdown.sdr",
    "daily_steps.sdr","derived_progress.sdr","input_goal.sdr",
    "task_manager.sdr","task_manager_navigation.sdr",
    "text_profile.sdr","timer.sdr","workflow.sdr",
)
WEB=(
    "platform_catalog.sdr","platform_crm.sdr","platform_site.sdr",
    "platform_tasks.sdr","web_ui_011_landing.sdr",
    "webapp_011_counter.sdr","webapp_011_tasks.sdr",
)
# Syntax accepted by Python's published 0.11.0, not current main.
ACTION_RE=re.compile(r"(?m)^action ([A-Za-z_][A-Za-z_0-9]*):")


def execute(cli: list[str],command:str,source:Path,actions:list[str]):
    result=subprocess.run(
        [*cli,command,str(source),*actions],
        cwd=source.parent, text=True, capture_output=True,timeout=20,check=False,
        encoding="utf-8",
    )
    return result.returncode,result.stdout.strip(),result.stderr.strip()


def compare(command:str,a,b):
    if (a[0]==0)!=(b[0]==0):
        return False
    if a[0]!=0:
        return True # Both rejected. The reasons may differ.
    if command=="run":
        try:
            return json.loads(a[1])==json.loads(b[1])
        except (TypeError,json.JSONDecodeError):
            return False
    if command=="test":
        return a[1]==b[1]
    return True


def verify_exact_upstream_tree(base:Path):
    """Verify all source blobs against the pinned GitHub release commit."""
    rev=subprocess.run(
        ["git","-C",str(ROOT),"rev-parse","refs/tags/v0.11.0^{commit}"],
        capture_output=True,text=True,check=True,timeout=20,
    ).stdout.strip()
    if rev!=STABLE_SHA:
        raise RuntimeError(f"Unexpected stable tag commit: {rev}")
    ls=subprocess.run(
        ["git","-C",str(ROOT),"ls-tree","-r","-z","refs/tags/v0.11.0"],
        capture_output=True,check=True,timeout=30,
    ).stdout
    paths=0
    total_bytes=0
    for record in ls.split(b"\0"):
        if not record:
            continue
        metadata,name=record.split(b"\t",1)
        mode,kind,sha=metadata.decode("ascii").split(" ")
        if kind!="blob" or mode not in ("100644","100755","120000"):
            raise RuntimeError(f"Unexpected source object: {metadata!r}")
        filename=Path(os.fsdecode(name))
        source=base/filename
        if mode=="120000":
            if not source.is_symlink():
                raise RuntimeError(f"Stable release symlink missing: {filename}")
            payload=os.readlink(source).encode("utf-8")
        else:
            if not source.is_file() or source.is_symlink():
                raise RuntimeError(f"Stable release file missing: {filename}")
            payload=source.read_bytes()
        actual=hashlib.sha1(
            b"blob "+str(len(payload)).encode("ascii")+b"\0"+payload
        ).hexdigest()
        if actual!=sha:
            raise RuntimeError(f"Stable release source differs from published tag: {filename}")
        paths+=1
        total_bytes+=len(payload)
    if paths<80:
        raise RuntimeError("Unexpectedly incomplete published source tree")
    return paths,total_bytes


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--stable-root",type=Path,required=True,
                   help="Exact source exported from upstream v0.11.0, SHA c9cde75...")
    p.add_argument("--native",type=Path,required=True)
    p.add_argument("--random-cases",type=int,default=45)
    p.add_argument("--seed",type=int,default=12011)
    p.add_argument("--report",type=Path)
    args=p.parse_args()
    if not 0<=args.random_cases<=200:
        p.error("random-cases must be 0..200")
    base=args.stable_root.resolve()
    stable_cli=base/"sedrava_cli.py"
    binary=args.native.resolve()
    assert stable_cli.is_file() and binary.is_file()
    stable_files,stable_bytes=verify_exact_upstream_tree(base)
    check=subprocess.run([sys.executable,str(stable_cli),"--version"],
                         capture_output=True,text=True,check=True,timeout=20)
    assert check.stdout.strip()=="sedrava 0.11.0",check.stdout
    stable_cases=sorted(base.glob("examples/*.sdr"))
    assert set(APPS+WEB)=={s.name for s in stable_cases},sorted(s.name for s in stable_cases)
    native=[str(binary)]
    python=[sys.executable,str(stable_cli)]
    rng=random.Random(args.seed)
    failures=[]
    total=0
    valid=0
    invalid=0
    by_case={}
    def check_case(name,cmd,source,actions):
        nonlocal total,valid,invalid
        original=execute(python,cmd,source,actions)
        newer=execute(native,cmd,source,actions)
        total+=1
        if original[0]==0:
            valid+=1
        else:
            invalid+=1
        if compare(cmd,original,newer):
            return
        failures.append({
            "file":name,"command":cmd,"actions":actions,
            "python_exit":original[0],"rust_exit":newer[0],
            "python_stdout":original[1][:1100],
            "rust_stdout":newer[1][:1100],
            "python_stderr":original[2][-500:],
            "rust_stderr":newer[2][-500:],
        })
    for name in APPS:
        source=base/"examples"/name
        actions=ACTION_RE.findall(source.read_text(encoding="utf-8"))
        assert actions,name
        before=total
        for cmd in ("check","test","run"):
            check_case(name,cmd,source,[])
        for action in actions:
            check_case(name,"run",source,[action])
        for _ in range(args.random_cases):
            picks=[rng.choice(actions) for _ in range(rng.randrange(0,9))]
            check_case(name,"run",source,picks)
        by_case[name]=total-before
    for name in WEB:
        source=base/"examples"/name
        before=total
        check_case(name,"check",source,[])
        by_case[name]=total-before
    result={
        "schema":"sedrava.native.stable011.differential.v1",
        "oracle":"published Sedrava Python 0.11.0 release source",
        "stable_release_commit":STABLE_SHA,
        "stable_tree_verified_against_git":True,
        "stable_tracked_files_verified":stable_files,
        "stable_tracked_source_bytes":stable_bytes,
        "stable_cli_version":check.stdout.strip(),
        "native_binary_sha256":hashlib.sha256(binary.read_bytes()).hexdigest(),
        "seed":args.seed,
        "random_cases_per_app":args.random_cases,
        "compared_apps":list(APPS),
        "checked_web_examples":list(WEB),
        "comparisons":total,"python_accepted":valid,
        "python_rejected":invalid,"mismatch_count":len(failures),
        "mismatches":failures[:30],
        "note":"Same rejection is not proof of same error semantics; no full Web output equivalence, Android, or security claim.",
    }
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({
        k:v for k,v in result.items() if k not in ("mismatches","compared_apps","checked_web_examples")
    },ensure_ascii=False,indent=2),flush=True)
    for problem in failures[:5]:
        print("MISMATCH",json.dumps(problem,ensure_ascii=False),flush=True)
    return 1 if failures else 0

if __name__=="__main__":
    sys.exit(main())
