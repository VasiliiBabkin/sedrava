"""Experimental Effects & Targets 0.12 A1.

A small, fail-closed static effect checker for the already-typed function IR.
It does not create filesystem/network capabilities, implement effectful user
functions, or grant permissions. Future targets must explicitly register their
primitive operations before they can be accepted.
"""
import ast
import hashlib
import json
from dataclasses import dataclass

# These identifiers are versioned *compiler* effect identifiers, not privileges.
KNOWN_EFFECTS = frozenset({
    "host.fs.read", "host.fs.write", "host.fs.list",
    "host.fs.mkdir", "host.fs.rmdir",
    "server.db.read", "server.db.write", "server.http",
    "web.api",
})

# Target compatibility is a static upper bound, never permission to execute.
ALLOWED_TARGETS = {
    "app": frozenset(),
    "web": frozenset({"web.api"}),
    "android": frozenset(),
    "webapp": frozenset({"web.api"}),
    "site": frozenset(),
    "host": frozenset(x for x in KNOWN_EFFECTS if x.startswith("host.")),
    "server": frozenset(x for x in KNOWN_EFFECTS if x.startswith("server.")),
}
MAX_FUNCTIONS = 32
MAX_CALLS = 256


def normalize_effects(raw):
    """Validate a public declaration or a registered primitive effect set."""
    if raw is None:
        return None
    requested = tuple(raw)
    effects = frozenset(requested)
    if len(effects) != len(requested) or not effects <= KNOWN_EFFECTS:
        raise ValueError("Unknown or duplicate effect identifier")
    return effects


def require_target(target, effects):
    """Reject at compilation if even one effect is outside the target."""
    if target not in ALLOWED_TARGETS:
        raise ValueError("Unknown compilation target")
    effects = normalize_effects(tuple(effects))
    unsupported = effects - ALLOWED_TARGETS[target]
    if unsupported:
        raise ValueError("E_TARGET_EFFECT: " + target +
                         " does not support " + ", ".join(sorted(unsupported)))
    return effects


@dataclass(frozen=True)
class FunctionEffect:
    name: str
    direct: frozenset
    effective: frozenset
    declared: frozenset | None


def infer_function_effects(functions, *, primitive_effects=None, contracts=None):
    """Transitive, validated effect closure for a bounded call graph.

    The normal Sedrava expression parser attaches .pure_function metadata to
    validated direct user calls. Every registered effectful primitive must
    have a known symbol and an explicit effect set. Unknown/untyped dynamic
    invocation cannot be used as an effect escape hatch.
    """
    primitive_effects = {} if primitive_effects is None else dict(primitive_effects)
    contracts = {} if contracts is None else dict(contracts)
    if len(functions) > MAX_FUNCTIONS:
        raise ValueError("Function effects resource limit")
    if set(contracts) - set(functions):
        raise ValueError("Contract for unknown function")
    for key, values in primitive_effects.items():
        if not isinstance(key, str) or not key.isidentifier():
            raise ValueError("Invalid primitive effect signature")
        normalize_effects(tuple(values))

    edges = {}
    direct = {}
    for name, function in functions.items():
        dependencies = set()
        native_effects = set()
        count = 0
        for node in ast.walk(function.body):
            if not isinstance(node, ast.Call):
                continue
            count += 1
            if count > MAX_CALLS:
                raise ValueError("Function call graph exceeds resource limit")
            if hasattr(node,'error_type'):
                from sedrava_errors import checked_constructor_metadata
                checked_constructor_metadata(node)
                continue  # Typed closed constructor, not an external call edge.
            if hasattr(node,'result_operation'):
                from sedrava_results import checked_binding_metadata
                checked_binding_metadata(node)
                continue
            if not isinstance(node.func, ast.Name):
                raise ValueError("Indirect/dynamic effectful calls are unsupported")
            target = node.func.id
            callee = getattr(node, "pure_function", None)
            if callee is not None:
                if target not in functions or callee is not functions[target]:
                    raise ValueError("Function call metadata does not match typed IR")
                dependencies.add(target)
            elif target in functions:
                raise ValueError("Unchecked call edge in typed function IR")
            elif target in primitive_effects:
                native_effects.update(primitive_effects[target])
            elif not any(hasattr(node, marker) for marker in (
                "pure_builtin", "result_operation", "collection_query",
                "collection_operation", "record_type", "query_function",
                "list_operation", "list_query", "sequence_operation",
            )):
                # A typed expression may contain legacy collection primitives.
                # Only the actual typed compiler is allowed to designate
                # unknown calls as pure; never infer safety from an identifier.
                raise ValueError("Unclassified function call: " + target)
        edges[name] = dependencies
        direct[name] = frozenset(native_effects)

    visiting, cache = set(), {}

    def solve(name):
        if name in cache:
            return cache[name]
        if name in visiting:
            raise ValueError("Recursive effects require a separately bounded contract")
        visiting.add(name)
        total = set(direct[name])
        for callee in sorted(edges[name]):
            total.update(solve(callee))
        visiting.remove(name)
        cache[name] = frozenset(total)
        return cache[name]

    result = {}
    for name in sorted(functions):
        actual = solve(name)
        function = functions[name]
        declared = contracts.get(name, getattr(function, "declared_effects", None))
        if declared is not None:
            declared = normalize_effects(tuple(declared))
            if not actual <= declared:
                diff = ", ".join(sorted(actual - declared))
                raise ValueError("E_PUBLIC_EFFECT: " + name + " exceeds declared effects: " + diff)
        result[name] = FunctionEffect(name, direct[name], actual, declared)
    return result


def manifest_for_program(program, source, target="app"):
    """Manifest of the already-checked pure expression/function domain.

    This is intentionally NOT a complete Web UI, persistence or server
    deployment manifest. Such runtime effects require separate audited
    registrations in subsequent milestones.
    """
    functions = getattr(program, "functions", None)
    if not isinstance(functions, dict):
        raise ValueError("Expected typed app program")
    inferred = infer_function_effects(functions)
    # Current app-domain operations are deterministic/pure or local state.
    # Host/server primitives are not part of the 0.12 app parser.
    effects = frozenset().union(*(f.effective for f in inferred.values()))
    require_target(target, effects)
    return {
        "schema": "sedrava.effects.v1",
        "kind": "app-domain",
        "target": target,
        "source_sha256": hashlib.sha256(str(source).encode("utf-8")).hexdigest(),
        "effective": sorted(effects),
        "functions": [
            {"name": name, "effective": sorted(f.effective),
             "declared": sorted(f.declared) if f.declared is not None else None}
            for name, f in sorted(inferred.items())
        ],
    }


def canonical_manifest_json(manifest):
    if manifest.get("schema") != "sedrava.effects.v1":
        raise ValueError("Unknown effect manifest version")
    return json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
