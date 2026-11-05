"""Read-only real PyPI stable 0.11.0 -> local 0.12.0a1 -> stable install audit.

Uses published immutable wheels/sdist, checks CLI/app state and removes alpha-only
modules on rollback. No registry publication and no source-tree Python imports.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv
from urllib.request import urlopen

STABLE = "0.11.0"
ALPHA = "0.12.0a1"
PUBLISHED_SHA256 = {
    "sedrava-0.11.0-py3-none-any.whl":
        "5780c3cb14f33b95689c518809254e269a3396bb02720e88f9407b9abbd24626",
    "sedrava-0.11.0.tar.gz":
        "453096116a9da834c4db9023069962cc0d5bf18acb88e403994ad61a339ef70b",
}

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def published_stable(destination: Path) -> Path:
    with urlopen("https://pypi.org/pypi/sedrava/0.11.0/json", timeout=30) as source:
        metadata = json.load(source)
    for name, expected in PUBLISHED_SHA256.items():
        item = next((x for x in metadata["urls"] if x["filename"] == name), None)
        if item is None or item["digests"]["sha256"] != expected:
            raise ValueError("Published stable archive identity changed: " + name)
        if not item["url"].startswith("https://files.pythonhosted.org/"):
            raise ValueError("Unexpected PyPI distribution host")
        with urlopen(item["url"], timeout=30) as source:
            blob = source.read(8 * 1024 * 1024 + 1)
        if len(blob) > 8 * 1024 * 1024 or sha256(blob) != expected:
            raise ValueError("Published stable content changed: " + name)
        (destination / name).write_bytes(blob)
    return destination / "sedrava-0.11.0-py3-none-any.whl"

def run(cwd: Path, *command: object) -> str:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env["PYTHONNOUSERSITE"] = "1"
    completed = subprocess.run(
        list(map(str, command)), cwd=cwd, env=env,
        check=True, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return completed.stdout

def check(dist: Path) -> None:
    dist = dist.resolve()
    wheel = dist / "sedrava-0.12.0a1-py3-none-any.whl"
    sdist = dist / "sedrava-0.12.0a1.tar.gz"
    if not (wheel.is_file() and sdist.is_file()):
        raise ValueError("Exactly one built alpha wheel/sdist pair required")
    with tempfile.TemporaryDirectory(prefix="sedrava-stable-alpha-") as folder:
        work = Path(folder)
        stable_wheel = published_stable(work)
        environment = work / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        bin_path = environment / ("Scripts" if os.name == "nt" else "bin")
        python = bin_path / ("python.exe" if os.name == "nt" else "python")
        cli = bin_path / ("sedrava.exe" if os.name == "nt" else "sedrava")
        projects = work / "original-projects"
        projects.mkdir()
        state = work / "user-state.json"
        original_hashes = {}
        preserved_hash = None
        steps = []
        for phase, archive, version in [
            ("published-011", stable_wheel, STABLE),
            ("experimental-alpha", wheel, ALPHA),
            ("stable-rollback", stable_wheel, STABLE),
        ]:
            run(work, python, "-m", "pip", "install", "--no-cache-dir", "--force-reinstall", archive)
            run(work, python, "-m", "pip", "check")
            if run(work, cli, "--version").strip() != "sedrava " + version:
                raise AssertionError("Incorrect installed CLI version")
            installed_version = run(
                work, python, "-I", "-c",
                "import importlib.metadata;print(importlib.metadata.version('sedrava'))",
            ).strip()
            if installed_version != version:
                raise AssertionError("Unexpected installed package version")

            for name in ("reference_09", "text_profile", "task_manager", "task_manager_navigation"):
                source = projects / (name + ".sdr")
                installed = environment / "share/sedrava/examples" / source.name
                if not source.is_file():
                    source.write_bytes(installed.read_bytes())
                    original_hashes[source.name] = sha256(source.read_bytes())
                if sha256(source.read_bytes()) != original_hashes[source.name]:
                    raise AssertionError("User source modified after installation")
                run(work, cli, "check", source)
                run(work, cli, "test", source)
                if name == "task_manager_navigation":
                    run(work, cli, "build", "web", source,
                        "--output", work / (phase + "-web") / "index.html")
                    run(work, cli, "build", "android", source,
                        "--output", work / (phase + "-android"))
            profile = projects / "text_profile.sdr"
            if phase == "published-011":
                output = json.loads(run(work, cli, "run", profile, "rename", "--state-file", state))
            else:
                output = json.loads(run(work, cli, "run", profile, "--state-file", state))
            if output["name"] != "Алиса 😀":
                raise AssertionError("User Unicode state changed across upgrade/rollback")
            current_hash = sha256(state.read_bytes())
            if preserved_hash is None:
                preserved_hash = current_hash
            if current_hash != preserved_hash:
                raise AssertionError("Canonical user state bytes changed")
            if phase == "experimental-alpha":
                for name, mode in [("platform_site", "site"), ("platform_tasks", "webapp")]:
                    example = environment / "share/sedrava/examples" / (name + ".sdr")
                    run(work, cli, "check", example)
                    run(work, cli, "build", mode, example,
                        "--output", work / (phase + "-" + name))
            steps.append({"phase": phase, "version": version, "state_sha256": current_hash})
        # No incompatible modules or package manager code may leak back after pip rollback.
        run(work, python, "-I", "-c",
            "import importlib.util;"
            "assert importlib.util.find_spec('sedrava_namespaces') is None;"
            "assert importlib.util.find_spec('sedrava_packages') is None")
        print(json.dumps({
            "status": "PASS",
            "upgrade": "published 0.11.0 -> local 0.12.0a1 -> published 0.11.0",
            "published_sha256": PUBLISHED_SHA256,
            "candidate_sha256": {p.name: sha256(p.read_bytes()) for p in (wheel, sdist)},
            "preserved_project_sha256": original_hashes,
            "steps": steps,
            "limits": "CLI/Web/Android source generation on Linux; Android APK update on device not tested",
        }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/check_stable_to_alpha_012.py dist")
    check(Path(sys.argv[1]))
