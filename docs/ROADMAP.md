# Sedrava roadmap

Current: Rust 0.12.0-alpha.2, the primary implementation. Alpha is not a claim of production readiness.

| Milestone | Status |
| --- | --- |
| Rust-only product and canonical CLI | Current release line |
| App core / Site / WebApp / Android generation | Implemented subset; extend target-specific conformance |
| Server and database-api | A21 loopback, auth and bounded transactions |
| SedravaSQL | NativeLog SQL B23; B25 separate pager/tree |
| Self-host | A5.11b bounded nested control; extend types and consolidate compiler |
| Performance | Remeasure event-driven HTTP, optimize query scans, generated Web and Android output |
| Storage | Integrate B+Tree with SQL only after recovery, ownership and migration gates |
| Full-stack | Same-origin client/API/data integration, security gates, examples |
| Distributions | Linux first; Windows/macOS after actual build and execution |
| Beta/stable | Browser/device tests, security review, compatibility contract, recovery and release validation |

[Current documentation](README.ru.md) · [Self-hosting](SELF_HOSTING_ROADMAP.ru.md) · [Benchmark baseline](BENCHMARK_2026_11_24.ru.md).
