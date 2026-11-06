# Sedrava Effects & Targets 0.12 A1 — experimental

**This is a stacked draft, not a published release.** It introduces an
auditable effect graph and canonical manifest for the existing pure typed
app-function domain only. It does not implement Host, Server, effectful
user-defined functions, general-purpose generics or worker execution.

Principle: **Types restrict values; effects restrict actions; runtimes
grant actual capabilities.**

Syntax for an optional explicit pure contract:

~~~text
fn increment(x: int) -> int effects pure = x + 1
~~~

Existing \`fn ... = ...\` declarations stay valid. Any annotation like
\`effects { host.fs.read }\` remains unsupported and is rejected.

~~~sh
python sedrava_cli.py effects examples/effects_pure_012.sdr --target web
~~~

The CLI checks the source using the existing typed compiler and checked
import expansion, infers function call effects, checks static target
compatibility and emits a canonical \`sedrava.effects.v1\` JSON manifest.
The \`source_sha256\` covers the *expanded source*; it changes when an
imported function body changes. It is not a deployment signature.

The public \`sedrava_effects.py\` helper checks transitive typed call
graphs, explicit upper-bound contracts, disallows unclassified/dynamic
calls and rejects effects not allowed for a target. Identifiers including
\`host.fs.read\`, \`server.db.read\` and \`web.api\` are **reserved effect
names, not callable functions or runtime permissions**.

This A1 manifest has \`kind: app-domain\` and **must not** be used as a
complete Web/UI storage, HTTP, Server, or Host capability manifest. It
does not infer all external effects in the product; those effect sources
are not yet registered in the compiler. The runtime does not rely on
this manifest for authorization.

Next stages: mandatory public exported-function contracts (with legacy
compatibility), end-to-end target verification across imported functions,
typed error variants with payloads and exhaustive match, host integration
and independently enforced execution permissions. NO-GO for merge,
release or deployment until full CI and security review.
