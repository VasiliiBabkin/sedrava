#!/usr/bin/env python3
"""Build published 0.11 Web fixtures in Python and native Rust on disposable paths.

Verifies deterministic native output, local asset resolution, and Node.js
parseability. Does not claim Chromium/Firefox/WebKit runtime equivalence.
"""
from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import unquote,urlsplit

ROOT=Path(__file__).resolve().parents[1]
from verify_native_stable011 import STABLE_SHA,verify_exact_upstream_tree

SOURCES={
    "platform_site.sdr":"site",
    "web_ui_011_landing.sdr":"site",
    "platform_catalog.sdr":"webapp",
    "platform_crm.sdr":"webapp",
    "platform_tasks.sdr":"webapp",
    "webapp_011_counter.sdr":"webapp",
    "webapp_011_tasks.sdr":"webapp",
}

class ResourceExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths=[]
    def handle_starttag(self,tag,attrs):
        values=dict(attrs)
        if tag=="script" and "src" in values:
            self.paths.append(values["src"])
        if tag=="link" and values.get("rel") in ("stylesheet","icon") and "href" in values:
            self.paths.append(values["href"])
        if tag in ("img","audio","video","source") and values.get("src"):
            self.paths.append(values["src"])


def run(args:list[str],cwd:Path,ok=True):
    result=subprocess.run(args,cwd=cwd,capture_output=True,text=True,timeout=40,check=False)
    if (result.returncode==0)!=ok:
        raise RuntimeError(f"Unexpected command exit={result.returncode}: {args!r}\n{result.stdout[-1000:]}\n{result.stderr[-1400:]}")
    return result


def files(root:Path)->dict[str,bytes]:
    return {str(p.relative_to(root)):p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def check_links(root:Path)->tuple[int,int]:
    pages=list(root.rglob("*.html"))
    assert pages
    checked=0
    for page in pages:
        parser=ResourceExtractor()
        parser.feed(page.read_text(encoding="utf-8"))
        for ref in parser.paths:
            parsed=urlsplit(ref)
            if parsed.scheme or parsed.netloc or ref.startswith("//"):
                raise AssertionError(f"Externally hosted resource in {page}: {ref}")
            if parsed.path.startswith("/"):
                location=root/parsed.path.lstrip("/")
            else:
                location=page.parent/unquote(parsed.path)
            resolved=location.resolve()
            if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
                raise AssertionError(f"Missing/unsafe local asset in {page}: {ref}")
            checked+=1
    return len(pages),checked


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--native",type=Path,required=True)
    ap.add_argument("--stable-root",type=Path,required=True)
    ap.add_argument("--report",type=Path)
    ap.add_argument("--keep-output",type=Path,
                    help="Preserve exact validated native/stable Web builds for external browser tests")
    args=ap.parse_args()
    binary=args.native.resolve()
    stable=args.stable_root.resolve()
    assert binary.is_file()
    count,byte_count=verify_exact_upstream_tree(stable)
    python=[sys.executable,str(stable/"sedrava_cli.py")]
    rust=[str(binary)]
    node_version=run(["node","--version"],ROOT).stdout.strip()
    report=[]
    with tempfile.TemporaryDirectory(prefix="sedrava-native-web011-") as name:
        tmp=Path(name)
        for basename,mode in SOURCES.items():
            source=stable/"examples"/basename
            builds={}
            for engine,cmd in [("stable011",python),("native012",rust)]:
                dest=tmp/engine/basename.removesuffix(".sdr")
                run([*cmd,"build",mode,str(source),"--output",str(dest)],ROOT)
                first=files(dest)
                assert "index.html" in first,(engine,basename)
                pages,resources=check_links(dest)
                js_files=list(dest.rglob("*.js"))
                for js in js_files:
                    run(["node","--check",str(js)],ROOT)
                assert not any(data.startswith(b"\xff\xfe") for data in first.values())
                builds[engine]={
                    "files":len(first),"html_pages":pages,
                    "checked_local_assets":resources,
                    "javascript_files_parsed":len(js_files),
                }
                if engine=="native012":
                    duplicate=tmp/"native-repeat"/basename.removesuffix(".sdr")
                    run([*cmd,"build",mode,str(source),"--output",str(duplicate)],ROOT)
                    assert files(duplicate)==first,(basename,"nondeterministic native output")
                    run([*cmd,"build",mode,str(source),"--output",str(dest)],ROOT,ok=False)
                    assert files(dest)==first,(basename,"overwrite changed content")
            report.append({"source":basename,"mode":mode,**builds})
            print(f"PASS {basename}: native stable-011 dual builds, asset paths, JS syntax, deterministic output",flush=True)
        if args.keep_output is not None:
            output=args.keep_output.resolve()
            if output.exists() or output.is_symlink():
                raise FileExistsError(f"Refusing to overwrite build outputs: {output}")
            output.mkdir(parents=True)
            shutil.copytree(tmp/"stable011",output/"stable011")
            shutil.copytree(tmp/"native012",output/"native012")
            print(f"Validated browser fixtures retained: {output}",flush=True)
    result={
        "schema":"sedrava.native.stable011.web-builds.v1",
        "stable_release_commit":STABLE_SHA,
        "stable_git_blobs_verified":count,
        "stable_source_bytes":byte_count,
        "native_sha256":hashlib.sha256(binary.read_bytes()).hexdigest(),
        "node_version":node_version,
        "cases":report,
        "result":"PASS",
        "limitations":"Generated assets and JavaScript syntax; no real browser engine or user UI interactions.",
    }
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(f"PASS {len(report)} exact-stable Web/Site build comparisons (no browser claim)",flush=True)


if __name__=="__main__":
    main()
