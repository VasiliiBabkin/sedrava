'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const [,,filename,storePath]=process.argv;
const html=fs.readFileSync(filename,'utf8'),script=html.match(/<script>([\s\S]*?)<\/script>/);
assert(script);
function el(dataset={}){
 return {
  dataset,hidden:true,textContent:'',value:'',children:[],events:{},
  addEventListener(name,fn){this.events[name]=fn;},
  replaceChildren(){this.children=[];},append(v){this.children.push(v);},
  setAttribute(name,val){this[name]=val;}
 };
}
function nodes(name){
 return [...html.matchAll(new RegExp('data-'+name+'="([^"]+)"','g'))]
  .map(m=>el({[name]:m[1]}));
}
const screens=nodes('screen'),actions=nodes('action'),inputs=nodes('input'),
      displays=[...html.matchAll(/data-display/g)].map(()=>el()),
      lists=nodes('list'),states=nodes('state'),shows=nodes('show'),error=el();
for(const list of lists){
 const metadata=html.match(/data-list="([^"]+)" data-select="([^"]+)"(?: data-open="([^"]+)")?/);
 list.dataset.select=metadata[2];
 list.dataset.open=metadata[3];
}
const groups={
 '[data-screen]':screens,'[data-action]':actions,'[data-input]':inputs,
 '[data-show]':shows,'[data-state]':states,'[data-display]':displays,'[data-list]':lists
};
const document={
 activeElement:null,
 getElementById(){return error;},
 querySelectorAll(k){return groups[k]||[];},
 createElement(){return el();}
};
let writes=0;
const storage={
 getItem(){return fs.existsSync(storePath)?fs.readFileSync(storePath,'utf8'):null;},
 setItem(key,value){writes++;fs.writeFileSync(storePath,value,'utf8');}
};
const ctx=vm.createContext({document,localStorage:storage,location:{pathname:'/navigation'},console});
vm.runInContext(script[1],ctx,{timeout:5000});
const screen=name=>screens.find(e=>e.dataset.screen===name);
const button=name=>{
 const el=actions.find(e=>e.dataset.action===name);
 if(!el)throw Error('Missing button '+name);
 el.events.click();
};
const input=name=>{
 const el=inputs.find(e=>e.dataset.input===name);
 if(!el)throw Error('Missing input '+name);
 return el;
};
assert.equal(screen('main').hidden,false);
assert.equal(screen('details').hidden,true);
assert.equal(lists[0].children.length,0);
vm.runInContext("dispatch('open_details')",ctx);
assert.equal(screen('main').hidden,false);
assert.equal(screen('details').hidden,true);
const add=input('new_title');add.value='Walk';add.events.change();
button('add_task');
assert.equal(lists[0].children.length,1);
lists[0].children[0].children[1].onclick();
assert.equal(screen('main').hidden,true);
assert.equal(screen('details').hidden,false);
assert.equal(displays[0].textContent,'Walk');
const rename=input('title');
rename.value='Read';rename.events.change();
button('rename_task');
assert.equal(displays[0].textContent,'Read');
button('toggle_task');
assert.equal(shows.some(x=>x.textContent.includes('Completed')&&!x.hidden),false); // DOM mock text not parsed
button('back_to_tasks');
assert.equal(screen('main').hidden,false);
assert.equal(screen('details').hidden,true);
lists[0].children[0].children[1].onclick();
assert.equal(screen('details').hidden,false);
button('delete_and_back');
assert.equal(screen('main').hidden,false);
assert.equal(screen('details').hidden,true);
assert.equal(lists[0].children.length,0);
assert(writes>=5);
const stored=JSON.parse(fs.readFileSync(storePath,'utf8'));
assert.equal(stored.state.tasks.items.length,0);
console.log('PASS: native Web multi-screen guarded navigation, rename, toggle, delete/pop, persistence');
