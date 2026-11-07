"""A3 host-only static effect manifest derived from checked HostStep instructions.

An effect manifest reports *requirements*, not grants. No source-supplied
effect list can increase privileges. This does not attest to a deployed
worker, nor authorize untrusted code.
"""
import hashlib
import json

from sedrava_effects import require_target
from sedrava_host import HostProgram, HostStep

_EFFECTS = {
    "read": frozenset(("host.fs.read",)),
    "try_read": frozenset(("host.fs.read",)),
    "read_json": frozenset(("host.fs.read",)),
    "list_dir": frozenset(("host.fs.list",)),
    "write": frozenset(("host.fs.write",)),
    "write_json": frozenset(("host.fs.write",)),
    "mkdir": frozenset(("host.fs.write", "host.fs.mkdir")),
    "rmdir": frozenset(("host.fs.write", "host.fs.rmdir")),
    "let": frozenset(),
    "json_get": frozenset(),
    "json_count": frozenset(),
    "json_object": frozenset(),
    "json_set": frozenset(),
    "emit": frozenset(),
    "emit_json": frozenset(),
    "match": frozenset(),
}


def infer_host_effects(program):
    if not isinstance(program, HostProgram) or len(program.steps) > 64:
        raise ValueError("Invalid bounded HostProgram")
    effects = set()
    for step in program.steps:
        if not isinstance(step, HostStep) or step.operation not in _EFFECTS:
            raise ValueError("Unclassified Host operation")
        if step.operation == "match":
            if not isinstance(step.second, tuple) or not step.second:
                raise ValueError("Malformed Host match")
            for arm in step.second:
                if len(arm.body) != 1 or arm.body[0].operation != "emit":
                    raise ValueError("Host match effects require verified scalar-only branch")
        effects.update(_EFFECTS[step.operation])
    return require_target("host", effects)


def host_effect_manifest(program, source):
    effects = infer_host_effects(program)
    return {
        "schema": "sedrava.host.effects.v1",
        "target": "host",
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "effective": sorted(effects),
        "required_grants": sorted(
            option for needed, option in (
                (program.needs_read, "--allow-read"),
                (program.needs_write, "--allow-write"),
                (program.needs_list, "--allow-list"),
                (program.needs_mkdir, "--allow-mkdir"),
                (program.needs_rmdir, "--allow-rmdir"),
            ) if needed
        ),
    }


def canonical_host_manifest(program, source):
    return json.dumps(host_effect_manifest(program, source), ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"))
