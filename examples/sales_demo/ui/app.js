"use strict";
(() => {
  const $ = id => document.getElementById(id);
  let token = "", busy = false, pending = null;
  const PAGE_SIZE = 25;
  const initialPage = () => ({after:"",history:[],next:null});
  let pages = {products:initialPage(),orders:initialPage()};
  function syncButtons(){
    document.querySelectorAll("button").forEach(b=>b.disabled=busy);
    for (const kind of ["products","orders"]){
      $(kind+"-prev").disabled=busy || !!pending || pages[kind].history.length===0;
      $(kind+"-next").disabled=busy || !!pending || pages[kind].next===null;
    }
  }
  function resetPages(){
    pages={products:initialPage(),orders:initialPage()};
    for(const kind of ["products","orders"]) $(kind+"-page").textContent="Страница 1";
    syncButtons();
  }
  const status = message => { $("status").textContent = message; };
  const clear = () => {
    token = ""; pending = null; $("token").value = ""; resetPages();
    $("workspace").hidden = true;
    for (const id of ["products","orders","product-select"]) $(id).replaceChildren();
    for (const id of ["paid-count","revenue","product-count"]) $(id).textContent = "—";
    for (const id of ["product-form","order-form","correct-form","atomic-form"]) $(id).reset();
  };
  async function api(path, body = {}, key = null) {
    const headers = {"Content-Type":"application/json","Authorization":"Bearer "+token};
    if (key) headers["Idempotency-Key"] = key;
    const response = await fetch(path,{method:"POST",headers,body:JSON.stringify(body),cache:"no-store",redirect:"error",credentials:"omit"});
    const data = await response.json();
    if (!response.ok) {
      const error = new Error(data.error?.code || "HTTP "+response.status);
      error.httpStatus = response.status;
      throw error;
    }
    return data;
  }
  function cell(row, value) {
    const td = document.createElement("td");
    td.textContent = String(value ?? "—"); row.append(td); return td;
  }
  async function refresh(target=pages) {
    const products = await api("/products-page",{after:target.products.after});
    const orders = await api("/orders-page",{after:target.orders.after});
    const paid = await api("/paid-summary"), count = await api("/product-count");
    const productRows=products.rows.slice(0,PAGE_SIZE), orderRows=orders.rows.slice(0,PAGE_SIZE);
    const page=(state,rows,all)=>({...state,next:all.length>PAGE_SIZE?rows.at(-1)[0]:null});
    const updated={products:page(target.products,productRows,products.rows),orders:page(target.orders,orderRows,orders.rows)};
    $("products").replaceChildren(); $("orders").replaceChildren(); $("product-select").replaceChildren();
    for (const values of productRows) {
      const row = document.createElement("tr"); values.forEach(v => cell(row,v)); $("products").append(row);
      const option = document.createElement("option"); option.value = values[0]; option.textContent = values[1]+" ("+values[0]+")"; $("product-select").append(option);
    }
    for (const values of orderRows) {
      const row = document.createElement("tr"); values.slice(0,3).forEach(v=>cell(row,v)); cell(row,values[3]?"Оплачен":"Не оплачен");
      const actions = cell(row,"");
      if (!values[3]) {
        const button=document.createElement("button"); button.type="button"; button.textContent="Отметить оплату";
        button.addEventListener("click",()=>task(()=>write("/mark-paid",{id:values[0]})));
        actions.append(button);
      }
      $("orders").append(row);
    }
    $("paid-count").textContent = String(paid.rows[0][0]); $("revenue").textContent = String(paid.rows[0][1] ?? 0); $("product-count").textContent = String(count.rows[0][0]);
    pages=updated;
    for(const kind of ["products","orders"]) $(kind+"-page").textContent="Страница "+(pages[kind].history.length+1);
  }
  function navigate(kind,direction){
    if(pending) return;
    const p=pages[kind];
    const next=direction===1 && p.next!==null?{after:p.next,history:[...p.history,p.after],next:null}:
      direction===-1 && p.history.length?{after:p.history.at(-1),history:p.history.slice(0,-1),next:null}:null;
    if(next) task(()=>refresh({...pages,[kind]:next}));
  }
  async function task(fn) {
    if (busy) return;
    busy=true; syncButtons();
    try { await fn(); }
    catch(e) { status("Ошибка: "+e.message); }
    finally { busy=false; syncButtons(); }
  }
  async function write(path, body, form) {
    const signature=JSON.stringify([path,body]);
    if (pending && pending.signature!==signature) throw new Error("Сначала повторите предыдущую запись с прежними полями.");
    pending ??= {signature,key:crypto.randomUUID()};
    let result;
    try { result=await api(path,body,pending.key); }
    catch(e) {
      if ([400,401,403,404,405,409,415,422,428,507].includes(e.httpStatus)) pending=null;
      else throw new Error("Результат записи неизвестен. Повторите те же поля. "+e.message);
      throw e;
    }
    pending=null;
    if (form) form.reset();
    status(result.replayed?"Повтор подтверждён.":"Запись сохранена.");
    try { await refresh(); } catch(e) { status("Запись сохранена, но обновление не удалось: "+e.message); }
  }
  $("login").addEventListener("submit",e=>{
    e.preventDefault();task(async()=>{
      clearWorkspaceOnly();
      token=$("token").value; $("token").value="";
      try { await refresh(); $("workspace").hidden=false; status("Подключено."); }
      catch(e) { clear(); throw e; }
    });
  });
  function clearWorkspaceOnly(){
    if (pending) throw new Error("Повторите незавершённую запись или отключитесь.");
    $("workspace").hidden=true; token=""; resetPages();
  }
  $("logout").addEventListener("click",()=>{clear();status("Отключено.");});
  $("refresh").addEventListener("click",()=>task(async()=>{await refresh();status("Данные обновлены.");}));
  for(const kind of ["products","orders"]){
    $(kind+"-prev").addEventListener("click",()=>navigate(kind,-1));
    $(kind+"-next").addEventListener("click",()=>navigate(kind,1));
  }
  resetPages();
  for(const [id,path] of [["product-form","/add-product"],["order-form","/add-order"],["correct-form","/correct-order"],["atomic-form","/new-product-order"]]){
    const form=$(id);
    form.addEventListener("submit",e=>{
      e.preventDefault();
      const body={};
      for(const [name,value] of new FormData(form)){
        const input=form.elements.namedItem(name);
        body[name]=input.type==="number"?Number(value):value;
      }
      task(()=>write(path,body,form));
    });
  }
})();
