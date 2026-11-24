#!/usr/bin/env python3
"""HTTP capacity must not poison native owner; replay and reads stay available."""
import tempfile,subprocess,selectors
from pathlib import Path
import verify_native_server_log_a12 as a
def main():
    with tempfile.TemporaryDirectory(prefix="sedrava-http-budget-") as temp:
        log=Path(temp)/"journal"
        a.cli("init",log)
        extra=("--native-max-bytes","67108864","--native-max-transactions","1")
        a.rejected(log,extra=("--native-max-bytes","8"))
        a.rejected(log,extra=("--native-max-bytes","7","--native-max-transactions","1"))
        def launch(count):
            p=subprocess.Popen(a.args(log,count,extra=extra),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,stdin=subprocess.DEVNULL,env={"PATH":"/nonexistent","LC_ALL":"C"})
            with selectors.DefaultSelector() as w:
                w.register(p.stdout,selectors.EVENT_READ)
                if not w.select(10):
                    a.kill(p);raise AssertionError("no startup")
                line=p.stdout.readline().strip()
            if not line.startswith("LISTENING http://127.0.0.1:"):
                a.kill(p);raise AssertionError(line)
            return p,int(line.rsplit(":",1)[1])
        p,port=launch(5)
        try:
            a.write(port,1);before=a.digest(log)
            a.error(a.send(port,2),507,"NATIVE_LOG_CAPACITY")
            a.pair(port,1);a.write(port,1,replay=True)
            a.error(a.send(port,1,payload=a.payload(2)),409,"IDEMPOTENCY_CONFLICT")
            a.stop(p);assert a.digest(log)==before
        finally:a.kill(p)
        a.check_journal(log,1)
        p,port=launch(3)
        try:
            a.write(port,1,replay=True);a.error(a.send(port,2),507,"NATIVE_LOG_CAPACITY");a.pair(port,1);a.stop(p)
        finally:a.kill(p)
        assert a.digest(log)==before
        print("PASS B15a HTTP: 507 capacity, unchanged journal, reads and historic replay after restart")
if __name__=="__main__":main()
