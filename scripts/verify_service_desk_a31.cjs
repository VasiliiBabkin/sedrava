"use strict";
const assert=require("node:assert/strict");
const {randomUUID}=require("node:crypto");
const {JSDOM}=require("jsdom");
const url=process.env.A31_URL;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function main(){
 const html=await(await fetch(url+"/")).text(),script=await(await fetch(url+"/app.js")).text();
 const dom=new JSDOM(html,{url,runScripts:"outside-only"}),w=dom.window,d=w.document;
 Object.assign(w,{TextEncoder,TextDecoder,AbortController,AbortSignal});
 w.crypto.randomUUID=randomUUID;
 let lose=false,requests=0,keys=[];
 w.fetch=async(target,options)=>{
  assert.equal(new URL(target,url).origin,url);
  const path=new URL(target,url).pathname;
  requests++;
  if(path==="/add-work")keys.push(options.headers["Idempotency-Key"]);
  const res=await fetch(target,options);
  if(lose&&path==="/add-work"){
   lose=false;assert.equal(res.status,200);await res.text();throw Error("lost committed response");
  }
  return res;
 };
 w.eval(script);
 const q=s=>d.querySelector(s),remote=n=>q('[data-remote="'+n+'"]'),result=n=>remote(n).querySelector("[data-remote-results]").textContent;
 const status=()=>q("[data-session-status]").textContent;
 const wait=async fn=>{for(let i=0;i<250;i++){if(fn())return;await sleep(30);}throw Error("UI timeout: "+status());};
 const input=(name,value)=>{
  navigate(inputSection[name]);const el=q('[data-input="'+name+'"]');assert.ok(el,name);assert.ok(!el.closest("[data-when]").hidden);
  el.value=String(value);el.dispatchEvent(new w.Event("input",{bubbles:true}));
 };
 const inputSection={client_new:"directory",client_name:"directory",client_contact:"directory",client_after:"directory",site_new:"directory",site_client:"directory",site_name:"directory",site_address:"directory",client_filter:"directory",asset_new:"equipment",asset_site:"equipment",asset_name:"equipment",asset_serial:"equipment",site_filter:"equipment",ticket_new:"register",ticket_asset:"register",ticket_issue:"register",ticket_priority:"register",ticket_day:"register",ticket_asset_filter:"overview",event_new:"workflow",event_ticket:"workflow",expected_event:"workflow",work_day:"workflow",work_note:"workflow",work_minutes:"workflow",work_cost:"workflow",history_ticket:"history",event_after:"history"};
 const fields=obj=>Object.entries(obj).forEach(([k,v])=>input(k,v));
 const sectionOf={clients:"directory",add_client:"directory",sites:"directory",add_site:"directory",assets:"equipment",add_asset:"equipment",add_ticket:"register",asset_tickets:"overview",tickets:"overview",dashboard:"overview",add_work:"workflow",close_ticket:"workflow",reopen_ticket:"workflow",events:"history",ticket_totals:"history"};
 function navigate(section){
  q('[data-action="go_'+section+'"]').click();
  const shown=[...d.querySelectorAll('[data-when^="show_"]')].filter(e=>!e.hidden);
  assert.equal(shown.length,1);assert.equal(shown[0].dataset.when,"show_"+section);
 }
 async function click(name,expected="success"){
  navigate(sectionOf[name]);
  const node=remote(name);assert.ok(node,name);assert.ok(!node.closest("[data-when]").hidden);
  q('[data-request="'+name+'"]').click();
  await wait(()=>node.dataset.status===expected);
 }
 async function login(user,key){q("[data-session-key]").value=key;q("[data-session-login]").click();await wait(()=>status().includes("Подключено: "+user));assert.equal(q("[data-session-key]").value,"");}
 async function logout(){q("[data-session-logout]").click();await wait(()=>status()==="Не подключено");}
 await click("clients","error");assert.equal(requests,0);
 await login("reader",process.env.A31_READER);
 await click("clients");assert.match(result("clients"),/Тестовый заказчик/);
 fields({client_new:"z-ui-client",client_name:"<img src=x onerror=alert(1)>",client_contact:""});
 await click("add_client","error");assert.match(remote("add_client").textContent,/403/);
 await logout();assert.equal(result("clients"),"");
 await login("writer",process.env.A31_WRITER);
 await click("add_client");
 input("client_after","c22");await click("clients");
 assert.match(result("clients"),/<img src=x/);assert.equal(remote("clients").querySelector("img"),null);
 fields({site_new:"z-ui-site",site_client:"z-ui-client",site_name:"Офис UI",site_address:"Тестовый адрес"});
 await click("add_site");
 input("client_filter","z-ui-client");await click("sites");assert.match(result("sites"),/Офис UI/);
 fields({asset_new:"z-ui-asset",asset_site:"z-ui-site",asset_name:"Считыватель",asset_serial:"UI-001"});
 await click("add_asset");input("site_filter","z-ui-site");await click("assets");assert.match(result("assets"),/Считыватель/);
 fields({ticket_new:"z-ui-ticket",ticket_asset:"z-ui-asset",ticket_issue:"Не читается карта",ticket_priority:2,ticket_day:"2026-11-28"});
 await click("add_ticket");
 input("ticket_asset_filter","z-ui-asset");await click("asset_tickets");assert.match(result("asset_tickets"),/Не читается карта/);
 fields({event_new:"z-ui-work",event_ticket:"z-ui-ticket",expected_event:"z-ui-ticket",work_day:"2026-11-28",work_note:"Настройка",work_minutes:20,work_cost:1200});
 lose=true;await click("add_work","error");
 await click("add_work");assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);assert.match(result("add_work"),/true/);
 fields({history_ticket:"z-ui-ticket",event_after:""});await click("events");assert.match(result("events"),/Настройка/);
 await click("ticket_totals");assert.match(result("ticket_totals"),/1200/);
 fields({event_new:"z-ui-close",expected_event:"z-ui-work",work_note:"Работает"});await click("close_ticket");
 await click("asset_tickets");assert.match(result("asset_tickets"),/true/);
 fields({event_new:"z-ui-reopen",expected_event:"z-ui-close",work_note:"Повторная проверка"});await click("reopen_ticket");
 await click("asset_tickets");assert.match(result("asset_tickets"),/false/);
 await click("events");assert.match(result("events"),/reopened/);
 await click("ticket_totals");assert.match(result("ticket_totals"),/1200/);
 await logout();for(const n of ["clients","asset_tickets","events","ticket_totals","add_work"])assert.equal(result(n),"");
 assert.equal(w.localStorage.length,0);assert.equal(w.sessionStorage.length,0);assert.equal(d.cookie,"");
 w.close();
 console.log("PASS A31 generated DOM:",requests,"actual requests; six native sections, read-only rejection, all four creation forms, XSS-safe rendering, lost response replay, close/reopen, totals, logout and no browser storage");
}
main().catch(e=>{console.error(e);process.exitCode=1;});
