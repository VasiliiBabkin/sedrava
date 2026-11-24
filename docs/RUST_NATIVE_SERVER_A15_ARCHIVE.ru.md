> Milestone-specific technical record. For current installation and supported scope, see [Sedrava Rust](README.ru.md). Commands below may use the transitional Rust CLI name.

# A15 — offline восстановление HTTP-приложения

Остановить единственного владельца журнала. Проверить SHA-256 исходного SEDRLOG1; `sedravasql-native-preview archive-create SOURCE ARCHIVE SOURCE_SHA256`, затем `archive-verify ARCHIVE`, `archive-restore ARCHIVE NEW_FILE ARCHIVE_SHA256`. Восстановление в новый приватный файл, без замены исходника. Запустить прежний исходник Sedrava с `--transactional --native-log NEW_FILE` и прежними лимитами. Не удалять оригинал автоматически. Проверены старый Idempotency-Key и продолжение записи после запуска восстановленного журнала. Это ручная offline процедура, не автоматическое восстановление, не online compaction и не тест обесточивания.

VDS: A15 HTTP archive/restore exact bytes, replay, continued writes and unchanged source PASS. B15a HTTP + A10–A13 regressions PASS, 83 Rust tests. Dependency 69eb7b739fac49f5aa0a44fa53b8b9e4e644dc50. Test: python3 -B scripts/verify_native_server_archive_a15.py with SEDRAVA_NATIVE_BIN and SEDRAVASQL_NATIVE_BIN.
