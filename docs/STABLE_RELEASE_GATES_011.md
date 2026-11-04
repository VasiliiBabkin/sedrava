# 0.11.0 stable acceptance checklist — source candidate only

Published baselines: [0.10.0 GitHub](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.10.0) · [0.10.0 PyPI](https://pypi.org/project/sedrava/0.10.0/); experimental [0.11.0rc1 GitHub](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1) · [0.11.0rc1 PyPI](https://pypi.org/project/sedrava/0.11.0rc1/). **0.11.0 is not published.**

1. Verify final immutable commit, version `0.11.0` and Android versionCode `11002` (strictly greater than published RC `11001`).
2. Require Python 3.10/3.12/3.13, existing legacy Web/Compose/Android/JVM/Lint tests and browser integration in Chromium, Firefox and WebKit. Disclose all actual skips.
3. Generate four real site/tasks/catalog/CRM projects; inspect resource, HTTP, storage and accessibility limits without claiming production security certification.
4. Produce and audit exact-source wheel/sdist, verify source/metadata/install contents and reproducible payloads, install each archive outside checkout.
5. Repeat **published PyPI 0.10.0 → 0.11.0 → 0.10.0** and **published PyPI 0.11.0rc1 → 0.11.0 → 0.11.0rc1** in isolated Python environments; check intact user source/data. Record exact archive digests.
6. Verify real Android API35 update 0.10.0 (10003) to 0.11.0 (11002) using unchanged application ID/signer, preserved storage, rejected normal downgrade and explicitly debug-only permitted rollback. RC-to-stable Android cannot be claimed tested without a separate real installation path.
7. Enforce read-only workflow and secret/security audit. Keep historical `publish-pypi.yml` pinned to `v0.10.0`; do not add wildcard publishing. Physical devices, production signing and automatic schema migrations remain out of scope.
8. Provide source SHA, passing exact-head workflow URLs, real artifact SHA-256, negative controls, known limitations and **explicit owner approval of the stable version and publication target** before merging/tagging/uploading.

No 0.12 namespace/package code or trusted server/database/auth is part of 0.11. The official website remains accurate about the [published RC](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.11.0rc1) until stable publication.

[EN candidate notes](RELEASE_NOTES_0_11_0.en.md) · [RU](RELEASE_NOTES_0_11_0.ru.md) · [original RC upgrade audit](UPGRADE_AUDIT_011.md).
