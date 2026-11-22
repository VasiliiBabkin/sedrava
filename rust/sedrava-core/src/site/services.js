const services = Object.create(null);
const requestTimes = [];
const utf8Encoder = new TextEncoder();
let servicesReady = false;

function checkRemote(data, config) {
    const rows = config.many ? data : [data];
    if (!Array.isArray(rows) || rows.length > config.maxItems) {
        throw Error('Invalid response collection');
    }
    const fields = Object.entries(config.fields);
    for (const row of rows) {
        if (!isPlainRecord(row) || Object.keys(row).length !== fields.length) {
            throw Error('Unexpected response fields');
        }
        for (const [field, kind] of fields) {
            if (!Object.hasOwn(row, field)) throw Error('Missing response field');
            const value = row[field];
            if (kind === 'text' && (!validText(value) || /[\x00-\x08\x0b-\x1f]/u.test(value))) {
                throw Error('Invalid text response');
            }
            if (kind === 'int32' && (!Number.isInteger(value) || value < -2147483648 || value > 2147483647)) {
                throw Error('Invalid integer response');
            }
            if (kind === 'bool' && typeof value !== 'boolean') throw Error('Invalid boolean response');
        }
    }
    return data;
}

function exceedsByteLimit(raw, limit) {
    return raw.length > limit || utf8Encoder.encode(raw).length > limit;
}

function readServiceCache(raw, config) {
    if (exceedsByteLimit(raw, config.maxBytes)) throw Error('Cache exceeds byte limit');
    return checkRemote(strictJSON(raw), config);
}

async function readServiceResponse(response, config) {
    if (!response.ok) throw Error('HTTP ' + response.status);
    if (response.status === 204) {
        if (!config.many) throw Error('Empty response requires a many schema');
        return [];
    }
    const mime = (response.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
    if (mime !== 'application/json') throw Error('Expected JSON response');
    const reader = response.body?.getReader();
    if (!reader) throw Error('Missing response stream');
    const bytes = new Uint8Array(config.maxBytes);
    let length = 0;
    try {
        while (true) {
            const item = await reader.read();
            if (item.done) break;
            if (item.value.byteLength > bytes.length - length) {
                throw Error('Response exceeds byte limit');
            }
            bytes.set(item.value, length);
            length += item.value.byteLength;
        }
    } catch (error) {
        // Cancel without waiting for further input from the peer.
        reader.cancel().catch(() => {});
        throw error;
    } finally {
        reader.releaseLock();
    }
    let text;
    try {
        text = new TextDecoder('utf-8', {fatal: true}).decode(bytes.subarray(0, length));
    } catch (_) {
        throw Error('Invalid UTF-8 response');
    }
    return checkRemote(strictJSON(text), config);
}

function renderRemote(values = resolved(state)) {
    for (const panel of document.querySelectorAll('[data-remote]')) {
        const {remote: name, remoteSearch, remoteTitle} = panel.dataset;
        const service = services[name];
        const config = serviceConfigs[name];
        panel.dataset.status = service.status;
        panel.setAttribute('aria-busy', String(service.status === 'loading'));
        panel.querySelector('[data-remote-status]').textContent =
            service.status + (service.error ? ': ' + service.error : '');
        let rows = service.data === null ? [] : (config.many ? service.data : [service.data]);
        if (remoteSearch) {
            const query = values[remoteSearch].toLowerCase();
            rows = rows.filter(row => Object.values(row).some(value => String(value).toLowerCase().includes(query)));
        }
        const items = document.createDocumentFragment();
        const template = panel.querySelector('template');
        for (const row of rows) {
            const card = element('article');
            if (template) {
                card.append(template.content.cloneNode(true));
                fillRow(card, row, values);
            } else {
                card.className = 's-card';
                for (const [key, value] of Object.entries(row)) {
                    card.append(element(key === remoteTitle ? 'h2' : 'p', String(value)));
                }
            }
            items.append(card);
        }
        if (service.status === 'success' && !rows.length) {
            items.append(element('p', 'No matching data'));
        }
        panel.querySelector('[data-remote-results]').replaceChildren(items);
    }
}

function consumeRequestBudget() {
    const now = performance.now();
    while (requestTimes.length && now - requestTimes[0] >= 60000) requestTimes.shift();
    if (requestTimes.length >= 60) return false;
    requestTimes.push(now);
    return true;
}

function createService(name, config) {
    const service = {
        status: 'idle', data: null, error: '', sequence: 0, controller: null,
        manuallyCancelled: false,
    };
    let cacheKey = '';
    let cacheRejected = false;

    function invalidateRequest() {
        service.sequence++;
        service.controller?.abort();
        service.controller = null;
    }

    function sync(values) {
        const path = config.path.replace(/:([A-Za-z][A-Za-z0-9_]*)/g, (_, key) => String(values[key]));
        if (service.path === path) return;
        invalidateRequest();
        service.path = path;
        service.status = 'idle';
        service.data = null;
        service.error = '';
        service.manuallyCancelled = false;
        cacheRejected = false;
        cacheKey = 'sedrava-api:' + location.pathname + ':' + document.title + ':' +
            name + ':' + JSON.stringify(config) + ':' + path;
        if (!config.cache) return;
        try {
            const raw = localStorage.getItem(cacheKey);
            if (raw === null) return;
            service.data = readServiceCache(raw, config);
            service.status = 'success';
        } catch (_) {
            cacheRejected = true;
            service.error = 'Saved API data rejected; original retained';
        }
    }

    function cancel(manual = false) {
        invalidateRequest();
        service.manuallyCancelled = manual;
        if (service.status === 'loading') {
            service.status = 'idle';
            service.error = 'Request cancelled';
        }
    }

    function saveCache(data) {
        if (!config.cache || cacheRejected) return;
        try {
            const previous = localStorage.getItem(cacheKey);
            if (previous !== null) readServiceCache(previous, config);
            const serialized = JSON.stringify(data);
            if (exceedsByteLimit(serialized, config.maxBytes)) throw Error('Cache exceeds byte limit');
            localStorage.setItem(cacheKey, serialized);
        } catch (_) {
            cacheRejected = true;
            service.error = 'Could not save API cache; original retained';
        }
    }

    async function load() {
        if (invalidInput()) return;
        const values = resolved(state);
        sync(values);
        cancel();
        if (!consumeRequestBudget()) {
            service.status = 'error';
            service.error = 'HTTP request budget exhausted';
            renderRemote(values);
            return;
        }
        const sequence = service.sequence;
        const controller = new AbortController();
        service.controller = controller;
        let expired = false;
        const timer = setTimeout(() => {
            expired = true;
            controller.abort();
        }, config.timeout);
        service.status = 'loading';
        service.error = '';
        renderRemote(values);
        try {
            const target = new URL(service.path, location.origin);
            if (target.origin !== location.origin || !['http:', 'https:'].includes(target.protocol)) {
                throw Error('Origin capability mismatch');
            }
            const body = serviceBodies[name] ? JSON.stringify(serviceBodies[name](values)) : undefined;
            if (body !== undefined && exceedsByteLimit(body, config.maxBytes)) {
                throw Error('Request exceeds byte limit');
            }
            const headers = {Accept: 'application/json'};
            if (body !== undefined) headers['Content-Type'] = 'application/json';
            const response = await fetch(target.href, {
                method: config.method, body, headers, mode: 'same-origin', credentials: 'omit',
                redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer', signal: controller.signal,
            });
            const data = await readServiceResponse(response, config);
            if (controller.signal.aborted) throw Error('Request aborted');
            if (sequence !== service.sequence) return;
            service.data = data;
            service.status = 'success';
            service.error = cacheRejected ? 'Saved API data rejected; original retained' : '';
            saveCache(data);
        } catch (error) {
            if (sequence !== service.sequence) return;
            service.status = 'error';
            service.error = expired ? 'Request timed out' :
                (error instanceof TypeError ? 'Network error' : String(error.message || 'Network error'));
        } finally {
            controller.abort();
            clearTimeout(timer);
            if (sequence === service.sequence) {
                service.controller = null;
                renderRemote();
            }
        }
    }

    return Object.assign(service, {sync, cancel, load});
}

function setupServices() {
    for (const [name, config] of Object.entries(serviceConfigs)) {
        services[name] = createService(name, config);
    }
    for (const button of document.querySelectorAll('[data-request]')) {
        button.addEventListener('click', () => services[button.dataset.request].load());
    }
    for (const button of document.querySelectorAll('[data-cancel-request]')) {
        button.addEventListener('click', () => {
            services[button.dataset.cancelRequest].cancel(true);
            renderRemote();
        });
    }
    window.addEventListener('pagehide', () => {
        for (const service of Object.values(services)) service.cancel();
    });
    window.addEventListener('pageshow', syncServiceViews);
    servicesReady = true;
    syncServiceViews();
}

function syncServiceViews() {
    if (!servicesReady) return;
    const values = resolved(state);
    const visible = new Set([...document.querySelectorAll('[data-remote]')]
        .filter(panel => !panel.closest('[hidden]'))
        .map(panel => panel.dataset.remote));
    for (const [name, service] of Object.entries(services)) {
        service.sync(values);
        if (!visible.has(name) && service.controller) service.cancel();
        if (visible.has(name) && serviceConfigs[name].auto && service.status === 'idle' &&
                !service.manuallyCancelled && !invalidInput()) service.load();
    }
    renderRemote(values);
}
