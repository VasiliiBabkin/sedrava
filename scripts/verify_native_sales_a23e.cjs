"use strict";
// Generated app.js is executed unchanged. Real loopback HTTP, synthetic credentials.
const assert=require("node:assert/strict");
const {randomUUID}=require("node:crypto");
const {JSDOM}=require("jsdom");
const url=process.env.SEDRAVA_A22_URL,writer=process.env.SEDRAVA_A22_WRITER,reader=process.env.SEDRAVA_A22_READER;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function main(){
 const html=await(await fetch(url+"/")).text(),script=await(await fetch(url+"/app.js")).text();
 const dom=new JSDOM(html,{url,runScripts:"outside-only"}),w=dom.window,d=w.document;
 Object.assign(w,{TextEncoder,TextDecoder,AbortController,AbortSignal});
 w.crypto.randomUUID=randomUUID;
 let lose=false,malformed=false,lastSession="",requests=0,keys=[];
 w.fetch=async(target,options)=>{
   const path=new URL(target,url).pathname;assert.equal(new URL(target,url).origin,url);
   requests++;
   const auth=options.headers.Authorization;
   if(path==="/session-login")assert(auth.startsWith("Bearer "));
   else {assert(auth.startsWith("Session "));lastSession=auth;}
   if(path==="/add-product")keys.push(options.headers["Idempotency-Key"]);
   const res=await fetch(target,options);
   if(path==="/products-page" && malformed){
      malformed=false;await res.text();
      return new Response(JSON.stringify({kind:"rows",columns:["title","id","category","price"],rows:[["bad","p","x",0]]}),{headers:{"Content-Type":"application/json"}});
   }
   if(path==="/add-product" && lose){
      lose=false;assert.equal(res.status,200);await res.text();
      const logout=await fetch(url+"/session-logout",{method:"POST",headers:{"Content-Type":"application/json",Authorization:auth},body:"{}"});assert.equal(logout.status,200);
      throw Error("lost committed response");
   }
   return res;
 };
 w.eval(script);
 const q=s=>d.querySelector(s), status=()=>q("[data-session-status]").textContent;
 const remote=n=>q('[data-remote="'+n+'"]');
 const result=n=>remote(n).querySelector("[data-remote-results]").textContent;
 const click=n=>q('[data-request="'+n+'"]').click();
 const wait=async(fn)=>{for(let i=0;i<250;i++){if(fn())return;await sleep(30);}throw Error("UI timeout");};
 const login=async(key,re)=>{q("[data-session-key]").value=key;q("[data-session-login]").click();await wait(()=>re.test(status()));assert.equal(q("[data-session-key]").value,"");};
 const input=(n,v)=>{const el=q('[data-input="'+n+'"]');el.value=String(v);el.dispatchEvent(new w.Event("input",{bubbles:true}));};
 click("products");await wait(()=>remote("products").dataset.status==="error");assert.equal(requests,0);
 await login(reader,/Подключено: reader/);
 click("products");await wait(()=>remote("products").dataset.status==="success");
 assert.match(result("products"),/Начальный/);
 input("product_id","p2");input("title","<img src=x onerror=alert(1)>");input("category","food");input("price",12);
 click("add_product");await wait(()=>remote("add_product").dataset.status==="error");assert.match(remote("add_product").textContent,/403/);
 q("[data-session-logout]").click();await wait(()=>status()==="Не подключено");assert.equal(result("products"),"");
 await login(writer,/Подключено: writer/);
 lose=true;click("add_product");await wait(()=>remote("add_product").dataset.status==="error");
 click("add_product");await wait(()=>/Сессия завершена/.test(status()));
 await login(reader,/прежним пользователем/);
 await login(writer,/Подключено: writer/);
 input("price",13);click("add_product");await wait(()=>/прежние параметры/.test(remote("add_product").textContent));
 input("price",12);click("add_product");await wait(()=>remote("add_product").dataset.status==="success");
 assert.equal(keys.length,4);assert.equal(keys[1],keys[2]);assert.equal(keys[2],keys[3]);assert.notEqual(keys[0],keys[1]);assert.match(result("add_product"),/true/);
 click("products");await wait(()=>remote("products").dataset.status==="success");
 assert.match(result("products"),/<img src=x/);assert.equal(remote("products").querySelector("img"),null);
 malformed=true;click("products");await wait(()=>remote("products").dataset.status==="error");assert.match(remote("products").textContent,/Invalid SQL response envelope/);
 const old=lastSession;q("[data-session-logout]").click();await wait(()=>status()==="Не подключено");
 assert.equal(result("products"),"");assert.equal(result("add_product"),"");
 const res=await fetch(url+"/products",{method:"POST",headers:{"Content-Type":"application/json",Authorization:old},body:"{}"});assert.equal(res.status,401);
 // A previously revoked session must not prevent local logout or re-login.
 await login(writer,/Подключено: writer/);
 click("products");await wait(()=>remote("products").dataset.status==="success");
 const revoke=await fetch(url+"/session-logout",{method:"POST",headers:{"Content-Type":"application/json",Authorization:lastSession},body:"{}"});assert.equal(revoke.status,200);
 q("[data-session-logout]").click();await wait(()=>status()==="Не подключено");assert.equal(result("products"),"");
 await login(writer,/Подключено: writer/);
 q("[data-session-logout]").click();await wait(()=>status()==="Не подключено");
 assert.equal(w.localStorage.length,0);assert.equal(w.sessionStorage.length,0);assert.equal(d.cookie,"");
 w.close();console.log("PASS A23e generated DOM: typed SQL rows, role checks, session-only requests, XSS-safe rendering, malformed envelope, same-principal durable replay, no browser storage");
}
main().catch(e=>{console.error(e);process.exitCode=1;});
