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
 let calls=0, lose=false, delayed=null, release=null;
 const paths=[], keys=[];
 w.fetch=async(target,options)=>{
  const path=new URL(target,url).pathname;assert.equal(new URL(target,url).origin,url);
  calls++;paths.push(path);const res=await fetch(target,options);
  if(path==="/workflow-close"){
   keys.push(options.headers["Idempotency-Key"]);
   if(lose){lose=false;assert.equal(res.status,200);await res.text();throw Error("lost committed response");}
  }
  if(path==="/domain-ticket-list"&&delayed===true){
   delayed=false;await new Promise(r=>{release=r;});
  }
  return res;
 };
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
 const selected=remote("list_asset").querySelector('[data-remote-pick="id:v_ticket_asset"]');assert.ok(selected&&!selected.disabled);selected.click();
 input("id_ticket","z-ui-ticket");input("v_ticket_issue","Проверка UI");input("ev_day","2026-11-28");
 await load("create_ticket");
 input("vf_tickets","open");input("va_tickets","t02");await load("vread_tickets");pick("vread_tickets");
 assert.equal(val("wf_selected"),"z-ui-ticket");assert.equal(val("wf_expected"),"z-ui-ticket");
 await load("wf_history");await load("vread_totals");
 const values=n=>[...remote(n).querySelectorAll("[data-remote-results] article")].map(r=>[...r.querySelectorAll("[data-row-field]")].map(f=>f.textContent));
 const totals=()=>values("vread_totals");
 assert.deepEqual(totals(),[["z-ui-ticket","1","0","0"]]);
 input("wf_event","z-ui-work");input("wf_note","Диагностика");input("ev_minutes","45");input("ev_cost","1500");
 await load("wf_work");
 await wait(()=>remote("vread_totals").dataset.status==="success"&&JSON.stringify(totals())===JSON.stringify([["z-ui-ticket","2","45","1500"]]));
 await wait(()=>remote("vread_tickets").dataset.status==="success");pick("vread_tickets");assert.equal(val("wf_expected"),"z-ui-work");
 input("wf_event","z-ui-close");input("wf_note","Готово");
 lose=true;await load("wf_close","error");await load("wf_close");assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);
 await wait(()=>remote("vread_totals").dataset.status==="success"&&JSON.stringify(totals())===JSON.stringify([["z-ui-ticket","3","45","1500"]]));
 input("vf_tickets","closed");await load("vread_tickets");pick("vread_tickets");assert.equal(val("wf_expected"),"z-ui-close");
 input("wf_event","z-ui-reopen");input("wf_note","Повтор");await load("wf_reopen");
 await wait(()=>remote("vread_totals").dataset.status==="success"&&JSON.stringify(totals())===JSON.stringify([["z-ui-ticket","4","45","1500"]]));
 await wait(()=>remote("wf_history").dataset.status==="success");
 assert.match(remote("wf_history").textContent,/2026-11-28/);
 assert.equal(remote("vread_tickets").querySelector("[data-remote-pick]"),null);
 await logout();assert.deepEqual(totals(),[]);assert.equal(w.localStorage.length,0);
 w.close();console.log("PASS A37 generated complete DOM",calls,"real requests; event capture, automatic sums, defaults on close/reopen, lost-response replay and logout");
}
main().catch(e=>{console.error(e);process.exitCode=1;});
