"""Core 0.12 + Host A2 integration: real typed read Results and four-outcome transport."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sedrava_host import parse_host, run_host
from sedrava_host_protocol import execute_protocol, validate_outcome, PROTOCOL
from sedrava_host_typed import HOST_READ_ERROR, HOST_READ_RESULT

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "sedrava_cli.py"
PROGRAM = '''host "Typed file read"
arg filename: text
try_read fetched from filename
match fetched:
    Ok(content):
        emit content
    Err(FileNotFound { path }):
        emit "missing"
    Err(error):
        emit error_id(error)
'''
WRITER = '''host "Write commit"
arg name: text
write name = "hello"
emit "ready"
'''


@unittest.skipUnless(os.name == "posix", "POSIX host runtime only")
class HostTypedRead(unittest.TestCase):
    def setup_workspace(self, root):
        ws = Path(root)
        (ws / "read").mkdir()
        (ws / "write").mkdir()
        return ws

    def test_typed_success_and_catchable_missing_file(self):
        program = parse_host(PROGRAM)
        with tempfile.TemporaryDirectory() as root:
            ws = self.setup_workspace(root)
            (ws / "read" / "exists.txt").write_text("data 😀", encoding="utf-8")
            kwargs = dict(root=ws, trusted=True, allow_read=True, read_scope="read")
            exists = run_host(program, supplied=("filename=exists.txt",), **kwargs)
            self.assertEqual(exists["result"], "data 😀")
            missing = run_host(program, supplied=("filename=missing.txt",), **kwargs)
            self.assertEqual(missing["result"], "missing")
            invalid = run_host(program, supplied=("filename=../secret.txt",), **kwargs)
            self.assertEqual(invalid["result"], "sedrava.host.read.v1.InvalidPath")

    def test_bounded_pure_match_lets_and_arm_scope(self):
        source = '''host "Computed match"
arg filename: text
try_read fetched from filename
match fetched:
    Ok(content):
        let initial = content
        let renamed = initial
        emit renamed
    Err(FileNotFound { path }):
        let missing = path
        emit missing
    Err(error):
        let stable = error_id(error)
        emit stable
'''
        with tempfile.TemporaryDirectory() as root:
            ws = self.setup_workspace(root)
            (ws / "read" / "sample.txt").write_text("UTF-8 text", encoding="utf-8")
            program = parse_host(source)
            kwargs = dict(root=ws, trusted=True, allow_read=True, read_scope="read")
            self.assertEqual(run_host(program, supplied=("filename=sample.txt",), **kwargs)["result"], "UTF-8 text")
            self.assertEqual(run_host(program, supplied=("filename=absent.txt",), **kwargs)["result"], "absent.txt")
            self.assertEqual(run_host(program, supplied=("filename=../outside",), **kwargs)["result"],
                             "sedrava.host.read.v1.InvalidPath")
            from sedrava_host_effects import infer_host_effects
            self.assertEqual(infer_host_effects(program), frozenset({"host.fs.read"}))
        bad = (
            source.replace("let renamed = initial", "let renamed = missing"),
            source.replace("let renamed = initial", "let renamed = missing\n        emit missing"),
            source.replace("let renamed = initial", "let renamed = initial\n        let renamed = initial"),
            source.replace("let renamed = initial", "write \"out.txt\" = initial"),
            source.replace("emit renamed", "let pending = renamed"),
            source.replace("let renamed = initial", "".join(
                f"let var{i} = initial\n        " for i in range(9)) + "let renamed = initial"),
        )
        for snippet in bad:
            with self.subTest(snippet=snippet[:100]), self.assertRaises(ValueError):
                parse_host(snippet)

    def test_read_expected_limit_and_utf8_failures(self):
        with tempfile.TemporaryDirectory() as root:
            ws = self.setup_workspace(root)
            (ws / "read" / "invalid.txt").write_bytes(b"\xff")
            (ws / "read" / "huge.txt").write_bytes(b"x" * 4097)
            (ws / "read" / "many-scalars.txt").write_text("a" * 1025, encoding="utf-8")
            for path, expected in [("invalid.txt", "InvalidEncoding"),
                                   ("huge.txt", "ResourceTooLarge"),
                                   ("many-scalars.txt", "TextTooLong")]:
                with self.subTest(path=path):
                    result = run_host(parse_host(PROGRAM), root=ws, supplied=("filename="+path,),
                                      trusted=True, allow_read=True, read_scope="read")
                    self.assertEqual(result["result"], "sedrava.host.read.v1."+expected)

    def test_policy_violation_not_a_catchable_result(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as elsewhere:
            ws = self.setup_workspace(root)
            (Path(elsewhere)/"private.txt").write_text("secret")
            (ws/"read"/"outside").symlink_to(Path(elsewhere)/"private.txt")
            out = execute_protocol(parse_host(PROGRAM), root=ws, trusted=True, allow_read=True,
                                   read_scope="read", supplied=("filename=outside",))
            self.assertEqual((out["status"], out["phase"], out["error"]["code"]),
                             ("fault", "execute", "POLICY_VIOLATION"))
            self.assertNotIn(str(elsewhere), json.dumps(out))

    def test_unhandled_expected_error_is_failed_in_execute_phase(self):
        source = 'host "Legacy read"\nread text_data from "missing.txt"\nemit text_data\n'
        with tempfile.TemporaryDirectory() as root:
            ws = self.setup_workspace(root)
            result = execute_protocol(parse_host(source), root=ws,
                                      trusted=True, allow_read=True, read_scope="read")
            self.assertEqual((result["status"], result["phase"], result["commit_state"]),
                             ("failed", "execute", "not_started"))
            self.assertEqual(result["error"]["code"], "FILE_NOT_FOUND")
            self.assertFalse(result["error"]["retryable"])
            self.assertNotIn(str(ws), json.dumps(result))

    def test_invalid_json_and_lookup_are_expected_task_failures(self):
        cases = (
            ('{"title":]', "json_get_text title from config at \"title\"", "INVALID_JSON"),
            ('{"other": true}', "json_get_text title from config at \"title\"", "JSON_LOOKUP_FAILED"),
            ('"scalar"', "json_count number from config", "JSON_OPERATION_FAILED"),
        )
        for payload, operation, expected_code in cases:
            with self.subTest(code=expected_code), tempfile.TemporaryDirectory() as root:
                ws = self.setup_workspace(root)
                (ws / "read" / "config.json").write_text(payload, encoding="utf-8")
                source = ('host "Expected JSON"\n'
                          'read_json config from "config.json"\n'
                          + operation + '\n'
                          + ('emit title\n' if "json_get_text" in operation else 'emit number\n'))
                program = parse_host(source)
                outcome = execute_protocol(program, root=ws, trusted=True, allow_read=True,
                                           read_scope="read")
                self.assertEqual(outcome["status"], "failed")
                self.assertEqual(outcome["phase"], "execute")
                self.assertEqual(outcome["commit_state"], "not_started")
                self.assertEqual(outcome["error"]["code"], expected_code)
                self.assertNotIn(str(ws), json.dumps(outcome))

    def test_configuration_rejected_before_execute(self):
        with tempfile.TemporaryDirectory() as root:
            ws = self.setup_workspace(root)
            result = execute_protocol(parse_host(PROGRAM), root=ws,
                                      trusted=True, supplied=("filename=missing.txt",))
            self.assertEqual((result["status"], result["phase"], result["commit_state"]),
                             ("rejected", "setup", "not_started"))
            self.assertEqual(result["error"]["code"], "CONFIGURATION_REJECTED")

    def test_commit_failure_is_expected_but_unknown_write_state(self):
        with tempfile.TemporaryDirectory() as root:
            ws = self.setup_workspace(root)
            from sedrava_host import _write
            with patch("sedrava_host._write", side_effect=FileNotFoundError(2, "Gone")):
                output = execute_protocol(parse_host(WRITER), root=ws, trusted=True,
                                          allow_write=True, write_scope="write",
                                          supplied=("name=out.txt",))
            self.assertEqual(output["status"], "failed")
            self.assertEqual(output["phase"], "commit")
            self.assertEqual(output["commit_state"], "unknown")
            self.assertEqual(output["error"]["code"], "FILE_NOT_FOUND")
            self.assertFalse(output["error"]["retryable"])

    def test_successful_commit_and_no_write_protocol(self):
        with tempfile.TemporaryDirectory() as root:
            ws = self.setup_workspace(root)
            output = execute_protocol(parse_host(WRITER), root=ws, trusted=True,
                                      allow_write=True, write_scope="write",
                                      supplied=("name=out.txt",))
            self.assertEqual(output["status"], "success")
            self.assertEqual(output["phase"], "commit")
            self.assertEqual(output["commit_state"], "committed")
            self.assertEqual((ws/"write"/"out.txt").read_text(), "hello")
            other = execute_protocol(parse_host(PROGRAM), root=ws, trusted=True, allow_read=True,
                                     read_scope="read", supplied=("filename=missing.txt",))
            self.assertEqual(other["status"], "success")
            self.assertEqual(other["phase"], "execute")
            self.assertEqual(other["commit_state"], "not_applicable")

    def test_match_compile_rejections(self):
        program = PROGRAM
        bad = [
            program.replace('    Err(error):\n        emit error_id(error)\n', ''),
            program.replace('Err(FileNotFound { path })', 'Err(FileNotFound { limit_bytes })'),
            program.replace('Err(FileNotFound { path })', 'Err(FakeError { path })'),
            program.replace('    Err(error):', '    Err(FileNotFound { path }):'),
            program.replace('        emit "missing"', '        emit secret_var'),
            program.replace('        emit content', '        emit error_id(content)'),
            program.replace('        emit content', '        emit content\n        emit content'),
        ]
        for source in bad:
            with self.subTest(source=source[:100]), self.assertRaises(ValueError):
                parse_host(source)

    def test_cli_protocol_and_target_isolation(self):
        with tempfile.TemporaryDirectory() as root:
            ws = self.setup_workspace(root)
            source = ws / "task.sdr"
            source.write_text(PROGRAM)
            call = lambda *args: subprocess.run([sys.executable, str(CLI), *map(str, args)],
                                                  capture_output=True, text=True, timeout=15)
            success = call("host", "run", source, "--root", ws, "--trusted", "--allow-read",
                           "--read-scope", "read", "--arg", "filename=missing.txt",
                           "--result-protocol", "v1")
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertEqual(json.loads(success.stdout)["result"]["result"], "missing")
            denied = call("host", "run", source, "--root", ws, "--trusted",
                          "--arg", "filename=missing.txt", "--result-protocol", "v1")
            self.assertNotEqual(denied.returncode, 0)
            self.assertEqual(json.loads(denied.stdout)["status"], "rejected")
            for invocation in (("check", source), ("build", "web", source, "--output", ws/"x.html"),
                               ("build", "android", source, "--output", ws/"android")):
                with self.subTest(invocation=invocation):
                    self.assertNotEqual(call(*invocation).returncode, 0)
            self.assertFalse((ws/"x.html").exists())

    def test_manifest_is_derived_not_author_granted(self):
        from sedrava_host_effects import canonical_host_manifest, host_effect_manifest
        program = parse_host(PROGRAM)
        manifest = host_effect_manifest(program, PROGRAM)
        self.assertEqual(manifest["effective"], ["host.fs.read"])
        self.assertEqual(manifest["required_grants"], ["--allow-read"])
        self.assertEqual(manifest["target"], "host")
        self.assertEqual(canonical_host_manifest(program, PROGRAM),
                         canonical_host_manifest(program, PROGRAM))
        writer = host_effect_manifest(parse_host(WRITER), WRITER)
        self.assertEqual(writer["effective"], ["host.fs.write"])
        with tempfile.TemporaryDirectory() as root:
            ws = self.setup_workspace(root)
            source = ws / "job.sdr"
            source.write_text(PROGRAM)
            response = subprocess.run([sys.executable, str(CLI), "host", "effects", str(source)],
                                      capture_output=True, text=True, timeout=15)
            self.assertEqual(response.returncode, 0, response.stderr)
            self.assertEqual(json.loads(response.stdout)["effective"], ["host.fs.read"])

    def test_protocol_rejects_inconsistent_results(self):
        out = {"protocol": PROTOCOL, "status": "rejected", "phase": "commit",
               "commit_state": "not_started", "result": None,
               "error": {"code": "CONFIGURATION_REJECTED", "retryable": False}}
        with self.assertRaises(ValueError):
            validate_outcome(out)


if __name__ == "__main__":
    unittest.main()
