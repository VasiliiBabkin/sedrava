"use strict";
// DOM integration against the actual native loopback HTTP server (not a browser engine).
const assert = require("node:assert/strict");
const {randomUUID} = require("node:crypto");
const {JSDOM} = require("jsdom");
const url=process.env.SEDRAVA_A22_URL, writer=process.env.SEDRAVA_A22_WRITER, reader=process.env.SEDRAVA_A22_READER;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function until(test){
  for(let i=0;i<200;i++){if(test())return;await sleep(30);}
  throw Error("UI wait timeout");
}
async function main(){
  const html=await (await fetch(url+"/")).text();
  const script=await (await fetch(url+"/ui-script")).text();
  const dom=new JSDOM(html,{url,runScripts:"outside-only"});
  const w=dom.window,d=w.document,$=id=>d.getElementById(id);
  w.crypto.randomUUID=randomUUID;
  let lose=false; const keys=[];
  w.fetch=async (path,options)=>{
    assert(path.startsWith("/")&&!path.startsWith("//"));
    const res=await fetch(url+path,options);
    if(options.headers["Idempotency-Key"])keys.push(options.headers["Idempotency-Key"]);
    if(lose && path==="/add-product"){lose=false;await res.text();throw Error("simulated lost response after commit");}
    return res;
  };
  w.eval(script);
  const submit=id=>$(id).dispatchEvent(new w.Event("submit",{cancelable:true,bubbles:true}));
  const fill=(id,values)=>{for(const [k,v] of Object.entries(values))$(id).elements.namedItem(k).value=String(v);};
  async function idle(){await until(()=>$("login").querySelector("button").disabled===false);}
  async function login(t){$("token").value=t;submit("login");await idle();}
  assert($("workspace").hidden);
  await login(reader); assert(!$("workspace").hidden);assert.equal($("token").value,"");
  fill("product-form",{id:"p0",title:"Forbidden",category:"food",price:2});submit("product-form");await idle();assert.match($("status").textContent,/WRITE_FORBIDDEN/);
  $("logout").click();assert($("workspace").hidden);assert.equal($("products").children.length,0);
  await login(writer);assert(!$("workspace").hidden);
  fill("product-form",{id:"p1",title:"<img src=x onerror=alert(1)>",category:"food",price:100});
  lose=true;submit("product-form");await idle();assert.match($("status").textContent,/неизвестен/);const key=keys.at(-1);
  submit("product-form");await idle();assert.equal(keys.at(-1),key);assert.match($("status").textContent,/Повтор подтверждён/);assert.equal($("products").children.length,1);
  assert.equal($("products").querySelector("img"),null);assert.match($("products").textContent,/<img src=x/);
  fill("order-form",{id:"o1",product_id:"p1",amount:150});submit("order-form");await idle();assert.match($("status").textContent,/Запись сохранена/);assert.equal($("orders").children.length,1);
  fill("correct-form",{id:"o1",old_amount:150,new_amount:175});submit("correct-form");await idle();assert.match($("orders").textContent,/175/);
  $("orders").querySelector("button").click();await idle();assert.equal($("paid-count").textContent,"1");assert.equal($("revenue").textContent,"175");
  fill("atomic-form",{product_id:"p2",title:"Чай",category:"food",price:50,order_id:"o2",amount:50});submit("atomic-form");await idle();assert.equal($("product-count").textContent,"2");assert.equal($("orders").children.length,2);
  fill("atomic-form",{product_id:"p3",title:"Отказ",category:"food",price:50,order_id:"o2",amount:50});submit("atomic-form");await idle();assert.match($("status").textContent,/SQL_CONFLICT/);assert.equal($("product-count").textContent,"2");
  $("refresh").click();await idle();assert.equal($("products").children.length,2);
  assert.equal(w.localStorage.length,0);assert.equal(w.sessionStorage.length,0);assert.equal(d.cookie,"");
  $("logout").click();assert.equal($("products").children.length,0);assert.equal($("orders").children.length,0);assert($("workspace").hidden);
  w.close();console.log("PASS A22 DOM + real HTTP: read/write auth, XSS-safe text, lost-response replay, add/correct/pay, atomic rollback, refresh/logout, no browser storage");
}
main().catch(e=>{console.error(e);process.exitCode=1;});
