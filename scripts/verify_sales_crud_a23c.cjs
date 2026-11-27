"use strict";
const assert=require("node:assert/strict");
const {randomUUID}=require("node:crypto");
const {JSDOM}=require("jsdom");
const url=process.env.SEDRAVA_A22_URL,token=process.env.SEDRAVA_A22_WRITER;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function main(){
 const html=await (await fetch(url+"/")).text(),script=await (await fetch(url+"/ui-script")).text();
 const dom=new JSDOM(html,{url,runScripts:"outside-only"}),w=dom.window,$=id=>w.document.getElementById(id);
 w.crypto.randomUUID=randomUUID;let confirmOK=true,lose=false;const keys=[];
 w.confirm=()=>confirmOK;
 w.fetch=async(path,options)=>{
   const res=await fetch(url+path,options);
   if(path==="/delete-product"){keys.push(options.headers["Idempotency-Key"]);if(lose){lose=false;await res.text();throw Error("lost committed response");}}
   return res;
 };
 w.eval(script);
 const idle=async()=>{for(let i=0;i<200;i++){if(!$("login").querySelector("button").disabled)return;await sleep(30);}throw Error("timeout");};
 const submit=id=>$(id).dispatchEvent(new w.Event("submit",{cancelable:true,bubbles:true}));
 const row=(kind,id)=>Array.from($(kind).children).find(r=>r.cells[0].textContent===id);
 $("token").value=token;submit("login");await idle();
 assert(!$("workspace").hidden);
 row("products","p3").querySelector("button").click();
 assert(!$("edit-panel").hidden);
 $("edit-product-form").elements.namedItem("title").value="Изменённый товар";
 $("edit-product-form").elements.namedItem("price").value="77";
 submit("edit-product-form");await idle();
 assert.match($("status").textContent,/Запись сохранена/);assert.match(row("products","p3").textContent,/Изменённый товар/);
 row("products","p3").querySelector("button").click();confirmOK=false;$("delete-product").click();await idle();assert(row("products","p3"));
 confirmOK=true;lose=true;$("delete-product").click();await idle();
 assert.match($("status").textContent,/неизвестен/);assert(!$("retry").hidden);
 $("refresh").click();await idle();assert(!row("products","p3"));
 $("retry").click();await idle();assert.equal(keys.length,2);assert.equal(keys[0],keys[1]);assert.match($("status").textContent,/Повтор подтверждён/);assert($("retry").hidden);
 assert.equal(row("orders","o1").querySelectorAll("button").length,0);
 const remove=Array.from(row("orders","o3").querySelectorAll("button")).find(b=>b.textContent==="Удалить");
 assert(remove);remove.click();await idle();assert(!row("orders","o3"));assert.equal($("paid-count").textContent,"1");
 $("logout").click();assert($("edit-panel").hidden);assert($("retry").hidden);
 w.close();console.log("PASS A23c DOM: edit, confirm/cancel, paid-order guard, lost delete response replay after refresh, logout");
}
main().catch(e=>{console.error(e);process.exitCode=1;});
