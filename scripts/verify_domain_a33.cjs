"use strict";
const assert=require("node:assert/strict");
const {randomUUID}=require("node:crypto");
const {JSDOM}=require("jsdom");
const url=process.env.A33_URL;
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
 async function login(role){q("[data-session-key]").value=process.env["A33_"+role.toUpperCase()];q("[data-session-login]").click();await wait(()=>status().includes("Подключено: "+role));}
 async function logout(){q("[data-session-logout]").click();await wait(()=>status()==="Не подключено");}
 function pick(n){const b=remote(n).querySelector("[data-remote-pick]");assert.ok(b&&!b.disabled);b.click();}
 await login("reader");go("client");await load("list_client");
 input("id_client","z-ui");input("v_client_name","<b>UI</b>");await load("create_client","error");assert.match(remote("create_client").textContent,/403/);
 await logout();assert.equal(val("v_client_name"),"");
 await login("writer");go("client");input("id_client","z-ui");input("v_client_name","<b>UI</b>");await load("create_client");
 input("after_client","c22");await load("list_client");assert.match(remote("list_client").textContent,/<b>UI<\/b>/);assert.equal(remote("list_client").querySelector("article b"),null);
 pick("list_client");assert.equal(val("v_site_client"),"z-ui");
 input("id_site","z-site");input("v_site_name","Office");input("v_site_address","Test");await load("create_site");
 input("after_site","s01");await load("list_site");pick("list_site");assert.equal(val("v_asset_site"),"z-site");
 input("id_asset","z-asset");input("v_asset_name","Camera");input("v_asset_serial","S1");await load("create_asset");await load("list_asset");
 assert.match(remote("list_asset").textContent,/Camera/);
 await logout();assert.equal(val("v_asset_site"),"");assert.equal(w.localStorage.length,0);
 w.close();console.log("PASS A33 generated DOM",calls,"real requests; generated forms, relations, role rejection, XSS-safe data and logout");
}
main().catch(e=>{console.error(e);process.exitCode=1;});
