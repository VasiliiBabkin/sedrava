# Распространение Sedrava после полного перехода на Rust

Статус: проектируемая схема. Готового стабильного нативного релиза пока нет.
Python 0.11 остаётся основным компилятором, а задача №65 открыта.

## Предлагаемый порядок

1. Основной способ: готовый исполняемый файл sedrava через GitHub Releases
   под поддерживаемые Windows, Linux и macOS. Python и Rust пользователю не нужны.
2. Для разработчиков Rust: cargo install после публикации в crates.io.
   До публикации можно установить экспериментальный sedrava-native из исходников.
3. Для пользователей Python: временно сохраняем pip install sedrava.
   Позднее возможен совместимый пакет-обёртка, но без подмены движка и
   неожиданной смены семантики.
4. Пакетные менеджеры winget, Homebrew и другие — только после появления
   проверенных архивов на соответствующих ОС.

Прямо сейчас экспериментальный CLI из рабочего клона можно установить:

    cargo install --path rust/sedrava-core --bin sedrava-native --locked
    sedrava-native --version

Подтверждена и установка без предварительного клонирования GitHub-репозитория
на Linux x86_64 (Cargo 1.100.0, коммит fcec9d5):

    cargo install --git https://github.com/VasiliiBabkin/sedrava sedrava-core --bin sedrava-native --locked

Cargo скачает исходники и соберёт бинарник. Для этого способа нужен Rust/Cargo,
но Python и pip не требуются. Это всё ещё неполный экспериментальный компилятор.

При наличии Rust и исходников пользователь может собрать preview-архив:

    cargo build --manifest-path rust/Cargo.toml --locked --release --bin sedrava-native
    python3 scripts/package_native_preview.py --binary rust/target/release/sedrava-native --output build/native-previews

Скрипт НЕ публикует и НЕ подписывает релизы. Архив включает лицензию,
предупреждение о неполном переносе, контрольные суммы SHA256 и manifest.
Целевая платформа определяется из фактически установленного компилятора.
Не переименовывайте Linux-сборку в Windows — это не кросс-компиляция.

Стандартная команда sedrava будет присвоена нативному продукту только
после прохождения полной матрицы совместимости, испытаний Web/Android,
публикации версионированных бинарников и описания миграции с pip.
До этого она принадлежит установленному Python-пакету.

Официальные источники:
- https://doc.rust-lang.org/cargo/commands/cargo-install.html
- https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
- https://packaging.python.org/en/latest/specifications/entry-points/

Требуемые релизные проверки: воспроизводимые SHA, тесты на реальных ОС,
подписи/хеши, лицензии, инструкции обновления/удаления, возможность отката,
прозрачное описание ограничений и неизменные версии тегов.
