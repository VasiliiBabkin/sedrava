"""Host A2: JSON, scoped directory capabilities, and effect-free browser builds."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sedrava_host import parse_host, run_host
from sedrava_host_json import JsonValue, dumps, loads, lookup, validate_json


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "sedrava_cli.py"

INVENTORY = '''host "Inventory"
arg source: text
read_json config from source
json_get_text owner from config at "owner"
list_dir entries from "."
json_count total from entries
json_object report
json_set report.owner = owner
json_set report.entries = entries
json_set report.count = total
write_json "inventory.json" = report
emit_json report
'''


class JsonContract(unittest.TestCase):
    def test_strict_roundtrip_type_distinctions(self):
        raw = '{"z":[true,null,1,"Привет"],"a":{"k":"😀"}}'
        value = loads(raw)
        self.assertEqual(dumps(value), '{"a":{"k":"😀"},"z":[true,null,1,"Привет"]}')
        self.assertEqual(lookup(value, "a", JsonValue).value, {"k": "😀"})
        self.assertEqual(lookup(lookup(value, "z", JsonValue), 2, int), 1)
        with self.assertRaises(ValueError):
            lookup(lookup(value, "z", JsonValue), 0, int)
        with self.assertRaises(ValueError):
            lookup(value, "missing", str)
        with self.assertRaises(ValueError):
            lookup(value, 0, JsonValue)

    def test_strict_json_adversarial_inputs(self):
        bad = ('{"a":1,"a":2}', '{"a":1.2}', '{"a":NaN}',
               '{"a":2147483648}', '{"a":-2147483649}',
               '{"k":"\\ud800"}', '[1,]', '{"x":' + '[' * 10 + '0' + ']' * 10 + '}',
               '[' + ','.join('1' for _ in range(129)) + ']',
               '{"text":"' + 'x'*1025 + '"}', '{"a":' + '9'*1000 + '}')
        for raw in bad:
            with self.subTest(raw=raw[:100]), self.assertRaises((ValueError, UnicodeError)):
                loads(raw)
        with self.assertRaises(ValueError):
            validate_json({"bad": 2.5})
        with self.assertRaises(ValueError):
            validate_json({42: "bad"})
        with self.assertRaises(ValueError):
            dumps(JsonValue("X"*1025))

    def test_json_arguments_and_nested_access(self):
        source = '''host "JSON CLI"
arg payload: json
json_get_json items from payload at "values"
json_count size from items
json_get_int first from items at 0
let computed = first + size
emit computed
'''
        program = parse_host(source)
        with tempfile.TemporaryDirectory() as root:
            result = run_host(program, root=root, trusted=True,
                              supplied=['payload={"values":[4,8,12]}'])
        self.assertEqual(result["result"], 7)
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                run_host(program, root=root, trusted=True,
                         supplied=['payload={"values":[1.5]}'])

    def test_json_document_cannot_escape_into_core_expression(self):
        for statement in ("let alias = payload", "let raw = concat(payload, \"x\")",
                          "emit payload"):
            with self.subTest(statement=statement), self.assertRaises(ValueError):
                parse_host('host "NoImplicit"\narg payload: json\n' +
                           statement + '\nemit "ok"\n')

    def test_json_typed_fields_and_duplicate_set(self):
        source = '''host "Create JSON"
arg enabled: bool
arg title: text
json_object output
json_set output.enabled = enabled
json_set output.title = title
emit_json output
'''
        with tempfile.TemporaryDirectory() as root:
            actual = run_host(parse_host(source), root=root, trusted=True,
                              supplied=["enabled=true", "title=hello"])
        self.assertEqual(actual["result"], {"enabled": True, "title": "hello"})
        with tempfile.TemporaryDirectory() as root:
            bad = source.replace('json_set output.title = title',
                                 'json_set output.enabled = title')
            with self.assertRaises(ValueError):
                run_host(parse_host(bad), root=root, trusted=True,
                         supplied=["enabled=true", "title=hello"])


class ScopedIO(unittest.TestCase):
    def fixture(self, root):
        workspace = Path(root)
        for name in ("inbox", "outbox", "private"):
            (workspace / name).mkdir()
        (workspace / "inbox" / "config.json").write_text(
            '{"owner":"Никита","active":true,"meta":{"v":1}}', encoding="utf-8")
        (workspace / "inbox" / "notes.txt").write_text("hello", encoding="utf-8")
        (workspace / "private" / "secret.txt").write_text("private", encoding="utf-8")
        return workspace

    def run_inventory(self, workspace, **changes):
        kw = dict(root=str(workspace), trusted=True,
                  allow_read=True, allow_list=True, allow_write=True,
                  read_scope="inbox", write_scope="outbox", list_scope="inbox",
                  supplied=["source=config.json"])
        kw.update(changes)
        return run_host(parse_host(INVENTORY), **kw)

    def test_json_and_directory_snapshot_scoped_by_independent_roots(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = self.fixture(root)
            result = self.run_inventory(workspace)
            self.assertEqual(result["written"], "inventory.json")
            obj = result["result"]
            self.assertEqual(obj["owner"], "Никита")
            self.assertEqual(obj["count"], 2)
            self.assertEqual(obj["entries"], [
                {"name": "config.json", "kind": "file"},
                {"name": "notes.txt", "kind": "file"}])
            saved = json.loads((workspace/"outbox"/"inventory.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, obj)
            self.assertFalse((workspace/"inbox"/"inventory.json").exists())
            self.assertFalse((workspace/"inventory.json").exists())

    def test_denied_missing_grants_scope_escape_and_linked_dir(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = self.fixture(root)
            for change in ({"allow_read":False}, {"allow_list":False}, {"allow_write":False},
                           {"read_scope":"private"}, {"write_scope":"inbox/nonexistent"},
                           {"list_scope":"../private"}):
                with self.subTest(change=change), self.assertRaises((OSError, ValueError)):
                    self.run_inventory(workspace, **change)
            (workspace/"shortcut").symlink_to(workspace/"private", target_is_directory=True)
            with self.assertRaises((OSError, ValueError)):
                self.run_inventory(workspace, list_scope="shortcut")
            self.assertFalse((workspace/"outbox"/"inventory.json").exists())

    def test_directory_entries_symlink_and_entry_limit(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = self.fixture(root)
            (workspace/"inbox"/"symlink").symlink_to(workspace/"private"/"secret.txt")
            with self.assertRaises((OSError, ValueError)):
                self.run_inventory(workspace)
            (workspace/"inbox"/"symlink").unlink()
            for number in range(32):
                (workspace/"inbox"/f"{number}.txt").write_text("", encoding="utf-8")
            with self.assertRaises(ValueError):
                self.run_inventory(workspace)

    def test_one_mutation_and_rollback_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = self.fixture(root)
            target = workspace/"outbox"/"inventory.json"
            target.write_text("untouched", encoding="utf-8")
            (workspace/"inbox"/"config.json").write_text('{"bad":1,"bad":2}')
            with self.assertRaises(ValueError):
                self.run_inventory(workspace)
            self.assertEqual(target.read_text(), "untouched")
            for source in (
                'host "Two"\nmkdir "a"\nmkdir "b"\nemit "x"\n',
                'host "Two"\nwrite "a" = "ok"\nrmdir "b"\nemit "x"\n',
                'host "Two"\nwrite_json "a" = missing\nemit "x"\n',
            ):
                with self.assertRaises(ValueError):
                    parse_host(source)

    def test_create_remove_empty_directory_capabilities(self):
        mk = parse_host('host "mkdir"\narg folder: text\nmkdir folder\nemit "created"\n')
        rm = parse_host('host "rmdir"\narg folder: text\nrmdir folder\nemit "removed"\n')
        with tempfile.TemporaryDirectory() as root:
            workspace = self.fixture(root)
            base = dict(root=root, trusted=True, allow_write=True, write_scope="outbox",
                        supplied=["folder=newdir"])
            with self.assertRaises(ValueError):
                run_host(mk, **base)
            result = run_host(mk, **base, allow_mkdir=True)
            self.assertEqual(result["result"], "created")
            self.assertTrue((workspace/"outbox"/"newdir").is_dir())
            with self.assertRaises(ValueError):
                run_host(rm, **base)
            (workspace/"outbox"/"newdir"/"inside").write_text("keep")
            with self.assertRaises(OSError):
                run_host(rm, **base, allow_rmdir=True)
            (workspace/"outbox"/"newdir"/"inside").unlink()
            result = run_host(rm, **base, allow_rmdir=True)
            self.assertEqual(result["result"], "removed")
            self.assertFalse((workspace/"outbox"/"newdir").exists())

    def test_read_json_rejects_invalid_utf8_and_oversize(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = self.fixture(root)
            program = parse_host('host "ReadJSON"\nread_json doc from "data.json"\nemit_json doc\n')
            opts = dict(root=root, trusted=True, allow_read=True, read_scope="inbox")
            (workspace/"inbox"/"data.json").write_bytes(b"\xff")
            with self.assertRaises((OSError, ValueError)):
                run_host(program, **opts)
            (workspace/"inbox"/"data.json").write_bytes(b" " * 4097)
            with self.assertRaises(ValueError):
                run_host(program, **opts)

    def test_scope_no_ambient_access_to_other_directory(self):
        source = ('host "ReadScope"\narg filename: text\n'
                  'read content from filename\nemit content\n')
        with tempfile.TemporaryDirectory() as root:
            ws = self.fixture(root)
            program = parse_host(source)
            with self.assertRaises((OSError, ValueError)):
                run_host(program, root=root, trusted=True, allow_read=True,
                         read_scope="inbox", supplied=["filename=../private/secret.txt"])
            with self.assertRaises((OSError, ValueError)):
                run_host(program, root=root, trusted=True, allow_read=True,
                         read_scope="inbox", supplied=["filename=private/secret.txt"])
            self.assertEqual((ws/"private"/"secret.txt").read_text(), "private")


class HostA2CLI(unittest.TestCase):
    def call(self, *args):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)],
                              capture_output=True, text=True, timeout=15)

    def test_cli_end_to_end_json_scoped_and_web_denial(self):
        with tempfile.TemporaryDirectory() as root:
            ws = Path(root)
            (ws/"inbox").mkdir()
            (ws/"outbox").mkdir()
            (ws/"inbox"/"config.json").write_text('{"owner":"a"}')
            script = ws/"source.sdr"
            script.write_text(INVENTORY)
            args = ("host","run",script,"--root",ws,"--trusted","--allow-read",
                    "--allow-list","--allow-write","--read-scope","inbox",
                    "--write-scope","outbox","--list-scope","inbox",
                    "--arg","source=config.json")
            check = self.call("host","check",script)
            self.assertEqual(check.returncode,0,check.stderr)
            denied = self.call(*[a for a in args if a!="--allow-list"])
            self.assertNotEqual(denied.returncode,0)
            self.assertFalse((ws/"outbox"/"inventory.json").exists())
            ok = self.call(*args)
            self.assertEqual(ok.returncode,0,ok.stderr)
            self.assertEqual(json.loads(ok.stdout)["result"]["count"],1)
            for target in ("web","android","webapp","site"):
                with self.subTest(target=target):
                    path = ws/("target-"+target)
                    result = self.call("build",target,script,"--output",path)
                    self.assertNotEqual(result.returncode,0)
                    self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
