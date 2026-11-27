"use strict";
const assert=require("node:assert/strict");
const {randomUUID}=require("node:crypto");
const {JSDOM}=require("jsdom");
const url=process.env.SEDRAVA_A22_URL, writer=process.env.SEDRAVA_A22_WRITER, reader=process.env.SEDRAVA_A22_READER;
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function main(){
 const html=await(await fetch(url+"/")).text(),script=await(await fetch(url+"/ui-script")).text();
 const dom=new JSDOM(html,{url,runScripts:"outside-only"}),w=dom.window,$=id=>w.document.getElementById(id);
 w.crypto.randomUUID=randomUUID;
 let lose=false,lastSession="",keys=[];
 w.fetch=async(path,options)=>{
   const auth=options.headers.Authorization;
   if(path==="/session-login") assert(auth.startsWith("Bearer "));
   else if(path!=="/session-policy"){assert(auth.startsWith("Session "));lastSession=auth;}
   if(path==="/add-product")keys.push(options.headers["Idempotency-Key"]);
   const res=await fetch(url+path,options);
   if(path==="/add-product" && lose){
     lose=false;assert.equal(res.status,200);await res.text();
     const revoke=await fetch(url+"/session-logout",{method:"POST",headers:{"Content-Type":"application/json",Authorization:auth},body:"{}"});assert.equal(revoke.status,200);
     throw Error("simulated lost committed response and revoked session");
   }
   return res;
 };
 w.eval(script);
 const idle=async()=>{for(let i=0;i<200;i++){if(!$("login").querySelector("button").disabled)return;await sleep(30);}throw Error("timeout");};
 const submit=id=>$(id).dispatchEvent(new w.Event("submit",{cancelable:true,bubbles:true}));
 const login=async key=>{$("token").value=key;submit("login");await idle();};
 await login(writer);assert(!$("workspace").hidden);assert.equal($("token").value,"");assert(lastSession.startsWith("Session "));
 for(const [k,v] of Object.entries({id:"dom1",title:"Товар",category:"food",price:"12"})) $("product-form").elements.namedItem(k).value=v;
 lose=true;submit("product-form");await idle();assert.match($("status").textContent,/неизвестен/);
 $("retry").click();await idle();assert($("workspace").hidden);assert.match($("status").textContent,/Сессия завершена/);
 await login(reader);assert($("workspace").hidden);assert.match($("status").textContent,/прежним пользователем/);
 await login(writer);assert(!$("workspace").hidden);assert.match($("status").textContent,/Повторите/);
 $("retry").click();await idle();assert.equal(keys.length,3);assert(keys.every(k=>k===keys[0]));assert.match($("status").textContent,/Повтор подтверждён/);
 const old=lastSession;$("logout").click();await idle();assert($("workspace").hidden);
 const res=await fetch(url+"/products",{method:"POST",headers:{"Content-Type":"application/json",Authorization:old},body:"{}"});assert.equal(res.status,401);
 assert.equal(w.localStorage.length,0);assert.equal(w.sessionStorage.length,0);assert.equal(w.document.cookie,"");
 w.close();console.log("PASS A23d DOM: login, temporary token only, lost write response, revoked session, same-principal reauthentication and replay, logout");
}
main().catch(e=>{console.error(e);process.exitCode=1;});
