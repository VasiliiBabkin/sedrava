"""Navigation Web adapter; domain functions are emitted by the existing backend."""
from dataclasses import replace
import html
from web_codegen import generate, json_script as q, js_expr

STYLE = '''
:root{font-family:Inter,ui-sans-serif,system-ui,sans-serif;color:#203b35;background:#f4f3ee;color-scheme:light;--accent:#245d4e;--line:#dce3db}*{box-sizing:border-box}body{margin:0}.brand{overflow-wrap:anywhere}.shell>*{min-width:0}button{max-width:100%;white-space:normal;overflow-wrap:anywhere}button:disabled{opacity:.55;cursor:not-allowed}.brand-mark{flex-shrink:0}.task-status{grid-column:1}button,textarea,input{font:inherit}button{cursor:pointer;border:1px solid var(--line);border-radius:14px;padding:.8rem 1.2rem;color:var(--accent);background:white;font-weight:650;min-height:48px}button:hover{background:#e7eee7}button:focus-visible,a:focus-visible,textarea:focus-visible,input:focus-visible{outline:3px solid #bc6b24;outline-offset:4px}.brand{max-width:1100px;margin:auto;padding:2rem 1.5rem;display:flex;align-items:center;gap:.75rem;font-size:1.15rem;font-weight:750;letter-spacing:-.03em}.brand-mark{background:var(--accent);color:white;border-radius:12px;width:36px;height:36px;display:grid;place-items:center}.shell{max-width:1100px;margin:1rem auto;padding:0 1.5rem 4rem;display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.55fr);gap:4rem}.intro{padding-top:1rem}.eyebrow{font-size:.75rem;letter-spacing:.18em;text-transform:uppercase;color:#526459}h1{font-family:Georgia,serif;font-weight:500;letter-spacing:-.045em;font-size:clamp(2.7rem,5vw,4.8rem);line-height:1.06;margin:1.2rem 0;overflow-wrap:anywhere}h1:focus{outline:none}h1,.subtitle,.notice,label{white-space:pre-wrap;overflow-wrap:anywhere}.subtitle{color:#526459;line-height:1.7;max-width:28rem}.workspace{background:#fffefa;border:1px solid #e1e5dc;border-radius:26px;padding:2rem;box-shadow:0 15px 55px #254c3410}.input-group{display:grid;gap:.6rem;margin-bottom:1rem}label{font-size:.85rem;font-weight:650}textarea,input{width:100%;padding:1rem;border:1px solid #cdd7cc;background:white;border-radius:12px;color:#203b35;resize:vertical;min-height:3.2rem}textarea{height:5.5rem}textarea[aria-invalid=true],input[aria-invalid=true]{border-color:#ac362e}.error{color:#982c26;font-size:.9rem;line-height:1.5}.actions{display:flex;gap:.6rem;flex-wrap:wrap;margin:1rem 0}.actions button:first-child{background:var(--accent);color:white;border-color:var(--accent)}ul{padding:0;margin:1.6rem 0;list-style:none;display:grid;gap:.75rem}.task{width:100%;text-align:left;background:#f8f9f4;border:1px solid #e1e7dc;border-radius:16px;padding:1.1rem;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:.4rem}.task-title{font-weight:650;white-space:pre-wrap;overflow-wrap:anywhere}.task-status{font-size:.76rem;font-weight:500;color:#526459}.task-arrow{grid-column:2;grid-row:1/3;align-self:center;width:8px;height:8px;border-right:2px solid #7b8e7c;border-top:2px solid #7b8e7c;transform:rotate(45deg)}.display{font-family:Georgia,serif;font-size:2rem;line-height:1.25;white-space:pre-wrap;overflow-wrap:anywhere}.notice{color:#61766a;font-size:.9rem;line-height:1.6;padding:.5rem 0}.footer{margin-top:2rem;font-size:.75rem;color:#526459}#sedrava-error{max-width:1050px;margin:0 auto 1rem;padding:1rem 1.5rem}[hidden]{display:none!important}@media(max-width:720px){.brand{padding:1.2rem}.shell{grid-template-columns:1fr;gap:1rem;margin:0;padding:0 1.2rem 2rem}.intro{padding:0}h1{font-size:3rem}.subtitle{margin-bottom:1.2rem}.workspace{padding:1.25rem;border-radius:20px}.footer{margin-top:1rem}}@media(prefers-reduced-motion:no-preference){.workspace.arrive{animation:arrive .18s ease-out}@keyframes arrive{from{opacity:.6;transform:translateY(5px)}to{opacity:1;transform:none}}}
'''


def generate_navigation(source, program):
    # Reuse the exact scalar/record/action/persistence adapter, not a parallel evaluator.
    script = generate(source, _program=replace(program, widgets=(("text", program.name),)), _domain_only=True)
    names={key:'values['+q(key)+']' for key in program.states}
    derived=[]
    for key,expr in program.derived.items():
        derived.append('values['+q(key)+']='+js_expr(expr,names)+';')
        names[key]='values['+q(key)+']'
    guards=[]
    for screen in program.screens.values():
        guards.append('case '+q(screen.name)+': return '+(js_expr(screen.guard,names) if screen.guard else 'true')+';')
    bindings={k:{'target':v.target,'action':v.action} for k,v in program.navigation.items()}
    runtime='\n'.join([
        'const initialScreen='+q(program.initial_screen)+';',
        'const presentationNames=JSON.parse('+q(__import__('json').dumps(program.display_names or {}))+');',
        'const screenNames='+q(list(program.screens))+';',
        'const navigationBindings=JSON.parse('+q(__import__('json').dumps(bindings))+');',
        'function domainValues(domain){const values={__proto__:null,...domain};'+''.join(derived)+'return values;}',
        'function screenVisible(domain,screen){try{const values=domainValues(domain);switch(screen){'+''.join(guards)+'default:return false;}}catch(_){return false;}}',
        PURE_RUNTIME,
    ])
    render_cases=[]
    refresh_cases=[]
    for screen in program.screens.values():
        widgets=screen.widgets
        texts=[w for w in widgets if w.kind=='text']
        title=texts[0].args[0] if texts else screen.name
        subtitle=texts[1].args[0] if len(texts)>1 else ''
        parts=[]
        refresh=[]
        for index,w in enumerate(widgets):
            args=w.args
            if w.kind=='text':
                if w not in texts[:2]: parts.append('addText(host,'+q(args[0])+',"notice");')
                continue
            elif w.kind.startswith('input'):
                key=args[0]; label=args[1] if len(args)>1 else (program.display_names or {}).get(key,key)
                ident='field-'+screen.name+'-'+str(index)
                attrs=' id="'+ident+'" data-input="'+html.escape(key,quote=True)+'" aria-describedby="error-'+ident+'" aria-invalid="false"'
                control='<textarea'+attrs+'></textarea>' if w.kind=='input_text' else '<input type="text" inputmode="numeric"'+attrs+'>'
                input_html='<div class="input-group"><label for="'+ident+'">'+html.escape(label)+'</label>'+control+'<small class="error" role="alert" id="error-'+ident+'" hidden>Enter a valid value that satisfies the app rules.</small></div>'
                parts.append('host.insertAdjacentHTML("beforeend",'+q(input_html)+');')
            elif w.kind=='button':
                parts.append('addAction(host,'+q(args[0])+','+q(args[1])+','+q('widget-'+screen.name+'-'+str(index))+');')
            elif w.kind=='show_text':
                parts.append('{ const el=addText(host,'+q(args[1])+',"notice");el.dataset.show='+q(args[0])+';el.hidden=!values['+q(args[0])+']; }')
            elif w.kind=='display':
                ident='display-'+screen.name+'-'+str(index)
                expression=js_expr(args[0],names)
                parts.append('{ const el=addText(host,"","display");el.id='+q(ident)+';try { el.textContent=String('+expression+'); } catch(_) { el.textContent="Unavailable"; } }')
                refresh.append('{ const el=document.getElementById('+q(ident)+');if(el){try {el.textContent=String('+expression+');}catch(_){el.textContent="Unavailable";}} }')
            elif w.kind=='value':
                parts.append('{ const el=addText(host,'+q((program.display_names or {}).get(args[0],args[0])+': ')+'+String(values['+q(args[0])+']),"notice");el.dataset.value='+q(args[0])+'; }')
            elif w.kind in ('list','list_open'):
                collection,selected=args[:2]
                command=args[2] if w.kind=='list_open' else None
                title_field=args[3] if w.kind=='list_open' else None
                status_field=args[4] if w.kind=='list_open' else None
                parts.append('addList(host,'+','.join(q(a) for a in (collection,selected,command,title_field,status_field))+');')
        refresh_cases.append('case '+q(screen.name)+':'+''.join(refresh)+'break;')
        render_cases.append('case '+q(screen.name)+': heading.textContent='+q(title)+';subtitle.textContent='+q(subtitle)+';'+''.join(parts)+'break;')
    ui=UI_RUNTIME.replace('/*SCREEN_CASES*/',''.join(render_cases)).replace('/*REFRESH_CASES*/',''.join(refresh_cases))
    page='<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(program.name)+'</title><style>'+STYLE+'</style></head><body><header class="brand"><span class="brand-mark" aria-hidden="true">✓</span>'+html.escape(program.name)+'</header><p id="sedrava-error" class="error" role="alert" hidden></p><main id="app"></main><script>'+script+runtime+ui+'</script></body></html>\n'
    return page


PURE_RUNTIME = r'''
function validStack(stack){return Array.isArray(stack)&&stack.length>=1&&stack.length<=32&&stack[0]===initialScreen&&stack.every(s=>typeof s==='string'&&screenNames.includes(s));}
function normalizeSession(domain,stack){stack=[...stack];while(stack.length>1&&!screenVisible(domain,stack.at(-1)))stack.pop();return {state:domain,stack};}
function initialSession(domain=initialState){if(!validateState(domain))throw Error('Invalid session');return {state:domain,stack:[initialScreen]};}
function restoreSession(domain,stack){const initial=initialSession(domain);return validStack(stack)?normalizeSession(domain,stack):initial;}
function dispatchSession(current,command){
 if(!validStack(current.stack)||!validateState(current.state))return current;
 let domain=current.state,stack=[...current.stack];
 try{
  if(command==='$back'){if(stack.length>1)stack.pop();}
  else if(Object.hasOwn(navigationBindings,command)){
   const binding=navigationBindings[command];
   if(binding.action){const next=actions[binding.action](domain);if(next===domain)return current;domain=next;}
   if(binding.target==='pop'){if(stack.length>1)stack.pop();}
   else{if(stack.length>=32||!screenVisible(domain,binding.target))return current;stack.push(binding.target);}
  }else if(Object.hasOwn(actions,command)){const next=actions[command](domain);if(next===domain)return current;domain=next;}
  else return current;
  return normalizeSession(domain,stack);
 }catch(_){return current;}
}
function editSession(current,key,value){if(!validStack(current.stack))return current;const next=editState(current.state,key,value);return next===current.state?current:normalizeSession(next,current.stack);}
function selectItem(current,collection,key,id,command=null){
 if(!Object.hasOwn(collectionTypes,collection)||typeof initialState[key]!=='number'||!Number.isInteger(id)||!current.state[collection].items.some(r=>r.id===id))return current;
 const selected=editSession(current,key,id);if(selected===current)return current;
 if(command===null)return selected;
 const next=dispatchSession(selected,command);return next===selected?current:next;
}
'''

UI_RUNTIME = r'''
let session=initialSession(state);
let historyToken=null,historyIndex=0,frameIndices=[0],traversing=false;
function showError(message){const el=document.getElementById('sedrava-error');if(el){el.textContent=message;el.hidden=!message;}}
function saveAccepted(){state=session.state;try{saveSnapshot();}catch(_){showError('Could not save your changes on this device.');}}
function historyRecord(){return {sedrava:historyToken,index:historyIndex,stack:session.stack,indices:frameIndices};}
function syncHistory(previous){
 if(typeof window==='undefined'||!window.history)return;
 if(session.stack.length>previous.stack.length){historyIndex++;frameIndices=[...frameIndices,historyIndex];window.history.pushState(historyRecord(),'');}
 else if(session.stack.length<previous.stack.length){const target=frameIndices[session.stack.length-1];frameIndices=frameIndices.slice(0,session.stack.length);if(Number.isInteger(target)&&target<historyIndex){traversing=true;window.history.go(target-historyIndex);}else window.history.replaceState(historyRecord(),'');}
 else window.history.replaceState(historyRecord(),'');
}
function commitSession(next,previous){if(next===previous){showError('Could not complete this action. Check the task, title and list capacity.');return false;}session=next;showError('');saveAccepted();syncHistory(previous);render(true,JSON.stringify(session.stack)!==JSON.stringify(previous.stack));return true;}
function addText(host,text,cls){const el=document.createElement('p');el.className=cls;el.textContent=text;host.append(el);return el;}
function syncControls(){const invalid=!!document.querySelector('[data-input][aria-invalid="true"]');document.querySelectorAll('button[data-action],button.task').forEach(el=>{const binding=navigationBindings[el.dataset.action];el.disabled=invalid&&!(binding&&!binding.action);});}
function addAction(host,label,command,id){let actions=host.lastElementChild;if(!actions||actions.className!=='actions'){actions=document.createElement('div');actions.className='actions';host.append(actions);}const button=document.createElement('button');button.type='button';button.textContent=label;button.dataset.action=command;button.id=id;button.onclick=()=>{if(!traversing)commitSession(dispatchSession(session,command),session);};actions.append(button);}
function addList(host,collection,key,command,titleField,statusField){
 const list=document.createElement('ul');list.dataset.list=collection;list.setAttribute('aria-label',collection);
 for(const row of session.state[collection].items){const item=document.createElement('li');item.dataset.id=String(row.id);const button=document.createElement('button');button.type='button';button.className='task';
  const title=document.createElement('span');title.className='task-title';title.textContent=titleField?row[titleField]:Object.entries(row).filter(([k])=>k!=='id').map(([k,v])=>k+': '+v).join(' · ');button.append(title);
  if(statusField){const status=document.createElement('span');status.className='task-status';status.textContent=row[statusField]?'Completed':'In progress';status.id='status-'+collection+'-'+row.id;button.setAttribute('aria-describedby',status.id);button.append(status);}
  const arrow=document.createElement('span');arrow.className='task-arrow';arrow.textContent='';arrow.setAttribute('aria-hidden','true');button.append(arrow);button.setAttribute('aria-label',(command?'Open ':'Select ')+title.textContent);
  button.onclick=()=>{if(!traversing)commitSession(selectItem(session,collection,key,row.id,command),session);};item.append(button);list.append(item);
 }host.append(list);
}
function render(resetInputs=false,focus=false){
 const root=document.getElementById('app');if(!root)return;
 const active=session.stack.at(-1),values=domainValues(session.state);
 if(!resetInputs&&root.dataset.screen===active){
  root.querySelectorAll('[data-show]').forEach(el=>{el.hidden=!values[el.dataset.show];});
  root.querySelectorAll('[data-value]').forEach(el=>{el.textContent=(Object.hasOwn(presentationNames,el.dataset.value)?presentationNames[el.dataset.value]:el.dataset.value)+': '+String(values[el.dataset.value]);});
  root.querySelectorAll('[data-input]').forEach(el=>{if(document.activeElement!==el)el.value=String(session.state[el.dataset.input]);});
  switch(active){/*REFRESH_CASES*/}
  return;
 }

 // Preserve the active draft/focus on accepted input; rebuild only for actions/transitions.
 const controlId=root.dataset.screen===active&&document.activeElement?document.activeElement.id:null;
 const editor=!resetInputs&&root.dataset.screen===active&&document.activeElement&&root.contains(document.activeElement)&&document.activeElement.dataset.input?{id:document.activeElement.id,value:document.activeElement.value,start:document.activeElement.selectionStart,end:document.activeElement.selectionEnd}:null;
 root.dataset.screen=active;root.inert=traversing;
 root.innerHTML='<section class="shell"><div class="intro"><p class="eyebrow">Your space · '+String(session.stack.length).padStart(2,'0')+'</p><h1 tabindex="-1"></h1><p class="subtitle"></p><p class="footer">Offline by design. A little progress, every day.</p></div><div class="workspace"></div></section>';
 const heading=root.querySelector('h1'),subtitle=root.querySelector('.subtitle'),host=root.querySelector('.workspace');if(focus)host.classList.add('arrive');
 switch(active){/*SCREEN_CASES*/}
 root.querySelectorAll('[data-input]').forEach(el=>{
  const key=el.dataset.input;el.value=String(session.state[key]);
  el.addEventListener('input',()=>{const text=typeof initialState[key]==='string';const raw=text?el.value:el.value.trim();const value=text?raw:/^-?[0-9]+$/.test(raw)?Number(raw):null;const previous=session;const next=editSession(previous,key,value);const accepted=next!==previous;el.setAttribute('aria-invalid',String(!accepted));document.getElementById('error-'+el.id).hidden=accepted;syncControls();if(accepted){session=next;saveAccepted();syncHistory(previous);render(session.stack.at(-1)!==active,session.stack.at(-1)!==active);}});
 });
 syncControls();
 if(focus)heading.focus();else if(editor){const el=document.getElementById(editor.id);if(el){el.value=editor.value;el.focus();el.setSelectionRange(editor.start,editor.end);}}else if(controlId){const el=document.getElementById(controlId);if(el)el.focus();}
}
if(typeof window!=='undefined'&&window.history){
 window.history.scrollRestoration='manual';
 historyToken=(typeof crypto!=='undefined'&&crypto.randomUUID)?crypto.randomUUID():String(Date.now())+String(Math.random());
 window.history.replaceState(historyRecord(),'');
 window.addEventListener('popstate',event=>{
  traversing=false;const entry=event.state;
  if(!entry||entry.sedrava!==historyToken||!validStack(entry.stack)||!Array.isArray(entry.indices)||entry.indices.length!==entry.stack.length||!entry.indices.every(Number.isSafeInteger)||entry.indices[0]!==0||entry.indices.some((n,i)=>n<0||(i>0&&n<=entry.indices[i-1]))||entry.indices.at(-1)!==entry.index){session=initialSession(session.state);historyIndex=0;frameIndices=[0];window.history.replaceState(historyRecord(),'');}
  else{historyIndex=entry.index;frameIndices=entry.indices;session=normalizeSession(session.state,entry.stack);if(session.stack.length<entry.stack.length){const target=frameIndices[session.stack.length-1];frameIndices=frameIndices.slice(0,session.stack.length);traversing=true;window.history.go(target-historyIndex);}}
  render(true,true);
 });
}
render(true,false);
if(restoreError)showError('Saved data could not be restored. Defaults are shown.');
'''
