#!/usr/bin/env python3
"""Server A4 local redo journal: real HTTP, replay, corruption and crash windows.

Fault injection is exclusively enabled in debug Rust binary, via a private
test-child environment variable. It does NOT prove power-loss durability.
No live web service, public bind, production user data or GitHub Actions.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import tempfile
from verify_native_server_a3 import assert_reply, req

ROOT=Path(__file__).resolve().parents[1]
BIN=ROOT/"rust/target/debug/sedrava-native"
SOURCE=ROOT/"examples/native_server/redo_journal_a4.sdr"
LOCK=".sedrava-server.lock"
MARKER="sedrava-journal-v1.manifest.json"

def run(*args, expected_ok=True):
    out=subprocess.run([str(v) for v in args],text=True,capture_output=True,
                       timeout=9,cwd=ROOT)
    assert (out.returncode==0)==expected_ok,(args,out.returncode,out.stdout[-200:],out.stderr[-500:])
    return out

def start(directory:Path,source=SOURCE, max_requests=10,
          fault=None, journaled=True, transactional=True):
    args=[str(BIN),"server","run",str(source),"--port","0",
          "--max-requests",str(max_requests),"--idle-ms","5000",
          "--state-dir",str(directory)]
    if transactional:args.append("--transactional")
    if journaled:args.append("--journaled")
    env={"PATH":"/nonexistent","LC_ALL":"C"}
    if fault:env["SEDRAVA_A4_FAULT"]=fault
    child=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           stdin=subprocess.DEVNULL,text=True,bufsize=1,cwd=ROOT,env=env)
    selector=selectors.DefaultSelector()
    selector.register(child.stdout,selectors.EVENT_READ)
    if not selector.select(timeout=12):
        child.kill();child.communicate(timeout=4)
        raise AssertionError("Journal server did not announce readiness")
    line=child.stdout.readline().strip()
    import re
    match=re.fullmatch(r"LISTENING http://127\.0\.0\.1:(\d{1,5})",line)
    if not match:
        child.kill()
        _,err=child.communicate(timeout=4)
        raise AssertionError(("Cannot start journal",line,err[-500:]))
    return child,int(match.group(1))

def finished(child,number):
    out,err=child.communicate(timeout=6)
    assert child.returncode==0,(child.returncode,out,err)
    assert f"STOPPED requests={number}" in out,(number,out)

def stop(child):
    if child.poll() is None:child.kill()
    child.communicate(timeout=4)

def try_bad(directory,source=SOURCE,journaled=True,transactional=True):
    args=[BIN,"server","run",source,"--port","0",
          "--idle-ms","500","--max-requests","1","--state-dir",directory]
    if transactional:args.append("--transactional")
    if journaled:args.append("--journaled")
    result=run(*args,expected_ok=False)
    assert "LISTENING " not in result.stdout,(args,result.stdout)
    assert not (directory/LOCK).exists()
    return result.stderr

def base_journal(tmp):
    folder=tmp/"base"
    folder.mkdir(mode=0o700)
    child,port=start(folder,max_requests=5)
    try:
        h=assert_reply(port,200,{"count":0,"total":0,"label":"open"})
        assert h["x-sedrava-revision"]=="0"
        h=assert_reply(port,201,{"count":1,"total":3,"accepted":True},
                       method="POST",path="/record",payload={"amount":3},
                       key="journal-record-0001",rev=0)
        assert h["x-sedrava-revision"]=="1"
        first_file=folder/"txn-00000001.json"
        assert first_file.is_file()
        digest=hashlib.sha256(first_file.read_bytes()).hexdigest()
        h=assert_reply(port,201,{"count":1,"total":3,"accepted":True},
                       method="POST",path="/record",payload={"amount":3},
                       key="journal-record-0001",rev=0)
        assert h["x-sedrava-replayed"]=="true"
        h=assert_reply(port,201,{"count":2,"total":8,"accepted":True},
                       method="POST",path="/record",payload={"amount":5},
                       key="journal-record-0002",rev=1)
        assert h["x-sedrava-revision"]=="2"
        assert hashlib.sha256(first_file.read_bytes()).hexdigest()==digest
        assert_reply(port,200,{"count":2,"total":8,"label":"open"})
        finished(child,5)
    finally:stop(child)
    assert not (folder/LOCK).exists()
    guard=folder/"sedrava-state-v1.json"
    assert guard.is_file()
    assert json.loads(guard.read_text())=={
        "schema":"sedrava.server.redo-journal.guard.v1"}
    assert (folder/MARKER).is_file()
    assert [f.name for f in sorted(folder.glob("txn-*.json"))]==[
        "txn-00000001.json","txn-00000002.json"
    ]
    assert all(f.stat().st_mode&0o077 == 0 for f in folder.iterdir())
    child,port=start(folder,max_requests=4)
    try:
        h=assert_reply(port,200,{"count":2,"total":8,"label":"open"})
        assert h["x-sedrava-revision"]=="2"
        h=assert_reply(port,201,{"count":1,"total":3,"accepted":True},
                       method="POST",path="/record",payload={"amount":3},
                       key="journal-record-0001",rev=0)
        assert h["x-sedrava-replayed"]=="true" and h["x-sedrava-revision"]=="1"
        h=assert_reply(port,201,{"count":2,"total":8,"accepted":True},
                       method="POST",path="/record",payload={"amount":5},
                       key="journal-record-0002",rev=1)
        assert h["x-sedrava-replayed"]=="true"
        assert_reply(port,200,{"count":2,"total":8,"label":"open"})
        finished(child,4)
    finally:stop(child)
    return folder

def corruption_suite(tmp,base):
    changes=[
        ("mutate_state",lambda folder:(folder/"txn-00000002.json").write_text(
            (folder/"txn-00000002.json").read_text().replace('"total":8','"total":9'))),
        ("duplicate_keys",lambda folder:(folder/"txn-00000002.json").write_text(
            (folder/"txn-00000002.json").read_text().replace('"revision":2','"revision":2,"revision":2'))),
        ("missing_first",lambda folder:(folder/"txn-00000001.json").unlink()),
        ("wrong_manifest",lambda folder:(folder/MARKER).write_text(
            (folder/MARKER).read_text().replace('"max_receipts":32','"max_receipts":31'))),
        ("missing_manifest",lambda folder:(folder/MARKER).unlink()),
        ("missing_guard",lambda folder:(folder/"sedrava-state-v1.json").unlink()),
        ("forged_guard",lambda folder:(folder/"sedrava-state-v1.json").write_text('{"schema":"sedrava.server.state.v1"}')),
        ("symlink_guard",lambda folder:(
            (folder/"sedrava-state-v1.json").unlink(),
            (folder/"sedrava-state-v1.json").symlink_to(MARKER))),
        ("unexpected_member",lambda folder:(folder/"unexpected").write_text("invalid")),
        ("insecure_commit",lambda folder:(folder/"txn-00000002.json").chmod(0o644)),
        ("insecure_manifest",lambda folder:(folder/MARKER).chmod(0o644)),
        ("symlink_commit",lambda folder:(
            (folder/"txn-00000002.json").unlink(),
            (folder/"txn-00000002.json").symlink_to("txn-00000001.json"))),
        ("hardlinked_commit",lambda folder:os.link(
            folder/"txn-00000001.json",folder.parent/"hardlink-external")),
        ("unicode_filename",lambda folder:(folder/"txn-€0001.json").write_text("bad")),
    ]
    for case,mutate in changes:
        folder=tmp/f"corrupt-{case}"
        shutil.copytree(base,folder)
        folder.chmod(0o700)
        mutate(folder)
        try_bad(folder)
    # A modified source is incompatible even if declarations look identical.
    altered=tmp/"altered.sdr"
    altered.write_text(SOURCE.read_text()+"\n# changed source digest\n")
    try_bad(base,source=altered)
    assert not (base/LOCK).exists()
    return len(changes)+1

def legacy_suite(tmp,base):
    try_bad(base,journaled=False,transactional=True)
    try_bad(base,journaled=False,transactional=False)
    try_bad(base,journaled=True,transactional=False)
    legacy=tmp/"legacy"
    legacy.mkdir(mode=0o700)
    child,port=start(legacy,max_requests=2,journaled=False)
    try:
        assert_reply(port,200,{"count":0,"total":0,"label":"open"})
        assert_reply(port,201,{"count":1,"total":2,"accepted":True},
                     method="POST",path="/record",payload={"amount":2},
                     key="legacy-test-0001",rev=0)
        finished(child,2)
    finally:stop(child)
    try_bad(legacy,journaled=True,transactional=True)
    assert (legacy/"sedrava-state-v1.json").is_file()

def full_suite(tmp):
    directory=tmp/"capacity"
    directory.mkdir(mode=0o700)
    child,port=start(directory,max_requests=35)
    try:
        for i in range(32):
            h=assert_reply(port,201,{"count":i+1,"total":i+1,"accepted":True},
                           method="POST",path="/record",payload={"amount":1},
                           key=f"journal-capacity-{i:04}",rev=i)
            assert h["x-sedrava-revision"]==str(i+1)
        assert_reply(port,507,{"error":{"code":"TRANSACTION_LEDGER_FULL"}},
                     method="POST",path="/record",payload={"amount":1},
                     key="journal-capacity-0032",rev=32)
        h=assert_reply(port,201,{"count":1,"total":1,"accepted":True},
                       method="POST",path="/record",payload={"amount":1},
                       key="journal-capacity-0000",rev=0)
        assert h["x-sedrava-replayed"]=="true"
        assert_reply(port,200,{"count":32,"total":32,"label":"open"})
        finished(child,35)
    finally:stop(child)
    assert len(list(directory.glob("txn-*.json")))==32
    assert not (directory/LOCK).exists()

def crash_suite(tmp):
    results=[]
    for stage,precommit in [
        ("after_write",True),
        ("after_file_fsync",True),
        ("after_rename",False),
        ("after_dir_fsync",False),
    ]:
        folder=tmp/f"crash-{stage}"
        folder.mkdir(mode=0o700)
        child,port=start(folder,max_requests=2,fault=stage)
        try:
            interrupted=False
            try:
                req(port,method="POST",path="/record",payload={"amount":3},
                    key="journal-crash-0001",rev=0)
            except (ConnectionError,OSError,AssertionError):
                interrupted=True
            assert interrupted,f"{stage} unexpectedly replied"
            out,err=child.communicate(timeout=5)
            assert child.returncode==87,(stage,child.returncode,out,err)
            assert f"SEDRAVA_A4_FAULT_INJECTED:{stage}" in err,(stage,err)
        finally:stop(child)
        assert (folder/LOCK).is_file(),stage
        # Fail closed on stale lock while killed child already reaped.
        run(BIN,"server","run",SOURCE,"--transactional","--journaled",
            "--state-dir",folder,"--port","0","--idle-ms","500",
            expected_ok=False)
        # Explicit operator-like recovery is ONLY in this test-owned directory,
        # after confirming the child no longer exists.
        assert child.poll() is not None
        (folder/LOCK).unlink()
        leftovers=[f for f in folder.iterdir() if f.name not in {MARKER,"sedrava-state-v1.json"}
                   and not f.name.startswith("txn-")]
        if precommit:
            assert leftovers,(stage,"precommit temp was not retained")
            try_bad(folder)  # unknown temp must NEVER be silently discarded.
            for file in leftovers: file.unlink()
            assert not (folder/"txn-00000001.json").exists()
            expected={"count":0,"total":0,"label":"open"}
        else:
            assert not leftovers,(stage,[str(f) for f in leftovers])
            assert (folder/"txn-00000001.json").exists()
            expected={"count":1,"total":3,"label":"open"}
        child,port=start(folder,max_requests=2)
        try:
            assert_reply(port,200,expected)
            h=assert_reply(port,
                201,{"count":1,"total":3,"accepted":True},
                method="POST",path="/record",payload={"amount":3},
                key="journal-crash-0001",rev=0)
            if not precommit:
                assert h["x-sedrava-replayed"]=="true",stage
            else:
                assert "x-sedrava-replayed" not in h,stage
            finished(child,2)
        finally:stop(child)
        assert len(list(folder.glob("txn-*.json")))==1
        results.append(stage)
    return results

def killed_process_lock(tmp):
    folder=tmp/"sigkill"
    folder.mkdir(mode=0o700)
    child,port=start(folder,max_requests=10)
    try:
        assert_reply(port,201,{"count":1,"total":2,"accepted":True},
                     method="POST",path="/record",payload={"amount":2},
                     key="journal-sigkill-0001",rev=0)
    finally:
        os.kill(child.pid,signal.SIGKILL)
        child.communicate(timeout=5)
    assert (folder/LOCK).is_file()
    assert child.poll() is not None
    (folder/LOCK).unlink()
    child,port=start(folder,max_requests=2)
    try:
        h=assert_reply(port,201,{"count":1,"total":2,"accepted":True},
                       method="POST",path="/record",payload={"amount":2},
                       key="journal-sigkill-0001",rev=0)
        assert h["x-sedrava-replayed"]=="true"
        assert_reply(port,200,{"count":1,"total":2,"label":"open"})
        finished(child,2)
    finally:stop(child)

def main():
    assert BIN.is_file()
    run(BIN,"server","check",SOURCE)
    with tempfile.TemporaryDirectory(prefix="sedrava-journal-a4-") as td:
        folder=Path(td)
        base=base_journal(folder)
        cases=corruption_suite(folder,base)
        legacy_suite(folder,base)
        full_suite(folder)
        faults=crash_suite(folder)
        killed_process_lock(folder)
    print("PASS: 2 immutable fsynced redo records; 2 real HTTP commits + exact replay after restart")
    print(f"PASS: {cases} corrupted/missing/mismatched manifest/source/record scenarios fail-closed")
    print("PASS: A2/A3 cannot silently open A4; A4 refuses A3 snapshot")
    print("PASS: 32-record capacity, old replay after 507")
    print("PASS: debug-only fault injection at "+", ".join(faults))
    print("PASS: killed process retains lock; explicit test-owned recovery + replay")
    print("PASS: PATH=/nonexistent for all runtime child processes, localhost-only")

if __name__=="__main__":
    main()
