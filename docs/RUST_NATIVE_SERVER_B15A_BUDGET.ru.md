> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# Native Server — B15a limits

При `--transactional --native-log ABSOLUTE_FILE` нативный движок использует пределы B15a: 64 MiB и 65536 транзакций по умолчанию. Пара `--native-max-bytes N --native-max-transactions N` позволяет установить более строгие пределы, оба параметра обязательны при явной настройке. Лимиты действуют на handle, повторно задаются при запуске, не меняют формат SEDRLOG1. При превышении лимита новая запись получает HTTP 507 NATIVE_LOG_CAPACITY до изменения файла или состояния; сервер остаётся доступен, старые идемпотентные запросы возвращают сохранённый ответ. Конфликт idempotency key по-прежнему 409. Это не квота ОС, не компактификация и не предел памяти при открытии старого журнала.

VDS: 83 Rust tests, HTTP capacity test (507, unchanged SHA, reads and replay after restart) PASS, A10/A11/A12/A13 regressions PASS. Dependency db2054efaeda0fd5cb4724f86c11586bdae45266. Test: set SEDRAVA_NATIVE_BIN and SEDRAVASQL_NATIVE_BIN to fresh debug binaries, python3 -B scripts/verify_native_server_budget_b15.py.
