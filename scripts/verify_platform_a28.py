#!/usr/bin/env python3
"""A28 offline installation, tamper rejection and actual installed CLI acceptance."""
import hashlib,io,os,shutil,subprocess,sys,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    archive=Path(sys.argv[1]).resolve()
    expected=sha(archive)
    with tempfile.TemporaryDirectory(prefix="a28-install-") as t:
        tmp=Path(t);tools=tmp/"tools";tools.mkdir()
        for n in ("sha256sum","cut","dirname","mktemp","rm","cp","mkdir","cat","tar","gzip","cmp","awk","chmod","mv"):
            p=shutil.which(n);assert p,n;(tools/n).symlink_to(p)
        env={"PATH":str(tools),"HOME":str(tmp),"LC_ALL":"C"}
        prefix=tmp/"prefix"
        def install(a=archive,h=expected,p=prefix,ok=True):
            result=subprocess.run(["/bin/sh",str(ROOT/"scripts/install_platform_a28.sh"),str(a),h,str(p)],env=env,capture_output=True,text=True,timeout=90)
            assert (result.returncode==0)==ok,(result.returncode,result.stdout,result.stderr)
        install()
        assert (prefix/"SERVER_SESSIONS_A23D.ru.md").is_file()
        lang=prefix/"bin/sedrava";sql=prefix/"bin/sedravasql-native-preview"
        hashes=[sha(lang),sha(sql)]
        install(ok=False);assert [sha(lang),sha(sql)]==hashes
        bad=tmp/"bad"
        install(h="0"*64,p=bad,ok=False);assert not bad.exists()
        bad.symlink_to(prefix,target_is_directory=True)
        install(p=bad,ok=False);assert bad.is_symlink();bad.unlink()
        for variant in ("extra","symlink","bad-sum"):
            modified=tmp/(variant+".tar.gz")
            with tarfile.open(archive,"r:gz") as src,tarfile.open(modified,"w:gz") as dst:
                for m in src:
                    data=src.extractfile(m).read()
                    if variant=="symlink" and m.name.endswith("/bin/sedrava"):
                        m.type=tarfile.SYMTYPE;m.linkname="/etc/passwd";m.size=0;dst.addfile(m);continue
                    if variant=="bad-sum" and m.name.endswith("/README.txt"):
                        data+=b"changed";m.size=len(data)
                    dst.addfile(m,io.BytesIO(data))
                if variant=="extra":
                    m=tarfile.TarInfo("sedrava-platform/unexpected");m.size=1;dst.addfile(m,io.BytesIO(b"x"))
            install(a=modified,h=sha(modified),p=bad,ok=False);assert not bad.exists()
        def call(args,cwd=tmp):
            return subprocess.run([str(x) for x in args],env=env,cwd=cwd,check=True,capture_output=True,text=True,timeout=30).stdout
        print(call([lang,"--version"]).strip())
        print(call([lang,"new","offline-demo"]).strip())
        project=tmp/"offline-demo"
        print(call([lang,"test"],project).strip())
        print(call([lang,"build"],project).strip())
        print(call([lang,"package","--output",tmp/"package"],project).strip())
        print(call([lang,"project","verify-package",tmp/"package"]).strip())
        data=tmp/"data";data.mkdir(mode=0o700)
        print(call([lang,"migrate","--data",data,"--trusted","--apply"],project).strip())
        print(call([sql,"verify",data/"app.log"]).strip())
        print("PASS A28 offline install, 6 negative cases, two installed binaries, new/test/build/package/migrate/verify without Python or Rust on PATH")
        # Independent full test harness uses Python outside the restricted runtime PATH.
        full={**os.environ,"SEDRAVA_NATIVE_BIN":str(lang),"SEDRAVASQL_NATIVE_BIN":str(sql)}
        subprocess.run([sys.executable,"-B",str(ROOT/"scripts/verify_project_a25.py")],env=full,check=True,timeout=150)
        subprocess.run([sys.executable,"-B",str(ROOT/"scripts/verify_migrations_a24.py")],env=full,check=True,timeout=150)
if __name__=="__main__":main()
