# records-v0 — shared behavioral contract

Target: a local-first application managing a list of records.

- Each record has a nonempty title and a stable identifier.
- Create, list, edit, and delete records.
- Reject an empty title without overwriting or deleting a previously valid record.
- Preserve records after reload/restart.
- Render user-provided titles as text rather than executable markup.

Acceptance tests cover create, edit, delete, rejection without data loss, and persistence. Framework-specific storage and widgets are unrestricted.
