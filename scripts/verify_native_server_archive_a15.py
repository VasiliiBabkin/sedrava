#!/usr/bin/env python3
"""A15 offline restoration of the real native HTTP application's journal."""
import tempfile
from pathlib import Path
import verify_native_server_log_a12 as a
def main():
    with tempfile.TemporaryDirectory(prefix="sedrava-a15-archive-") as temp:
        root=Path(temp);log=root/"original";archive=root/"archive";restored=root/"restored"
        a.cli("init",log)
        p,port=a.launch(log,3)
        try:
            a.write(port,1);a.write(port,2);a.pair(port,2);a.stop(p)
        finally:a.kill(p)
        before=a.digest(log)
        report=a.cli("archive-create",log,archive,before)
        assert a.cli("archive-verify",archive)==report
        assert a.cli("archive-restore",archive,restored,a.digest(archive))==report
        assert a.digest(restored)==before
        p,port=a.launch(restored,3)
        try:
            a.write(port,1,replay=True);a.pair(port,2);a.write(port,3);a.stop(p)
        finally:a.kill(p)
        a.check_journal(restored,3);a.check_journal(log,2)
        assert a.digest(log)==before and a.digest(archive)==report["archive_sha256"]
        print("PASS A15: real native HTTP journal archived and byte-exact restored; original response replay and new writes; original unchanged")
if __name__=="__main__":main()
