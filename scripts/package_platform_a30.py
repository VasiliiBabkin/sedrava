#!/usr/bin/env python3
"""A30 versioned candidate packager. Maintainer-side only, no publishing."""
import argparse,gzip,hashlib,io,json,os,platform,re,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
SQL_SHA="b36a628c95598a3e8e04b40ebf9c86cdc20e0604"
NAMES=("sedrava","sedravasql-native-preview","sedravasql")
def sha(data):return hashlib.sha256(data).hexdigest()
def git(root,*args):
    return subprocess.check_output(["git","-C",str(root),*args],text=True).strip()
def main():
    p=argparse.ArgumentParser()
    for flag in ("lang-source","sql-source","lang-bin","sql-bin","managed-bin","output"):
        p.add_argument("--"+flag,type=Path,required=True)
    p.add_argument("--lang-sha",required=True)
    a=p.parse_args()
    lang_sha=a.lang_sha
    if not re.fullmatch(r"[0-9a-f]{40}",lang_sha):raise ValueError("Exact language SHA required")
    for source,expected in [(a.lang_source,lang_sha),(a.sql_source,SQL_SHA)]:
        if git(source,"rev-parse","HEAD")!=expected or git(source,"status","--porcelain"):
            raise ValueError("Expected clean, exact A30 source checkout")
    if platform.system()!="Linux" or platform.machine()!="x86_64":
        raise ValueError("Only Linux x86-64 qualified")
    binaries={}
    for name,path in zip(NAMES,[a.lang_bin,a.sql_bin,a.managed_bin]):
        if path.name!=name or not path.is_file() or path.is_symlink():
            raise ValueError("Wrong executable path")
        data=path.read_bytes()
        # ELF64, little endian, x86-64, executable or PIE.
        if len(data)<1000 or data[:6]!=b"\x7fELF\x02\x01" or data[18:20]!=b"\x3e\x00":
            raise ValueError("Wrong executable format")
        binaries[name]=data
    reply=subprocess.check_output([str(a.lang_bin.resolve()),"--version"],text=True,timeout=10).strip()
    if reply!="sedrava 0.12.0-alpha.3 (Rust alpha)":
        raise ValueError("Wrong language version")
    for path,expected in [(a.sql_bin,"sedravasql-native-preview 0.0.2 (NativeLog alpha)"),(a.managed_bin,"sedravasql 0.1.0-alpha.2 (managed SQLite alpha)")]:
        if subprocess.check_output([str(path.resolve()),"--version"],text=True,timeout=10).strip()!=expected:raise ValueError("Wrong SQL version")
    lock=(a.lang_source/"rust/Cargo.lock").read_text()
    if SQL_SHA not in lock:raise ValueError("SQL source mismatch")
    files={"bin/"+k:v for k,v in binaries.items()}
    files["LICENSE.sedrava"]=(a.lang_source/"LICENSE").read_bytes()
    files["LICENSE.sedravasql"]=(a.sql_source/"LICENSE").read_bytes()
    files["README.txt"]=(
        "Sedrava Platform A30 — experimental alpha candidate\n"
        "Linux x86-64 GNU; tested Ubuntu 24.04. No production data.\n"
        "sedrava: 0.12.0-alpha.3.\n"
        "sedravasql-native-preview: native-engine 0.0.2, limited SQL and A24 migrations.\n"
        "sedravasql: managed SQLite key/value alpha 0.1.0-alpha.2, separate database format.\n"
        "No Python/Rust needed for installed programs.\n"
        "Add this prefix/bin to PATH. Use sedrava new myapp, cd myapp, sedrava test, sedrava build.\n"
        "See PROJECT_CLI_A25.ru.md for private data/auth setup and migration/serve commands.\n"
        "NativeLog single writer; loopback-only server; no public deployment.\n"
        "Experimental alpha; not production-ready.\n"
    ).encode()
    files["PROJECT_CLI_A25.ru.md"]=(a.lang_source/"docs/PROJECT_CLI_A25.ru.md").read_bytes()
    files["SERVER_SESSIONS_A23D.ru.md"]=(a.lang_source/"docs/SERVER_SESSIONS_A23D.ru.md").read_bytes()
    files["NATIVE_MIGRATIONS_A24.ru.md"]=(a.sql_source/"docs/NATIVE_MIGRATIONS_A24.ru.md").read_bytes()
    files["RELEASE_NOTES_SEDRAVA.md"]=(a.lang_source/"docs/RELEASE_NOTES_0_12_0_ALPHA3.md").read_bytes()
    files["RELEASE_NOTES_SEDRAVASQL.md"]=(a.sql_source/"docs/RELEASE_NOTES_0_1_0_ALPHA2.md").read_bytes()
    manifest={"format":1,"distribution":"0.12.0-alpha.3-sql-0.1.0-alpha.2","target":"x86_64-unknown-linux-gnu",
        "channel":"experimental","sources":{"sedrava":lang_sha,"sedravasql":SQL_SHA},
        "versions":{"sedrava":"0.12.0-alpha.3","native-engine":"0.0.2","sedravasql":"0.1.0-alpha.2"},
        "compiler":subprocess.check_output(["rustc","-vV"],text=True).strip(),
        "binaries":{k:sha(v) for k,v in binaries.items()},
        "limitations":"Source and binary hashes are provenance records, not signatures."}
    files["manifest.json"]=(json.dumps(manifest,sort_keys=True,indent=2)+"\n").encode()
    files["SHA256SUMS.txt"]="".join(f"{sha(v)}  {k}\n" for k,v in sorted(files.items())).encode()
    a.output.mkdir(parents=True,exist_ok=True)
    out=a.output/"sedrava-platform-0.12.0-alpha.3-sql-0.1.0-alpha.2-linux-x86_64.tar.gz"
    with out.open("xb") as f:
        with gzip.GzipFile(fileobj=f,mode="wb",mtime=0,filename="") as gz:
            with tarfile.open(fileobj=gz,mode="w",format=tarfile.USTAR_FORMAT) as tar:
                for name,data in sorted(files.items()):
                    entry=tarfile.TarInfo("sedrava-platform/"+name)
                    entry.size=len(data);entry.mode=0o755 if name.startswith("bin/") else 0o644
                    entry.mtime=0;entry.uid=entry.gid=0
                    tar.addfile(entry,io.BytesIO(data))
    print(json.dumps({**manifest,"archive":str(out),"archive_sha256":sha(out.read_bytes()),"archive_bytes":out.stat().st_size},indent=2,sort_keys=True))
if __name__=="__main__":main()
