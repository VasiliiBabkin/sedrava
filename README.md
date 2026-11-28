<p align="center"><img src="assets/brand/sedrava-logo-primary.png" width="220" alt="Sedrava logo" /></p>

# Sedrava — Rust toolchain

**Describe the application; get the application.**

Sedrava is a declarative programming language with a Rust compiler and runtime. The current release line is **0.12.0-alpha.3**. It is experimental, not a production-ready release.

[Download Linux x86-64](https://sedrava.virtreal.ru/downloads/0.12.0-alpha.3/) · [GitHub release](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.12.0-alpha.3) · [Official documentation](https://sedrava.virtreal.ru/) · [Русский](docs/README.ru.md)

## Get started

The versioned platform archive includes **sedrava**, **sedravasql-native-preview**, and the separate managed **sedravasql** CLI, a manifest and SHA-256 checksums. The offline installer refuses to overwrite an existing prefix. Install into a separate prefix and put its bin directory first on PATH. No Python or Rust needed on the target system. GNU Linux x86-64 tested on Ubuntu 24.04; Windows/macOS not verified.

Build from source:

~~~sh
git clone https://github.com/VasiliiBabkin/sedrava.git
cd sedrava
cargo build --manifest-path rust/Cargo.toml --locked --release --bin sedrava
./rust/target/release/sedrava --version
./rust/target/release/sedrava check examples/counter.sdr
./rust/target/release/sedrava test examples/counter.sdr
./rust/target/release/sedrava run examples/counter.sdr increment increment
./rust/target/release/sedrava build web examples/counter.sdr --output build/counter.html
~~~

## Current scope

| Capability | Status |
| --- | --- |
| Language | Typed state, rules, records, bounded collections, functions, navigation, Unicode, imports and package locks |
| CLI | check, test, run, inspect, expand, IR, effects |
| Web | Standalone HTML, Site, interactive WebApp; verified DOM subset |
| Android | Kotlin/Compose sources; explicit application ID, tested debug APK build; limited device acceptance |
| Host | Trusted bounded local file effects |
| Server | Published alpha and A21 baseline; A26 candidate adds sessions, generated WebApp, migration gates and project binding |
| Storage | [SedravaSQL](https://sql.virtreal.ru/): NativeLog; A24 additive migrations in the A26 candidate |
| Self-host | Experimental compiler A5.11b written in Sedrava, not the primary compiler |

One source can target different runtimes when its constructs are supported by the chosen generator. Unsupported constructs fail rather than silently switching implementation. Public deployment, complete platform coverage and production security are not established.

## Learn and develop

[Quickstart](docs/QUICKSTART.md) · [Distribution](docs/PLATFORM_RELEASE_A30.ru.md) · [Release notes](docs/RELEASE_NOTES_0_12_0_ALPHA3.md) · [Roadmap](docs/ROADMAP.md) · [Language examples](examples/README.md) · [Benchmarks](docs/BENCHMARK_2026_11_24.ru.md) · [Security](docs/SECURITY.md).

For maintainers: run cargo test --manifest-path rust/Cargo.toml --locked --all-targets. Python scripts in scripts/ are test/packaging helpers only; the old implementation and package publishing are not part of the current toolchain. For past releases and comparison oracles see [History](docs/HISTORY.md).

[Dedication / Посвящение](DEDICATION.md): Геннадию Ивановичу Смирных.

Apache-2.0 license.

**A30 release (28 November 2026).** Sedrava 0.12.0-alpha.3, SedravaSQL 0.1.0-alpha.2 and NativeLog 0.0.2 published. VDS qualification: 85 Rust, 319 HTTP, 21+73 SQL tests and offline installation. Prior A26 passed Forgejo CI. COW remains research; not production-ready.

## A30 integrated platform

[Project CLI](docs/PROJECT_CLI_A25.ru.md) · [Migration gate](docs/SCHEMA_MIGRATIONS_A24.ru.md) · [Offline distribution](docs/PLATFORM_RELEASE_A30.ru.md). Commands new/build/test/migrate/serve/package are available in alpha.3.
