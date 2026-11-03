# Sedrava 0.11 experimental WebApp — typed records and collections

> Historical slice scope / исторический срез. Current integration adds routes, composition, typed HTTP, custom assets and domain queries. See [English guide](011_WEB_PLATFORM.en.md), [русское руководство](011_WEB_PLATFORM.ru.md) and [actual status](011_IMPLEMENTATION_STATUS.md). Statements below about missing features describe the original slice, not the complete integration branch.


**Status:** experimental B1 collections slice, stacked on B1 scalar UI PR #34.
Not part of the stable Sedrava release. No deployment.

## Run the CRUD task app

    python -m sedrava_cli check examples/webapp_011_tasks.sdr
    python -m sedrava_cli build webapp examples/webapp_011_tasks.sdr --output build/tasks
    python -m http.server 8000 --directory build/tasks

Open http://127.0.0.1:8000/. Browser storage is local. No external APIs
or JavaScript dependencies.

## Source grammar

    webapp "Tasks"
    record Task:
        title: text
        done: bool
    state tasks: list<Task>(max=100) = []
    state selected = 0
    state new_title = ""
    persist tasks
    derive empty = count(tasks) == 0
    derive chosen = has(tasks, selected)
    action add:
        require new_title != ""
        tasks = append(tasks, Task(title=new_title, done=false))
        new_title = ""
    action toggle:
        require has(tasks, selected)
        tasks = update(tasks, selected, Task(title=get(tasks, selected).title, done=not get(tasks, selected).done))
    action remove_selected:
        require has(tasks, selected)
        tasks = remove(tasks, selected)
        selected = 0
    view main:
        column:
            heading "Tasks"
            input new_title label "New task"
            button "Add" action add
            when empty:
                paragraph "No tasks"
            list tasks select selected title title status done label "Task list"
            when chosen:
                button "Complete" action toggle
                button "Delete" action remove_selected

The compiler reuses 0.10 typed records and bounded ordered collections,
including atomic append/update/remove/get/has/count operations. In generated
JavaScript, the same 0.10 Web domain runtime validates actions, list bounds,
stable IDs and persisted snapshots; the WebApp layer only renders data and
dispatches selection to validated scalar state.

## New UI binding

    list COLLECTION select STATE [title TEXT_FIELD] [status BOOL_FIELD] [label "Accessible name"]

- COLLECTION must be declared as a bounded list of a named record.
- STATE must be a mutable integer state for the selected record's stable ID.
- Optional title must be an existing text record field.
- Optional status must be an existing boolean record field. The initial UI
  labels are "Completed" and "In progress" and are not localized yet.
- Optional label names the list for assistive technology; otherwise the
  collection name is used.
- Rows are native HTML buttons with aria-pressed for the active selection.
  Selection uses the checked scalar editor from the existing 0.10 backend;
  the existing state rules may reject it. A rejected edit is not persisted.
- Strings are written using textContent, never raw HTML; IDs are bounded
  positive int32 values. Collections are rendered with stable IDs.
- Record fields cannot be edited directly through arbitrary bindings;
  author a normal Sedrava action using update(...), and attach its name
  to a button. This preserves atomicity and existing invariants.
- A stale selected ID is not automatically remapped to another record.
  For delete actions, reset the selected state explicitly (see the example).

## Limits

No multi-view navigation, row templates, sortable virtual lists, async HTTP,
module imports, server secrets, authentication, record-field inputs or
webapp-to-Android compilation in this slice. A single list uses a maximum
of 100 records as defined by the 0.10 core. More complex UX needs separate
implementation and tests. Do not reinterpret static site documents as apps.

## Verification commands

    python -m unittest discover -s tests -p 'test_webapp*.py' -v
    python scripts/test_webapp_browser.py
    python scripts/test_webapp_collections_browser.py

The Chromium suite tests CRUD, reloading persisted tasks, selection,
capacity overflow and rollback, long drafts, unsafe HTML input,
invalid persisted snapshots, keyboard focus, and 360/768/1440 widths.
The app bundle includes HTML, CSS, JavaScript and a hashed ownership
manifest, built deterministically. Full repository CI is still required.
