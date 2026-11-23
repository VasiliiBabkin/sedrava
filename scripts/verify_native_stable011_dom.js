#!/usr/bin/env node
/* Browser-independent but real DOM test for *generated* stable/native WebApps.
 * Requires an isolated jsdom install; NOT a substitute for Chromium/Firefox.
 */
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const base=path.resolve(process.argv[2]||'');
if (!base || !fs.existsSync(base)) throw Error('Usage: node verify_native_stable011_dom.js DIR_WITH_BUILDS');
const location=process.env.SEDRAVA_JSDOM_PATH||'jsdom';
const {JSDOM,ResourceLoader,VirtualConsole}=require(location);

class LocalResources extends ResourceLoader {
  constructor(folder){super();this.folder=folder;}
  fetch(url){
    const parsed=new URL(url);
    if(parsed.origin!=='http://webapp.test') throw Error('Outbound resource refused '+url);
    const target=path.resolve(this.folder,decodeURIComponent(parsed.pathname).replace(/^\/+/,''));
    if(!target.startsWith(this.folder+path.sep))throw Error('Path escape refused');
    return Promise.resolve(fs.readFileSync(target));
  }
}
function text(doc,name){
  const el=doc.querySelector('output[data-state="'+name+'"]');
  assert(el,'Missing output '+name);
  return el.textContent;
}
function input(dom, selector, value, event='input'){
  const el=dom.window.document.querySelector(selector);
  assert(el,'Missing input '+selector);
  el.value=value;
  el.dispatchEvent(new dom.window.Event(event,{bubbles:true}));
  return el;
}
async function load(engine,example){
  const dir=path.join(base,engine,example);
  const html=fs.readFileSync(path.join(dir,'index.html'),'utf8');
  const errors=[];
  const virtualConsole=new VirtualConsole();
  virtualConsole.on('jsdomError',e=>errors.push(String(e)));
  const dom=new JSDOM(html,{
    url:'http://webapp.test/index.html',
    resources:new LocalResources(dir),
    runScripts:'dangerously',
    pretendToBeVisual:true,
    virtualConsole,
  });
  await new Promise((resolve,reject)=>{
    const guard=setTimeout(()=>reject(Error('DOM load timed out '+example)),12000);
    dom.window.addEventListener('load',()=>{clearTimeout(guard);resolve();},{once:true});
  });
  assert.deepEqual(errors,[],example+' script errors');
  return dom;
}
async function main(){
  let checked=0;
  for(const engine of ['stable011','native012']){
    let dom=await load(engine,'webapp_011_counter');
    let doc=dom.window.document;
    assert.equal(text(doc,'count'),'0');
    doc.querySelector('[data-action="increment"]').click();
    assert.equal(text(doc,'count'),'1');
    assert.equal(text(doc,'double_count'),'2');
    const editor=input(dom,'[data-input="count"]','101');
    assert.equal(editor.getAttribute('aria-invalid'),'true');
    assert.equal(text(doc,'count'),'1');
    doc.querySelector('[data-action="reset"]').click();
    assert.equal(text(doc,'count'),'1','Rejected input must block reset action');
    dom.window.close();
    checked++;
    console.log('PASS',engine,'counter: real DOM state, click, typed validation');
    dom=await load(engine,'webapp_011_tasks');
    doc=dom.window.document;
    assert.equal(text(doc,'task_count'),'0');
    input(dom,'[data-input="new_title"]','Task from DOM');
    doc.querySelector('[data-action="add"]').click();
    assert.equal(text(doc,'task_count'),'1');
    const selection=doc.querySelector('ul[data-list="tasks"] button');
    assert(selection,'List selection was not rendered');
    selection.click();
    assert.equal(doc.querySelector('ul[data-list="tasks"] button').getAttribute('aria-pressed'),'true');
    input(dom,'[data-input="rename_to"]','Updated task');
    doc.querySelector('[data-action="rename"]').click();
    assert(doc.querySelector('ul[data-list="tasks"]').textContent.includes('Updated task'));
    doc.querySelector('[data-action="delete"]').click();
    assert.equal(text(doc,'task_count'),'0');
    dom.window.close();
    checked++;
    console.log('PASS',engine,'tasks: real DOM add/select/rename/delete');
  }
  console.log('PASS',checked,'jsdom WebApp scenarios across exact stable 0.11 and native 0.12. Chromium NOT tested');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
