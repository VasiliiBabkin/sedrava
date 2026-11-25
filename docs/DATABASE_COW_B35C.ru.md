# B35c — экспериментальный COW backend Sedrava

На research-ветке зависимость SedravaSQL закреплена на 40a0cdc214af177957f94d0173b6b5c5d481c2f2. Язык сохраняет существующий DSL, SQL parser, typed parameters, trusted/allow-write policy, loopback API и авторизацию. Выбор только явно через `--backend cow`; default NativeLog. Другой формат отклоняется. COW доступен на Unix, проверено на Linux.

Пример (приватный каталог 0700, абсолютные пути):
    sedravasql-native-preview cow-init /private/demo.cow
    sedravasql-native-preview cow-sql /private/demo.cow "CREATE TABLE T (id TEXT PRIMARY KEY,n INT)" demo-create-0001
    sedrava database run query.sdr --database /private/demo.cow --trusted --backend cow
    sedrava database-api run api.sdr --database /private/demo.cow --trusted --backend cow --allow-write --auth-file /private/auth.json

COW хранит каноническую историю транзакций на COW pages, а Replay, row/secondary indexes находятся в RAM. Логические byte/transaction limits сохранены; независимо действуют 32 MiB serialized payload, physical page/row/stage caps. Это не direct on-disk SQL row index, не production и не автоматическая миграция B34 образа в writable CowStore. Backup состоит из согласованной пары data/head; не копировать произвольно во время записи. Не заявляется power-loss durability. Публичные релизы и main не переключены.

Проверки на VDS: offline debug build PASS; standalone database policy/write/read/replay/conflict/wrong format PASS; A17–A21 по 63 реальных HTTP-запроса для каждого backend, всего 126/126 PASS. Для COW тесты refusal/replay сравнивают data и head. Логи: evidence/b35c-cow-database-2026-11-25.

Воспроизведение: выставить SEDRAVA_NATIVE_BIN и SEDRAVASQL_NATIVE_BIN на соответствующие собранные CLI; python3 scripts/verify_cow_database_b35c.py; для каждого из native-log/cow выставить SEDRAVA_SQL_TEST_BACKEND и запустить verify_native_sql_api_a17.py, verify_native_sql_api_a18.py, verify_sales_demo_a19.py, verify_sales_demo_a20.py, verify_sales_demo_a21.py.

Далее: writable migration, direct ordered row storage, recovery and performance qualification before any stable release.
