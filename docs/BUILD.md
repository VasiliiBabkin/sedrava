# Build Sedrava

Run cargo build --manifest-path rust/Cargo.toml --locked --release --bin sedrava from the source root. Use the pinned toolchain in rust/rust-toolchain.toml. Test with cargo test --manifest-path rust/Cargo.toml --locked --all-targets.

## Android

~~~sh
sedrava build android examples/counter.sdr --output build/counter-android --application-id org.example.counter
cd build/counter-android
gradle assembleDebug
~~~

Use JDK 17, Android SDK 35, Gradle 8.11.1, a configured ANDROID_HOME and matching build tools. The CLI generates source; Gradle builds an APK. No claim that every source accepted by the CLI targets Android. Verify APK signature, manifest, install and actual device behavior separately.

## Web

sedrava build web produces standalone HTML. sedrava build site and sedrava build webapp create fresh output directories; serve static files using a local HTTP server for testing. For WebApp persistence use a stable origin. Production security is not established.

[Distribution](DISTRIBUTION_NATIVE.ru.md) · [Android evidence](NATIVE_012_ANDROID_APK_SMOKE.ru.md).
