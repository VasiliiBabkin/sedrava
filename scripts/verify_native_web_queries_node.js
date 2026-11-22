'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[2],'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/);
if(!script)throw Error('Web script missing');
const element=dataset=>({
 dataset:dataset||{},children:[],events:{},textContent:'',hidden:true,value:'',
 addEventListener(e,cb){this.events[e]=cb;},replaceChildren(){this.children=[];},
 append(x){this.children.push(x);},setAttribute(a,b){this[a]=b;}
});
const nodes=name=>[...html.matchAll(new RegExp('data-'+name+'="([^"]+)"','g'))]
 .map(m=>element({[name]:m[1]}));
const states=nodes('state'),actions=nodes('action'),inputs=nodes('input'),
 lists=nodes('list'),shows=nodes('show'),error=element({});
for(const list of lists){
 const pair=html.match(/data-list="([^"]+)" data-select="([^"]+)"/);
 list.dataset.select=pair[2];
}
const group={
 '[data-state]':states,'[data-action]':actions,'[data-input]':inputs,
 '[data-list]':lists,'[data-show]':shows,'[data-display]':[]
};
let saved;
const storage={getItem(){return saved||null;},setItem(key,s){saved=s;}};
const document={
 activeElement:null,
 getElementById(){return error;},
 querySelectorAll(k){return group[k]||[];},
 createElement(){return element({});}
};
const context=vm.createContext({document,localStorage:storage,location:{pathname:'/query'},console});
vm.runInContext(script[1],context,{timeout:4000});
function click(key){
 const b=actions.find(v=>v.dataset.action===key);
 if(!b)throw Error('Unknown action '+key);
 b.events.click();
}
click('add_one');
click('add_two');
const parsed=JSON.parse(vm.runInContext('JSON.stringify(resolved(state))',context));
assert.equal(parsed.total,5);
assert.equal(parsed.done_count,1);
assert.equal(parsed.first_done,2);
assert.equal(parsed.any_done,true);
assert.equal(parsed.all_done,false);
assert.deepEqual(parsed.mapped.items.map(x=>x.score),[3,4]);
assert.deepEqual(parsed.ordered.items.map(x=>x.label),['A','B']);
assert.deepEqual(parsed.filtered.items.map(x=>x.id),[2]);
assert(saved&&JSON.parse(saved).state.items.items.length===2);
console.log('RESULT_JSON '+JSON.stringify(parsed));
