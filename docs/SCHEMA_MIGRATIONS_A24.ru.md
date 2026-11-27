# A24b — миграции схем при запуске Sedrava

Sedrava закреплена на точном коммите SedravaSQL 60a7d0488a23135fa064b7cf2496f93a78b519bd (ветка feat/a24-migrations). Нативный NativeLog остаётся выбранным движком. В примере sales_demo появился migrations.json с пятью добавочными шагами (две таблицы, два индекса и внешний ключ).

Новый запуск:

```bash
sedrava build webapp examples/sales_demo/native_app.sdr --output "$PWD/build/native-sales"
sedrava database-api run examples/sales_demo/sales_api.sdr \
  --database "$DB" --trusted --allow-write --auth-file "$AUTH" \
  --web-ui "$PWD/build/native-sales" --session-ttl 900 \
  --migrations "$PWD/examples/sales_demo/migrations.json" --apply-migrations
```

DB — заранее созданная пустая база NativeLog в приватной директории (инициализация через sedravasql-native-preview init). AUTH — приватный файл по A23d. Оба пути абсолютные. При следующем запуске удалить --apply-migrations, оставив --migrations. Прежний запуск без манифеста оставлен для совместимости и не проверяет версию. Уже созданную вручную схему нельзя автоматически принять за выполненные миграции.

Манифест проверяется до старта. Флаг применения требует манифеста и --allow-write; прежние правила --trusted и absolute DB path сохранены. Сервер резервирует loopback-порт до применения, но не принимает HTTP-запросы до успешного завершения миграций. Поэтому конфликт порта не изменяет данные. При отсутствии разрешения, несовпадении истории или незавершённом плане сервер отказывается стартовать. SCHEMA_VERSION выводится в stderr. Сессии и статические файлы работают как прежде.

Каждый шаг атомарен, весь многошаговый план не атомарен: уже успешно применённые версии остаются в журнале при отказе последующего шага. При повторном запуске проверяется история и выполняются оставшиеся шаги. Для смены существующих столбцов, DROP/RENAME, downgrade, DML migration и baseline нужна отдельная разработка. Не заменяет резервное копирование и проверку целевой схемы. Нативное хранилище остаётся экспериментальным, ограниченным одним писателем.

## Проверка

```bash
export SEDRAVA_NATIVE_BIN=/absolute/sedrava
export SEDRAVASQL_NATIVE_BIN=/absolute/sedravasql-native-preview
python3 -B scripts/verify_migrations_a24.py
# Node 20+, jsdom 27.2.0, NODE_PATH на node_modules:
SEDRAVA_A22_DOM=1 python3 -B scripts/verify_migrations_a24.py
```

Тест использует временную базу, обновляет схему с версии 2 до 5, сохраняет существующие строки, проверяет FK, отказ при неприменённом плане, занятый порт, отсутствие повторной записи, отказ изменённого/укороченного плана и реальное взаимодействие с нативным WebApp. 16 прямых HTTP-запросов A24 PASS. Повторно PASS 296 прямых HTTP-тестов A17–A23d, A22 HTTP/DOM и A23e compiler/HTTP/DOM. Вся регрессия выполнена на новом закреплённом SQL-коммите. Отчёт SQL: docs/NATIVE_MIGRATIONS_A24.ru.md в SedravaSQL.

Проверено через jsdom, не Chromium. Независимая CI Forgejo пока не подтверждена. Main, релизы и рабочие сервисы не изменены. Логи и хэши бинарников в evidence/a24-schema-migrations-2026-11-27.

Final Rust workspace: 85 tests PASS, 0 failed.
