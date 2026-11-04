"""Verify pinned PyPI RC -> local stable wheel -> pinned RC in a disposable venv."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import urlopen
import venv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RC = "0.11.0rc1"
FINAL = "0.11.0"
PUBLISHED = {
    "sedrava-0.11.0rc1-py3-none-any.whl": "8a5080a9208718ceb6f32205e05314286164d7f994f2fce94edcddef09975674",
    "sedrava-0.11.0rc1.tar.gz": "07dc2380002016b6e64a5563698fe0c86cb4bafbde801197bd279845692d822d",
}

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def download(folder):
    with urlopen("https://pypi.org/pypi/sedrava/0.11.0rc1/json", timeout=30) as stream:
        data = json.load(stream)
    for name, expected in PUBLISHED.items():
        entry = next((f for f in data["urls"] if f["filename"] == name), None)
        if not entry or entry["digests"]["sha256"] != expected:
            raise ValueError("Published RC identity mismatch: " + name)
        if not entry["url"].startswith("https://files.pythonhosted.org/"):
            raise ValueError("Untrusted package host")
        with urlopen(entry["url"], timeout=30) as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024 or digest(raw) != expected:
            raise ValueError("Published RC bytes mismatch: " + name)
        (folder / name).write_bytes(raw)
    return folder / "sedrava-0.11.0rc1-py3-none-any.whl"

def invoke(cwd, *args):
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(key, None)
    env["PYTHONNOUSERSITE"] = "1"
    result = subprocess.run(list(map(str, args)), cwd=cwd, env=env,
                            check=True, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    return result.stdout

def main(dist):
    from sedrava_version import VERSION, ANDROID_VERSION_CODE
    assert (VERSION, ANDROID_VERSION_CODE) == (FINAL, 11002)
    stable_wheel = dist.resolve() / "sedrava-0.11.0-py3-none-any.whl"
    assert stable_wheel.is_file()
    with tempfile.TemporaryDirectory(prefix="sedrava rc stable ") as temp:
        root = Path(temp)
        old_wheel = download(root)
        environment = root / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        cli = scripts / ("sedrava.exe" if os.name == "nt" else "sedrava")
        project = root / "text_profile.sdr"
        state = root / "user-state.json"
        receipts = []
        for phase, archive, version in (
            ("published-rc", old_wheel, RC),
            ("stable-candidate", stable_wheel, FINAL),
            ("return-to-rc", old_wheel, RC),
        ):
            invoke(root, python, "-m", "pip", "install", "--force-reinstall", "--no-cache-dir", archive)
            invoke(root, python, "-m", "pip", "check")
            assert invoke(root, cli, "--version").strip() == "sedrava " + version
            assert invoke(root, python, "-I", "-c", "import importlib.metadata;print(importlib.metadata.version('sedrava'))").strip() == version
            installed = environment / "share/sedrava/examples/text_profile.sdr"
            if phase == "published-rc":
                project.write_bytes(installed.read_bytes())
            else:
                assert project.read_bytes() == installed.read_bytes()
            invoke(root, cli, "check", project)
            invoke(root, cli, "test", project)
            actions = ["rename"] if phase == "published-rc" else []
            observed = json.loads(invoke(root, cli, "run", project, *actions, "--state-file", state))
            assert observed["name"] == "Алиса 😀"
            invoke(root, cli, "build", "web", project, "--output", root / (phase + ".html"))
            invoke(root, cli, "build", "android", project, "--output", root / (phase + "-android"))
            site = environment / "share/sedrava/examples/platform_site.sdr"
            invoke(root, cli, "check", site)
            invoke(root, cli, "build", "site", site, "--output", root / (phase + "-site"))
            receipts.append({"phase": phase, "version": version,
                             "state_sha256": digest(state.read_bytes()),
                             "source_sha256": digest(project.read_bytes())})
        assert len({r["state_sha256"] for r in receipts}) == 1
        assert len({r["source_sha256"] for r in receipts}) == 1
        print(json.dumps({"result": "PASS", "phases": receipts,
                          "limitation": "CLI + installed packages; not an Android RC-to-stable update"},
                         ensure_ascii=False, indent=2))

if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/check_rc_to_stable_011.py dist")
    main(Path(sys.argv[1]))
