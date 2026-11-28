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
 const selected=remote("list_asset").querySelector('[data-remote-pick="id:v_ticket_asset"]');
 assert.ok(selected&&!selected.disabled);selected.click();
 assert.equal(val("v_ticket_asset"),"a01");
 input("after_ticket","t01");await load("list_ticket");
 const total=p=>paths.filter(x=>x===p).length;
 const countBefore=total("/domain-ticket-list"), unrelated=total("/domain-asset-list");
 input("id_ticket","z-ui-ticket");input("v_ticket_issue","Тест интерфейса");await load("create_ticket");
 await wait(()=>remote("list_ticket").dataset.status==="success" && remote("list_ticket").textContent.includes("z-ui-ticket"));
 assert.equal(total("/domain-ticket-list"),countBefore+1);assert.equal(total("/domain-asset-list"),unrelated);
 pick("list_ticket");assert.equal(val("wf_selected"),"z-ui-ticket");assert.equal(val("wf_expected"),"z-ui-ticket");
 await load("wf_history");
 // Simulate a slow old read response that arrives after a committed transition.
 delayed=true;q('[data-request="list_ticket"]').click();await wait(()=>release!==null);
 input("wf_event","z-ui-close");input("wf_note","Готово");
 const historyBefore=total("/workflow-history");
 lose=true;await load("wf_close","error");
 assert.equal(remote("list_ticket").querySelector("[data-remote-pick]"),null);
 assert.equal(remote("wf_history").querySelector("[data-remote-results]").textContent,"");
 release();await sleep(50);assert.equal(remote("list_ticket").querySelector("[data-remote-pick]"),null);
 assert.equal(total("/workflow-history"),historyBefore);
 await load("wf_close");assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);
 await wait(()=>remote("list_ticket").dataset.status==="success" && remote("list_ticket").textContent.includes("z-ui-close"));
 await wait(()=>remote("wf_history").dataset.status==="success" && remote("wf_history").textContent.includes("close"));
 assert.equal(total("/workflow-history"),historyBefore+1);
 assert.equal(val("wf_expected"),"z-ui-ticket"); // drafts are not silently rewritten
 pick("list_ticket");assert.equal(val("wf_expected"),"z-ui-close");
 input("wf_event","z-ui-reopen");input("wf_note","Повтор");
 q('[data-request="wf_reopen"]').click();go("client");
 await wait(()=>remote("wf_reopen").dataset.status==="success");
 const hiddenBefore=total("/workflow-history");await sleep(60);assert.equal(total("/workflow-history"),hiddenBefore);
 go("ticket");await wait(()=>remote("wf_history").dataset.status==="success" && remote("wf_history").textContent.includes("reopen"));
 await wait(()=>remote("list_ticket").dataset.status==="success" && remote("list_ticket").textContent.includes("z-ui-reopen"));
 assert.equal(total("/workflow-history"),hiddenBefore+1);assert.equal(total("/workflow-reopen"),1);
 assert.equal(total("/domain-asset-list"),unrelated);
 await logout();assert.equal(val("wf_selected"),"");assert.equal(w.localStorage.length,0);
 w.close();console.log("PASS A35 reactive DOM",calls,"real requests; automatic targeted refresh, stale response rejection, replay, hidden deferral, draft retention and logout");
}
main().catch(e=>{console.error(e);process.exitCode=1;});
