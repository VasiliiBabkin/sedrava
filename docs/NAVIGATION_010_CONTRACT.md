# Sedrava 0.10 multi-screen navigation — implementation contract

**Status:** implemented in the published experimental Sedrava 0.10.0 release. The development-branch references below are historical; coverage: [report](NAVIGATION_010_REPORT.md).

## Objective / Цель

A single `.sdr` source generates a task list screen and a task-detail screen for offline Web and Android. Screens share one accepted domain state; navigation has deterministic semantics and requires no author-written JavaScript, Kotlin or Android navigation controller.

## Navigation grammar / Грамматика

```sdr
app "Tasks"
state selected = 0
screen main:
    text "Tasks"
    button "Details" -> open_details
screen details:
    text "Task details"
    button "Back" -> back
navigation:
    initial main
    action open_details -> details
    action back -> pop
```

This grammar is accepted by the compiler. Domain actions and navigation commands have distinct names; conflicts are rejected.

## Normative behavior / Семантика

1. Named screens are unique; `main` remains the implicit initial screen for legacy programs. Explicit initial screen is allowed only when declared.
2. Navigation stack is nonempty, bounded (suggested maximum 32), and stores screen IDs, never mutable widget instances. Opening a screen pushes it; `pop` returns to the previous screen; popping the root is a deterministic no-op.
3. Domain state is shared across screens; navigation never silently commits rejected edits. Failed domain actions do not navigate.
4. Invalid targets, duplicate screens, unreachable navigation actions and conflicting action names are compile errors with line/column.
5. Web browser Back and Android system Back must match the language stack semantics. Forward/history behavior and reload restoration must be specified explicitly before coding.
6. Rotation/Activity recreation must preserve accepted domain state and active screen. Cold launch restores persisted domain state; screen restoration behavior must be documented and tested.
7. No hidden network, permissions, generated-file edits or arbitrary host-language callbacks.
8. Screen-reader labels, keyboard focus and visible errors are acceptance criteria.

## Implementation and evidence

- Extend Program/AST and parser with explicit screen/navigation nodes and source positions; retain all 0.9 and 0.10 examples.
- Interpreter exposes a deterministic navigation transition model testable without a UI.
- Web: real browser tests for list → detail → back, invalid action, reload, browser Back and focus.
- Android: generated Compose screens, system Back, rotation/recreation, cold launch and JVM conformance; build and emulator test.
- Create `examples/task_manager_navigation.sdr` using real collection CRUD on two screens, generated unchanged for both targets.
- Test Python 3.10/3.12/3.13, Chromium and Android; compare state and navigation traces across platforms.
- Update README, roadmap, changelog and bilingual quickstarts after implementation, not before.
- Keep the PR draft for review; record the final evidence in PR #15. No merge, tag, release, PyPI publish or deployment.

## Non-goals

Nested records, schema migrations, routing parameters, deep links, tabs, animation systems and multi-window UI are separate milestones.

## Acceptance / Приёмка

The reference source compiles unchanged to a usable standalone Web app and Android APK; actual Web/Android interactions and back-stack semantics match the Python oracle; existing tests pass. Unsupported checks must be reported as unavailable, never as passed.

## Adopted implementation decisions / Принятые решения

The grammar above is retained. Optional `using domain_action` on a navigation
binding performs a domain action and push/pop in one transaction. `screen details
when chosen:` is a bool guard; the initial screen must be unguarded. A false/failed
guard rejects entry atomically. After accepted data edits/removal, invalid active
screens are popped until a valid screen is found. Shared selection is ordinary
int state; deleting a selected row never substitutes another row.

Bounds: 32 screens, 64 navigation bindings, 32 stack entries including root;
identifiers at most 64 ASCII identifier characters. Navigation command names
cannot collide with states/derives/records/domain actions/screens. All screens
must be reachable from initial via declared screen controls; every navigation
binding must be used by a screen control. `pop` is reserved as a target.

Additional presentation: `display <scalar expression>`, `input title label "Title"`,
and `list tasks select selected open open_details title title status done`.
List opening atomically selects the stable ID and invokes the navigation binding;
optional title/status refer to text/bool record fields. The status role means
completion. Old single-screen syntax remains unchanged.

Web history stores only bounded screen stacks, never domain snapshots. Back and
Forward re-evaluate guards against current shared data, so they do not undo edits
or resurrect deleted records. Stale/foreign history metadata is replaced safely.
Browser Back at the root can leave the document; Android system Back at root is
not intercepted and belongs to the host Activity lifecycle. The language `pop` at
root is a successful no-op. Navigation and pending browser traversal are serialized.
Reload and cold launch start at the declared initial screen and restore only
`persist` domain fields. Android rotation/recreation retains all accepted domain
fields and the stack together; invalid saved navigation falls back to initial.
Drafts are not promised to survive transitions/recreation. Navigation is not part
of the domain persistence schema. These boundaries are deliberate, not migrations.

Русский: `using` объединяет изменение данных и переход в атомарную операцию.
Охраняемый экран недоступен без существующей выбранной записи; удаление записи
возвращает к ближайшему допустимому экрану. Стек ограничен 32 элементами. История
браузера не отменяет изменения задач. Перезагрузка/холодный запуск открывают начальный
экран; поворот и пересоздание Activity сохраняют принятое состояние и стек.


Presentation uses the first two `text` widgets as title/subtitle; further text
widgets stay in the content area. `display` errors show `Unavailable` without
mutating data; screen guards should protect record-dependent displays. Numeric
editors validate explicit decimal syntax and int32 bounds. Navigation to repeated
screen names is allowed and restores keyboard focus just like a different screen.
