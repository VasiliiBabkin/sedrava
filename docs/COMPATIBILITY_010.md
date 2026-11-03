# Compatibility / Совместимость Sedrava 0.10

This describes the observed 0.10 storage/update contract. The 0.10.0 version number does not imply migration support or future compatibility.
The audit does not change the public grammar, Android IDs, storage encoding,
or the immutable rc1 kit. See [audit](STABILITY_AUDIT_010.md).

## Programs and builds / Программы и сборки

Existing 0.9 reference, 0.10 text, records, collections and navigation programs
remain regression fixtures. Integers are signed int32; bool is not an integer.
Text contains at most 1024 Unicode scalar values, including empty text and control
characters. No normalization or trimming of text is performed. Numeric UI drafts
may trim surrounding whitespace. Text equality is exact; text ordering is not
part of the language. All signed-minimum expression positions are supported.

Android's default ID depends on the exact UTF-8 app title, not compiler version
or source filename. Renaming the title changes that ID; select a stable explicit
`--application-id` before distributing an app. Same title means same default ID.
Updating requires the same ID and signing key, and a nondecreasing Android
versionCode. An APK with another signing key cannot update an existing install.
The audit retains rc1 metadata intentionally; it is not a new release artifact.

Русский: публичный синтаксис и идентификаторы не меняются. Числа — int32, строки
не нормализуются. Для обновления Android нужны прежние application ID и ключ
подписи; смена названия меняет ID по умолчанию. Два разных ID хранят данные отдельно.

Web localStorage is isolated by browser origin; the generated key also includes
`location.pathname` and the exact app title. Moving/renaming the HTML path, changing
origin or changing the title selects different storage, even if the schema stays
compatible. Query strings and URL fragments are not part of this key. Existing
bytes stay under the old key; there is no automatic transfer. CLI uses the explicit
`--state-file` path. The schema fingerprint validates structure, not data ownership
or authenticity; it is not an encryption/signature mechanism.

Русский: Web выбирает хранилище по origin, пути HTML и точному названию приложения.
Изменение адреса или названия не переносит данные; оригинал остаётся под старым
ключом. Query/fragment ключ не меняют. CLI использует указанный путь state-file.

## Exact snapshots / Строгие снимки

Programs declaring records or navigation use schema 1. The fingerprint includes
**every state declaration in source order**, its type, persistence flag, and each
collection's record name, ordered fields/types and capacity. Persistent keys
must match exactly. The envelope contains schema, fingerprint and persistent data;
it does not contain screen history. Duplicate JSON keys, float/exponent syntax,
wrong scalar types, unknown/missing fields, repeated/nonpositive IDs, exhausted or
inconsistent next_id, capacity/resource excess and final invariant violations
reject the entire snapshot before any persistent field is applied.

| Source change | Existing schema-1 data |
| --- | --- |
| Actions, button labels, screen presentation/routes | Fingerprint unchanged; new rules/derived evaluation must still accept data |
| Initial scalar defaults only, same names/types/order | Fingerprint unchanged; saved persistent values override defaults; transient values use new defaults |
| Rules or derives | Fingerprint unchanged; any invalid restored candidate rejects as a whole |
| Add/remove/rename/reorder state, including transient state | Rejected |
| Change a type, persist flag, list capacity, record name or ordered fields/types | Rejected |
| Unused record declaration only | Does not enter the fingerprint unless used by state |

Maximum snapshot and full accepted domain envelope: 200000 UTF-16 code units.
Selection is ordinary int state: deleting an item does not universally reset that
integer. A guarded detail screen whose record disappears is popped by navigation
normalization; an attempted open for a missing record is rejected atomically.

Русский: схема зависит даже от непостоянных объявлений и их порядка. Изменение
типа, вместимости или persist-флага несовместимо. Изменение действий/подписей
само по себе совместимо; новые правила могут отклонить старые значения. Миграций
нет. При ошибке строгий снимок отклоняется целиком.

## Legacy scalar storage / Старый скалярный формат

Single-screen scalar-only Web apps retain the legacy plain JSON object;
Android retains typed SharedPreferences keys. Their historical restore adapters
may salvage valid persistent fields and use defaults for missing/invalid fields,
then validate the whole candidate. Unknown keys are ignored in the recovery
preview. This is intentionally different from strict envelope restoration.

The generated applications now **refuse to overwrite rejected legacy data**:
malformed objects, unknown keys, incorrect field types/values or a failed final
candidate block writes. Missing keys alone remain compatible with legacy defaults.
A recovery preview is not a migrated or successfully saved state. Scalar Web
JSON cannot identify schema changes that retain the same names and runtime types.
CLI `run --state-file` always uses the strict envelope, including scalar programs;
its files are not automatically interchangeable with legacy Web/Android storage.
Python host APIs accept typed values, not UI string drafts.

Русский: старый скалярный адаптер сохраняет прежнее восстановление отдельных
корректных полей, но больше не перезаписывает отвергнутый оригинал. CLI хранит
строгий конверт даже для скалярных программ; перенос форматов не автоматизирован.

## Recovery and writes / Восстановление и запись

Rejected schema-1 data stays byte-for-byte in Web storage and unchanged as the
Android snapshot string. New accepted edits can be visible in memory, but cannot
replace the rejected snapshot. Web keeps that session locked after a failed
startup restore, even if storage is subsequently removed; reload after recovery.
Android revalidates current preferences on each write. Nonempty preferences
without a required schema-1 snapshot also block writes; old scalar keys are not
automatically migrated or discarded. A concurrently corrupted
Web snapshot is also revalidated before saving. CLI restore failure returns 1
before replacing any state file.

Before resetting anything, **back up the original storage and source project**.
Try the compatible previous build with the same ID/key (Android normally rejects
version downgrades). Keep copies of Web localStorage values or debug Android
SharedPreferences using supported development tools. There is no built-in export,
repair, reset button or automatic migration. Only after backup and an explicit
user decision should storage be removed and the app restarted. Clearing browser
site data or Android app storage deletes the original. Never treat that as repair.

CLI state/Web output writes use a same-directory temporary file, flush/fsync and
replace; write/replace failure preserves an existing target and removes the temp
file. This is not a guarantee against filesystem/hardware failure or power loss
before directory metadata is durable. Android uses one synchronous commit for a
whole accepted snapshot; its return value is checked. SharedPreferences may
update process memory even when disk commit fails. Web setItem failure is reported.
Storage failure does not roll back the accepted in-memory domain action; changes
may be temporary. Rejected actions leave accepted domain state unchanged.

No multi-tab/process conflict resolution, backup service, encryption, cross-device
sync or crash/power-cut certification is provided. Concurrent valid writers are
last-writer-wins. Do not promise zero data loss under unsupported concurrency or
physical storage failure. Cold launch restores persist fields and initial screen;
rotation/recreation retains accepted Android session state, not invalid drafts.

Русский: отвергнутый оригинал защищён от перезаписи. Новые изменения могут оставаться
только в памяти. Сначала сохраните оригинал и проект, затем восстановите совместимую
сборку или осознанно удалите данные. Автоматической миграции нет. Ошибка записи
показывается пользователю; принятые значения в памяти не откатываются. Одновременная
запись из нескольких окон не согласуется; гарантии при аппаратном отказе нет.
