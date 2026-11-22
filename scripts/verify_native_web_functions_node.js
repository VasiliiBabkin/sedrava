'use strict';
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[2],'utf8');
const match=html.match(/<script>([\s\S]*?)<\/script>/);
assert(match);
const create=dataset=>({
 dataset,textContent:'',hidden:true,events:{},addEventListener(name,listener){this.events[name]=listener;}
});
const get=name=>[...html.matchAll(new RegExp('data-'+name+'="([^"]+)"','g'))]
   .map(match=>create({[name]:match[1]}));
const states=get('state'),actions=get('action'),error=create({});
const groups={'[data-state]':states,'[data-action]':actions,'[data-input]':[],'[data-show]':[],'[data-display]':[]};
const document={
 activeElement:null,
 getElementById(name){return name==='sedrava-error'?error:null;},
 querySelectorAll(name){return groups[name]||[];}
};
vm.runInNewContext(match[1],{document,console},{timeout:3000});
function out(name) {
 const node=states.find(v=>v.dataset.state===name);
 if(!node)throw Error('Missing output '+name);
 return node.textContent;
}
function click(name) {
 const button=actions.find(v=>v.dataset.action===name);
 if(!button)throw Error('Missing action '+name);
 button.events.click();
}
assert.equal(out('doubled'),'2');
assert.equal(out('hello'),'Hello, A😀Z');
assert.equal(out('length'),'3');
assert.equal(out('ascii'),'a😀z');
assert.equal(out('next_day'),'2024-03-01');
assert.equal(out('can_reset'),'true');
click('add');
assert.equal(out('doubled'),'4');
click('reset');
assert.equal(out('doubled'),'0');
click('reset');
assert.equal(out('doubled'),'0');
assert.equal(error.hidden,false);
console.log('PASS: browser pure functions and scalar stdlib conformance');
