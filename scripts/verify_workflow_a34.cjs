"use strict";
const assert=require("node:assert/strict");
const {randomUUID}=require("node:crypto");
const {JSDOM}=require("jsdom");
const url=process.env.A34_URL;
async function main(){
 const html=await(await fetch(url+"/")).text(),script=await(await fetch(url+"/app.js")).text();
 const dom=new JSDOM(html,{url,runScripts:"outside-only"}),w=dom.window,d=w.document;
 Object.assign(w,{TextEncoder,TextDecoder,AbortController,AbortSignal});
 w.crypto.randomUUID=randomUUID;
 let calls=0;
 w.fetch=async(target,options)=>{assert.equal(new URL(target,url).origin,url);calls++;return fetch(target,options);};
 w.eval(script);
 const q=s=>d.querySelector(s),remote=n=>q('[data-remote="'+n+'"]');
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const wait=async fn=>{for(let i=0;i<250;i++){if(fn())return;await sleep(30);}throw Error("UI timeout");};
 const status=()=>q("[data-session-status]").textContent;
 function go(n){q('[data-action="go_'+n+'"]').click();assert.equal(q('[data-when="show_'+n+'"]').hidden,false);}
 function input(n,v){const el=q('[data-input="'+n+'"]');assert.ok(!el.closest("[data-when]").hidden);el.value=v;el.dispatchEvent(new w.Event("input",{bubbles:true}));}
 function val(n){return q('[data-input="'+n+'"]').value;}
 async function load(n,expected="success"){const p=remote(n);q('[data-request="'+n+'"]').click();await wait(()=>p.dataset.status===expected);}
 async function login(role){q("[data-session-key]").value=process.env["A34_"+role.toUpperCase()];q("[data-session-login]").click();await wait(()=>status().includes("Подключено: "+role));}
 async function logout(){q("[data-session-logout]").click();await wait(()=>status()==="Не подключено");}
 function pick(n){const b=remote(n).querySelector("[data-remote-pick]");assert.ok(b&&!b.disabled);b.click();}
 await login("writer");go("asset");await load("list_asset");
 const selected=remote("list_asset").querySelector('[data-remote-pick="id:v_ticket_asset"]');
 assert.ok(selected&&!selected.disabled);selected.click();
 assert.equal(val("v_ticket_asset"),"a01");
 input("id_ticket","z-ui-ticket");input("v_ticket_issue","Тест интерфейса");await load("create_ticket");
 input("after_ticket","t01");await load("list_ticket");pick("list_ticket");
 assert.equal(val("wf_selected"),"z-ui-ticket");assert.equal(val("wf_expected"),"z-ui-ticket");
 input("wf_event","z-ui-close");input("wf_note","Готово");await load("wf_close");
 await load("list_ticket");pick("list_ticket");assert.equal(val("wf_expected"),"z-ui-close");
 input("wf_event","z-ui-reopen");input("wf_note","Повтор");await load("wf_reopen");
 await load("wf_history");assert.match(remote("wf_history").textContent,/reopen/);
 await logout();assert.equal(val("wf_selected"),"");assert.equal(w.localStorage.length,0);
 w.close();console.log("PASS A34 generated DOM",calls,"real requests; generated forms, typed selection, lifecycle, history and logout");
}
main().catch(e=>{console.error(e);process.exitCode=1;});
