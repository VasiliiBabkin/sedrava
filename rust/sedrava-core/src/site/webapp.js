const errorNode = document.getElementById('sedrava-error');
const views = [...document.querySelectorAll('[data-view]')];
const inputs = [...document.querySelectorAll('[data-input]')];
const checkboxes = [...document.querySelectorAll('[data-check]')];
const choices = [...document.querySelectorAll('[data-choice]')];
const templates = [...document.querySelectorAll('[data-each]')];
const collections = [...document.querySelectorAll('[data-list]')];
const routed = views.length > 1;
let activeView = 'main';

function showError(message) {
    errorNode.textContent = message;
    errorNode.hidden = !message;
}

function invalidInput() {
    return inputs.some(input => input.getAttribute('aria-invalid') === 'true');
}

function syncButtons() {
    const disabled = invalidInput();
    document.querySelectorAll('[data-action], [data-list] button, [data-each] button, button[type=submit], [data-navigate], [data-request]')
        .forEach(button => { button.disabled = disabled; });
}

function accept(next) {
    if (!validate(next)) {
        showError('Change rejected by declared rules');
        return false;
    }
    if (!saveSnapshot(next)) return false;
    state = next;
    showError('');
    return true;
}

function commit(next) {
    if (!accept(next)) return false;
    render();
    return true;
}

function perform(action, candidate = state) {
    const next = actions[action](candidate);
    if (next === candidate) throw Error('Change rejected by declared rules');
    return next;
}

function run(action) {
    try {
        commit(perform(action));
    } catch (error) {
        showError('Action rejected: ' + error.message);
    }
}

function rowLabel(row, title) {
    return title ? String(row[title]) : Object.entries(row)
        .filter(([key]) => key !== 'id').map(([key, value]) => key + ': ' + String(value)).join(' · ');
}

function compare(a, b) {
    if (typeof a !== 'string') return a < b ? -1 : a > b ? 1 : 0;
    const x = Array.from(a, c => c.codePointAt(0)), y = Array.from(b, c => c.codePointAt(0));
    for (let i = 0; i < Math.min(x.length, y.length); i++) {
        if (x[i] !== y[i]) return x[i] < y[i] ? -1 : 1;
    }
    return x.length - y.length;
}

function queryRows(node, values) {
    const {list, each, titleField, queryWhere, queryActive, queryEquals, querySearch, querySort} = node.dataset;
    let rows = [...values[list || each].items];
    if (queryWhere && (!queryActive || values[queryActive])) {
        rows = rows.filter(row => row[queryWhere] === values[queryEquals]);
    }
    if (querySearch && values[querySearch]) {
        const needle = values[querySearch].toLowerCase();
        rows = rows.filter(row => rowLabel(row, titleField).toLowerCase().includes(needle));
    }
    if (querySort) rows.sort((a, b) => compare(a[querySort], b[querySort]));
    return rows;
}

function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
}

function selectionButton(owner, row, label) {
    const button = element('button');
    button.type = 'button';
    button.dataset.itemId = String(row.id);
    button.setAttribute('aria-label', 'Select ' + label);
    button.setAttribute('aria-pressed', String(state[owner.dataset.select] === row.id));
    button.onclick = () => {
        if (!button.disabled && commit({...state, [owner.dataset.select]: row.id})) {
            owner.querySelector('[data-item-id="' + row.id + '"]')?.focus({preventScroll: true});
        }
    };
    return button;
}

function renderTable(owner, rows) {
    const {table: fieldList, titleField, queryEmpty} = owner.dataset;
    const fields = fieldList.split(' ');
    const table = element('table');
    table.append(element('caption', owner.getAttribute('aria-label')));
    const header = table.createTHead().insertRow();
    for (const field of fields) {
        const cell = element('th', field);
        cell.scope = 'col';
        header.append(cell);
    }
    const body = table.createTBody();
    for (const row of rows) {
        const tr = body.insertRow();
        tr.dataset.id = String(row.id);
        const first = String(row[fields[0]]);
        const button = selectionButton(owner, row, titleField ? String(row[titleField]) : first);
        button.textContent = first;
        tr.insertCell().append(button);
        for (const field of fields.slice(1)) tr.insertCell().textContent = String(row[field]);
    }
    if (!rows.length) {
        const cell = body.insertRow().insertCell();
        cell.colSpan = fields.length;
        cell.textContent = queryEmpty || 'No matching records';
    }
    owner.replaceChildren(table);
}

function renderList(owner, rows) {
    const {titleField, statusField, queryEmpty} = owner.dataset;
    const fragment = document.createDocumentFragment();
    if (!rows.length && queryEmpty) {
        const item = element('li');
        const note = element('span', queryEmpty);
        note.setAttribute('role', 'status');
        item.append(note);
        fragment.append(item);
    }
    for (const row of rows) {
        const item = element('li');
        item.dataset.id = String(row.id);
        const label = rowLabel(row, titleField);
        const button = selectionButton(owner, row, label);
        button.className = 's-list-choice';
        button.append(element('span', label, 's-list-title'));
        if (statusField) {
            const note = element('span', row[statusField] ? 'Completed' : 'In progress', 's-list-status');
            note.id = 'sdr-list-status-' + collections.indexOf(owner) + '-' + row.id;
            button.setAttribute('aria-describedby', note.id);
            button.append(note);
        }
        item.append(button);
        fragment.append(item);
    }
    owner.replaceChildren(fragment);
}

function fillRow(item, row, values) {
    item.querySelectorAll('[data-row-field]').forEach(el => { el.textContent = String(row[el.dataset.rowField]); });
    item.querySelectorAll('[data-row-when]').forEach(el => { el.hidden = !row[el.dataset.rowWhen]; });
    item.querySelectorAll('[data-state]').forEach(el => { el.textContent = String(values[el.dataset.state]); });
    item.querySelectorAll('[data-when]').forEach(el => { el.hidden = !values[el.dataset.when]; });
}

function renderEach(owner, rows, values) {
    const template = owner.querySelector('template');
    const list = owner.querySelector('[data-each-items]');
    const fragment = document.createDocumentFragment();
    for (const row of rows) {
        const item = element('div');
        item.setAttribute('role', 'listitem');
        item.dataset.rowId = String(row.id);
        item.append(template.content.cloneNode(true));
        fillRow(item, row, values);
        const buttons = [...item.querySelectorAll('[data-action], [data-pick]')];
        for (const [index, button] of buttons.entries()) {
            const label = owner.dataset.titleField ? rowLabel(row, owner.dataset.titleField) : String(row.id);
            button.setAttribute('aria-label', button.textContent + ' ' + label);
            button.onclick = () => {
                if (button.disabled) return;
                try {
                    if (!resolved(state)[owner.dataset.each].items.some(current => current.id === row.id)) {
                        throw Error('Record no longer exists');
                    }
                    const next = {...state, [owner.dataset.select]: row.id};
                    if (!validate(next)) throw Error('Selection rejected');
                    const action = button.dataset.action;
                    if (commit(action ? perform(action, next) : next)) {
                        const updated = list.querySelector('[data-row-id="' + row.id + '"]');
                        updated?.querySelectorAll('[data-action], [data-pick]')[index]?.focus({preventScroll: true});
                    }
                } catch (error) {
                    showError('Row action rejected: ' + error.message);
                }
            };
        }
        fragment.append(item);
    }
    if (!rows.length && owner.dataset.queryEmpty) {
        const item = element('div');
        item.setAttribute('role', 'listitem');
        const note = element('p', owner.dataset.queryEmpty);
        note.setAttribute('role', 'status');
        item.append(note);
        fragment.append(item);
    }
    list.replaceChildren(fragment);
}

function pathFor(name, candidate = state) {
    return viewConfig[name].path.replace(/:([A-Za-z][A-Za-z0-9_]*)/g, (_, key) => String(candidate[key]));
}

function canView(name, values) {
    const guard = Object.hasOwn(viewConfig, name) && viewConfig[name].guard;
    return !guard || values[guard] === true;
}

function showViews(values) {
    if (!canView(activeView, values)) {
        activeView = 'main';
        if (routed) history.replaceState({sedravaDepth: 0}, '', '#/');
    }
    for (const view of views) {
        view.hidden = view.dataset.view !== activeView;
        if (view.hidden) view.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
    }
    if (routed && location.hash !== '#' + pathFor(activeView)) {
        history.replaceState(history.state, '', '#' + pathFor(activeView));
    }
}

function focusView() {
    const heading = views.find(view => view.dataset.view === activeView).querySelector('h1');
    heading.tabIndex = -1;
    heading.focus({preventScroll: true});
}

function render() {
    const values = resolved(state);
    if (themeState) document.documentElement.dataset.theme = state[themeState];
    document.querySelectorAll('[data-state]').forEach(el => { el.textContent = String(values[el.dataset.state]); });
    document.querySelectorAll('[data-when]').forEach(el => { el.hidden = !values[el.dataset.when]; });
    for (const input of inputs) {
        if (document.activeElement !== input) input.value = String(state[input.dataset.input]);
    }
    for (const input of checkboxes) input.checked = state[input.dataset.check];
    for (const input of choices) input.value = JSON.stringify(state[input.dataset.choice]);
    for (const owner of collections) {
        const rows = queryRows(owner, values);
        if (owner.dataset.table) renderTable(owner, rows);
        else renderList(owner, rows);
    }
    for (const owner of templates) renderEach(owner, queryRows(owner, values), values);
    showViews(values);
    if (typeof syncServiceViews === "function") syncServiceViews();
    syncButtons();
}

function navigate(name, action) {
    try {
        const depth = (history.state?.sedravaDepth || 0) + 1;
        if (depth > 32) throw Error('Navigation stack limit reached');
        const next = action ? perform(action) : state;
        if (!canView(name, resolved(next))) throw Error('View unavailable: missing data or invalid route');
        if (!accept(next)) return;
        activeView = name;
        if (routed) history.pushState({sedravaDepth: depth}, '', '#' + pathFor(name));
        render();
        focusView();
    } catch (error) {
        showError(error.message);
    }
}

function restoreRoute() {
    const path = location.hash.slice(1) || '/';
    for (const [name, spec] of Object.entries(viewConfig)) {
        const keys = [...spec.path.matchAll(/:([A-Za-z][A-Za-z0-9_]*)/g)].map(m => m[1]);
        const pattern = '^' + spec.path.replace(/:[A-Za-z][A-Za-z0-9_]*/g, '(-?[0-9]+)') + '$';
        const match = path.match(new RegExp(pattern));
        if (!match) continue;
        const next = {...state};
        keys.forEach((key, index) => { next[key] = Number(match[index + 1]); });
        if (match.slice(1).some(raw => raw.length > 11) || !validate(next) || !canView(name, resolved(next))) break;
        state = next;
        activeView = name;
        render();
        focusView();
        return;
    }
    activeView = 'main';
    history.replaceState({sedravaDepth: 0}, '', '#/');
    render();
    focusView();
    if (!restoreBlocked) showError('Page not found or selected record no longer exists');
}

function setInvalid(input, invalid) {
    input.setAttribute('aria-invalid', String(invalid));
    document.getElementById(input.getAttribute('aria-describedby')).hidden = !invalid;
    syncButtons();
}

for (const input of inputs) {
    input.addEventListener('input', () => {
        const key = input.dataset.input;
        const raw = input.value;
        const value = typeof state[key] === 'number'
            ? (/^-?[0-9]+$/.test(raw.trim()) ? Number(raw.trim()) : NaN)
            : raw;
        const next = {...state, [key]: value};
        const accepted = input.checkValidity() && validate(next) && accept(next);
        setInvalid(input, !accepted);
        if (accepted) render();
    });
    input.addEventListener('blur', () => {
        if (input.getAttribute('aria-invalid') === 'true') {
            input.value = String(state[input.dataset.input]);
            setInvalid(input, false);
        }
    });
}

for (const input of checkboxes) {
    input.addEventListener('change', () => {
        if (!commit({...state, [input.dataset.check]: input.checked})) render();
    });
}
for (const el of choices) {
    el.addEventListener('change', () => {
        if (el.selectedIndex >= 0 && !commit({...state, [el.dataset.choice]: JSON.parse(el.value)})) render();
    });
}
document.querySelectorAll('[data-action]').forEach(el => el.onclick = () => {
    if (!invalidInput()) run(el.dataset.action);
});
document.querySelectorAll('[data-submit]').forEach(el => el.onsubmit = event => {
    event.preventDefault();
    if (!invalidInput()) run(el.dataset.submit);
});
document.querySelectorAll('[data-open-dialog]').forEach(el => el.onclick = () => {
    const dialog = document.getElementById(el.dataset.openDialog);
    if (!dialog.open && !dialog.closest('[data-view]').hidden) dialog.showModal();
});
document.querySelectorAll('[data-close-dialog]').forEach(el => el.onclick = () => {
    document.getElementById(el.dataset.closeDialog).close();
});
document.querySelectorAll('[data-navigate]').forEach(el => el.onclick = () => {
    if (!invalidInput()) navigate(el.dataset.navigate, el.dataset.routeAction);
});
document.querySelectorAll('[data-back]').forEach(el => el.onclick = () => {
    if (routed && (history.state?.sedravaDepth || 0) > 0) history.back();
    else {
        activeView = 'main';
        render();
        focusView();
    }
});
if (!validate(state)) {
    showError('Invalid initial state');
} else {
    restoreSaved();
    if (routed) {
        window.addEventListener('popstate', restoreRoute);
        restoreRoute();
    } else render();
    if (typeof setupServices === "function") setupServices();
}
