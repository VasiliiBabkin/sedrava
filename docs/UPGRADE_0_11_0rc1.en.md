# Test upgrading 0.10.0 to the unpublished 0.11.0rc1 candidate

This is an experimental candidate in PR #42, **not a published release**. Do not
use a presumed PyPI RC or tag. Obtain the wheel/sdist from a successful exact-head
candidate workflow, review its commit and SHA-256, and retain both original files.
The published baseline package is **`sedrava==0.10.0`**, not `sedrava-lang` or 0.9.

## Back up first

Keep user `.sdr` projects outside the virtual environment. Copy sources, imported
modules/assets, the old generated application, explicit CLI state files and raw
browser storage before testing. Preserve Android application ID and signing key.
No automatic storage migration, export or repair is provided. Do not clear storage
or uninstall an Android application to disguise a failed update as success.

## Recommended: independent environments

```sh
python -m venv .venv-010
.venv-010/bin/python -m pip install sedrava==0.10.0
.venv-010/bin/sedrava --version
python -m venv .venv-011
.venv-011/bin/python -m pip install /absolute/path/sedrava-0.11.0rc1-py3-none-any.whl
.venv-011/bin/sedrava --version
.venv-011/bin/sedrava check /absolute/path/project.sdr
.venv-011/bin/sedrava test /absolute/path/project.sdr
.venv-011/bin/sedrava run /absolute/path/project.sdr
```

Windows: replace `bin/python` and `bin/sedrava` with `Scripts/python.exe` and
`Scripts/sedrava.exe`. Run these commands outside a compiler checkout; otherwise
Python imports can accidentally use source files instead of installed packages.
For rollback, reactivate `.venv-010` and the backed-up compatible generated app.
New 0.11 `site`/`webapp` source is not expected to compile on 0.10.

## In-place installation and reverse installation

First download the old wheel and record its hash. In the **same** disposable venv:

```sh
python -m pip install /absolute/path/sedrava-0.10.0-py3-none-any.whl
sedrava --version
python -m pip install --force-reinstall /absolute/path/sedrava-0.11.0rc1-py3-none-any.whl
sedrava --version
python -m pip check
# Return to the exact original package; do not delete user projects or state.
python -m pip install --force-reinstall /absolute/path/sedrava-0.10.0-py3-none-any.whl
sedrava --version
python -m pip check
```

Expected versions are `sedrava 0.10.0`, `sedrava 0.11.0rc1`, `sedrava 0.10.0`.
The independent audit also checks that candidate-only modules are removed on reverse
installation, all four common project states match, and same-version wheel/sdist
and reinstalled generators produce identical complete output bytes.

## Web data and schema limits

Retain the **same origin, HTML pathname and exact app title** when replacing old
HTML with the candidate build. Query/hash navigation does not select a new store.
A changed host, path or title selects a different key; there is no automatic move.
Returning the old compatible HTML to the same address can restore compatible
accepted values written by the candidate. Source backups alone do not back up data.

The audit uses actual browser storage and UI actions, including Unicode, stable
record IDs, rename/completion/delete, cold reload and returning the previous HTML.
Malformed JSON, duplicate keys and incompatible fingerprints are rejected and
remain byte-for-byte intact after attempted edits and reload/rollback. Defaults
shown after rejection are **not a successful migration**. Restore a backed-up
compatible snapshot only after preserving the rejected original.

A real recompilation with list capacity 100 → 99 is also tested: saved data is
rejected even if it fits the new capacity, and the original remains recoverable.

The tests cover unchanged 0.10 scalar and records/navigation schemas, not arbitrary
schema changes or migration from `app` storage to new `webapp` storage. See
[the exact compatibility contract](COMPATIBILITY_010.md). No concurrent-writer,
power-loss, encryption or cross-device guarantee is implied.

## Android installation is a separate gate

Generate both APKs from the same user source using the installed published wheel
and candidate wheel. Same application ID and signer are mandatory; the tested
versionCode transition is **10003 → 11001**. A successful source build/JVM test is
not evidence of a device installation or data-preserving update.

The dedicated workflow uses a fresh **API35 emulator**. It seeds through the old
Compose UI, performs `adb install -r` without uninstall/clear, checks full stored
snapshots and cold launch, edits in RC, rotates/recreates Activity and uses system
Back. A normal lower-version `adb install -r` must fail with
`INSTALL_FAILED_VERSION_DOWNGRADE` and retain data. `adb install -r -d` is tested
**only for these debuggable, same-key APKs**; it is not a supported consumer/Play
production rollback mechanism. A production forward-fix build needs a monotonic
higher code and compatible schema. Uninstalling normally deletes application data.
Malformed/incompatible snapshots must remain intact across update/restart/debug
rollback. A debug signer must never be described as a production signing identity.

## Reproduce and review evidence

```sh
python scripts/check_upgrade_011.py --candidate-dist /absolute/verified/dist \
  --candidate-sha FULL_40_HEX_SHA --work /tmp/new-unique-upgrade-directory
python -m pip install playwright==1.62.0
python -m playwright install chromium
python scripts/test_upgrade_011_browser.py --work /tmp/new-unique-upgrade-directory
```

The work directory must be new and outside the checkout. The runner downloads the
real PyPI baseline and validates fixed hashes. Use `--candidate-version` for a later
candidate with the same supported contract. The read-only `upgrade-011.yml` builds
one candidate pair, transfers those exact files/generated projects to browser and
Android jobs, and emits an exact-SHA machine-readable final gate. It never publishes.

See [audit and original hashes](UPGRADE_AUDIT_011.md), [Russian instructions](UPGRADE_0_11_0rc1.ru.md)
and [release gates](RELEASE_TRACK_011.md). A technical GO is not owner authorization.
