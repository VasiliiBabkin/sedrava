# Independent security audit: Sedrava Host A3

## Scope and identity / Область проверки

Original release candidate: **102ae4a2198c1cdefb5ec65e0a37471370210287**
(release/012-alpha1-acceptance, PR #60). Audit branch:
security/host-a3-release-audit, based on that exact commit, not stable main.
No release/tag/package publication or deployment is authorized by this audit.

Reviewed: sedrava_host.py, sedrava_host_fs.py, sedrava_host_typed.py,
sedrava_host_protocol.py, sedrava_host_effects.py, Host CLI path,
existing Host A1/A2/A3 tests, JSON validation and Core expression limits.
Line numbers below refer to the original commit.

Threat model: trusted local POSIX programs, trusted OS account and workspace,
explicit grants. This is not an untrusted-code sandbox, remote authorization
layer, or isolation from a hostile process with the same filesystem rights.

## Findings / Дефекты

### H3-01 — Medium / P1: cleanup deletes a file this invocation did not create

Location: sedrava_host.py:399–401, 414–418.

Temporary name is recorded before O_CREAT|O_EXCL succeeds. If another file
collides, open raises FileExistsError, but finally unlinks that existing entry.
The destination is preserved, yet another operation's file can be deleted.
With 128 random bits a spontaneous collision is extraordinarily unlikely:
this is an error-path ownership defect, not practical random-name prediction.

Reproduce: precreate .sedrava-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.tmp with sentinel
content; inject token_hex -> "a"*32; execute an ordinary granted write. Original
code deletes the sentinel after EEXIST. Regression:
test_temp_collision_preserves_existing_file.

Fix: keep the candidate separate; mark temp as owned only after successful
exclusive creation. Never remove an entry whose creation failed.

### H3-02 — Low / P2: directory policy violations become engine faults

Location: sedrava_host_fs.py:58, 80; sedrava_host_protocol.py:_error_code.

Listing a symlink/special entry, or rmdir targeting a symlink/file, raises plain
ValueError. The protocol reports ENGINE_FAULT rather than POLICY_VIOLATION.
Operations fail closed: no traversal, no typed Err catch, no outside access.
This is observable misclassification, not a capability bypass.

Reproduce: list_dir "." containing a symlink; separately rmdir "link" with
the correct grants. Regressions: test_list_symlink_is_policy_fault and
test_rmdir_symlink_is_policy_fault. Fix: existing fatal HostPolicyViolation.

### H3-03 — Medium / P1: failed stdout after commit falsely reports no execution

Location: sedrava_cli.py:130, 134–138.

The CLI catches OSError around execution and printing. JSON delivery failure
after mutation is followed by rejected/setup/not_started. This misrepresents
committed work as a configuration rejection. A closed pipe can fail again,
but a transient failing stream can accept the false second response.

Reproduce: execute a real write with --result-protocol v1 while stdout raises
EIO on its first write and accepts later writes. File contains new bytes while
original CLI emits rejection. Regression:
test_cli_transport_failure_never_fabricates_setup_rejection.

Fix: only pre-execution compile/source errors outside execute_protocol produce
reject(). Once execution was attempted, transport failure returns nonzero with
no fabricated outcome and a fixed non-sensitive stderr notice. Missing delivery
acknowledgement is not rollback; do not replay automatically.

### H3-04 — Low / P2: deeply nested JSON exposes decoder recursion as engine fault

Location: sedrava_host_json.py:loads, json.loads exception handler (original
lines 103–108). A 3001-byte input consisting of 1500 opening brackets, 0,
1500 closing brackets is within the byte limit, but the Python decoder raises
RecursionError before the depth validator runs. On Python versions whose C decoder raises at this depth, the protocol says
ENGINE_FAULT rather than INVALID_JSON. Some CPython versions (observed 3.13)
finish decoding and correctly reject depth in the validator instead. No execution budget
exception is made catchable; the fix catches decoder-local RecursionError only.
Regression: test_deep_json_input_is_expected_failure_not_python_recursion_fault.

### H3-05 — Low / P2: bounded directory overflow is reported as engine fault

Location: sedrava_host_fs.py:47–48. A directory with 33 ordinary files hits the
documented 32-entry data limit, raises plain ValueError, becomes ENGINE_FAULT.
It must remain a failed bounded-data operation, not a claim the engine crashed.
Fix: existing HostResourceTooLarge -> failed/RESOURCE_TOO_LARGE. This does not
turn execution/work-budget or policy violations into typed read Results.
Regression: test_directory_entry_limit_is_data_failure_not_engine_fault.

## Boundaries checked / Границы модели

- Relative paths reject absolute/dot-dot/empty/control/backslash paths and
  oversized segments. Scoped traversal uses dir_fd, O_DIRECTORY, O_NOFOLLOW;
  final reads use O_NOFOLLOW|O_NONBLOCK and fstat regular/single-link validation.
- Every read/list/write/mkdir/rmdir grant is checked before opening root.
  mkdir/rmdir need allow-write plus the specific directory grant.
  Effect inference describes requirements, never grants them.
- Reads/writes reject pre-existing hardlinks; symlinks and FIFOs are refused.
  New files use mode 0600, directories 0700, subject to umask. A real chmod(0)
  read verifies that --allow-read does not bypass OS permissions (non-root).
- One mutation is deferred until all computations pass. A private exclusive
  temp is flushed/fsynced before one os.replace and parent fsync. Pre-replace
  failures preserve the destination. Post-replace/mkdir/rmdir failures may
  follow visible changes: commit_state unknown, retryable false.
- Existing post-replace-fsync and destination-symlink-swap tests are retained.
  New tests cover pre-replace failures and directory post-mutation fsync.
  Replacing a final symlink does not write through to its outside referent.
- An open parent descriptor is not retargeted by replacing its pathname with
  a symlink. However **hostile rename/mount races remain explicitly excluded**:
  moving an open scoped directory outside root causes later descriptor-relative
  operations there. A real rename/write regression records this limitation,
  not a sandbox guarantee. Root ancestors are operator-trusted; O_NOFOLLOW on
  its final component does not authenticate every ancestor or forbid mounts.
- Concurrent in-place mutation can produce mixed contents; listings are not
  atomic snapshots. Test: read abc, overwrite the inode, then read 123 -> abc123.
  Do not use Host as a transactional reader of actively modified data.
- Hardlink count is checked at observation time, not frozen against a same-UID
  hostile process. Non-POSIX, exotic/network filesystems and mount attacks are
  not certified by Linux tests.
- Limits: 64 statement/body lines, 16 args, 8 read/list operations, 4096 bytes
  per read, 1024 Core text scalars, eight pure lets plus emit per match arm.
  Existing AST depth/cost checks apply. Host has no general loops or execution
  of user-defined module/function bodies.
- Growing reads stop at 4097 bytes; FIFO rejected before reading. JSON has
  4096-byte serialization, depth 8, 128 nodes, 32 fields. There is no OS
  wall-clock/syscall timeout or disk quota: filesystem open/read/fsync can
  block. Use trusted local storage and an external OS supervisor if needed.
- try_read catches only registered expected errors. Policy and unknown
  engine/budget-like exceptions remain fatal; they never become ordinary Err.
- Error protocol has fixed codes + retryable false, no exception messages,
  tracebacks or operator root/scope paths. Explicit emit/file contents remain
  application data and may intentionally contain secrets/paths: this protocol
  is not a content-redaction/confidentiality boundary.
- Repeated failed reads check descriptor counts on Linux /proc.

## Test method and evidence / Испытания

24 additional tests use real temporary files/directories, hardlinks, symlinks,
FIFOs and deterministic syscall-boundary fault injection. This controls ordering
without pretending to exhaustively test kernel scheduling or all filesystems.

The audit workflow checks out original SHA in a separate worktree and runs
the same new suite. Exactly five consistently failing assertions are required, plus the deep-JSON
assertion only when an independent stdlib decoder probe raises RecursionError.
CPython decoder limits vary; fixed Host behavior is checked identically on all
versions. Unexpected errors/skips fail reproduction.
Then it runs fixed regressions, existing A1/A2/A3 tests, full Python regression
on 3.10/3.12/3.13 with Node 24, docs/security guards and clean wheel/sdist
checks. Artifacts record logs, original reproduction, tested SHA and hashes.

Execution results are generated by the workflow into the artifact report
SECURITY_AUDIT_HOST_A3.md and audit-result.json, with actual SHA, Python version,
run URL, counts, skips and verdict. Source documentation is not an execution
certificate; use artifacts from the exact candidate SHA. The local
executor is unavailable ("No usable execution environment is available";
environment ccarenv_b64_Y2NhcmVudl9lYTZlYWIyYmZhMmM4MTkxOTU5OWVjNjE1MjUzOWE0OA).
GitHub API inspection/changes work independently. No local tests are claimed.
An intermediate
workflow incorrectly required the decoder-recursion reproduction on every
Python version; the 3.13 run exposed that audit-harness assumption. It remains
visible in run 43492709125. The baseline gate now records the independent
stdlib probe, without weakening any fixed-Host assertion.

## Observed first checkpoint (not the final code gate)

At e69d2bb1dbcc575e6180817bd52efcb2e68720ce, hosted run
https://github.com/VasiliiBabkin/sedrava/actions/runs/43492362865 completed all
three Python 3.10/3.12/3.13 jobs successfully. Each ran 21 audit tests, existing
Host A1/A2/A3 suites (10/13/15), and full regression: 493 total, 491 passed,
two skipped because Playwright was not installed in those jobs. Wheel/sdist
metadata/archive and clean-install checks passed on all three.
The first four original-commit reproductions matched exactly. The later JSON,
directory-size and real chmod checks are not covered by this checkpoint:
their actual final-head results belong to the artifact described above.

## Decision / Решение

**NO-GO for the original candidate** until H3-01 and H3-03 are fixed.
Audit branch: **CONDITIONAL GO only if its exact-SHA audit workflow completes
all gates and emits the execution artifact**, with owner acceptance of the
race/timeout/delivery limitations. Otherwise NO-GO; no static-only approval.
Never advertise Host as hostile-code isolation.

Серьёзность: H3-01 и H3-03 — средняя/P1, H3-02/H3-04/H3-05 — низкая/P2. Исправления
изолированы в отдельной ветке. Враждебные переименования, несогласованные
конкурентные чтения, блокирующие системные вызовы и вывод секретов доверенной
программой не устранены и прямо ограничивают применимость заключения.

Stable main, parallel server branches, release artifacts, versions, grants,
tags, production and package registries remain unchanged.
