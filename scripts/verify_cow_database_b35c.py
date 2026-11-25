#!/usr/bin/env python3
"""Standalone Sedrava database backend selection and policy checks."""
import json, os, subprocess, tempfile
from pathlib import Path
BIN=Path(os.environ["SEDRAVA_NATIVE_BIN"])
DB=Path(os.environ["SEDRAVASQL_NATIVE_BIN"])
def run(args, fail=False):
    p=subprocess.run([str(x) for x in args],capture_output=True,text=True,timeout=20)
    assert (p.returncode!=0)==fail,(p.stdout,p.stderr)
    return p.stdout
with tempfile.TemporaryDirectory(prefix="sedrava-b35c-") as tmp:
    root=Path(tmp);cow=root/"cow";log=root/"log";query=root/"query.sdr";write=root/"write.sdr"
    query.write_text('database Test\n    query "SELECT n FROM T WHERE id=\'a\'"\n')
    write.write_text('database Test\n    param n: int\n    execute "INSERT INTO T (id,n) VALUES (\'a\',?)"\n')
    for p,prefix in [(cow,"cow-"),(log,"")]:
        run([DB,prefix+"init",p])
        run([DB,prefix+"sql",p,"CREATE TABLE T (id TEXT PRIMARY KEY,n INT)","test-create-00001"])
    base=[BIN,"database","run",write,"--database",cow,"--backend","cow","--trusted","--allow-write","--request-key","test-insert-00001","--arg","n=12"]
    first=json.loads(run(base));assert first["replayed"] is False
    before=cow.read_bytes(),cow.with_name("cow.head").read_bytes()
    assert json.loads(run(base))=={**first,"replayed":True}
    run([*base[:-1],"n=13"],fail=True)
    assert before==(cow.read_bytes(),cow.with_name("cow.head").read_bytes())
    assert json.loads(run([BIN,"database","run",query,"--database",cow,"--trusted","--backend","cow"]))["rows"]==[[12]]
    for p,backend in [(cow,"native-log"),(log,"cow"),(log,"wrong")]:
        run([BIN,"database","run",query,"--database",p,"--trusted","--backend",backend],fail=True)
    run([BIN,"database","run",query,"--database",cow,"--backend","cow"],fail=True)
    run([DB,"cow-verify",cow])
print("PASS B35c standalone: explicit backend, trusted policy, typed write, durable replay, conflict, unchanged data/head, wrong format refusal")
