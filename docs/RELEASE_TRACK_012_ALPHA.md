# Sedrava 0.12.0a1 — proposed alpha acceptance

**Status:** separate experimental source candidate on `release/012-alpha1-preparation`. No publication, tag, merge to main or deployment.

Parent: experimental 0.12 [packages PR #41](https://github.com/VasiliiBabkin/sedrava/pull/41), based on [provenance #40](https://github.com/VasiliiBabkin/sedrava/pull/40), [namespaces #39](https://github.com/VasiliiBabkin/sedrava/pull/39), and unmerged [0.11 Web integration #36](https://github.com/VasiliiBabkin/sedrava/pull/36). The planned 0.11 release candidate is handled independently by [PR #42](https://github.com/VasiliiBabkin/sedrava/pull/42).

## Gates (all required before any alpha tag)

1. Full Python, browser, Android and original 0.10 compatibility gates pass for the exact head SHA.
2. Alias/private/duplicate/cycle/path/symlink/resource limits and old flat imports have positive and negative acceptance.
3. Report errors against original imported file and line; document missing full columns/typed IR.
4. Exact local vendor package versions, SHA-256 lockfile and transitive dependency validations pass; no network fetch is introduced.
5. Source and distribution packages, clean installs, deterministic regeneration and tamper rejection are verified.
6. Final alpha is rebased or otherwise reconciled on the **approved 0.11 release baseline** and retested; do not silently substitute an unreleased 0.11 preview.
7. RU/EN official docs and website show published 0.10/0.11 only when verifiably published and explicitly mark the alpha experimental.
8. Owner approves immutable SHA, build artifact digest, target and limitations before any GitHub release/tag/PyPI upload.

The read-only candidate workflow never publishes. The historical PyPI publisher remains pinned to v0.10.0. A new reviewed, least-privilege publishing route is required for future versions.

## Deliberate omissions

No semver resolver/online package manager, full native typed-IR symbols, importable mutable state, trusted server/SQLite, authentication, migrations or real multiuser isolation. These are not blockers for an explicitly limited **alpha**, but are not promised as present.
