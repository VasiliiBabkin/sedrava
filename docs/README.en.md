# Sedrava — Rust toolchain

**Describe the application; get the application.**

Sedrava is a declarative programming language with a Rust compiler and runtime. The current release line is **0.12.0-alpha.4**. It is experimental, not a production-ready release.

[Download Linux x86-64](https://sedrava.virtreal.ru/downloads/0.12.0-alpha.4/) · [GitHub release](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.12.0-alpha.4) · [Official documentation](https://sedrava.virtreal.ru/) · [Русский](README.ru.md)

## Get started

The platform archive includes **sedrava**, **sedravasql-native-preview**, **sedravasql**, the domain example, a manifest and SHA-256 checksums. The offline installer refuses to overwrite an existing executable. Install into a separate prefix and put its bin directory first on PATH. No Python or Rust needed on the target system. GNU Linux x86-64 tested on Ubuntu 24.04; Windows/macOS not verified.

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
| Server | Local HTTP and typed SQL API A21, bearer roles, bounded transactions and durable receipts |
| Storage | [SedravaSQL](https://sql.virtreal.ru/): NativeLog SQL B28 in main; B31 separate storage research |
| Self-host | Experimental compiler A5.11b written in Sedrava, not the primary compiler |

One source can target different runtimes when its constructs are supported by the chosen generator. Unsupported constructs fail rather than silently switching implementation. Public deployment, complete platform coverage and production security are not established.

## Learn and develop

[Quickstart](QUICKSTART.md) · [Distribution](PLATFORM_RELEASE_A39.ru.md) · [Release notes](RELEASE_NOTES_0_12_0_ALPHA4.md) · [Roadmap](ROADMAP.md) · [Language examples](../examples/README.md) · [Benchmarks](BENCHMARK_2026_11_24.ru.md) · [Security](SECURITY.md).

For maintainers: run cargo test --manifest-path rust/Cargo.toml --locked --all-targets. Python scripts in scripts/ are test/packaging helpers only; the old implementation and package publishing are not part of the current toolchain. For past releases and comparison oracles see [History](HISTORY.md).

[Dedication / Посвящение](../DEDICATION.md): Геннадию Ивановичу Смирных.

Apache-2.0 license.

**Development checkpoint:** [B31 status and evidence](DEVELOPMENT_STATUS.en.md). Public binaries are unchanged; B31 is not the SQL backend.

**Format 2 / формат 2:** [A39 installation and domain example](PLATFORM_RELEASE_A39.ru.md) · [A37 model](SERVICE_DOMAIN_A37.ru.md) · [A38 qualification](QUALIFICATION_A38.ru.md). Experimental A33–A37 databases are incompatible with A38 semantic migration names; use new private test data.
