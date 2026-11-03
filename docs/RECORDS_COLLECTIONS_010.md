# Records and collections / Записи и коллекции — Sedrava 0.10.0

Normative 0.10.0 syntax (published experimental implementation):

```sdr
record Task:
    title: text
    done: bool
state tasks: list<Task>(max=100) = []
state selected = 0
state title = ""
persist tasks
action add: tasks = append(tasks, Task(title=title, done=false))
action rename: tasks = update(tasks, selected, Task(title=title, done=false))
action delete: tasks = remove(tasks, selected)
```

Derives must precede actions. See
`examples/task_manager.sdr` for a complete valid program.

Records declare 1–16 fields of `int`, `bool`, `text`; no nesting or implicit
conversion. Constructors require every field exactly once, using named arguments.
Field order is declaration order. Record and list equality are forbidden; compare
scalar fields. `get(tasks, id).title` returns a scalar field; missing ID rejects
the entire action. `has(tasks, id)` is boolean; `count(tasks)` and `next_id(tasks)`
return int32. `append`, `update`, `remove` return new immutable list values.
`update` replaces all user fields and preserves identity. There is no indexing.

Each list has capacity 1–100, insertion order, and an automatic positive int32 ID
outside user fields. IDs are never reused. Removal preserves relative order.
`next_id` starts at 1; append rejects at 2147483647 (reserved exhaustion sentinel).
An action uses candidate values, checks derived values after each assignment and
rules on the final candidate; any failure leaves all accepted state unchanged.
Missing IDs, capacity, overflow and invalid Unicode reject without repair.
`require <bool-expression>` inside an action rejects unless true. `has` returns
false for a missing ID; `get`, `update`, `remove` reject. IDs cannot be assigned.
Text is at most 1024 Unicode scalar values; no trimming or normalization.
At most 16 record declarations and 16 collection states; source and expression
limits remain those of the text core.

`value` displays scalars; use the list widget for collection display.
Record values are collection elements or derived expressions, not standalone state.

`list tasks select selected` renders ordered records and a Select button per row;
`selected` must be an int state. Selection is validated like other input. Authors
use ordinary inputs and actions for add/edit/delete; no target code is required.

Collection programs persist one schema-1 envelope with an exact declaration
fingerprint, all and only persistent keys, and lists containing `next_id` and
ordered `items` (`id` plus exact declared fields). All fields, IDs, capacities,
scalar types and final rules are checked before restoration. Wrong schema,
unknown/missing fields, duplicate keys, malformed/oversized JSON reject the entire
snapshot. No migrations; report rejection and show defaults. Rejected original
data is retained and cannot be overwritten by subsequent edits. Back up before
any manual reset; see [compatibility](COMPATIBILITY_010.md). Maximum encoded
snapshot and full accepted state envelope: 200000 UTF-16 code units on every target.
JSON numbers must use int32 integer syntax (no fraction/exponent).
The full-state envelope bound is checked on the final candidate; intermediate
list operations still enforce their declared capacities. Scalar-only programs retain
the legacy restoration contract. Storage failure does not alter accepted state.

Русский: записи имеют фиксированные типизированные поля; список хранит порядок и
выдаёт ID независимо от индекса. Изменения выполняются над кандидатом и принимаются
целиком после проверки правил. Повреждённое сохранение отклоняется целиком; миграций
нет. Пределы: 16 полей, 100 элементов, int32, 1024 скалярных значения в строке.
Статус платформ и фактические проверки указаны в COLLECTIONS_010_REPORT.md.
