#!/usr/bin/env python3
"""A10 HTTP verification: many keys one SedravaSQL WAL snapshot.

Only test-owned SQLite in mode 0700 TemporaryDirectory and two loopback
Sedrava Server processes. A9 batch writes happen while a different
process serves A10 coherent multi-key reads.
"""
from __future__ import annotations
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import time

from verify_native_server_a3 import assert_reply,req
from verify_native_server_sqlite_a6 import launch,kill

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"examples/native_server/sqlite_a10_snapshot.sdr"
CLI=Path(os.environ["SEDRAVASQL_CLI"])
N=80

def payload(n):
    value=f"запись-{n:04d}"
    return {"left":value,"right":value,"left_rev":n-1,"right_rev":n-1}

def send(port,n):
    code,data,headers=req(port,method="PUT",path="/update",payload=payload(n),
                          key=f"a10-atomic-update-{n:06d}",rev=n-1)
    expected={"left":payload(n)["left"],"right":payload(n)["right"],"counter":n}
    assert (code,data)==(200,expected),(n,code,data,headers)
    assert headers.get("x-sedrava-revision")==str(n)
    assert headers.get("x-sedrava-batch-kv-revisions")==f"{n},{n}"

def check_pair(port):
    code,data,_=req(port,path="/pair")
    assert code==200,(code,data)
    assert sorted(data)==["left","left_revision","right","right_revision"]
    left,right=data["left_revision"],data["right_revision"]
    assert left==right,(data,"mixed committed generations")
    assert data["left"]==data["right"]==f"запись-{left:04d}",data
    return left

def main():
    assert CLI.is_file()
    with tempfile.TemporaryDirectory(prefix="sedrava-a10-coherent-get-") as temp:
        root=Path(temp)
        root.chmod(0o700)
        db=root/"a10.sqlite"
        writer,writer_port=launch(db,count=N+10,source=SOURCE)
        reader=None
        try:
            assert_reply(writer_port,404,{"error":{"code":"DB_KEY_NOT_FOUND"}},path="/pair")
            send(writer_port,1)
            reader,reader_port=launch(db,count=320,source=SOURCE)
            assert check_pair(reader_port)==1
            failures=[]
            started=threading.Event()
            def write_rest():
                started.set()
                try:
                    for n in range(2,N+2):
                        send(writer_port,n)
                        if n%7==0:time.sleep(0.004)
                except BaseException as exc:
                    failures.append(exc)
            thread=threading.Thread(target=write_rest,daemon=True)
            thread.start()
            assert started.wait(timeout=5)
            seen={1}
            for i in range(240):
                seen.add(check_pair(reader_port))
                if i%10==0:time.sleep(0.002)
            thread.join(timeout=35)
            assert not thread.is_alive(),"writer did not terminate"
            assert not failures,failures
            assert check_pair(reader_port)==N+1
            seen.add(N+1)
            assert len(seen)>=2
            print(f"PASS A10: 242 coherent HTTP GET /pair responses across {N+1} atomic writer generations")
            print(f"PASS A10: separate Sedrava reader/writer processes, observed {len(seen)} versions")
            # The reader's in-memory server counter remains from startup.
            # Do not claim it is from the DB snapshot; only public KV keys are.
            assert_reply(reader_port,200,{"counter":1},path="/counter")
            assert_reply(writer_port,200,{"counter":N+1},path="/counter")
        finally:
            if reader is not None:kill(reader)
            kill(writer)
        with sqlite3.connect(db) as con:
            assert con.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
            assert con.execute("SELECT count(*) FROM managed_batch_receipts").fetchone()[0]==N+1
            assert con.execute("SELECT count(*) FROM audit").fetchone()[0]==3*(N+1)
            assert con.execute("SELECT count(*) FROM receipts").fetchone()[0]==3*(N+1)
        print("PASS A10: persisted B6 audit/receipts count matches all atomic writes")
        # A deleted key must fail the entire HTTP response, not leak partial data.
        import json,subprocess
        proc=subprocess.run([str(CLI),"delete",str(db),"public_notes","right",
            "--expect",str(N+1),"--request-key","a10-right-delete-0001","--confirm"],
            capture_output=True,text=True,timeout=15)
        assert proc.returncode==0,(proc.stdout,proc.stderr)
        reader,port=launch(db,count=1,source=SOURCE)
        try:
            assert_reply(port,404,{"error":{"code":"DB_KEY_NOT_FOUND"}},path="/pair")
        finally:kill(reader)
        print("PASS A10: tombstone on any key fails entire paired GET (404)")
        # A rogue externally modified oversized revision must fail closed.
        oversized=root/"oversized.sqlite"
        def cli(*args):
            p=subprocess.run([str(CLI),*map(str,args)],capture_output=True,
                             text=True,timeout=15)
            assert p.returncode==0,(args,p.stderr,p.stdout)
        cli("init",oversized)
        for name in ("left","right"):
            cli("put",oversized,"public_notes",name,"запись-0001",
                "--expect","0","--request-key",f"a10-overflow-{name}-00001")
        with sqlite3.connect(oversized) as con:
            con.execute("UPDATE records SET revision=? WHERE namespace=? AND key=?",
                        (2**31,"public_notes","left"))
        reader,port=launch(oversized,count=1,source=SOURCE)
        try:
            assert_reply(port,503,{"error":{"code":"DB_REVISION_RANGE"}},path="/pair")
        finally:kill(reader)
        print("PASS A10: unrepresentable revision fails closed (503)")
        print("LIMIT: only values within a single GET, NOT in-memory server state or different requests")

if __name__=="__main__":
    main()
