# Sedrava 0.12.0a1 — proposed alpha acceptance

**Status:** unpublished experimental source candidate **reintegrated on top of published stable [0.11.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0)** ([PyPI](https://pypi.org/project/sedrava/0.11.0/)), on `integration/012-alpha1-stable-base`. No 0.12 tag, PyPI upload, merge into stable main or production deployment. Android alpha versionCode 12001 (stable 0.11: 11002).

**Provenance:** the namespace/provenance/lockfile code is carried from original experimental [PR #39](https://github.com/VasiliiBabkin/sedrava/pull/39), [#40](https://github.com/VasiliiBabkin/sedrava/pull/40), [#41](https://github.com/VasiliiBabkin/sedrava/pull/41) and source-alpha [#43](https://github.com/VasiliiBabkin/sedrava/pull/43). The old stack was based on a pre-release Web branch; the new integration branch starts from the **published 0.11 stable tree**, preserves the 0.12-only code blobs, and reconciles version, tests and docs separately. Do not treat historical green checks on #43 as acceptance of this new SHA.

## Gates (all required before any alpha tag)

1. Full Python, browser, Android and original 0.10 compatibility gates pass for the exact head SHA.
2. Alias/private/duplicate/cycle/path/symlink/resource limits and old flat imports have positive and negative acceptance.
3. Report errors against original imported file and line; document missing full columns/typed IR.
4. Exact local vendor package versions, SHA-256 lockfile and transitive dependency validations pass; no network fetch is introduced.
5. Source and distribution packages, clean installs, deterministic regeneration and tamper rejection are verified.
6. Alpha must be based on the **published stable 0.11.0** ([tag](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0)); that source integration has been prepared. The read-only candidate acceptance passed on `14951a74e57929777560003aa52a425391bc41b2` ([run 42371782797](https://github.com/VasiliiBabkin/sedrava/actions/runs/42371782797)); the PR-head browser/Android-domain matrix also passed ([run 42371782882](https://github.com/VasiliiBabkin/sedrava/actions/runs/42371782882)). The candidate job skipped two HTTP-browser tests because Playwright was not installed in that job; the HTTP API-specific E2E passed on the unchanged Host/Core parent SHA #57 ([run 42343889050](https://github.com/VasiliiBabkin/sedrava/actions/runs/42343889050)). This is not a claim that every test ran in one job. Any subsequent source or release-document commit requires fresh exact-head candidate checks. Preserve tested stable 0.11 behavior and explicitly test 0.12 versionCode 12001.
7. RU/EN docs and website must show the published stable [0.11.0](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0) and historic 0.10/0.11rc1 truthfully; mark alpha 0.12.0a1 unpublished until separately approved and released.
8. Owner approves immutable SHA, build artifact digest, target and limitations before any GitHub release/tag/PyPI upload.

The read-only candidate workflow never publishes. The historical PyPI publisher remains pinned to v0.10.0. A new reviewed, least-privilege publishing route is required for future versions.

## Latest stacked implementation status

Core namespaces/provenance/packages #52 is the base of Effects & Targets #55, typed Result/Error/match #56 and Host A3 integration #57. Exact head SHAs:

- #52: `59d003f9dfa4ae73e8724fdb24956a7d66921a80`
- #55: `cb10863ea8d82c8c4a73e8242d733226183ba2ac`
- #56: `06e4d435bbf168c5df64f6bcd73b54cba8797a64`
- #57: `46de3aa4d19f8ea641898e8f5537639548d71f42`
- #60: `14951a74e57929777560003aa52a425391bc41b2`

The #57 head SHA above is the verified value; do not use the older incorrect value `46de3aa45c6c88c2ccdeddf2ac2e8a66ea99e2d9b`. The #57 CI completed 16/16 surfaced workflows on its head. The #60 read-only candidate audit is complete on the SHA shown above, but these checks **do not automatically approve an alpha publication**. The audit is recorded in [release issue #59](https://github.com/VasiliiBabkin/sedrava/issues/59). No independent review has yet been submitted on the stacked PRs.

The `host` target executes **trusted local scripts only**; scoped file descriptors and capability flags are not a malicious-code sandbox. Actual independent security review and explicit owner approval remain required before a public alpha. The accepted brand assets from stable-main PR #58 are now copied into the read-only alpha candidate by reusing the exact Git blobs; the master PNG and every derivative must pass SHA-256 checks in the candidate workflow. This integration affects only release preparation, not historical Core/Host PRs.

## Deliberate omissions

No semver resolver/online package manager, full native typed-IR symbols, importable mutable state, trusted server/SQLite, authentication, migrations or real multiuser isolation. These are not blockers for an explicitly limited **alpha**, but are not promised as present.

## Release preparation checkpoint — 2026-11-14

Owner approved preparation and publication of experimental 0.12.0a1. Security fixes from PR #62 were merged into the release branch at `2d1d2052966776114071f02ec1d860ff3e2eaae4`. On that exact merge SHA, 16/16 surfaced GitHub Actions workflows completed successfully, including the read-only release candidate run https://github.com/VasiliiBabkin/sedrava/actions/runs/43551718450. This is an **integration checkpoint, not a final publishing SHA**: documentation changes below require fresh exact-head verification. Security disposition is **CONDITIONAL GO for trusted local POSIX execution only**; Host is not a sandbox, and hostile rename/mount races, atomic read snapshots and syscall timeouts are not guaranteed. See [Host A3 audit](SECURITY_AUDIT_HOST_A3.md).

Publication checklist (pending until verified):

- [x] Owner authorized the experimental alpha publication.
- [x] Merge PR #62 Host A3 security fixes into release candidate branch.
- [x] Verify 16/16 GitHub workflows on the integration merge SHA above.
- [ ] Verify CI and release candidate on the **final documentation/build SHA**.
- [ ] Record exact wheel/sdist and any APK SHA-256 digests from the final build artifacts; do not reuse earlier digests.
- [ ] Reconcile public RU/EN website and release notes with actual published status.
- [ ] Verify a least-privilege PyPI publishing route for 0.12.0a1; the historical publisher must not be assumed to support it.
- [ ] Create tag and GitHub release only from the final verified SHA; publish PyPI only after the publishing route is verified.

Until publication actually succeeds, 0.12.0a1 remains unpublished and 0.11.0 remains the published stable release.
