type Ticket = {id:number; title:string; site:string; done:boolean};
type State = {nextId:number; tickets:Ticket[]};
const storageKey = "service-journal-ts-v1";
function textValid(v:unknown):v is string {
    return typeof v==="string" && v.length>0 && v.length<=1024;
}
function load():State {
    const raw=localStorage.getItem(storageKey);
    if(raw===null)return {nextId:1,tickets:[]};
    try{
        const s=JSON.parse(raw) as State;
        if(!Number.isSafeInteger(s.nextId)||s.nextId<1||!Array.isArray(s.tickets)||s.tickets.length>100)throw Error();
        const ids=new Set<number>();
        for(const t of s.tickets){
            if(!Number.isSafeInteger(t.id)||t.id<1||t.id>=s.nextId||ids.has(t.id)||!textValid(t.title)||!textValid(t.site)||typeof t.done!=="boolean")throw Error();
            ids.add(t.id);
        }
        return s;
    }catch{ return {nextId:1,tickets:[]}; }
}
function el<T extends HTMLElement>(q:string):T {
    const found=document.querySelector<T>(q); if(!found)throw Error(q);return found;
}
const input=(name:string)=>el<HTMLInputElement>('[data-input="'+name+'"]');
const button=(name:string)=>el<HTMLButtonElement>('[data-action="'+name+'"]');
const body=el<HTMLTableSectionElement>("tbody");
let state=load();
let selected=0;
function report(message:string){el("#error").textContent=message;}
function render(){
    const done=state.tickets.filter(t=>t.done).length;
    for(const [name,n] of [["ticket_count",state.tickets.length],["done_count",done],["open_count",state.tickets.length-done]] as const)
        el('output[data-state="'+name+'"]').textContent=String(n);
    const query=input("search_text").value.toLowerCase();
    const visible=state.tickets.filter(t=>[t.title,t.site,String(t.done)].some(x=>x.toLowerCase().includes(query))).sort((a,b)=>a.title<b.title?-1:a.title>b.title?1:a.id-b.id);
    body.replaceChildren();
    for(const t of visible){
        const row=body.insertRow();
        row.setAttribute("aria-selected",String(t.id===selected));
        const pick=document.createElement("button");
        pick.textContent=t.title;
        pick.onclick=()=>{selected=t.id;render();};
        row.insertCell().append(pick);
        row.insertCell().textContent=t.site;
        row.insertCell().textContent=String(t.done);
    }
    el("#chosen").hidden=!state.tickets.some(t=>t.id===selected);
}
function change(fn:(s:State)=>void):boolean {
    const draft:State={nextId:state.nextId,tickets:state.tickets.map(t=>({...t}))};
    try{fn(draft);localStorage.setItem(storageKey,JSON.stringify(draft));state=draft;report("");render();return true;}
    catch(e){report(e instanceof Error?e.message:"Ошибка");return false;}
}
function chosen(s:State):Ticket {
    const t=s.tickets.find(t=>t.id===selected);if(!t)throw Error("Выберите заявку");return t;
}
button("add").onclick=()=>{
    if(change(s=>{
        const title=input("title").value,site=input("site_name").value;
        if(!textValid(title)||!textValid(site)||s.tickets.length>=100||s.nextId>=2147483647)throw Error("Некорректная заявка");
        s.tickets.push({id:s.nextId++,title,site,done:false});
    })){input("title").value="";input("site_name").value="";}
};
button("rename").onclick=()=>{
    if(change(s=>{const title=input("new_title").value;if(!textValid(title))throw Error("Некорректное описание");chosen(s).title=title;}))input("new_title").value="";
};
button("toggle").onclick=()=>change(s=>{const t=chosen(s);t.done=!t.done;});
button("delete").onclick=()=>{if(change(s=>{chosen(s);s.tickets=s.tickets.filter(t=>t.id!==selected);})) {selected=0;render();}};
input("search_text").oninput=render;
render();
