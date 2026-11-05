# Sedrava Host A2 — scoped directories and typed JSON

**Experimental stacked draft based on Host A1.** Not a published 0.11
capability. No host file access is registered in browser or Android code.

JSON is host-only and has strict types: object, array, text, int32,
boolean and null. Floats, NaN, duplicate keys, overlong and invalid
Unicode values are rejected. Limits: 4096 UTF-8 bytes, 128 nodes,
depth 8, 32 object fields and 1024 Unicode scalar values per text.

Host A2 supports:

- arg payload: json — strict JSON CLI argument (do not pass secrets).
- read_json doc from path — bounded UTF-8 JSON read.
- json_get_text, json_get_int, json_get_bool, json_get_json
  value from doc at key — exact typed field or array-index lookup.
- json_count count from doc — array/object length.
- json_object result / json_set result.key = scalar_or_json_variable
  — build an object, rejecting duplicate key assignment.
- write_json path = document / emit_json document — canonical JSON
  file output and structured CLI result.
- list_dir entries from "." — sorted JSON array of up to 32 regular
  files and directories, with "name" and "kind" fields.
- mkdir path / rmdir path — create or remove a single empty directory,
  with no recursive traversal or parent auto-creation.

**Capabilities and scope confinement:** --root DIR defines an explicitly
trusted workspace. --read-scope, --write-scope and --list-scope select
independent relative directories inside it; program paths resolve relative
to each corresponding scope, never via absolute paths or dot-dot.
--trusted must always be given. Reads require --allow-read, listing
--allow-list, writes --allow-write, creation --allow-write --allow-mkdir,
removal --allow-write --allow-rmdir. No implied capabilities.

Example: [host_inventory_013.sdr](../examples/host_inventory_013.sdr)

~~~sh
mkdir -p build/demo/inbox build/demo/outbox
printf '{"title":"Inventory"}' > build/demo/inbox/config.json
python sedrava_cli.py host check examples/host_inventory_013.sdr
python sedrava_cli.py host run examples/host_inventory_013.sdr \
  --root build/demo --trusted --allow-read --allow-list --allow-write \
  --read-scope inbox --list-scope inbox --write-scope outbox \
  --arg input=config.json
~~~

One planned filesystem mutation occurs only after all computations pass.
This does not provide multi-file atomicity; fsync failure after a mutation
may leave the final state uncertain. POSIX only. The OS account and
workspace must be trusted; concurrent hostile directory renaming or
mount changes are outside the security guarantee. No process execution,
network, symlink following, automatic directory walk, binary I/O, secrets
protection, public HTTP service or hostile-code sandbox.

Namespace PR #47, bounded core PR #50/#51 and server PR #48/#49
are independent. No release, tag, PyPI or production change.
