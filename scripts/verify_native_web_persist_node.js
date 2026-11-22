'use strict';
// This is a Node.js *mock DOM* test, not browser acceptance.
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const [,,htmlPath,snapshotPath,scenario]=process.argv;
if (!htmlPath||!snapshotPath||!scenario) throw Error('Usage: node FILE.html SNAPSHOT.json write|read|reject|conflict');
const html=fs.readFileSync(htmlPath,'utf8');
const match=html.match(/<script>([\s\S]*?)<\/script>/);
if(!match) throw Error('Missing embedded JS');
function el(dataset={}) {
 return {dataset,textContent:'',hidden:false,value:'',events:{},addEventListener(event,cb){this.events[event]=cb;}};
}
const nodes=attr=>[...html.matchAll(new RegExp(attr+'="([^"]+)"','g'))].map(m=>el({[attr.replace('data-','')]:m[1]}));
const groups={
 '[data-action]':nodes('data-action'),
 '[data-state]':nodes('data-state'),
 '[data-input]':nodes('data-input'),
 '[data-show]':nodes('data-show'),
 '[data-display]':[]
};
const error=el();
error.hidden=true;
let overwrites=0;
const storage={
 getItem() {return fs.existsSync(snapshotPath)?fs.readFileSync(snapshotPath,'utf8'):null;},
 setItem(key,raw){overwrites++;fs.writeFileSync(snapshotPath,raw,'utf8');}
};
const document={
 activeElement:null,
 getElementById(k){return k==='sedrava-error'?error:null;},
 querySelectorAll(q){return groups[q]||[];}
};
const location={pathname:'/my-sedrava-test'};
vm.runInNewContext(match[1],{document,localStorage:storage,location,console},{timeout:5000});
const output=k=>{
 const node=groups['[data-state]'].find(el=>el.dataset.state===k);
 if(!node) throw Error('Missing output '+k);
 return node.textContent;
};
const click=label=>{
 const btn=groups['[data-action]'].find(el=>el.dataset.action===label);
 if(!btn||!btn.events.click)throw Error('Missing action '+label);
 btn.events.click();
};
if(scenario==='write'){
 assert.equal(output('progress'),'0');
 click('add');
 assert.equal(output('progress'),'1');
 if(error.hidden!==true)console.log("RESTORE ERROR:",error.textContent);
 assert.equal(error.hidden,true);
 assert.equal(overwrites,1);
 const payload=JSON.parse(fs.readFileSync(snapshotPath,'utf8'));
 assert.equal(payload.schema,1);
 assert.equal(payload.state.progress,1);
 assert.equal(payload.state.goal,5);
 assert.equal(payload.state.sessions,1);
 assert.equal(Object.keys(payload.state).length,3);
} else if(scenario==='read'){
 const snapshot=JSON.parse(fs.readFileSync(snapshotPath,'utf8'));
 if(output('progress')!==String(snapshot.state.progress))console.log('RESTORE DEBUG:',error.textContent);
 assert.equal(output('progress'),String(snapshot.state.progress));
 assert.equal(output('sessions'),String(snapshot.state.sessions));
 if(error.hidden!==true)console.log("RESTORE ERROR:",error.textContent);
 assert.equal(error.hidden,true);
 assert.equal(overwrites,0);
} else if(scenario==='reject'){
 const original=fs.readFileSync(snapshotPath,'utf8');
 assert.equal(error.hidden,false);
 click('add');
 assert.equal(fs.readFileSync(snapshotPath,'utf8'),original);
 assert.equal(overwrites,0);
 assert.equal(error.hidden,false);
} else if(scenario==='conflict'){
 const orig=fs.readFileSync(snapshotPath,'utf8');
 const changed=JSON.stringify({...JSON.parse(orig), external_edit:true});
 fs.writeFileSync(snapshotPath,changed,'utf8');
 click('add');
 assert.equal(output('progress'),String(JSON.parse(orig).state.progress));
 assert.equal(fs.readFileSync(snapshotPath,'utf8'),changed);
 assert.equal(overwrites,0);
 assert.equal(error.hidden,false);
} else throw Error('Unknown scenario '+scenario);
console.log('PASS: native browser snapshot scenario',scenario);
