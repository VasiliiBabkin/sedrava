#!/usr/bin/env python3
"""Local real-socket acceptance for experimental Server A3 transaction protocol.

No external ports, external network, long-running daemon or runtime Python.
All state directories are temporary, discarded on exit.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import selectors
import socket
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/"rust/target/debug/sedrava"
EXAMPLE=ROOT/"examples/native_server/transactions_a3.sdr"
SCHEMA="sedrava.server.transaction.v1"

def call(*args, ok=True, timeout=12):
    result=subprocess.run([str(x) for x in args],cwd=ROOT,text=True,
                          capture_output=True,timeout=timeout,check=False)
    assert (result.returncode==0)==ok,(args,result.returncode,
                                        result.stdout[-350:],result.stderr[-650:])
    return result

def launch(state_dir, transactional=True, source=EXAMPLE, max_requests=80):
    args=[str(BIN),"server","run",str(source),"--port","0",
          "--max-requests",str(max_requests),"--idle-ms","20000",
          "--state-dir",str(state_dir)]
    if transactional:args.append("--transactional")
    proc=subprocess.Popen(args,cwd=ROOT,stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,bufsize=1,env={"PATH":"/nonexistent","LC_ALL":"C"})
    watcher=selectors.DefaultSelector()
    watcher.register(proc.stdout,selectors.EVENT_READ)
    if not watcher.select(12):
        proc.kill()
        raise AssertionError("No server startup")
    ready=proc.stdout.readline().strip()
    m=re.fullmatch(r"LISTENING http://127\.0\.0\.1:(\d{1,5})",ready)
    if not m:
        proc.kill()
        err=proc.communicate(timeout=3)[1]
        raise AssertionError((ready,err[-350:]))
    return proc,int(m.group(1))

def req(port, method="GET",path="/summary",payload=None,key=None,rev=None,
        ct="application/json", extra_headers=()):
    if payload is None:body=b""
    elif isinstance(payload,str):body=payload.encode("utf8")
    else:body=json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode("utf8")
    headers=[("Host",f"127.0.0.1:{port}"),("Content-Length",str(len(body)))]
    if payload is not None:headers.append(("Content-Type",ct))
    if key is not None:headers.append(("Idempotency-Key",key))
    if rev is not None:headers.append(("X-Sedrava-If-Revision",str(rev)))
    headers.extend(extra_headers)
    source=f"{method} {path} HTTP/1.1\r\n"+ "".join(f"{k}: {v}\r\n" for k,v in headers)+"\r\n"
    with socket.create_connection(("127.0.0.1",port),timeout=3) as stream:
        stream.settimeout(5)
        stream.sendall(source.encode("ascii")+body)
        stream.shutdown(socket.SHUT_WR)
        output=bytearray()
        while True:
            segment=stream.recv(4096)
            if not segment:break
            output.extend(segment)
    header,sep,body=bytes(output).partition(b"\r\n\r\n")
    assert sep, output[:240]
    lines=header.decode("ascii").split("\r\n")
    status=int(lines[0].split(" ")[1])
    h={}
    for line in lines[1:]:
        k,v=line.split(":",1)
        assert k.lower() not in h,(status,k)
        h[k.lower()]=v.strip()
    assert h["connection"]=="close"
    assert int(h["content-length"])==len(body)
    return status,json.loads(body),h

def assert_reply(port,status,body,**kwargs):
    actual=req(port,**kwargs)
    assert actual[0]==status and actual[1]==body,(kwargs,actual,status,body)
    return actual[2]

def stop(proc):
    if proc.poll() is None:
        proc.kill()
    proc.communicate(timeout=4)

def completed(proc,requests):
    out,err=proc.communicate(timeout=6)
    assert proc.returncode==0,(out,err)
    assert f"STOPPED requests={requests}" in out,(out,requests)

INITIAL={"count":0,"total":0,"label":"open"}
def initial(p):
    h=assert_reply(p,200,INITIAL)
    assert h["x-sedrava-revision"]=="0"

def positive(directory):
    proc,port=launch(directory,max_requests=17)
    try:
        initial(port)
        h=assert_reply(port,428,{"error":{"code":"IDEMPOTENCY_KEY_REQUIRED"}},
                       method="POST",path="/record",payload={"amount":2})
        assert h["x-sedrava-revision"]=="0"
        assert_reply(port,400,{"error":{"code":"INVALID_IDEMPOTENCY_KEY"}},
                     method="POST",path="/record",payload={"amount":2},key="x")
        assert_reply(port,400,{"error":{"code":"INVALID_REVISION_CONDITION"}},
                     method="POST",path="/record",payload={"amount":2},
                     key="request-key-0001",rev="00")
        h=assert_reply(port,201,{"count":1,"total":2,"accepted":True},
                       method="POST",path="/record",payload={"amount":2},
                       key="request-key-0001",rev=0)
        assert h["x-sedrava-revision"]=="1"
        h=assert_reply(port,201,{"count":1,"total":2,"accepted":True},
                       method="POST",path="/record",payload={"amount":2},
                       key="request-key-0001",rev=0)
        assert h["x-sedrava-replayed"]=="true"
        assert h["x-sedrava-revision"]=="1"
        h=assert_reply(port,200,{"count":1,"total":2,"label":"open"})
        assert h["x-sedrava-revision"]=="1"
        assert_reply(port,409,{"error":{"code":"IDEMPOTENCY_CONFLICT"}},
                     method="POST",path="/record",payload={"amount":3},
                     key="request-key-0001",rev=0)
        assert_reply(port,412,{"error":{"code":"REVISION_CONFLICT"}},
                     method="POST",path="/record",payload={"amount":1},
                     key="request-key-0002",rev=0)
        assert_reply(port,422,{"error":{"code":"GUARD_REJECTED"}},
                     method="POST",path="/record",payload={"amount":200},
                     key="request-key-0002",rev=1)
        h=assert_reply(port,201,{"count":2,"total":5,"accepted":True},
                       method="POST",path="/record",payload={"amount":3},
                       key="request-key-0002",rev=1)
        assert h["x-sedrava-revision"]=="2"
        h=assert_reply(port,201,{"count":1,"total":2,"accepted":True},
                       method="POST",path="/record",payload={"amount":2},
                       key="request-key-0001",rev=0)
        assert h["x-sedrava-revision"]=="1" and h["x-sedrava-replayed"]=="true"
        h=assert_reply(port,200,{"label":"изменено"},
                       method="PUT",path="/label",payload={"name":"изменено"},
                       key="request-key-0003",rev=2)
        assert h["x-sedrava-revision"]=="3"
        h=assert_reply(port,200,{"count":2,"total":5,"label":"изменено"})
        assert h["x-sedrava-revision"]=="3"
        assert_reply(port,400,{"error":{"code":"READ_CANNOT_USE_TRANSACTION_HEADERS"}},
                     key="request-key-0004")
        assert_reply(port,400,{"error":{"code":"INVALID_OR_DUPLICATE_HEADER"}},
                     method="POST",path="/record",payload={"amount":1},
                     key="request-key-0004",extra_headers=(("idempotency-key","request-key-0005"),))
        assert_reply(port,404,{"error":{"code":"NOT_FOUND"}},path="/unknown")
        completed(proc,17)
    finally:
        stop(proc)
    file=directory/"sedrava-state-v1.json"
    snapshot=json.loads(file.read_text())
    assert snapshot["schema"]==SCHEMA,snapshot
    assert snapshot["revision"]==3
    assert snapshot["state"]=={"count":2,"total":5,"label":"изменено"}
    assert [x["revision"] for x in snapshot["receipts"]]==[1,2,3]
    assert len({x["key"] for x in snapshot["receipts"]})==3
    assert not (directory/".sedrava-server.lock").exists()
    assert file.stat().st_mode & 0o077 == 0
    return snapshot

def restart(directory):
    proc,port=launch(directory,max_requests=3)
    try:
        h=assert_reply(port,200,{"count":2,"total":5,"label":"изменено"})
        assert h["x-sedrava-revision"]=="3"
        h=assert_reply(port,201,{"count":1,"total":2,"accepted":True},
                       method="POST",path="/record",payload={"amount":2},
                       key="request-key-0001",rev=0)
        assert h["x-sedrava-replayed"]=="true" and h["x-sedrava-revision"]=="1"
        h=assert_reply(port,200,{"count":2,"total":5,"label":"изменено"})
        assert h["x-sedrava-revision"]=="3"
        completed(proc,3)
    finally:
        stop(proc)

def negative(directory,snapshot):
    file=directory/"sedrava-state-v1.json"
    original=file.read_bytes()
    corruptions=[
        '{"schema":"wrong"}',
        '{"schema":"wrong","schema":"other"}',
        json.dumps(dict(snapshot,revision=4)),
        json.dumps(dict(snapshot,receipts=[])),
        json.dumps(dict(snapshot,revision=1)),
        json.dumps(dict(snapshot,unknown=True)),
        json.dumps(dict(snapshot,state={"count":2,"total":5,"label":"ok","unknown":1})),
        json.dumps(dict(snapshot,receipts=[dict(snapshot["receipts"][0],key="bad key")])),
        json.dumps(dict(snapshot,receipts=[dict(snapshot["receipts"][0],fingerprint="A"*64)])),
        json.dumps(dict(snapshot,receipts=[dict(snapshot["receipts"][0],status=999)])),
        json.dumps(dict(snapshot,receipts=[dict(snapshot["receipts"][0],response={"a":[1]})])),
    ]
    for data in corruptions:
        file.write_text(data)
        call(BIN,"server","run",EXAMPLE,"--transactional","--state-dir",directory,
             "--port","0","--idle-ms","500",ok=False)
        assert not (directory/".sedrava-server.lock").exists()
    file.write_bytes(original)
    assert file.read_bytes()==original
    # The same directory cannot be silently opened with legacy A2 mode.
    call(BIN,"server","run",EXAMPLE,"--state-dir",directory,
         "--port","0","--idle-ms","500",ok=False)
    assert file.read_bytes()==original

def legacy_refusal(tmp):
    a2=tmp/"legacy"
    a2.mkdir(mode=0o700)
    # Use the same A3 example but deliberately start without txn mode.
    proc,port=launch(a2,transactional=False,max_requests=2)
    try:
        assert_reply(port,200,INITIAL)
        assert_reply(port,201,{"count":1,"total":2,"accepted":True},
                     method="POST",path="/record",payload={"amount":2})
        completed(proc,2)
    finally:
        stop(proc)
    state=a2/"sedrava-state-v1.json"
    assert json.loads(state.read_text())["schema"]=="sedrava.server.state.v1"
    call(BIN,"server","run",EXAMPLE,"--transactional","--state-dir",a2,
         "--port","0","--idle-ms","500",ok=False)
    assert json.loads(state.read_text())["schema"]=="sedrava.server.state.v1"
    call(BIN,"server","run",EXAMPLE,"--transactional","--port","0",
         "--idle-ms","500",ok=False)

def ledger_full(tmp):
    store=tmp/"full"
    store.mkdir(mode=0o700)
    proc,port=launch(store,max_requests=34)
    try:
        for i in range(32):
            key=f"capacity-request-{i:04}"
            h=assert_reply(port,201,{"count":i+1,"total":i+1,"accepted":True},
                           method="POST",path="/record",payload={"amount":1},
                           key=key,rev=i)
            assert h["x-sedrava-revision"]==str(i+1)
        assert_reply(port,507,{"error":{"code":"TRANSACTION_LEDGER_FULL"}},
                     method="POST",path="/record",payload={"amount":1},
                     key="capacity-request-0032",rev=32)
        h=assert_reply(port,201,{"count":1,"total":1,"accepted":True},
                       method="POST",path="/record",payload={"amount":1},
                       key="capacity-request-0000",rev=0)
        assert h["x-sedrava-replayed"]=="true"
        completed(proc,34)
    finally:
        stop(proc)
    assert json.loads((store/"sedrava-state-v1.json").read_text())["revision"]==32

def failed_commit_retry(tmp):
    directory=tmp/"failed-commit"
    directory.mkdir(mode=0o700)
    proc,port=launch(directory,max_requests=5)
    try:
        h=assert_reply(port,201,{"count":1,"total":2,"accepted":True},
                       method="POST",path="/record",payload={"amount":2},
                       key="write-failure-0001",rev=0)
        assert h["x-sedrava-revision"]=="1"
        directory.chmod(0o500)
        h=assert_reply(port,503,{"error":{"code":"STATE_WRITE_FAILED"}},
                       method="POST",path="/record",payload={"amount":3},
                       key="write-failure-0002",rev=1)
        assert h["x-sedrava-revision"]=="1"
        assert_reply(port,200,{"count":1,"total":2,"label":"open"})
        directory.chmod(0o700)
        h=assert_reply(port,201,{"count":2,"total":5,"accepted":True},
                       method="POST",path="/record",payload={"amount":3},
                       key="write-failure-0002",rev=1)
        assert h["x-sedrava-revision"]=="2"
        assert_reply(port,200,{"count":2,"total":5,"label":"open"})
        completed(proc,5)
    finally:
        directory.chmod(0o700)
        stop(proc)
    saved=json.loads((directory/"sedrava-state-v1.json").read_text())
    assert saved["revision"]==2 and len(saved["receipts"])==2
    assert saved["state"]["total"]==5


def crash_lock_recovery(tmp):
    directory=tmp/"crashed"
    directory.mkdir(mode=0o700)
    proc,port=launch(directory,max_requests=10)
    try:
        h=assert_reply(port,201,{"count":1,"total":3,"accepted":True},
                       method="POST",path="/record",payload={"amount":3},
                       key="crash-replay-0001",rev=0)
        assert h["x-sedrava-revision"]=="1"
    finally:
        stop(proc)  # Abrupt kill; intentionally leaves stale single-writer lock.
    lock=directory/".sedrava-server.lock"
    assert lock.is_file()
    call(BIN,"server","run",EXAMPLE,"--transactional",
         "--state-dir",directory,"--port","0","--idle-ms","500",ok=False)
    assert lock.is_file()
    # The test has already reaped its own killed child. Manual unlink is
    # performed ONLY inside this test-owned temporary directory.
    lock.unlink()
    proc,port=launch(directory,max_requests=2)
    try:
        h=assert_reply(port,201,{"count":1,"total":3,"accepted":True},
                       method="POST",path="/record",payload={"amount":3},
                       key="crash-replay-0001",rev=0)
        assert h["x-sedrava-replayed"]=="true" and h["x-sedrava-revision"]=="1"
        assert_reply(port,200,{"count":1,"total":3,"label":"open"})
        completed(proc,2)
    finally:
        stop(proc)
    assert not lock.exists()


def main():
    assert BIN.is_file()
    call(BIN,"server","check",EXAMPLE)
    with tempfile.TemporaryDirectory(prefix="sedrava-a3-") as td:
        tmp=Path(td)
        store=tmp/"transactional"
        store.mkdir(mode=0o700)
        snapshot=positive(store)
        restart(store)
        negative(store,snapshot)
        legacy_refusal(tmp)
        ledger_full(tmp)
        failed_commit_retry(tmp)
        crash_lock_recovery(tmp)
    print("PASS: real HTTP 201 replay with exact response+original revision; state unchanged")
    print("PASS: conflict on reused key with different request, stale CAS 412, 428 missing key")
    print("PASS: receipt and multiple state fields committed atomically; strict restart persistence")
    print("PASS: 11 malformed/forged transactional snapshots reject without HTTP bind")
    print("PASS: failed disk write 503 preserves revision; same key succeeds after permission recovery")
    print("PASS: killed server leaves stale lock; explicit test-only recovery restores replay ledger")
    print("PASS: no silent A2-to-A3 format migration or downgrade")
    print("PASS: 32 non-evicting transactions; next write 507, earlier replay still works")
    print("PASS: native server subprocess PATH=/nonexistent, loopback-only, auto-stop")

if __name__=="__main__":
    main()
