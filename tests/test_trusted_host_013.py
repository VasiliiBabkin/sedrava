"""Host A1 capability boundary: execute real filesystem operations only with grants."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sedrava_host import parse_host, run_host


COPY = '''host "Safe report"
arg input: text
arg output: text
arg prefix: text
read body from input
let content = concat(prefix, body)
write output = content
emit content
'''

CLI = Path(__file__).resolve().parents[1] / "sedrava_cli.py"


class HostParsing(unittest.TestCase):
    def test_host_parser_and_typed_arguments(self):
        program = parse_host(COPY)
        self.assertTrue(program.needs_read)
        self.assertTrue(program.needs_write)
        self.assertEqual([name for name, _ in program.arguments], ["input", "output", "prefix"])
        typed = parse_host('host "Typed"\narg n: int\narg enabled: bool\nlet bigger = n + 2\nemit bigger\n')
        with tempfile.TemporaryDirectory() as root:
            self.assertEqual(run_host(typed, root=root, trusted=True,
                                     supplied=["n=5", "enabled=false"])["result"], 7)
            with self.assertRaises(ValueError):
                run_host(typed, root=root, trusted=True,
                         supplied=["n=true", "enabled=false"])
            with self.assertRaises(ValueError):
                run_host(typed, root=root, trusted=True,
                         supplied=["n=5", "enabled=False"])
            with self.assertRaises(ValueError):
                run_host(typed, root=root, trusted=True,
                         supplied=["n=5", "enabled=false", "extra=1"])

    def test_reserved_bindings_and_unbounded_cli_inputs_rejected(self):
        for name in ("concat", "count", "false", "for", "class", "assert",
                     "text_length", "has", "_hidden"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                parse_host('host "Reserved"\narg ' + name + ': text\nemit "done"\n')
        typed = parse_host('host "Typed"\narg n: int\nemit n\n')
        with tempfile.TemporaryDirectory() as root:
            for args in (["n=" + "9" * 1000], ["n=2147483648"],
                         ["n=-2147483649"], ["n=3"] * 17):
                with self.subTest(args=args[:2]), self.assertRaises(ValueError):
                    run_host(typed, root=root, trusted=True, supplied=args)

    def test_forbidden_host_syntax_and_effects(self):
        for body in (
            'import os',
            'let unsafe = __import__("os")',
            'read x from "../secret"',
            'write "a.txt" = "ok"\nwrite "b.txt" = "ok"',
            'emit "done"\nlet other = 1',
            'while true:',
            'read x from 20',
            'arg a: list<text>',
            'write "a.txt" = 42',
            'let y = open("x")',
        ):
            with self.subTest(body=body), self.assertRaises(ValueError):
                parse_host('host "Denied"\n' + body + '\nemit "done"\n')
        with self.assertRaises(ValueError):
            parse_host('host "Bad"\nlet n = 0\n')  # emit required


class HostIO(unittest.TestCase):
    def test_granted_read_then_atomic_write(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root)
            (workspace / "sub").mkdir()
            (workspace / "sub" / "in.txt").write_text("Привет 😀", encoding="utf-8")
            result = run_host(parse_host(COPY), root=root, trusted=True, allow_read=True,
                              allow_write=True, supplied=["input=sub/in.txt",
                                                         "output=sub/out.txt", "prefix=Text: "])
            self.assertEqual(result, {"result": "Text: Привет 😀", "written": "sub/out.txt"})
            self.assertEqual((workspace / "sub" / "out.txt").read_text(encoding="utf-8"),
                             "Text: Привет 😀")
            self.assertEqual((workspace / "sub" / "out.txt").stat().st_mode & 0o777, 0o600)
            self.assertFalse(list((workspace / "sub").glob(".sedrava-*.tmp")))

    def test_denied_without_explicit_trust_or_grants(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "in.txt").write_text("ok", encoding="utf-8")
            opts = {"root": root, "supplied": ["input=in.txt", "output=out.txt", "prefix="]}
            for changes in ({}, {"trusted": True},
                            {"trusted": True, "allow_read": True},
                            {"trusted": True, "allow_write": True}):
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    run_host(parse_host(COPY), **opts, **changes)
            self.assertFalse((Path(root) / "out.txt").exists())

    def test_host_disallows_control_character_paths(self):
        with tempfile.TemporaryDirectory() as root:
            program = parse_host('host "Control"\narg target: text\n'
                                 'write target = "safe"\nemit "ok"\n')
            for bad in ("tab\tfile.txt", "line\nfile.txt", "del\x7ffile.txt"):
                with self.subTest(bad=repr(bad)), self.assertRaises(ValueError):
                    run_host(program, root=root, trusted=True, allow_write=True,
                             supplied=["target=" + bad])
            self.assertFalse(list(Path(root).iterdir()))

    def test_path_traversal_absolute_and_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as other:
            ws = Path(root)
            (ws / "source.txt").write_text("safe", encoding="utf-8")
            (Path(other) / "outside.txt").write_text("outside", encoding="utf-8")
            (ws / "link.txt").symlink_to(Path(other) / "outside.txt")
            (ws / "linked").symlink_to(other, target_is_directory=True)
            opts = {"root": root, "trusted": True, "allow_read": True, "allow_write": True}
            for path in ("../outside.txt", "/etc/passwd", "./source.txt", "sub/../source.txt",
                         "link.txt", "linked/outside.txt", "source.txt/child",
                         "bad//path", "bad\\path"):
                with self.subTest(path=path), self.assertRaises((OSError, ValueError)):
                    run_host(parse_host(COPY), **opts,
                             supplied=[f"input={path}", "output=out.txt", "prefix="])
            self.assertEqual((Path(other) / "outside.txt").read_text(), "outside")
            with self.assertRaises((OSError, ValueError)):
                run_host(parse_host('host "Write"\narg target: text\nwrite target = "changed"\nemit "ok"\n'),
                         root=root, trusted=True, allow_write=True, supplied=["target=link.txt"])
            self.assertEqual((Path(other) / "outside.txt").read_text(), "outside")

    def test_limits_invalid_utf8_and_atomic_failure(self):
        with tempfile.TemporaryDirectory() as root:
            ws = Path(root)
            (ws / "too-big.txt").write_bytes(b"a" * 4097)
            (ws / "invalid.txt").write_bytes(b"\xff")
            opts = {"root": root, "trusted": True, "allow_read": True, "allow_write": True}
            for filename in ("too-big.txt", "invalid.txt"):
                with self.subTest(filename=filename), self.assertRaises(ValueError):
                    run_host(parse_host(COPY), **opts,
                             supplied=[f"input={filename}", "output=out.txt", "prefix="])
            self.assertFalse((ws / "out.txt").exists())
            # No write occurs when later pure-expression evaluation fails.
            (ws / "out.txt").write_text("original", encoding="utf-8")
            broken = parse_host('host "Rollback"\n'
                                'write "out.txt" = "changed"\n'
                                'emit date_add("9999-12-31", 1)\n')
            with self.assertRaises(ValueError):
                run_host(broken, root=root, trusted=True, allow_write=True)
            self.assertEqual((ws / "out.txt").read_text(), "original")
            with self.assertRaises(ValueError):
                run_host(parse_host('host "Oversize"\nwrite "out.txt" = '
                                    'concat("a", "b")\nemit "ok"\n'),
                         root=root, trusted=False, allow_write=True)

    def test_no_hardlinked_or_special_file_reads(self):
        if os.name != "posix":
            self.skipTest("POSIX host only")
        with tempfile.TemporaryDirectory() as root:
            ws = Path(root)
            (ws / "file.txt").write_text("secret")
            os.link(ws / "file.txt", ws / "alias.txt")
            program = parse_host('host "Links"\nread body from "file.txt"\nemit body\n')
            with self.assertRaises(ValueError):
                run_host(program, root=root, trusted=True, allow_read=True)


class HostCLI(unittest.TestCase):
    def call(self, *args):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                              capture_output=True, text=True, timeout=15)

    def test_end_to_end_cli_and_non_host_rejection(self):
        with tempfile.TemporaryDirectory() as root:
            ws = Path(root)
            source = ws / "job.sdr"
            source.write_text(COPY, encoding="utf-8")
            (ws / "input.txt").write_text("a", encoding="utf-8")
            check = self.call("host", "check", source)
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertFalse((ws / "output.txt").exists())
            failed = self.call("host", "run", source, "--root", ws,
                               "--arg", "input=input.txt",
                               "--arg", "output=output.txt",
                               "--arg", "prefix=!")
            self.assertNotEqual(failed.returncode, 0)
            ok = self.call("host", "run", source, "--root", ws, "--trusted",
                           "--allow-read", "--allow-write",
                           "--arg", "input=input.txt", "--arg", "output=output.txt",
                           "--arg", "prefix=!")
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertEqual(json.loads(ok.stdout)["result"], "!a")
            for args in (("check", source),
                         ("build", "web", source, "--output", ws / "bad.html"),
                         ("build", "android", source, "--output", ws / "bad-android")):
                with self.subTest(args=args):
                    self.assertNotEqual(self.call(*args).returncode, 0)
            self.assertFalse((ws / "bad.html").exists())
            self.assertFalse((ws / "bad-android").exists())


if __name__ == "__main__":
    unittest.main()
