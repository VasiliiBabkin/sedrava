"use strict";
const assert=require("node:assert/strict");
const {chromium}=require("playwright");
const url=process.env.A40_URL;
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
 const page=await browser.newPage();
 const errors=[], paths=[];
 page.on("pageerror",e=>errors.push(e.message));
 page.on("request",r=>{if(r.url().startsWith(url+"/"))paths.push(new URL(r.url()).pathname);});
 const q=s=>page.locator(s), remote=n=>q('[data-remote="'+n+'"]');
 const count=n=>paths.filter(x=>x===n).length;
 const reads=()=>paths.filter(x=>/\/domain-.*-list$/.test(x));
 const quiet=()=>page.waitForTimeout(160);
 async function ready(n,s="success"){await page.waitForFunction(([n,s])=>document.querySelector('[data-remote="'+n+'"]').dataset.status===s,[n,s]);}
 async function login(role){await q("[data-session-key]").fill(process.env["A40_"+role.toUpperCase()]);await q("[data-session-login]").click();await page.waitForFunction(r=>document.querySelector("[data-session-status]").textContent.includes("Подключено: "+r),role);}
 async function logout(){await q("[data-session-logout]").click();await page.waitForFunction(()=>document.querySelector("[data-session-status]").textContent==="Не подключено");}
 async function go(n){await q('[data-action="go_'+n+'"]').click();}
 async function input(n,v){await q('[data-input="'+n+'"]').fill(v);}
 await page.goto(url);await q("[data-session-login]").waitFor();await quiet();
 assert.equal(reads().length,0);
 // Login loads exactly the visible directory once. No hidden prefetch.
 await login("writer");await ready("list_client");assert.deepEqual(reads(),["/domain-client-list"]);
 await quiet();assert.equal(reads().length,1);
 // Create from a previously untouched list: receipt triggers the automatic refresh.
 await input("id_client","c01");await input("v_client_name","Учебный клиент");
 await q('[data-request="create_client"]').click();await ready("create_client");
 await page.waitForFunction(()=>document.querySelector('[data-remote="list_client"]').textContent.includes("Учебный клиент"));
 assert.equal(count("/domain-client-list"),2);
 // Change a cursor; do not turn typing into a stream of automatic requests.
 await input("after_client","c01");await quiet();
 assert.equal(count("/domain-client-list"),2);
 assert.equal(await remote("list_client").locator("article").count(),0);
 await q('[data-request="list_client"]').click();await ready("list_client");assert.equal(count("/domain-client-list"),3);
 // First visit to another directory loads once; switching back does not poll.
 await go("site");await ready("list_site");assert.equal(count("/domain-site-list"),1);
 await go("client");await go("site");await quiet();assert.equal(count("/domain-site-list"),1);
 // Abort an initial read. It must not be retried automatically on error.
 await page.route("**/domain-asset-list",route=>route.abort("failed"));
 await go("asset");await ready("list_asset","error");await quiet();assert.equal(count("/domain-asset-list"),1);
 await go("site");await go("asset");await quiet();assert.equal(count("/domain-asset-list"),1);
 await page.unroute("**/domain-asset-list");
 await q('[data-request="list_asset"]').click();await ready("list_asset");assert.equal(count("/domain-asset-list"),2);
 // Reports and history need a selected subject/filter and stay manual.
 await go("ticket");await ready("list_ticket");assert.equal(count("/domain-ticket-list"),1);
 assert.equal(paths.filter(x=>x.startsWith("/view-")||x==="/workflow-history").length,0);
 await logout();const before=reads().length;
 await go("ticket");await quiet();assert.equal(reads().length,before);
 // New principal starts with fresh authorized reads and no stale drafts.
 await login("reader");await ready("list_ticket");assert.equal(reads().length,before+1);
 await logout();assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
 assert.equal(paths.filter(x=>x.includes("-create")).length,1);
 assert.deepEqual(errors,[]);
 console.log("PASS A40 Chromium: first-visible read, no unauthenticated/hidden fetch, targeted refresh, no typing/polling, explicit retry, fresh principal; requests",paths.length);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
