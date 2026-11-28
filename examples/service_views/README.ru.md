# Сервисные заявки и отчёты A36

Высокоуровневый domain.sdr и манифест format 2. Компилятор из ветки A36 генерирует справочники, workflow, два представления и два отчёта. [Контракт A36](../../docs/DOMAIN_VIEWS_A36.ru.md). Сборка из корня: cargo build --manifest-path rust/Cargo.toml --locked --bin sedrava. Из каталога примера: sedrava test, sedrava build; далее обычные migrate/serve с новой приватной БД и auth-file, см. [A33](../../docs/DOMAIN_MODEL_A33.ru.md). Не использовать рабочие данные, публичный сервер или старые базы примеров.
