"""A40 browser test: lazy authenticated reads on a fresh format 2 project."""
import hashlib,json,os,secrets,selectors,shutil,subprocess,tempfile
from pathlib import Path
from verify_sales_web_a22 import BIN,ROOT
with tempfile.TemporaryDirectory(prefix="sedrava-a40-") as t:
    root=Path(t);src=root/"project";src.mkdir();data=root/"data";data.mkdir(mode=0o700)
    auth=root/"auth.json";tokens={n:secrets.token_hex(32) for n in ("reader","writer")}
    auth.write_text(json.dumps([{"id":n,"sha256":hashlib.sha256(v.encode()).hexdigest(),"role":"read" if n=="reader" else "write"} for n,v in tokens.items()]));auth.chmod(0o600)
    for f in ("domain.sdr","sedrava-project.json"):
        shutil.copy2(ROOT/"examples/service_complete"/f,src/f)
    def run(*args):
        p=subprocess.run([str(BIN),*map(str,args)],cwd=src,capture_output=True,text=True,check=True,timeout=30);return p.stdout
    run("test")
    run("migrate","--data",data,"--trusted","--apply")
    p=subprocess.Popen([str(BIN),"serve","--data",str(data),"--trusted","--auth-file",str(auth),"--allow-write","--port","0","--max-requests","200"],cwd=src,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        with selectors.DefaultSelector() as sel:
            sel.register(p.stdout,selectors.EVENT_READ);assert sel.select(15)
            line=p.stdout.readline().strip()
        assert line.startswith("LISTENING http://127.0.0.1:"),line
        subprocess.run(["node",str(ROOT/"scripts/verify_initial_reads_a40.cjs")],env={**os.environ,"A40_URL":line.split(" ",1)[1],"A40_WRITER":tokens["writer"],"A40_READER":tokens["reader"]},check=True,timeout=150)
    finally:
        p.terminate();p.wait(timeout=8)
