# Sedrava host A1 — experimental trusted local runner

Separate opt-in POSIX host execution, not part of the published stable 0.11.
**Not an operating-system sandbox.** Only run trusted programs and workspaces.

Host documents start with host "Name". sedrava host check file.sdr
type-checks without I/O. sedrava host run file.sdr requires --root DIR
and --trusted, with --allow-read / --allow-write for independent file grants.
No host effects are registered in Web, WebApp, site or Android targets.
No shell, subprocess, arbitrary Python, environment or network effects.

Supported instructions:

- arg name: text|int|bool: required strictly typed CLI argument
- let name = expr: pure Sedrava scalar expression
- read name from expr: UTF-8 text read within explicit workspace
- write expr = expr: one UTF-8 output file
- emit expr: required final scalar emitted in JSON

Run [host_report_013.sdr](../examples/host_report_013.sdr):

~~~sh
mkdir -p build/host-demo
printf 'Hello\n' > build/host-demo/input.txt
python sedrava_cli.py host check examples/host_report_013.sdr
python sedrava_cli.py host run examples/host_report_013.sdr \
  --root build/host-demo --trusted --allow-read --allow-write \
  --arg input=input.txt --arg output=report.txt --arg heading="Report: "
~~~

Limits: 16 args, 64 statements, eight reads, one write, 4096 UTF-8
bytes per file and 1024 Unicode scalar values per Sedrava text.
POSIX only; workspace-relative components cannot be empty/dot/dot-dot,
backslash, symbolic-link components or multiply hard-linked files.
Descriptor-relative access, O_NOFOLLOW, regular-file checks and atomic
single-file replace with fsync are used. Output permissions are 0600.

Not a hostile concurrent-directory-mutation defense or OS privilege boundary.
No binary files, directory creation, multi-file transactions, network, process
execution or Windows support. Do not put credentials in visible --arg values.

This source-only experiment must be explicitly reconciled with namespace
PR #47, bounded-core PRs #50/#51 and server PRs #48/#49. No releases, merges,
package publication or production deployments are authorized.
