# Распространение Sedrava

Основной CLI: **sedrava**, Rust 0.12.0-alpha.2. [GitHub Releases](https://github.com/VasiliiBabkin/sedrava/releases/tag/v0.12.0-alpha.2) · [официальные загрузки](https://sedrava.virtreal.ru/downloads/0.12.0-alpha.2/).

## Готовый Linux-дистрибутив

Скачайте архив, SHA256SUMS, manifest.json, install_native_preview.sh и RELEASE_NOTES.md. Сверьте контрольные суммы с доверенным источником. Пример для нового пользовательского префикса:

~~~sh
sha256sum -c SHA256SUMS
ARCHIVE=sedrava-0.12.0-alpha.2-x86_64-unknown-linux-gnu.tar.gz
HASH=$(sha256sum "$ARCHIVE" | cut -d ' ' -f 1)
sh install_native_preview.sh "$ARCHIVE" "$HASH" "$HOME/.local/sedrava/0.12.0-alpha.2"
export PATH="$HOME/.local/sedrava/0.12.0-alpha.2/bin:$PATH"
sedrava --version
~~~

Затем сохраните нужный PATH в профиле оболочки. Не перезаписывайте старые команды и данные. Для отката переключите PATH на прежний префикс; для удаления удалите только выбранный бинарник и при необходимости пустой каталог версии. SHA-256 подтверждает целостность, не заменяет подпись.

Linux x86-64 GNU, проверено Ubuntu 24.04; Windows/macOS не проверены. Пользователю не нужны Python и Rust. При самостоятельной сборке требуется Rust/Cargo (закреплённый toolchain в rust/rust-toolchain.toml).

~~~sh
cargo build --manifest-path rust/Cargo.toml --locked --release --bin sedrava
cargo install --path rust/sedrava-core --bin sedrava --locked
~~~

Совместимое имя sedrava-native остаётся отдельной Cargo-целью переходного периода, исполняет тот же Rust код. Основная команда — sedrava. Не устанавливайте два несовместимых инструментария в один префикс.

Старые выпуски и их происхождение: [история](HISTORY.md). Нет PyPI-распространения новой линии, автоматической миграции данных или обещаний промышленной совместимости.
