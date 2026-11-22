'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const [,,htmlPath,storePath]=process.argv;
const html=fs.readFileSync(htmlPath,'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/);
assert(script);
function el(dataset={}){
  return {
    dataset,hidden:true,textContent:'',value:'',children:[],events:{},
    addEventListener(name,cb){this.events[name]=cb;},
    replaceChildren(){this.children=[];},
    append(v){this.children.push(v);},
    setAttribute(name,value){this[name]=value;}
  };
}
function nodes(name){
  const re=new RegExp('data-'+name+'="([^"]+)"','g');
  return [...html.matchAll(re)].map(m=>el({[name]:m[1]}));
}
const states=nodes('state'),actions=nodes('action'),inputs=nodes('input'),
      lists=nodes('list'),shows=nodes('show');
for(const list of lists){
  const match=html.match(/data-list="[^"]+" data-select="([^"]+)"/);
  list.dataset.select=match[1];
}
const errors=el();
const groups={
 '[data-state]':states,'[data-action]':actions,'[data-input]':inputs,
 '[data-show]':shows,'[data-list]':lists,'[data-display]':[]
};
const document={
 activeElement:null,
 getElementById(name){return name==='sedrava-error'?errors:null;},
 querySelectorAll(name){return groups[name]||[];},
 createElement(tag){const node=el();node.tag=tag;return node;}
};
let writes=0;
const storage={
 getItem(){return fs.existsSync(storePath)?fs.readFileSync(storePath,'utf8'):null;},
 setItem(key,value){writes++;fs.writeFileSync(storePath,value,'utf8');}
};
vm.runInNewContext(script[1],{document,localStorage:storage,location:{pathname:'/tasks'},console},{timeout:4000});
const input=name=>inputs.find(node=>node.dataset.input===name);
const click=name=>actions.find(node=>node.dataset.action===name).events.click();
const output=name=>states.find(node=>node.dataset.state===name).textContent;
const list=lists.find(node=>node.dataset.list==='tasks');
assert.equal(list.children.length,0);
assert.equal(output('selected'),'0');
assert.equal(shows[0].hidden,false);
const title=input('title');
title.value='Laundry';title.events.change();
click('add');
fs.copyFileSync(storePath,storePath+'.withrow');
assert.equal(list.children.length,1);
assert.equal(list.children[0].dataset.id,'1');
assert(list.children[0].children[0].textContent.includes('Laundry'));
assert.equal(shows[0].hidden,true);
assert.equal(output('selected'),'0');
list.children[0].children[1].onclick();
assert.equal(output('selected'),'1');
click('complete');
assert.equal(list.children.length,1);
assert(list.children[0].children[0].textContent.includes('true'));
click('delete');
assert.equal(output('selected'),'0');
assert.equal(list.children.length,0);
assert.equal(shows[0].hidden,false);
assert(writes>=4);
assert.equal(JSON.parse(fs.readFileSync(storePath,'utf8')).state.tasks.items.length,0);
console.log('PASS: native Web record/list lifecycle, selection, persistence and derived fields');
