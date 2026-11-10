# Sedrava trusted Host A4: typed JSON text lookup (experimental)

Branch `dev/offline-012` only. Not part of released stable 0.11 or the frozen 0.12.0a1 release-candidate acceptance scope. Trusted POSIX local sources only; not an untrusted-code sandbox.

`try_json_get_text target from json_document at text_or_int_key` produces nominal `Result<text,HostJsonLookupError>`, stable family ID `sedrava.host.json.lookup.v1`. Its closed, zero-field variants are `MissingKey` (absent object key), `InvalidIndex` (invalid/out-of-range array index), and `UnexpectedType` (non-text value or incompatible container/selector). The existing statically checked terminal Host `match` validates coverage and bounded pure `let`/final `emit` arms. The old `json_get_text` stays unchanged.

Try `examples/host_json_typed_013.sdr` with:

```sh
python sedrava_cli.py host check examples/host_json_typed_013.sdr
python sedrava_cli.py host run examples/host_json_typed_013.sdr --root . --trusted --arg 'config={"title":"Sedrava"}' --result-protocol v1
python scripts/offline_verify.py quick
```

In-memory lookup needs no read grant; reading a JSON **file** still requires `--allow-read`. Strict Host A2 JSON validation limits continue to apply (4096 bytes, 128 nodes, max depth 8, max 32 object fields, max 1024 Unicode scalars in text). Malformed input JSON, capability/policy denial, budget failures and engine faults are not catchable Results. No input JSON or key is automatically included in error variants. User-authored `emit` may deliberately expose user data.

Only text lookup is supported, not generic typed JSON, arbitrary blocks in Host match, remote server calls, workers, or access to the browser/Android filesystem. Full cross-target and packaging acceptance has not been executed on this branch; no release/tag/publishing authorization is implied.
