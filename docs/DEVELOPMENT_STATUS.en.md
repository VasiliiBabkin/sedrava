# Sedrava / SedravaSQL development status

## B31 development checkpoint · 24–25 November 2026

**Public releases remain unchanged:** [Sedrava 0.12.0-alpha.2](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.12.0-alpha.2) and [SedravaSQL 0.1.0-alpha.1](https://github.com/VasiliiBabkin/sedravasql/releases/tag/v0.1.0-alpha.1), Linux x86-64 GNU. Rust is the sole maintained Sedrava implementation. Neither release is production-ready.

| Track | Verified source basis | Status |
|---|---|---|
| Sedrava main | [896685c](https://github.com/VasiliiBabkin/sedrava/commit/896685ce31f915d1ab69223f98451c2504792cf7) | 83 Rust tests, 63 HTTP A17–A21 requests |
| SedravaSQL main | [363ccbc](https://github.com/VasiliiBabkin/sedravasql/commit/363ccbc9542ed8e3ecf41e3619f78823ffeb97d4) | NativeLog SQL B28, 67 tests, strict Clippy |
| Storage research | [a98e709](https://github.com/VasiliiBabkin/sedravasql/commit/a98e709cc591057298818d0972c12cf020054295) | B31, 81 tests, strict Clippy; not the SQL backend |

B26 reuses validated schemas; B27 directly decodes JSON scalars (row cache rejected); B28 bounds primary-key range reads in the in-memory ordered Replay. In the 2048-key paired experiment, 1/8/32-row ranges were 138.4×/89.7×/37.8× faster than forced full scans with a redundant predicate. Disk-tree projection B28-A was not adopted.

B29 implements a separate binary copy-on-write B+Tree, 4 KiB pages, 64-node cache, up to 16 distinct mutations per atomic batch. B30 builds independent compact copies preserving revisions, generation and tombstones (20,480 keys; final phase 50.79 to 10.94 MB). B31 adds checksummed overflow chains for UTF-8 text up to 64 KiB, inline up to 256 bytes (960 keys, 16.08 MB payload, 24.76 to 18.87 MB after compaction). Compact-copy materialized payload budget is 32 MiB, verified at the exact boundary and one byte over.

Measurements are workload-specific on a shared VDS, not universal speedups or proof of superiority over SQLite. Process-exit tests do not establish physical power-loss durability. These post-release changes are not in the public archives. Milestone IDs are not release versions.

**Next:** B32 crash-safe reuse of unreachable pages; then durable receipts, migration, and SQL integration only after separate acceptance gates. No in-place vacuum, arbitrary BLOBs, automatic compact-file switch, production reliability or multi-user SQL server. NativeLog remains authoritative for SQL. Test data only.

**Reports and raw evidence:** [B26](https://github.com/VasiliiBabkin/sedravasql/blob/main/docs/NATIVE_SQL_B26_PERFORMANCE.ru.md) · [B27](https://github.com/VasiliiBabkin/sedravasql/blob/main/docs/NATIVE_SQL_B27_PERFORMANCE.ru.md) · [B28](https://github.com/VasiliiBabkin/sedravasql/blob/main/docs/NATIVE_SQL_B28_ORDERED_RANGE.ru.md) · [B28-A](https://github.com/VasiliiBabkin/sedravasql/blob/research/b28-tree-sql/docs/NATIVE_SQL_B28_TREE_EXPERIMENT.ru.md) · [B29](https://github.com/VasiliiBabkin/sedravasql/blob/research/b29-cow-tree/docs/NATIVE_COW_B29.ru.md) · [B30](https://github.com/VasiliiBabkin/sedravasql/blob/research/b30-compact/docs/NATIVE_COW_B30.ru.md) · [B31](https://github.com/VasiliiBabkin/sedravasql/blob/research/b31-overflow/docs/NATIVE_COW_B31.ru.md).
