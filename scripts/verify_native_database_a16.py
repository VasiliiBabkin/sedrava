#!/usr/bin/env python3
"""Real .sdr SQL host programs; typed named arguments, explicit policy and native journal."""
import hashlib,json,os,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"])
DB=Path(os.environ["SEDRAVASQL_NATIVE_BIN"])
def call(args,fail=False):
    p=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=20)
    assert (p.returncode!=0)==fail,(args,p.stdout,p.stderr)
    return None if fail else p.stdout
def main():
    with tempfile.TemporaryDirectory(prefix="sedrava-a16-") as t:
        path=Path(t)/"journal";call([DB,"init",path]);sample=ROOT/"examples/database"
        def run(name,*args,fail=False,policy=True):
            cmd=[BIN,"database","run",sample/(name+".sdr"),"--database",path]
            if policy:cmd.append("--trusted")
            raw=call([*cmd,*args],fail=fail)
            return json.loads(raw) if raw else None
        def digest():return hashlib.sha256(path.read_bytes()).hexdigest()
        for p in (sample/name for name in ("create_orders.sdr","insert_order.sdr","select_order.sdr","mark_paid.sdr")):call([BIN,"database","check",p])
        before=digest()
        run("create_orders","--allow-write","--request-key","create-orders-001",fail=True,policy=False)
        run("create_orders",fail=True);assert digest()==before
        run("create_orders","--allow-write","--request-key","create-orders-001")
        note="x'); DELETE FROM Orders WHERE id='o1'; --"
        args=["--allow-write","--request-key","insert-orders-001","--arg",'id="o1"',"--arg","amount=42","--arg","note="+json.dumps(note)]
        first=run("insert_order",*args);assert first["affected"]==1
        query=run("select_order","--arg",'id="o1"');assert query["rows"]==[["o1",42,False,note]]
        before=digest()
        assert run("insert_order",*args)=={**first,"replayed":True}
        run("select_order","--arg","id=1",fail=True)
        run("select_order","--arg",'id="o1"',"--allow-write",fail=True)
        run("select_order","--arg",'id="o1"',"--arg",'id="o2"',fail=True)
        run("insert_order",*["amount=43" if a=="amount=42" else a for a in args],fail=True)
        assert digest()==before
        paid=run("mark_paid","--allow-write","--request-key","mark-paid-00001","--arg",'id="o1"')
        assert paid["affected"]==1
        assert run("select_order","--arg",'id="o1"')["rows"]==[["o1",42,True,note]]
        wrong=Path(t)/"wrong.sdr";wrong.write_text("database Wrong\n    query " + json.dumps("DELETE FROM Orders WHERE id='o1'") + "\n")
        call([BIN,"database","check",wrong],fail=True)
        call([DB,"verify",path])
        print("PASS A16: four real .sdr SQL host programs, native persisted CRUD, typed bindings, injection-as-data, explicit policy and durable replay")
if __name__=="__main__":main()
