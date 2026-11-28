"use strict";
const assert=require("node:assert/strict");
const {chromium}=require("playwright");
const url=process.env.A38_URL;
async function main(){
 const browser=await chromium.launch({headless:true});
 try{
 const context=await browser.newContext({viewport:{width:1366,height:900}});
 const page=await context.newPage();
 const errors=[], paths=[];
 page.on("pageerror",e=>errors.push(e.message));
 page.on("request",r=>{if(r.url().startsWith(url+"/"))paths.push(new URL(r.url()).pathname);});
 await page.goto(url);
 await page.waitForSelector("[data-session-login]");
 const q=s=>page.locator(s),remote=n=>q('[data-remote="'+n+'"]');
 const status=q("[data-session-status]");
 async function login(role){await q("[data-session-key]").fill(process.env["A38_"+role.toUpperCase()]);await q("[data-session-login]").click();await page.waitForFunction(r=>document.querySelector("[data-session-status]").textContent.includes("Подключено: "+r),role);}
 async function logout(){await q("[data-session-logout]").click();await page.waitForFunction(()=>document.querySelector("[data-session-status]").textContent==="Не подключено");}
 async function go(n){await q('[data-action="go_'+n+'"]').click();assert.ok(await q('[data-when="show_'+n+'"]').isVisible());}
 async function input(n,v){await q('[data-input="'+n+'"]').fill(String(v));}
 async function val(n){return q('[data-input="'+n+'"]').inputValue();}
 async function ready(n,expected="success"){await page.waitForFunction(([n,s])=>document.querySelector('[data-remote="'+n+'"]').dataset.status===s,[n,expected]);}
 async function load(n,expected="success"){await q('[data-request="'+n+'"]').click();await ready(n,expected);}
 async function pick(n,bindings){await remote(n).locator('[data-remote-pick="'+bindings+'"]').first().click();}
 async function totals(expected){await page.waitForFunction(e=>{const r=document.querySelector('[data-remote="vread_totals"]');return r.dataset.status==="success" && JSON.stringify([...r.querySelectorAll("[data-remote-results] article [data-row-field]")].map(x=>x.textContent))===JSON.stringify(e)},expected);}
 if(process.env.A38_SINGLE==="1"){
  assert.equal(await q("[data-remote-pick]").count(),0);
  await login("writer");await input("id_item","private");await input("v_item_name","private draft");
  await logout();assert.equal(await val("id_item"),"");assert.equal(await val("v_item_name"),"");
  await login("reader");assert.equal(await val("v_item_name"),"");await logout();
  console.log("PASS A38 single-entity Chromium logout clears draft, requests",paths.length);
  await context.close();return;
 }
 await login("reader");await go("client");await load("list_client");
 await input("id_client","browser-denied");await input("v_client_name","Denied");await load("create_client","error");
 assert.match(await remote("create_client").textContent(),/403/);
 await logout();assert.equal(await val("v_client_name"),"");
 await login("writer");await go("asset");await load("list_asset");await pick("list_asset","id:v_ticket_asset");
 await input("id_ticket","zz-browser");await input("v_ticket_issue","<img src=x onerror=alert(1)>");await input("ev_day","2026-11-28");await load("create_ticket");
 await input("vf_tickets","open");await input("va_tickets","z-ui-ticket");await load("vread_tickets");
 assert.match(await remote("vread_tickets").textContent(),/<img src=x/);assert.equal(await remote("vread_tickets").locator("img").count(),0);
 await pick("vread_tickets","id:wf_selected w_revision:wf_expected");assert.equal(await val("wf_expected"),"zz-browser");
 await load("wf_history");await load("vread_totals");await totals(["zz-browser","1","0","0"]);
 await input("wf_event","zz-work");await input("wf_note","Browser work");await input("ev_minutes",45);await input("ev_cost",1500);
 await load("wf_work");await totals(["zz-browser","2","45","1500"]);await ready("vread_tickets");await pick("vread_tickets","id:wf_selected w_revision:wf_expected");
 await input("wf_event","zz-close");await input("wf_note","Closed");await load("wf_close");await totals(["zz-browser","3","45","1500"]);
 await input("vf_tickets","closed");await load("vread_tickets");await pick("vread_tickets","id:wf_selected w_revision:wf_expected");
 await input("wf_event","zz-reopen");await input("wf_note","Reopen");await load("wf_reopen");await totals(["zz-browser","4","45","1500"]);
 await ready("wf_history");assert.match(await remote("wf_history").textContent(),/reopen/);
 const metrics=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
 assert.ok(metrics.scroll<=metrics.width+1,JSON.stringify(metrics));
 await page.setViewportSize({width:390,height:844});await page.waitForTimeout(100);
 const mobile=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
 assert.ok(mobile.scroll<=mobile.width+1,JSON.stringify(mobile));
 if(process.env.A38_SCREENSHOT_DIR){await page.screenshot({path:process.env.A38_SCREENSHOT_DIR+"/mobile.png",fullPage:true});await page.setViewportSize({width:1366,height:900});await page.screenshot({path:process.env.A38_SCREENSHOT_DIR+"/desktop.png",fullPage:true});}
 await logout();assert.equal(await val("wf_selected"),"");assert.equal(await page.evaluate(()=>localStorage.length+sessionStorage.length),0);
 assert.deepEqual(errors,[]);
 console.log("PASS A38 real Chromium",browser.version(),"requests",paths.length,"desktop",metrics,"mobile",mobile,"roles, XSS-safe text, workflow and reactive totals, logout");
 await context.close();
 }finally{await browser.close();}
}
main().catch(e=>{console.error(e);process.exitCode=1});
