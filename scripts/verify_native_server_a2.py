#!/usr/bin/env python3
"""Native A2 live HTTP, atomic handlers, private persistence, restart & fail closed.

No production ports, services, external network, Python interpreter in Rust
runtime, or GitHub Actions. All server data directories are temporary.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import selectors
import shutil
import socket
import subprocess
import tempfile
import time
from verify_native_server import request

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/"rust/target/debug/sedrava-native"
SAMPLE=ROOT/"examples/native_server/counter_a2.sdr"

def run(*args, ok=True, timeout=15):
    p=subprocess.run([str(a) for a in args],text=True,capture_output=True,
        timeout=timeout,check=False,cwd=ROOT)
    assert (p.returncode==0)==ok,(args,p.returncode,p.stdout,p.stderr[-1000:])
    return p

def spawn(sample=SAMPLE, state_dir=None, max_requests=30, idle_ms=20000):
    cmd=[str(NATIVE),"server","run",str(sample),"--port","0",
         "--max-requests",str(max_requests),"--idle-ms",str(idle_ms)]
    if state_dir is not None:
        cmd+=["--state-dir",str(state_dir)]
    p=subprocess.Popen(cmd,stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
        bufsize=1,cwd=ROOT,env={"PATH":"/nonexistent","LC_ALL":"C"})
    watcher=selectors.DefaultSelector()
    watcher.register(p.stdout,selectors.EVENT_READ)
    if not watcher.select(timeout=10):
        p.kill()
        p.communicate(timeout=3)
        raise AssertionError("No loopback readiness signal")
    header=p.stdout.readline().strip()
    m=re.fullmatch(r"LISTENING http://127\.0\.0\.1:(\d{1,5})",header)
    if not m:
        p.kill()
        _,err=p.communicate(timeout=3)
        raise AssertionError(f"Failed to bind: {header} {err[-400:]}")
    return p,int(m.group(1))

def expect(port, code, result, method="GET", path="/counter",data=None):
    options={}
    if data is not None:
        options["body"]=json.dumps(data,ensure_ascii=False)
        options["headers"]=(("Content-Type","application/json"),)
    actual=request(port,method=method,path=path,**options)
    assert actual==(code,result),(method,path,code,result,actual)

INITIAL={"count":0,"label":"new","enabled":False}
def initial(port):
    expect(port,200,INITIAL)

def mutate(port):
    expect(port,200,{"count":2,"accepted":True},"POST","/increment",{"delta":2})
    expect(port,422,{"error":{"code":"GUARD_REJECTED"}},
           "POST","/increment",{"delta":0})
    expect(port,422,{"error":{"code":"GUARD_REJECTED"}},
           "POST","/increment",{"delta":4})
    expect(port,422,{"error":{"code":"INTEGER_OVERFLOW"}},
           "POST","/increment",{"delta":2147483647})
    expect(port,422,{"error":{"code":"REQUEST_SCHEMA_MISMATCH"}},
           "POST","/increment",{"delta":"2"})
    expect(port,422,{"error":{"code":"GUARD_REJECTED"}},
           "POST","/label",{"label":""})
    expect(port,200,{"label":"Привет, мир + 2"},
           "POST","/label",{"label":"Привет, мир + 2"})
    expect(port,200,{"enabled":True},"PUT","/enabled",{"enabled":True})
    expect(port,200,{"count":2,"label":"Привет, мир + 2","enabled":True})
    return {"count":2,"label":"Привет, мир + 2","enabled":True}

def finish(proc,timeout=8):
    out,err=proc.communicate(timeout=timeout)
    assert proc.returncode==0,(proc.returncode,out,err)
    assert "STOPPED requests=" in out,(out,err)

def stop(proc):
    if proc.poll() is None:
        proc.kill()
    proc.communicate(timeout=4)

def negative_dsl(tmp):
    invalid=[
        'server "C"\nstate count: int = "wrong"\nroute GET "/":\n    respond 200 {a: state.count}\n',
        'server "C"\nstate count: int = 0\nstate count: int = 1\nroute GET "/":\n    respond 200 {a: state.count}\n',
        'server "C"\nroute GET "/":\n    respond 200 {a: 1}\nstate n: int = 0\n',
        'server "C"\nstate n: int = 0\nroute GET "/":\n    set n = 1\n    respond 200 {a: state.n}\n',
        'server "C"\nstate n: int = 0\nroute POST "/":\n    set n = "bad"\n    respond 200 {a: state.n}\n',
        'server "C"\nstate n: int = 0\nroute POST "/":\n    set wrong = 1\n    respond 200 {a: state.n}\n',
        'server "C"\nstate n: int = 0\nroute POST "/":\n    set n = state.n + "invalid"\n    respond 200 {a: state.n}\n',
        'server "C"\nstate n: int = 0\nroute POST "/":\n    set n = state.n + state.n + 1\n    respond 200 {a: state.n}\n',
        'server "C"\nstate n: int = 0\nroute POST "/":\n    require state.n > "a"\n    respond 200 {a: state.n}\n',
        'server "C"\nstate n: int = 0\nroute POST "/":\n    respond 200 {a: state.n}\n    set n = 1\n',
        'server "C"\nstate n: int = 0\nroute POST "/":\n    respond 200 {a: state.missing}\n',
        'server "C"\nstate n: float = 0\nroute POST "/":\n    respond 200 {a: 1}\n',
        'server "C"\nstate n: int = 2147483648\nroute POST "/":\n    respond 200 {a: 1}\n',
        'server "C"\nstate n: int = 0\nroute POST "/":\n    require state.n == true\n    respond 200 {a: 1}\n',
        'server "C"\nstate n: int = 0\nroute POST "/":\n    set n = state.n + nonexistent\n    respond 200 {a: state.n}\n',
        'server "C"\nstate n: int = 0\nroute POST "/":\n    set n = 0\n    require state.n >> 0\n    respond 200 {a: true}\n',
    ]
    file=tmp/"invalid.sdr"
    for source in invalid:
        file.write_text(source,encoding="utf8")
        run(NATIVE,"server","check",file,ok=False)
    return len(invalid)

def statefile(dir):
    return dir/"sedrava-state-v1.json"

def persistence(tmp):
    directory=tmp/"persistent"
    directory.mkdir(mode=0o700)
    p,port=spawn(state_dir=directory,max_requests=11)
    try:
        initial(port)
        target=mutate(port)
        # Original instance is still running, so a concurrent writer must
        # reject the existing lock rather than waiting or reusing the state.
        assert p.poll() is None
        run(NATIVE,"server","run",SAMPLE,"--port","0",
            "--idle-ms","500","--state-dir",directory,ok=False)
        expect(port,200,target)
        finish(p)
    finally:
        stop(p)
    assert not (directory/".sedrava-server.lock").exists()
    meta=statefile(directory).stat()
    assert meta.st_mode & 0o077==0
    stored=json.loads(statefile(directory).read_text())
    assert stored["schema"]=="sedrava.server.state.v1"
    assert len(stored["signature"])==64
    assert stored["state"]==target
    p,port=spawn(state_dir=directory,max_requests=2)
    try:
        expect(port,200,target)
        expect(port,200,target)
        finish(p)
    finally:
        stop(p)
    assert not (directory/".sedrava-server.lock").exists()

    # No write permissions after an accepted in-memory request: write must
    # fail, and the live state must still be the previous value.
    p,port=spawn(state_dir=directory,max_requests=3)
    try:
        directory.chmod(0o500)
        expect(port,503,{"error":{"code":"STATE_WRITE_FAILED"}},
            "POST","/increment",{"delta":1})
        expect(port,200,target)
        directory.chmod(0o700)
        expect(port,200,target)
        finish(p)
    finally:
        directory.chmod(0o700)
        stop(p)
    assert json.loads(statefile(directory).read_text())["state"]==target
    assert not (directory/".sedrava-server.lock").exists()

    corruptions=[
        '{"schema":1}',
        '{"schema":1,"schema":2}',
        '{"schema":"sedrava.server.state.v1","signature":"bad","state":{}}',
    ]
    original=statefile(directory).read_bytes()
    for data in corruptions:
        statefile(directory).write_text(data)
        run(NATIVE,"server","run",SAMPLE,"--port","0","--idle-ms","500",
            "--state-dir",directory,ok=False)
        assert not (directory/".sedrava-server.lock").exists()
    statefile(directory).write_bytes(original)
    snapshot=json.loads(original)
    snapshot["state"]["count"]=1.25
    statefile(directory).write_text(json.dumps(snapshot))
    run(NATIVE,"server","run",SAMPLE,"--port","0","--idle-ms","500",
        "--state-dir",directory,ok=False)
    statefile(directory).write_bytes(original)
    snapshot=json.loads(original)
    snapshot["state"]["secret"]="unexpected"
    statefile(directory).write_text(json.dumps(snapshot))
    run(NATIVE,"server","run",SAMPLE,"--port","0","--idle-ms","500",
        "--state-dir",directory,ok=False)
    statefile(directory).write_bytes(original)

    statefile(directory).chmod(0o644)
    run(NATIVE,"server","run",SAMPLE,"--port","0","--idle-ms","500",
        "--state-dir",directory,ok=False)
    statefile(directory).chmod(0o600)

    directory.chmod(0o755)
    run(NATIVE,"server","run",SAMPLE,"--port","0","--idle-ms","500",
        "--state-dir",directory,ok=False)
    directory.chmod(0o700)

    backup=directory/"safe-copy"
    statefile(directory).rename(backup)
    statefile(directory).symlink_to(backup)
    run(NATIVE,"server","run",SAMPLE,"--port","0","--idle-ms","500",
        "--state-dir",directory,ok=False)
    statefile(directory).unlink()
    os.link(backup,statefile(directory))
    run(NATIVE,"server","run",SAMPLE,"--port","0","--idle-ms","500",
        "--state-dir",directory,ok=False)
    statefile(directory).unlink()
    backup.rename(statefile(directory))
    assert statefile(directory).stat().st_nlink==1

    lock=directory/".sedrava-server.lock"
    lock.write_text("stale, manually inspect process before removal")
    run(NATIVE,"server","run",SAMPLE,"--port","0","--idle-ms","500",
        "--state-dir",directory,ok=False)
    lock.unlink()
    p,port=spawn(state_dir=directory,max_requests=1)
    try:
        expect(port,200,target)
        finish(p)
    finally:
        stop(p)
    return target

def main():
    run(NATIVE,"server","check",SAMPLE)
    with tempfile.TemporaryDirectory(prefix="sedrava-a2-") as td:
        tmp=Path(td)
        negative=negative_dsl(tmp)
        # Default state stays in process memory and is lost on restart.
        p,port=spawn(max_requests=10)
        try:
            initial(port)
            mutate(port)
            finish(p)
        finally:
            stop(p)
        p,port=spawn(max_requests=1)
        try:
            initial(port)
            finish(p)
        finally:
            stop(p)
        restored=persistence(tmp)
        print(f"PASS: {negative} invalid A2 handler/state programs rejected at compile-time")
        print("PASS: in-memory typed set/require, overflow and late guard atomic rollback")
        print("PASS: strict state schema, durable private JSON reload across real restarts")
        print("PASS: concurrent start lock, stale lock, invalid JSON/schema/type, extra keys")
        print("PASS: symlink/hardlink/world-readable file and public directory rejected")
        print("PASS: state-write failure returns 503 and does not publish candidate")
        print("PASS: server runtime PATH=/nonexistent, no Python or Rust dependency")
        print("RESTORED_STATE="+json.dumps(restored,ensure_ascii=False,sort_keys=True))

if __name__=="__main__":
    main()
