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
 await login("writer");go("ticket");
 input("vf_equipment","a01");
 await load("vread_equipment");await load("vread_open");await load("vread_statuses");await load("vread_priorities");
 const total=p=>paths.filter(x=>x===p).length;
 const result=n=>remote(n).querySelector("[data-remote-results]").textContent;
 const rows=n=>[...remote(n).querySelectorAll("[data-remote-results] article")].map(r=>[...r.querySelectorAll("[data-row-field]")].map(f=>f.textContent));
 assert.match(result("vread_statuses"),/23/);
 go("asset");await load("list_asset");
 const selected=remote("list_asset").querySelector('[data-remote-pick="id:v_ticket_asset"]');assert.ok(selected&&!selected.disabled);selected.click();
 const reads=["equipment","open","statuses","priorities"];
 const counts=()=>reads.map(n=>total("/view-"+n));
 const before=counts(),unrelated=total("/domain-asset-list");
 input("id_ticket","z-ui-ticket");input("v_ticket_issue","Проверка отчёта");await load("create_ticket");
 await wait(()=>reads.every(n=>remote("vread_"+n).dataset.status==="success"));
 assert.deepEqual(counts(),before.map(n=>n+1));
 assert.match(result("vread_statuses"),/24/);assert.equal(total("/domain-asset-list"),unrelated);
 // Select a record directly from a filtered view; workflow updates all dependent views.
 input("va_open","t23");await load("vread_open");
 pick("vread_open");assert.equal(val("wf_selected"),"z-ui-ticket");assert.equal(val("wf_expected"),"z-ui-ticket");
 input("wf_event","z-ui-close");input("wf_note","Готово");
 const beforeClose=counts();await load("wf_close");
 await wait(()=>reads.every(n=>remote("vread_"+n).dataset.status==="success"));
 assert.deepEqual(counts(),beforeClose.map(n=>n+1));
 assert.equal(remote("vread_open").querySelector("[data-remote-pick]"),null);
 assert.match(result("vread_statuses"),/closed/);assert.match(result("vread_statuses"),/23/);
 input("va_equipment","t20");go("asset");
 const asset2=[...remote("list_asset").querySelectorAll("article")].find(r=>r.textContent.includes("a02"));
 const filter=asset2.querySelector('[data-remote-pick="id:vf_equipment"]');assert.ok(filter&&!filter.disabled);filter.click();
 assert.equal(val("vf_equipment"),"a02");assert.equal(val("va_equipment"),"");
 assert.equal(remote("vread_equipment").querySelector("[data-remote-pick]"),null);
 await load("vread_equipment");assert.ok(!result("vread_equipment").includes("z-ui-ticket"));
 await logout();assert.equal(result("vread_statuses"),"");assert.equal(w.localStorage.length,0);
 w.close();console.log("PASS A36 generated views DOM",calls,"real requests; filtered selection, automatic reports, no unrelated refresh, filter invalidation and logout");
}
main().catch(e=>{console.error(e);process.exitCode=1;});
