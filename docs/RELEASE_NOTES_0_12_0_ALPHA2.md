# Sedrava 0.12.0-alpha.2 — Rust becomes the primary toolchain

The executable is now sedrava. sedrava-native remains a compatibility Cargo target using the same Rust implementation. Removed the old Python compiler, PyPI packaging and publishing workflows from the active source branch. Historical sources remain reachable by immutable release tags; the old distribution is no longer recommended. Current release remains alpha.

No new language semantics or storage-format migration is claimed. Linux x86-64 GNU is the initial distribution. Test-only Python scripts are not runtime dependencies. Installation is SHA-256 checked and fail-closed on overwrite. The previously published distributions are unchanged.

[Distribution](DISTRIBUTION_NATIVE.ru.md) · [History](HISTORY.md) · [Roadmap](ROADMAP.md).
