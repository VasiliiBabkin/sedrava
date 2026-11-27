"use strict";
// DOM integration against actual native server, not Chromium.
const assert=require("node:assert/strict");
const {randomUUID}=require("node:crypto");
const {JSDOM}=require("jsdom");
const url=process.env.SEDRAVA_A22_URL, token=process.env.SEDRAVA_A22_WRITER;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function main(){
 const html=await (await fetch(url+"/")).text(),script=await (await fetch(url+"/ui-script")).text();
 const dom=new JSDOM(html,{url,runScripts:"outside-only"}),w=dom.window,d=w.document,$=id=>d.getElementById(id);
 w.crypto.randomUUID=randomUUID;w.fetch=(path,options)=>fetch(url+path,options);w.eval(script);
 const idle=async()=>{for(let i=0;i<200;i++){if(!$("login").querySelector("button").disabled)return;await sleep(30);}throw Error("timeout");};
 const submit=id=>$(id).dispatchEvent(new w.Event("submit",{cancelable:true,bubbles:true}));
 const ids=kind=>Array.from($(kind).children,r=>r.cells[0].textContent);
 const expected=(prefix,start,end)=>Array.from({length:end-start+1},(_,i)=>prefix+String(start+i).padStart(3,"0"));
 $("token").value=token;submit("login");await idle();assert(!$("workspace").hidden);assert.equal($("product-count").textContent,"105");
 assert.deepEqual(ids("products"),expected("p",0,24));assert.deepEqual(ids("orders"),expected("o",0,24));
 assert($("products-prev").disabled);assert(!$("products-next").disabled);
 for(let page=2;page<=5;page++){
   $("products-next").click();await idle();assert.equal($("products-page").textContent,"Страница "+page);
   assert.deepEqual(ids("products"),expected("p",(page-1)*25,Math.min(page*25-1,104)));
   assert.deepEqual(ids("orders"),expected("o",0,24));
 }
 assert($("products-next").disabled);assert(!$("products-prev").disabled);
 $("orders-next").click();await idle();assert.deepEqual(ids("orders"),expected("o",25,49));assert.deepEqual(ids("products"),expected("p",100,104));
 $("products-prev").click();await idle();assert.deepEqual(ids("products"),expected("p",75,99));
 // A product not on the displayed page can still be referenced.
 const form=$("order-form");for(const [k,v] of Object.entries({id:"o105",product_id:"p000",amount:"7"}))form.elements.namedItem(k).value=v;
 submit("order-form");await idle();assert.match($("status").textContent,/Запись сохранена/);
 $("orders-prev").click();await idle();assert.deepEqual(ids("orders"),expected("o",0,24));
 $("logout").click();assert($("workspace").hidden);assert.equal($("products-page").textContent,"Страница 1");assert.equal($("orders-page").textContent,"Страница 1");assert.equal($("products").children.length,0);assert.equal($("product-select").children.length,0);
 w.close();console.log("PASS A23b DOM: 5 pages, independent cursors, backward navigation, last-page guard, product reference outside current page, reset/logout");
}
main().catch(e=>{console.error(e);process.exitCode=1;});
