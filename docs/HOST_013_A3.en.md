# Sedrava Host A3: typed reads and execution outcome v1

Experimental stacked integration of Core #56 with Host A2 #54. Not a
released or remotely callable worker. Trusted local POSIX code only; no
untrusted sandbox guarantees.

\`try_read result from path\` creates the existing Core
\`Result<text, HostReadError>\` and consumes only registered expected
errors. \`HostReadError\` is open, identity \`sedrava.host.read.v1\`,
with typed variants FileNotFound(path), PermissionDenied(path),
InvalidEncoding(path), InvalidPath(reason), ResourceTooLarge(limit_bytes),
TextTooLong(limit_scalars) and IOFailure(operation). A final checked \`match\` supports up to eight pure branch-local \`let\` bindings and a final scalar
\`emit\` per arm, requires Ok plus the final Err(error) fallback.
It reuses Core #56 ErrorType/ResultType/ResultValue and exhaustive
checker, not a separate handwritten Result evaluator.

CapabilityDenied/policy/symlink traversal is never an Err. Grant checks
happen before execution. Host remains separate from browser and Android.

\`sedrava host run ... --result-protocol v1\` emits versioned JSON with
one of success/failed/fault/rejected, setup/execute/commit phase and
not_started/not_applicable/committed/unknown commit state. An exception
after entering commit yields unknown, never automatic retry. Error
codes are sanitized; no machine paths or stack traces are included.
Default CLI output stays A2-compatible. No server API, auth, queue,
signed manifest, worker isolation, or untrusted-source execution.

Malformed JSON and expected JSON lookup/operation failures yield `failed`
outcomes with stable `INVALID_JSON`, `JSON_LOOKUP_FAILED`, and
`JSON_OPERATION_FAILED` codes. They are **not** yet catchable
`Result<JsonValue,E>` values; the bounded typed `match` applies to text `try_read`.

~~~sh
python sedrava_cli.py host check examples/host_typed_read_013.sdr
python sedrava_cli.py host run examples/host_typed_read_013.sdr --root build/a3 \
  --trusted --allow-read --read-scope read --arg filename=example.txt \
  --result-protocol v1
~~~

Only bounded pure-lets plus terminal-emit match arms and typed text reads are
implemented; general Host block actions, user-defined Host error
declarations, HostPath, scoped path type parameters and typed writes
remain future milestones. Do not merge, publish or deploy without
actual exact-head CI and security review.
