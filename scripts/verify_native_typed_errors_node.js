'use strict';
// Node mock DOM acceptance for native Rust-generated typed Result/match Web.
// This is not a substitute for Chromium/Firefox/WebKit execution.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const html = fs.readFileSync(process.argv[2], 'utf8');
const match = html.match(/<script>([\s\S]*?)<\/script>/);
assert(match, 'Generated JS not found');
const el = dataset => ({
    dataset, textContent:'', value:'', hidden:true, events:{},
    addEventListener(name,fn){this.events[name]=fn;}
});
const get = key => [...html.matchAll(new RegExp('data-'+key+'="([^"]+)"','g'))]
    .map(m=>el({[key]:m[1]}));
const states=get('state'), actions=get('action'), error=el({});
const groups={
    '[data-state]':states, '[data-action]':actions,
    '[data-screen]':get('screen'), '[data-input]':[],
    '[data-show]':[], '[data-display]':[]
};
const document={
    activeElement:null,
    getElementById(id){return id==='sedrava-error'?error:null;},
    querySelectorAll(key){return groups[key]||[];}
};
const ctx=vm.createContext({document,console});
vm.runInContext(match[1],ctx,{timeout:4500});
const snapshot=()=>JSON.parse(vm.runInContext('JSON.stringify(resolved(state))',ctx));
function emit(action){console.log('RESULT_STATE '+action+' '+JSON.stringify(snapshot()));}
function click(action){
    const button=actions.find(x=>x.dataset.action===action);
    assert(button,'Missing action '+action);
    assert.equal(typeof button.events.click,'function');
    button.events.click();
}
const state=()=>Object.fromEntries(states.map(v=>[v.dataset.state,v.textContent]));
assert.deepStrictEqual(state(),{total:'0',message:'',flag:'false'});
emit('initial');
click('success');
assert.deepStrictEqual(state(),{total:'4',message:'',flag:'true'});
emit('success');
click('fail');
assert.deepStrictEqual(state(),{total:'101',message:'/foo',flag:'true'});
emit('success_fail');
click('fallback');
assert.deepStrictEqual(state(),{total:'101',message:'example.ReadError.Denied',flag:'true'});
emit('success_fail_fallback');
const before=JSON.stringify(snapshot());
click('rollback');
assert.strictEqual(JSON.stringify(snapshot()),before);
assert.strictEqual(error.hidden,false);
emit('rollback_rejected');
console.log('PASS: Node simulated Web typed Result/match, default error ID, no mutation on overflow');
