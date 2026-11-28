# Sedrava roadmap

**Governing document:** [Sedrava declaration / Architecture Gate](DECLARATION.ru.md). The post-A32 priority is a high-level declarative domain model, a single source of truth, generated data/API/UI and validation on the A31 service desk. The milestones below preserve earlier planning context; they do not override this direction or assert new syntax is implemented.

Current published line: Rust 0.12.0-alpha.4, the primary implementation. Alpha is not a claim of production readiness.

| Milestone | Status |
| --- | --- |
| Rust-only product and canonical CLI | Current release line |
| App core / Site / WebApp / Android generation | Implemented subset; extend target-specific conformance |
| Server and database-api | A21 loopback, auth and bounded transactions |
| SedravaSQL | NativeLog SQL B28; B31 storage research is separate |
| Self-host | A5.11b bounded nested control; extend types and consolidate compiler |
| Performance | Remeasure event-driven HTTP, optimize query scans, generated Web and Android output |
| Storage | B32 safe page reuse → durable receipts → migration and SQL integration after recovery/ownership gates |
| Full-stack | Same-origin client/API/data integration, security gates, examples |
| Distributions | Linux first; Windows/macOS after actual build and execution |
| Beta/stable | Browser/device tests, security review, compatibility contract, recovery and release validation |

[Current documentation](README.ru.md) · [Self-hosting](SELF_HOSTING_ROADMAP.ru.md) · [Benchmark baseline](BENCHMARK_2026_11_24.ru.md).

[Checkpoint B31](DEVELOPMENT_STATUS.en.md) · [Контрольная точка](DEVELOPMENT_STATUS.ru.md).
