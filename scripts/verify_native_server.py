#!/usr/bin/env python3
"""Native Rust Sedrava Server A1: real loopback HTTP acceptance.

No requests to production services, network interfaces or external hosts.
Expected to run against a local native binary built from this worktree.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import selectors
import socket
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
NATIVE=ROOT/"rust/target/debug/sedrava"
DSL=ROOT/"examples/native_server/hello.sdr"

def invoke(*args,ok=True):
    result=subprocess.run(
        [str(x) for x in args],cwd=ROOT,
        capture_output=True,text=True,timeout=15,check=False)
    assert (result.returncode==0)==ok,(args,result.returncode,result.stdout,result.stderr)
    return result

def startup(file=DSL,max_requests=32,idle_ms=15000):
    proc=subprocess.Popen(
        [str(NATIVE),"server","run",str(file),"--port","0",
         "--max-requests",str(max_requests),"--idle-ms",str(idle_ms)],
        cwd=ROOT,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,bufsize=1,
        env={"PATH":"/nonexistent","LC_ALL":"C"})
    selector=selectors.DefaultSelector()
    selector.register(proc.stdout,selectors.EVENT_READ)
    if not selector.select(timeout=15):
        proc.kill()
        raise AssertionError("Server never announced a loopback port")
    line=proc.stdout.readline().strip()
    match=re.fullmatch(r"LISTENING http://127\.0\.0\.1:(\d{1,5})",line)
    if not match:
        proc.kill()
        raise AssertionError(f"Wrong listen address or startup failure: {line!r}")
    port=int(match.group(1))
    assert 0<port<65536
    return proc,port

def request(port,method="GET",path="/health",body=b"",headers=(),version="HTTP/1.1",
            content_length=None,host=None):
    if isinstance(body,str):
        body=body.encode("utf8")
    if content_length is None:
        content_length=len(body)
    host=f"127.0.0.1:{port}" if host is None else host
    header=f"{method} {path} {version}\r\n"
    if host is not False:
        header+=f"Host: {host}\r\n"
    for key,value in headers:
        header+=f"{key}: {value}\r\n"
    if content_length is not False:
        header+=f"Content-Length: {content_length}\r\n"
    wire=header.encode("ascii")+b"\r\n"+body
    with socket.create_connection(("127.0.0.1",port),timeout=3) as sock:
        sock.settimeout(4)
        sock.sendall(wire)
        sock.shutdown(socket.SHUT_WR)
        response=bytearray()
        while True:
            chunk=sock.recv(8192)
            if not chunk:break
            response.extend(chunk)
    head,sep,payload=bytes(response).partition(b"\r\n\r\n")
    assert sep, response[:400]
    lines=head.decode("ascii").split("\r\n")
    status=int(lines[0].split(" ")[1])
    hdr={}
    for line in lines[1:]:
        key,value=line.split(":",1)
        assert key.lower() not in hdr
        hdr[key.lower()]=value.strip()
    if status==405:
        assert "allow" in hdr and hdr["allow"],hdr
    assert hdr["connection"]=="close"
    assert hdr["cache-control"]=="no-store"
    assert hdr["x-content-type-options"]=="nosniff"
    assert "application/json" in hdr["content-type"]
    assert int(hdr["content-length"])==len(payload)
    return status,json.loads(payload)

def main():
    assert NATIVE.is_file(),NATIVE
    invoke(NATIVE,"server","check",DSL)
    invalid_opts=[
        ("--host","0.0.0.0"),("--port","70000"),
        ("--max-requests","0"),("--max-requests","10001"),
        ("--idle-ms","499"),("--idle-ms","120001"),
        ("--port","10","--port","11"),
    ]
    for options in invalid_opts:
        invoke(NATIVE,"server","run",DSL,*options,ok=False)

    negative_source=[
        'server "a"\n',
        'app "a"\nroute GET "/health":\n    respond 200 {status: "ok"}\n',
        'server "a"\nroute GET "/../secret":\n    respond 200 {status: "ok"}\n',
        'server "a"\nroute GET "/x%2fy":\n    respond 200 {status: "ok"}\n',
        'server "a"\nroute POST "/create":\n    request x: float\n    respond 201 {x: request.x}\n',
        'server "a"\nroute GET "/x":\n    respond 200 {x: request.missing}\n',
        'server "a"\nroute GET "/x":\n    respond 200 {x: 1}\nroute GET "/x":\n    respond 200 {x: 2}\n',
        'server "a"\nroute GET "/x":\n    respond 200 {x: null}\n',
        'server "a"\nroute GET "/x":\n    respond 200 {x: [1,2]}\n',
        'server "a"\nroute GET "/x":\n    respond 200 {x: 1}\n    respond 200 {x: 2}\n',
        'server "a"\nroute GET "/x":\n    request x: int\n    respond 200 {x: request.x}\n',
        'server "a"\nroute POST "/x":\n    request x: int\n    respond 200 {x: request.y}\n',
        'server "a"\nroute POST "/x":\n    request x: int\n    request x: int\n    respond 200 {x: request.x}\n',
        'server "a"\nroute GET "/x":\n    respond 500 {status: "ok"}\n',
        'server "a"\nroute GET "/x":\n    host_write "/etc/passwd"\n',
    ]
    with tempfile.TemporaryDirectory(prefix="sedrava-server-") as td:
        file=Path(td)/"bad.sdr"
        for raw in negative_source:
            file.write_text(raw,encoding="utf8")
            invoke(NATIVE,"server","check",file,ok=False)

    requests=[]
    def add(expected,**kwargs):
        requests.append((expected,kwargs))

    add((200,{"status":"ok","version":1}))
    add((200,{"message":"Привет от Sedrava!"}),path="/hello")
    content={"name":"молоко \"без сахара\"","quantity":-3,"available":True}
    add((201,{"status":"created",**content}),method="POST",path="/items",
        body=json.dumps(content,ensure_ascii=False),
        headers=(("Content-Type","application/json"),))
    add((202,{"status":"accepted","name":"test"}),method="PUT",path="/items",
        body='{"name":"test"}',headers=(("Content-Type","application/json"),))
    add((200,{"deleted":True}),method="DELETE",path="/items")
    add((404,{"error":{"code":"NOT_FOUND"}}),path="/other")
    add((405,{"error":{"code":"METHOD_NOT_ALLOWED"}}),path="/items")
    add((405,{"error":{"code":"METHOD_NOT_ALLOWED"}}),method="OPTIONS")
    add((400,{"error":{"code":"UNEXPECTED_BODY"}}),body="{}")
    add((415,{"error":{"code":"JSON_CONTENT_TYPE_REQUIRED"}}),
        method="POST",path="/items",body="{}")
    add((400,{"error":{"code":"INVALID_JSON"}}),method="POST",path="/items",
        body="not JSON",headers=(("Content-Type","application/json"),))
    add((422,{"error":{"code":"REQUEST_SCHEMA_MISMATCH"}}),
        method="POST",path="/items",body='{"name":"a","quantity":2}',
        headers=(("Content-Type","application/json"),))
    add((422,{"error":{"code":"REQUEST_SCHEMA_MISMATCH"}}),
        method="POST",path="/items",
        body='{"name":"a","quantity":2,"available":true,"hidden":"secret"}',
        headers=(("Content-Type","application/json"),))
    add((422,{"error":{"code":"REQUEST_SCHEMA_MISMATCH"}}),
        method="POST",path="/items",body='{"name":"a","quantity":"2","available":true}',
        headers=(("Content-Type","application/json"),))
    add((422,{"error":{"code":"REQUEST_SCHEMA_MISMATCH"}}),
        method="POST",path="/items",body='{"name":"a","quantity":2147483648,"available":true}',
        headers=(("Content-Type","application/json"),))
    add((422,{"error":{"code":"REQUEST_SCHEMA_MISMATCH"}}),
        method="POST",path="/items",body='{"name":"a","quantity":1,"available":null}',
        headers=(("Content-Type","application/json"),))
    add((400,{"error":{"code":"INVALID_JSON"}}),
        method="POST",path="/items",
        body='{"name":"a","name":"b","quantity":1,"available":true}',
        headers=(("Content-Type","application/json"),))
    add((400,{"error":{"code":"INVALID_JSON"}}),
        method="POST",path="/items",body='[1,2,3]',
        headers=(("Content-Type","application/json"),))
    add((422,{"error":{"code":"REQUEST_SCHEMA_MISMATCH"}}),
        method="POST",path="/items",
        body=json.dumps({"name":"x"*1025,"quantity":1,"available":True}),
        headers=(("Content-Type","application/json"),))
    add((400,{"error":{"code":"INVALID_HOST"}}),host="host.evil.com")
    add((400,{"error":{"code":"INVALID_HOST"}}),host="127.0.0.1:1")
    add((400,{"error":{"code":"INVALID_REQUEST_TARGET"}}),path="/hello?x=y")
    add((400,{"error":{"code":"INVALID_REQUEST_TARGET"}}),path="/hello%2f")
    add((400,{"error":{"code":"HOST_REQUIRED"}}),host=False)
    add((400,{"error":{"code":"INVALID_REQUEST_LINE"}}),version="HTTP/1.0")
    add((400,{"error":{"code":"INVALID_OR_DUPLICATE_HEADER"}}),
        headers=(("Host","localhost"),))
    add((400,{"error":{"code":"INVALID_OR_DUPLICATE_HEADER"}}),
        headers=(("X-Example","1"),("X-Example","2")))
    add((400,{"error":{"code":"TRANSFER_ENCODING_UNSUPPORTED"}}),
        method="POST",path="/items",headers=(("Transfer-Encoding","chunked"),),
        content_length=False)
    add((400,{"error":{"code":"INVALID_CONTENT_LENGTH"}}),
        method="POST",path="/items",
        headers=(("Content-Length","oops"),),content_length=False)
    add((413,{"error":{"code":"BODY_TOO_LARGE"}}),
        method="POST",path="/items",content_length=16385)
    add((400,{"error":{"code":"INCOMPLETE_BODY"}}),
        method="POST",path="/items",content_length=20,body="{}")
    add((431,{"error":{"code":"HEADERS_TOO_LARGE"}}),
        headers=(("X-Large","z"*9000),))
    add((400,{"error":{"code":"INVALID_HEADER"}}),
        headers=(("Bad Header","2"),))
    add((400,{"error":{"code":"INVALID_OR_DUPLICATE_HEADER"}}),
        headers=(("host","localhost"),))
    add((422,{"error":{"code":"REQUEST_SCHEMA_MISMATCH"}}),
        method="POST",path="/items",
        body='{"name":"a\\n","quantity":1,"available":true}',
        headers=(("Content-Type","application/json"),))

    proc,port=startup(max_requests=len(requests))
    try:
        for index,(expected,kwargs) in enumerate(requests,1):
            try:
                actual=request(port,**kwargs)
            except Exception as exc:
                raise AssertionError(f"HTTP failure at case {index}: {kwargs}") from exc
            assert actual==expected, (index,kwargs,expected,actual)
        done=proc.communicate(timeout=8)
        assert proc.returncode==0,done
        assert f"STOPPED requests={len(requests)}" in done[0],done
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=4)

    # Idle shutdown is checked separately with no HTTP connections.
    proc,port=startup(max_requests=2,idle_ms=500)
    try:
        out,err=proc.communicate(timeout=5)
        assert proc.returncode==0,(out,err)
        assert "STOPPED requests=0" in out
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=3)

    # Absolute connection-read deadline: sending one partial request cannot
    # monopolize the preview service by dripping bytes forever.
    proc,port=startup(max_requests=1,idle_ms=5000)
    try:
        with socket.create_connection(("127.0.0.1",port),timeout=3) as sock:
            sock.settimeout(4)
            sock.sendall(b"GET /health HTTP/1.1\r\nHost: localhost\r\nX-Wait: ")
            time.sleep(1.8)
            sock.shutdown(socket.SHUT_WR)
            parts=[]
            while True:
                part=sock.recv(8192)
                if not part:break
                parts.append(part)
            raw=b"".join(parts)
            assert b"HTTP/1.1 400" in raw,raw[:250]
            assert b"INCOMPLETE_HEADERS" in raw,raw[:250]
        out,err=proc.communicate(timeout=6)
        assert proc.returncode==0,(out,err)
        assert "STOPPED requests=1" in out
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=3)

    print("PASS: native Sedrava Server compiled/validated "+str(len(negative_source))+" invalid DSL programs")
    print("PASS: rejected "+str(len(invalid_opts))+" invalid CLI bind/budget options")
    print("PASS: "+str(len(requests))+" real loopback HTTP/1.1 requests and exact JSON/status verification")
    print("PASS: duplicate JSON fields, Host rebinding, malformed framing, oversized/partial bodies")
    print("PASS: bounded request count, idle shutdown and 1.5s absolute read deadline")
    print("PASS: server process ran with PATH=/nonexistent (no Python/Rust runtime)")

if __name__=="__main__":
    main()
