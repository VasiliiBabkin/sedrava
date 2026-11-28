const services = Object.create(null);
const requestTimes = [];
const utf8Encoder = new TextEncoder();
let servicesReady = false;
// Auth state deliberately lives outside the serializable Sedrava state.
let session = null, sessionBusy = false;
let sessionControl = null;
function reactiveWriteBusy() {
    return Object.entries(services).some(([n,s])=>serviceConfigs[n].refresh?.length && s.controller);
}
function invalidateDependents(config, confirmed=false) {
    for (const target of config.refresh) services[target].invalidateRead(confirmed);
}
function flushReactiveReads() {
    if (!session || sessionBusy || reactiveWriteBusy() || invalidInput()) return;
    for (const [name,s] of Object.entries(services)) {
        if (s.refreshNeeded && !s.controller && !s.manuallyCancelled &&
            [...document.querySelectorAll('[data-remote]')].some(p=>p.dataset.remote===name && !p.closest('[hidden]'))) {
            s.load();
        }
    }
}
function sessionStatus(message) {
    if(sessionControl) sessionControl.querySelector('[data-session-status]').textContent=message;
}
function clearSession(discardPending=false) {
    const keepReadIntent=!discardPending && Object.values(services).some(s=>s.pending);
    session=null;
    for(const [name,service] of Object.entries(services)) {
        if(serviceConfigs[name].session) service.resetAuth(discardPending,keepReadIntent);
    }
    // Explicit logout clears all volatile state of remote-pick apps. On a 401
    // preserve pending mutation parameters for same-principal retry, otherwise reset.
    if (document.querySelector('[data-remote] template') &&
        [...document.querySelectorAll('[data-remote] template')].some(t=>t.content.querySelector('[data-remote-pick]')) &&
        (discardPending || !Object.values(services).some(s=>s.pending))) {
        state={...initialState};
        for (const input of inputs) { input.value=String(state[input.dataset.input]); setInvalid(input,false); }
        render();
    } else renderRemote();
}
async function sessionCall(path,authorization) {
    if(!["http:","https:"].includes(location.protocol)) throw Error("HTTP origin required");
    const response=await fetch(new URL(path,location.origin).href,{
        method:'POST',body:'{}',headers:{Authorization:authorization,'Content-Type':'application/json'},
        mode:'same-origin',credentials:'omit',redirect:'error',cache:'no-store',referrerPolicy:'no-referrer',
        signal:AbortSignal.timeout(10000)
    });
    if(path==="/session-logout" && response.status===401) return {revoked:false};
    // Reuse bounded, strict response decoding. Never expose raw response/error to UI.
    const schema=path==='/session-login'
        ? {token:'text',principal:'text',role:'text',expires_in:'int32'}
        : {revoked:'bool'};
    return readServiceResponse(response,{many:false,maxItems:1,maxBytes:4096,fields:schema});
}
async function changeSession(login) {
    if(sessionBusy) return;
    sessionBusy=true;
    const keyInput=sessionControl.querySelector('[data-session-key]');
    const key=keyInput.value; keyInput.value='';
    try {
        if(login) {
            if(session) throw Error('Сначала завершите текущую сессию');
            if(!/^[0-9a-f]{64}$/.test(key)) throw Error('Неверный формат ключа');
            const result=await sessionCall('/session-login','Bearer '+key);
            if(!/^[0-9a-f]{64}$/.test(result.token)||!/^[A-Za-z][A-Za-z0-9_]{0,47}$/.test(result.principal)||
                !['read','write'].includes(result.role)||result.expires_in<1||result.expires_in>3600) throw Error('Некорректный ответ входа');
            if(Object.values(services).some(s=>s.pending && s.pending.owner!==result.principal)) {
                await sessionCall('/session-logout','Session '+result.token);
                throw Error('Войдите под прежним пользователем для повтора записи');
            }
            session={token:result.token,principal:result.principal};
            sessionStatus('Подключено: '+result.principal+' ('+result.role+')');
        } else {
            if(session) await sessionCall('/session-logout','Session '+session.token);
            clearSession(true);
            sessionStatus('Не подключено');
        }
    } catch(error) {
        sessionStatus('Ошибка: '+String(error.message||'Network error'));
    } finally { sessionBusy=false; }
}
function setupSession() {
    sessionControl=document.querySelector('[data-session-control]');
    if(!sessionControl) return;
    sessionControl.querySelector('[data-session-login]').onclick=()=>changeSession(true);
    sessionControl.querySelector('[data-session-logout]').onclick=()=>changeSession(false);
}


function checkRemote(data, config) {
    if(config.sqlColumns) {
        if(!isPlainRecord(data)||Object.keys(data).length!==3||
            !['rows','join_rows','aggregate_rows'].includes(data.kind)||
            !Array.isArray(data.columns)||!Array.isArray(data.rows)||
            data.columns.length!==config.sqlColumns.length||
            !config.sqlColumns.every((key,i)=>key===data.columns[i])||
            data.rows.length>config.maxItems) throw Error('Invalid SQL response envelope');
        data=data.rows.map(row=>{
            if(!Array.isArray(row)||row.length!==config.sqlColumns.length) throw Error('Invalid SQL row');
            return Object.fromEntries(config.sqlColumns.map((key,i)=>[key,row[i]]));
        });
    }
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
        if(config.sqlColumns) throw Error("SQL response envelope required");
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

function serviceSignature(name, values) {
    const config=serviceConfigs[name];
    const path=config.path.replace(/:([A-Za-z][A-Za-z0-9_]*)/g,(_,key)=>String(values[key]));
    const body=serviceBodies[name]?JSON.stringify(serviceBodies[name](values)):undefined;
    return JSON.stringify([path,body]);
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
                for (const button of card.querySelectorAll('[data-remote-pick]')) {
                    const data=service.data, sequence=service.sequence;
                    const available=()=>{try{return !!session && !sessionBusy && service.status==='success' &&
                        service.data===data && service.sequence===sequence &&
                        service.resultSignature===serviceSignature(name,resolved(state)) &&
                        !invalidInput();}catch(_){return false;}};
                    button.disabled=!available();
                    button.onclick=()=>{
                        if (!button.isConnected || button.closest('[hidden]') || !available()) {
                            showError('Remote selection expired; reload the list');
                            return;
                        }
                        try {
                            const next={...state};
                            for (const binding of button.dataset.remotePick.split(/\s+/)) {
                                const [field,target]=binding.split(':');
                                next[target]=row[field];
                            }
                            if (!validate(next)) throw Error('Selection rejected');
                            const action=button.dataset.remotePickAction;
                            if (!commit(action?perform(action,next):next)) throw Error('Selection rejected');
                        } catch(error) { showError('Remote selection rejected: '+error.message); }
                    };
                }

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
        manuallyCancelled: false, pending: null, resultSignature: null,
        requested:false, refreshNeeded:false, readSignature:null,
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
        const signature=config.tracked?serviceSignature(name,values):null;
        if (service.path === path && service.readSignature===signature) return;
        service.readSignature=signature;
        invalidateRequest();
        service.path = path;
        service.status = 'idle';
        service.data = null;
        service.resultSignature = null;
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

    function resetAuth(discardPending,keepReadIntent=false) {
        invalidateRequest();
        service.data=null;service.resultSignature=null;service.status='idle';service.error='';
        if(!keepReadIntent) service.requested=false;
        service.refreshNeeded=false;service.manuallyCancelled=false;
        if(discardPending) service.pending=null;
    }
    function invalidateRead(confirmed) {
        invalidateRequest();
        service.data=null;service.resultSignature=null;service.status='idle';service.error='';
        service.refreshNeeded=confirmed && service.requested;
        service.manuallyCancelled=false;
    }
    function cancel(manual = false) {
        invalidateRequest();
        service.manuallyCancelled = manual;
        if(manual) service.refreshNeeded=false;
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
        if ((config.tracked || config.refresh?.length) && reactiveWriteBusy()) return;
        if(config.session && (!session || sessionBusy)){
            service.status='error';service.error='Требуется вход';service.data=null;renderRemote();return;
        }
        const values = resolved(state);
        sync(values);
        cancel();
        if(config.tracked){service.requested=true;service.refreshNeeded=false;}
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
            if(config.session) headers.Authorization='Session '+session.token;
            if(config.idempotency) {
                const signature=JSON.stringify([target.pathname,body]);
                if(service.pending && (service.pending.owner!==session.principal||service.pending.signature!==signature))
                    throw Error('Восстановите прежние параметры незавершённой записи');
                service.pending ??= {owner:session.principal,signature,key:crypto.randomUUID()};
                headers['Idempotency-Key']=service.pending.key;
            }
            if(config.refresh?.length){invalidateDependents(config);renderRemote();}
            const response = await fetch(target.href, {
                method: config.method, body, headers, mode: 'same-origin', credentials: 'omit',
                redirect: 'error', cache: 'no-store', referrerPolicy: 'no-referrer', signal: controller.signal,
            });
            if(config.session && response.status===401) {
                if(sequence===service.sequence){clearSession();sessionStatus('Сессия завершена. Войдите снова');}
                return;
            }
            if(config.idempotency && sequence===service.sequence &&
                [400,403,404,405,409,415,422,428,507].includes(response.status)) service.pending=null;
            const data = await readServiceResponse(response, config);
            if (controller.signal.aborted) throw Error('Request aborted');
            if (sequence !== service.sequence) return;
            if(config.refresh?.length && (data.kind!=='write' ||
                data.affected<1 || data.sequence<1)) throw Error('Invalid mutation receipt');
            if(config.idempotency) service.pending=null;
            if(config.refresh?.length) invalidateDependents(config,true);
            service.data = data;
            service.resultSignature=serviceSignature(name,values);
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
                if(config.refresh?.length) flushReactiveReads();
            }
        }
    }

    return Object.assign(service, {sync, cancel, load, resetAuth, invalidateRead});
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
    setupSession();
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
        if (!visible.has(name) && service.controller && !serviceConfigs[name].refresh?.length) {
            const resume=serviceConfigs[name].tracked && service.requested;
            service.cancel();
            if(resume) service.refreshNeeded=true;
        }
        if (visible.has(name) && serviceConfigs[name].auto && service.status === 'idle' &&
                !service.manuallyCancelled && !invalidInput()) service.load();
    }
    renderRemote(values);
    flushReactiveReads();
}
