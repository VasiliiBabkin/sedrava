"""Effects & Targets A1: real compiler regression plus negative effect graph gates."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sedrava_core import parse, run
from sedrava_effects import (
    canonical_manifest_json, infer_function_effects, manifest_for_program,
    normalize_effects, require_target,
)
from sedrava_functions import FunctionType

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "sedrava_cli.py"
EXAMPLE = '''app "Effect A1"
fn increase(x: int) -> int effects pure = x + 1
fn twice(y: int) -> int = increase(increase(y))
state total = twice(2)
action update: total = twice(total)
screen main:
    value total
test update:
    total == 6
'''


def call(name):
    return ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=[], keywords=[])


def function(name, body):
    return FunctionType(name, (), int, body, 1)


class EffectContracts(unittest.TestCase):
    def test_explicit_pure_signature_executes_in_existing_core(self):
        program = parse(EXAMPLE)
        self.assertEqual(run(program), 1)
        self.assertEqual(program.functions["increase"].declared_effects, frozenset())
        self.assertIsNone(program.functions["twice"].declared_effects)
        inferred = infer_function_effects(program.functions)
        self.assertEqual(inferred["increase"].effective, frozenset())
        self.assertEqual(inferred["twice"].effective, frozenset())
        data = manifest_for_program(program, EXAMPLE, "web")
        self.assertEqual(data["effective"], [])
        self.assertEqual(data["kind"], "app-domain")
        self.assertEqual(data["source_sha256"], hashlib.sha256(EXAMPLE.encode()).hexdigest())
        self.assertEqual(canonical_manifest_json(data), canonical_manifest_json(data))

    def test_unsupported_effect_annotation_is_compile_error(self):
        for declaration in (
            'fn escalate(x: int) -> int effects { host.fs.read } = x',
            'fn escalate(x: int) -> int effects host.fs.read = x',
            'fn escalate(x: int) -> int effects all = x',
        ):
            with self.subTest(declaration=declaration), self.assertRaises(ValueError):
                parse('app "Denied"\n' + declaration + '\nstate n = 0\nscreen main:\n    value n\n')

    def test_effectful_primitive_propagates_transitively(self):
        leaf = function("leaf", call("read_file"))
        mid_call = call("leaf")
        mid_call.pure_function = leaf
        mid = function("mid", mid_call)
        top_call = call("mid")
        top_call.pure_function = mid
        top = function("top", top_call)
        graph = {"leaf": leaf, "mid": mid, "top": top}
        effects = infer_function_effects(graph, primitive_effects={"read_file": ("host.fs.read",)})
        self.assertEqual(effects["top"].effective, frozenset({"host.fs.read"}))
        self.assertEqual(effects["mid"].effective, frozenset({"host.fs.read"}))
        self.assertEqual(require_target("host", effects["top"].effective), frozenset({"host.fs.read"}))
        for target in ("web", "android", "app", "server"):
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, "E_TARGET_EFFECT"):
                require_target(target, effects["top"].effective)
        with self.assertRaisesRegex(ValueError, "E_PUBLIC_EFFECT"):
            infer_function_effects(graph,
                primitive_effects={"read_file": ("host.fs.read",)},
                contracts={"top": ()})
        declared = infer_function_effects(graph,
            primitive_effects={"read_file": ("host.fs.read",)},
            contracts={"top": ("host.fs.read",)})
        self.assertEqual(declared["top"].declared, frozenset({"host.fs.read"}))

    def test_untyped_or_dynamic_calls_cannot_escape_effect_checker(self):
        leaf = function("leaf", ast.Constant(value=1))
        unannotated = function("top", call("leaf"))
        with self.assertRaisesRegex(ValueError, "Unchecked call edge"):
            infer_function_effects({"leaf": leaf, "top": unannotated})
        evil = function("evil", call("open"))
        with self.assertRaisesRegex(ValueError, "Unclassified function call"):
            infer_function_effects({"evil": evil})
        dynamic = function("dynamic", ast.Call(
            func=ast.Attribute(value=ast.Name(id="x", ctx=ast.Load()), attr="run", ctx=ast.Load()),
            args=[], keywords=[]))
        with self.assertRaisesRegex(ValueError, "Indirect/dynamic"):
            infer_function_effects({"dynamic": dynamic})
        self.assertEqual(normalize_effects(x for x in ("host.fs.read",)), frozenset({"host.fs.read"}))
        with self.assertRaisesRegex(ValueError, "Unknown or duplicate"):
            normalize_effects(("host.fs.read", "host.fs.read"))
        with self.assertRaisesRegex(ValueError, "Unknown or duplicate"):
            normalize_effects(("host.shell.exec",))
        with self.assertRaisesRegex(ValueError, "Unknown compilation target"):
            require_target("windows-os", frozenset())

    def test_cycle_is_rejected_and_wrong_metadata_cannot_fake_pure(self):
        first_call = call("second")
        second_call = call("first")
        first = function("first", first_call)
        second = function("second", second_call)
        first_call.pure_function = second
        second_call.pure_function = first
        with self.assertRaisesRegex(ValueError, "Recursive effects"):
            infer_function_effects({"first": first, "second": second})
        first_call.pure_function = first
        with self.assertRaisesRegex(ValueError, "metadata"):
            infer_function_effects({"first": first, "second": second})

    def test_cli_manifest_is_stable_and_rejects_bad_program(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "main.sdr"
            path.write_text(EXAMPLE, encoding="utf-8")
            cmd = [sys.executable, str(CLI), "effects", str(path), "--target", "web"]
            first = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            second = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(first.stdout, second.stdout)
            payload = json.loads(first.stdout)
            self.assertEqual(payload["schema"], "sedrava.effects.v1")
            self.assertEqual(payload["functions"][0]["name"], "increase")
            path.write_text('app "Oops"\nfn leak(x: int) -> int effects { host.fs.read } = x\n'
                            'state n = 1\nscreen main:\n    value n\n')
            denied = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(denied.returncode, 0)
            self.assertNotIn('"schema"', denied.stdout)

    def test_cli_uses_verified_import_expansion(self):
        with tempfile.TemporaryDirectory() as directory:
            ws = Path(directory)
            (ws / "functions.sdr").write_text(
                'module util\nexport fn duplicate(x: int) -> int effects pure = x + x\n',
                encoding="utf-8")
            (ws / "main.sdr").write_text(
                'app "Modular effects"\nimport "functions.sdr" as util\n'
                'state n = util.duplicate(2)\nscreen main:\n    value n\n',
                encoding="utf-8")
            command = [sys.executable, str(CLI), "effects", str(ws / "main.sdr"), "--target", "web"]
            first = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(first.returncode, 0, first.stderr)
            result1 = json.loads(first.stdout)
            self.assertEqual(result1["effective"], [])
            (ws / "functions.sdr").write_text(
                'module util\nexport fn duplicate(x: int) -> int effects pure = x + 1\n',
                encoding="utf-8")
            second = subprocess.run(command, capture_output=True, text=True, timeout=15)
            self.assertEqual(second.returncode, 0, second.stderr)
            result2 = json.loads(second.stdout)
            self.assertNotEqual(result1["source_sha256"], result2["source_sha256"])


if __name__ == "__main__":
    unittest.main()
