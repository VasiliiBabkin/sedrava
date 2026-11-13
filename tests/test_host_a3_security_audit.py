"""Independent Host A3 audit: real POSIX I/O with deterministic fault injection."""
import errno
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

from sedrava_host import _read, _write, parse_host, run_host
from sedrava_host_protocol import execute_protocol
from sedrava_host_typed import HostPolicyViolation, read_result

ROOT = Path(__file__).resolve().parents[1]
WRITE = 'host "write"\nwrite "out" = "new"\nemit "ready"\n'
READ = 'host "read"\narg name: text\ntry_read value from name\nmatch value:\n    Ok(content):\n        emit content\n    Err(error):\n        emit error_id(error)\n'


@unittest.skipUnless(os.name == "posix", "POSIX-only Host")
class HostSecurityAudit(unittest.TestCase):
    def outcome(self, source, root, **options):
        return execute_protocol(parse_host(source), root=root, trusted=True, **options)

    def test_temp_collision_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as root:
            ws = Path(root)
            collision = ws / (".sedrava-" + "a" * 32 + ".tmp")
            collision.write_text("another operation's data")
            (ws / "out").write_text("original")
            with patch("sedrava_host.secrets.token_hex", return_value="a" * 32):
                out = self.outcome(WRITE, root, allow_write=True)
            self.assertEqual(out["error"]["code"], "FILE_EXISTS")
            self.assertEqual(out["commit_state"], "unknown")
            self.assertTrue(collision.exists(), "O_EXCL collision must not unlink another file")
            self.assertEqual(collision.read_text(), "another operation's data")
            self.assertEqual((ws / "out").read_text(), "original")

    def test_list_symlink_is_policy_fault(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            (Path(root) / "link").symlink_to(other, target_is_directory=True)
            out = self.outcome('host "list"\nlist_dir entries from "."\nemit_json entries\n',
                               root, allow_list=True)
            self.assertEqual(out["status"], "fault")
            self.assertEqual(out["error"]["code"], "POLICY_VIOLATION")

    def test_rmdir_symlink_is_policy_fault(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            link = Path(root) / "link"
            link.symlink_to(other, target_is_directory=True)
            out = self.outcome('host "remove"\nrmdir "link"\nemit "done"\n',
                               root, allow_write=True, allow_rmdir=True)
            self.assertEqual(out["error"]["code"], "POLICY_VIOLATION")
            self.assertTrue(link.is_symlink())
            self.assertTrue(Path(other).is_dir())

    def test_cli_transport_failure_never_fabricates_setup_rejection(self):
        from sedrava_cli import main

        class FailOnce(io.StringIO):
            failed = False

            def write(self, text):
                if not self.failed:
                    self.failed = True
                    raise OSError(errno.EIO, "/internal/transport/detail")
                return super().write(text)

        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "job.sdr"
            source.write_text(WRITE)
            stdout, stderr = FailOnce(), io.StringIO()
            argv = ["sedrava", "host", "run", str(source), "--root", root,
                    "--trusted", "--allow-write", "--result-protocol", "v1"]
            with patch.object(sys, "argv", argv), patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr):
                self.assertEqual(main(), 1)
            self.assertEqual((Path(root) / "out").read_text(), "new")
            self.assertEqual(stdout.getvalue(), "", "A committed write cannot become rejected/not_started")
            self.assertIn("do not retry automatically", stderr.getvalue())
            self.assertNotIn("/internal", stderr.getvalue())

    def test_hardlink_read_and_write_never_touch_other_inode_alias(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            victim = Path(other) / "private"
            victim.write_text("private")
            os.link(victim, Path(root) / "out")
            for source, grants in [(READ, {"allow_read": True, "supplied": ["name=out"]}),
                                   (WRITE, {"allow_write": True})]:
                with self.subTest(source=source):
                    out = self.outcome(source, root, **grants)
                    self.assertEqual(out["error"]["code"], "POLICY_VIOLATION")
                    self.assertIsNone(out["result"])
            self.assertEqual(victim.read_text(), "private")

    def test_fifo_read_rejected_before_any_read(self):
        with tempfile.TemporaryDirectory() as root:
            os.mkfifo(Path(root) / "fifo")
            with patch("sedrava_host.os.read", side_effect=AssertionError("must not read FIFO")):
                out = self.outcome(READ, root, allow_read=True, supplied=["name=fifo"])
            self.assertEqual(out["error"]["code"], "POLICY_VIOLATION")

    def test_scope_symlinks_and_parent_traversal_rejected_at_setup(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            (Path(root) / "scope").symlink_to(other, target_is_directory=True)
            for scope in ["scope", "../outside", "/absolute", "a//b", "a/../b"]:
                with self.subTest(scope=scope):
                    out = self.outcome(READ, root, allow_read=True, read_scope=scope,
                                       supplied=["name=private"])
                    self.assertEqual((out["status"], out["phase"], out["commit_state"]),
                                     ("rejected", "setup", "not_started"))

    def test_each_grant_is_checked_before_filesystem_is_opened(self):
        programs = [
            (READ, {"allow_read": True}),
            ('host "list"\nlist_dir entries from "."\nemit_json entries\n', {"allow_list": True}),
            (WRITE, {"allow_write": True}),
            ('host "mkdir"\nmkdir "newdir"\nemit "done"\n',
             {"allow_write": True, "allow_mkdir": True}),
            ('host "rmdir"\nrmdir "old"\nemit "done"\n',
             {"allow_write": True, "allow_rmdir": True}),
        ]
        for source, grants in programs:
            for denied in grants:
                options = dict(grants)
                options[denied] = False
                with self.subTest(source=source, denied=denied):
                    with patch("sedrava_host.os.open", side_effect=AssertionError("no I/O before grants")):
                        out = self.outcome(source, "/unused", **options)
                    self.assertEqual(out["status"], "rejected")
        with patch("sedrava_host.os.open", side_effect=AssertionError("no I/O without trust")):
            out = execute_protocol(parse_host(WRITE), root="/unused", allow_write=True)
        self.assertEqual(out["status"], "rejected")

    def test_expected_read_errors_are_exactly_typed(self):
        with tempfile.TemporaryDirectory() as root:
            ws = Path(root)
            for name, data, variant in [
                ("invalid", b"\xff", "InvalidEncoding"),
                ("oversized", b"a" * 4097, "ResourceTooLarge"),
                ("long", b"a" * 1025, "TextTooLong"),
                ("missing", None, "FileNotFound"),
            ]:
                if data is not None:
                    (ws / name).write_bytes(data)
                out = self.outcome(READ, root, allow_read=True, supplied=["name=" + name])
                self.assertEqual(out["status"], "success")
                self.assertEqual(out["result"]["result"], "sedrava.host.read.v1." + variant)
            (ws / "unicode").write_text("😀" * 1024, encoding="utf-8")
            out = self.outcome(READ, root, allow_read=True, supplied=["name=unicode"])
            self.assertEqual(out["result"]["result"], "😀" * 1024)

    def test_policy_and_unknown_engine_faults_are_not_catchable_results(self):
        with tempfile.TemporaryDirectory() as root:
            for error in [HostPolicyViolation("/private/policy"), RuntimeError("/private/engine"),
                          ValueError("BudgetExceeded /private/budget"), OSError(errno.ELOOP, "/private/link")]:
                with self.subTest(error=type(error).__name__):
                    with patch("sedrava_host._read", side_effect=error):
                        out = self.outcome(READ, root, allow_read=True, supplied=["name=normal"])
                    self.assertEqual(out["status"], "fault")
                    self.assertIsNone(out["result"])
                    self.assertNotIn("/private", json.dumps(out))
                    self.assertFalse(out["error"]["retryable"])

    def test_read_permission_error_is_expected_without_path_leak(self):
        with tempfile.TemporaryDirectory() as root:
            with patch("sedrava_host._read", side_effect=PermissionError(errno.EACCES, "/private/path")):
                out = self.outcome(READ, root, allow_read=True, supplied=["name=normal"])
            self.assertEqual(out["status"], "success")
            self.assertEqual(out["result"]["result"], "sedrava.host.read.v1.PermissionDenied")
            self.assertNotIn("/private", json.dumps(out))

    def test_file_fsync_failure_does_not_replace_existing_target(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "out"
            target.write_text("old")
            with patch("sedrava_host.os.fsync", side_effect=OSError(errno.EIO, "failure")):
                out = self.outcome(WRITE, root, allow_write=True)
            self.assertEqual(target.read_text(), "old")
            self.assertEqual(out["commit_state"], "unknown")
            self.assertFalse(list(Path(root).glob(".sedrava-*.tmp")))

    def test_mkdir_and_rmdir_post_mutation_fsync_failures_are_unknown(self):
        with tempfile.TemporaryDirectory() as root:
            for operation in ["mkdir", "rmdir"]:
                if operation == "rmdir":
                    (Path(root) / "empty").mkdir()
                source = f'host "directory"\n{operation} "empty"\nemit "done"\n'
                with patch("sedrava_host_fs.os.fsync", side_effect=OSError(errno.EIO, "/private/detail")):
                    out = self.outcome(source, root, allow_write=True,
                                       **{"allow_" + operation: True})
                self.assertEqual(out["status"], "failed")
                self.assertEqual((out["phase"], out["commit_state"]), ("commit", "unknown"))
                self.assertFalse(out["error"]["retryable"])
                self.assertEqual((Path(root) / "empty").exists(), operation == "mkdir")
                self.assertNotIn("/private", json.dumps(out))
                if operation == "mkdir":
                    (Path(root) / "empty").rmdir()

    def test_replace_failure_cleans_only_own_temp_and_preserves_target(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "out"
            target.write_text("old")
            with patch("sedrava_host.os.replace", side_effect=OSError(errno.ENOSPC, "full")):
                out = self.outcome(WRITE, root, allow_write=True)
            self.assertEqual(target.read_text(), "old")
            self.assertEqual(out["error"]["code"], "IO_FAILURE")
            self.assertFalse(list(Path(root).glob(".sedrava-*.tmp")))

    def test_new_file_and_directory_permissions_are_private(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(self.outcome(WRITE, root, allow_write=True)["status"], "success")
            self.assertEqual(stat.S_IMODE((Path(root) / "out").stat().st_mode), 0o600)
            self.outcome('host "mkdir"\nmkdir "directory"\nemit "ok"\n', root,
                         allow_write=True, allow_mkdir=True)
            self.assertEqual(stat.S_IMODE((Path(root) / "directory").stat().st_mode), 0o700)

    def test_open_parent_descriptor_not_retargeted_by_symlink_swap(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            ws = Path(root)
            (ws / "sub").mkdir()
            (ws / "sub" / "data").write_text("safe")
            (Path(other) / "data").write_text("private")
            real_open = os.open
            swapped = []

            def swap(name, flags, *args, **kwargs):
                fd = real_open(name, flags, *args, **kwargs)
                if name == "sub" and not swapped:
                    (ws / "sub").rename(ws / "held")
                    (ws / "sub").symlink_to(other, target_is_directory=True)
                    swapped.append(True)
                return fd

            with patch("sedrava_host.os.open", side_effect=swap):
                out = self.outcome(READ, root, allow_read=True, supplied=["name=sub/data"])
            self.assertEqual(out["result"]["result"], "safe")

    def test_hostile_directory_relocation_is_explicitly_outside_threat_model(self):
        """Records the limitation, not a sandbox-confinement guarantee."""
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            ws = Path(root)
            (ws / "sub").mkdir()
            destination = Path(other) / "moved"
            real_open = os.open
            moved = []

            def relocate(name, flags, *args, **kwargs):
                fd = real_open(name, flags, *args, **kwargs)
                if name == "sub" and not moved:
                    (ws / "sub").rename(destination)
                    moved.append(True)
                return fd

            with patch("sedrava_host.os.open", side_effect=relocate):
                out = self.outcome('host "race"\nwrite "sub/out" = "new"\nemit "ok"\n',
                                   root, allow_write=True)
            self.assertEqual(out["status"], "success")
            self.assertEqual((destination / "out").read_text(), "new")

    def test_in_place_concurrent_read_is_not_a_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "data"
            target.write_bytes(b"abcdef")
            real_read = os.read
            first = []

            def modify(fd, size):
                chunk = real_read(fd, min(size, 3) if not first else size)
                if not first:
                    first.append(True)
                    target.write_bytes(b"XYZ123")
                return chunk

            with patch("sedrava_host.os.read", side_effect=modify):
                out = self.outcome(READ, root, allow_read=True, supplied=["name=data"])
            self.assertEqual(out["result"]["result"], "abc123")

    def test_growing_file_read_is_bounded(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "data").write_text("a")
            requests = []

            def growing(fd, size):
                requests.append(size)
                return b"a" * min(size, 7)

            with patch("sedrava_host.os.read", side_effect=growing):
                out = self.outcome(READ, root, allow_read=True, supplied=["name=data"])
            self.assertEqual(out["result"]["result"], "sedrava.host.read.v1.ResourceTooLarge")
            self.assertEqual(sum(min(n, 7) for n in requests), 4097)
            self.assertLessEqual(len(requests), 586)

    def test_overflow_after_planning_write_leaves_target_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "out"
            target.write_text("old")
            source = 'host "overflow"\narg n: int\nwrite "out" = "new"\nemit n + 1\n'
            out = self.outcome(source, root, allow_write=True, supplied=["n=2147483647"])
            self.assertEqual(out["status"], "fault")
            self.assertEqual(out["commit_state"], "not_started")
            self.assertEqual(target.read_text(), "old")

    def test_repeated_failed_reads_do_not_leak_file_descriptors(self):
        if not Path("/proc/self/fd").is_dir():
            self.skipTest("Linux fd accounting only")
        with tempfile.TemporaryDirectory() as root:
            before = len(list(Path("/proc/self/fd").iterdir()))
            for unused in range(50):
                out = self.outcome(READ, root, allow_read=True, supplied=["name=missing"])
                self.assertEqual(out["status"], "success")
            self.assertEqual(len(list(Path("/proc/self/fd").iterdir())), before)


if __name__ == "__main__":
    unittest.main()
