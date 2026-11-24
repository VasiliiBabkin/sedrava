#!/usr/bin/env node
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {JSDOM,ResourceLoader,VirtualConsole}=require(process.env.SEDRAVA_JSDOM_PATH||'jsdom');
const dir=path.resolve(process.argv[2]);
class LocalResources extends ResourceLoader {
  fetch(url){
    const u=new URL(url);assert.equal(u.origin,'http://journal.test');
    const p=path.resolve(dir,decodeURIComponent(u.pathname).replace(/^\/+/,''));
    assert(p.startsWith(dir+path.sep));return Promise.resolve(fs.readFileSync(p));
  }
}
async function load(storage={}){
  const errors=[];const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(String(e)));
  const dom=new JSDOM(fs.readFileSync(path.join(dir,'index.html'),'utf8'),{
    url:'http://journal.test/index.html',resources:new LocalResources(),runScripts:'dangerously',
    pretendToBeVisual:true,virtualConsole:vc,
    beforeParse(w){for(const [k,v] of Object.entries(storage))w.localStorage.setItem(k,v);}
  });
  await new Promise((resolve,reject)=>{const t=setTimeout(()=>reject(Error('timeout')),10000);
    dom.window.addEventListener('load',()=>{clearTimeout(t);resolve();},{once:true});});
  assert.deepEqual(errors,[]);return dom;
}
function input(dom,name,value){let el=dom.window.document.querySelector('[data-input="'+name+'"]');assert(el,name);el.value=value;el.dispatchEvent(new dom.window.Event('input',{bubbles:true}));}
function click(dom,action){const el=dom.window.document.querySelector('[data-action="'+action+'"]');assert(el,action);el.click();}
function count(dom,name,value){assert.equal(dom.window.document.querySelector('output[data-state="'+name+'"]').textContent,String(value));}
function table(dom){return dom.window.document.querySelector('table');}
function select(dom,title){const el=[...table(dom).querySelectorAll('button')].find(x=>x.textContent.includes(title)||x.getAttribute('aria-label')?.includes(title));assert(el,title);el.click();}
async function main(){
  let dom=await load();
  count(dom,'ticket_count',0);
  for(const [site,title] of [['Объект А','Проверка камеры'],['Объект Б','Замена датчика']]){
    input(dom,'site_name',site);input(dom,'title',title);click(dom,'add');
  }
  count(dom,'ticket_count',2);count(dom,'open_count',2);count(dom,'done_count',0);
  assert(table(dom).textContent.includes('Объект А'));
  input(dom,'search_text','Замена');assert(!table(dom).textContent.includes('Проверка камеры'));assert(table(dom).textContent.includes('Замена датчика'));
  input(dom,'search_text','');
  select(dom,'Проверка камеры');click(dom,'toggle');
  count(dom,'open_count',1);count(dom,'done_count',1);
  input(dom,'new_title','Камера проверена');click(dom,'rename');assert(table(dom).textContent.includes('Камера проверена'));
  const storage={};for(let i=0;i<dom.window.localStorage.length;i++){const k=dom.window.localStorage.key(i);storage[k]=dom.window.localStorage.getItem(k);}
  assert(Object.keys(storage).length>0);dom.window.close();
  dom=await load(storage);count(dom,'ticket_count',2);count(dom,'done_count',1);assert(table(dom).textContent.includes('Камера проверена'));
  select(dom,'Замена датчика');click(dom,'delete');count(dom,'ticket_count',1);count(dom,'open_count',0);count(dom,'done_count',1);
  dom.window.close();console.log('PASS service journal: generated WebApp DOM, create/search/select/rename/status/delete, localStorage reload, derived totals; no real browser');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
