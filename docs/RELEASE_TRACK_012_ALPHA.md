# Sedrava 0.12.0a1 — proposed alpha acceptance

**Status:** unpublished experimental source candidate **reintegrated on top of published stable [0.11.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0)** ([PyPI](https://pypi.org/project/sedrava/0.11.0/)), on `integration/012-alpha1-stable-base`. No 0.12 tag, PyPI upload, merge into stable main or production deployment. Android alpha versionCode 12001 (stable 0.11: 11002).

**Provenance:** the namespace/provenance/lockfile code is carried from original experimental [PR #39](https://github.com/VasiliiBabkin/sedrava/pull/39), [#40](https://github.com/VasiliiBabkin/sedrava/pull/40), [#41](https://github.com/VasiliiBabkin/sedrava/pull/41) and source-alpha [#43](https://github.com/VasiliiBabkin/sedrava/pull/43). The old stack was based on a pre-release Web branch; the new integration branch starts from the **published 0.11 stable tree**, preserves the 0.12-only code blobs, and reconciles version, tests and docs separately. Do not treat historical green checks on #43 as acceptance of this new SHA.

## Gates (all required before any alpha tag)

1. Full Python, browser, Android and original 0.10 compatibility gates pass for the exact head SHA.
2. Alias/private/duplicate/cycle/path/symlink/resource limits and old flat imports have positive and negative acceptance.
3. Report errors against original imported file and line; document missing full columns/typed IR.
4. Exact local vendor package versions, SHA-256 lockfile and transitive dependency validations pass; no network fetch is introduced.
5. Source and distribution packages, clean installs, deterministic regeneration and tamper rejection are verified.
6. Alpha must be based on the **published stable 0.11.0** ([tag](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0)); that source integration has been prepared, but **fresh exact-head CI is still required**. Preserve tested stable 0.11 behavior and explicitly test 0.12 versionCode 12001.
7. RU/EN docs and website must show the published stable [0.11.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0) and historic 0.10/0.11rc1 truthfully; mark alpha 0.12.0a1 unpublished until separately approved and released.
8. Owner approves immutable SHA, build artifact digest, target and limitations before any GitHub release/tag/PyPI upload.

The read-only candidate workflow never publishes. The historical PyPI publisher remains pinned to v0.10.0. A new reviewed, least-privilege publishing route is required for future versions.

## Latest stacked implementation status

Core namespaces/provenance/packages #52 is the base of Effects & Targets #55, typed Result/Error/match #56 and Host A3 integration #57. Exact-head GitHub CI for #57 completed 16/16 workflows successfully on `46de3aa45c6c88c2ccdeddf2ac2e8a66ea99e2d9b`. Those checks **do not automatically approve an alpha publication**. The next independent read-only candidate audit is tracked in [release issue #59](https://github.com/VasiliiBabkin/sedrava/issues/59).

The `host` target executes **trusted local scripts only**; scoped file descriptors and capability flags are not a malicious-code sandbox. Actual security review and explicit owner approval remain required before a public alpha, The accepted brand assets from stable-main PR #58 are now copied into the read-only alpha candidate by reusing the exact Git blobs; the master PNG and every derivative must pass SHA-256 checks in the candidate workflow. This integration affects only release preparation, not historical Core/Host PRs.

## Deliberate omissions

No semver resolver/online package manager, full native typed-IR symbols, importable mutable state, trusted server/SQLite, authentication, migrations or real multiuser isolation. These are not blockers for an explicitly limited **alpha**, but are not promised as present.
