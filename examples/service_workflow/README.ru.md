# Сервисный журнал: декларативный жизненный цикл A34

Один domain.sdr и манифест format 2. Требуется компилятор A34 этой ветки. Сборка из корня: cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava. Из каталога примера: sedrava test, sedrava build, затем обычные migrate/serve с отдельной приватной БД и явным файлом авторизации. [Контракт A34](../../docs/WORKFLOW_A34.ru.md) · [Инструкция A33](../../docs/DOMAIN_MODEL_A33.ru.md). Только локальные тестовые данные. Полный A31 по-прежнему отдельный пример service_desk.
