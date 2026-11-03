"""Native Web form/dialog adapter; state writes use the existing validated edit/action runtime."""
EXTRA_CSS = r'''
.s-remote-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,16rem),1fr));gap:16px}.s-remote-grid article{padding:20px;border-radius:16px;overflow-wrap:anywhere;min-width:0}
.s-webapp [data-each-items]{display:grid;gap:16px;min-width:0}.s-webapp [data-each-items]>[role=listitem]{min-width:0}
.s-webapp [data-table]{max-width:100%;overflow:auto}.s-webapp table{width:100%;border-collapse:collapse;table-layout:fixed}.s-webapp th,.s-webapp td{text-align:start;border-block-end:1px solid var(--border);padding:12px 8px;overflow-wrap:anywhere}.s-webapp td button{font:inherit;padding:8px;border-radius:10px;background:var(--surface);color:var(--foreground);border:1px solid var(--border);width:100%}
.s-webapp select{font:inherit;padding:12px;color:var(--foreground);background:var(--surface);border:1px solid var(--border);border-radius:10px;width:100%;max-width:100%}
.s-webapp form{display:grid;gap:16px}.s-webapp dialog{color:var(--foreground);background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:24px;width:min(34rem,calc(100% - 32px));max-height:85vh;overflow:auto}
.s-webapp dialog::backdrop{background:#0009}.s-webapp button{overflow-wrap:anywhere;min-height:44px;max-width:100%}
.s-webapp [data-view][hidden]{display:none!important}.s-webapp [data-view]{min-width:0}
'''
EXTRA_JS = r'''
function renderTable(rows,el,selected,fragment){
 const fields=el.dataset.table.split(' '),table=document.createElement('table');
 const caption=document.createElement('caption');caption.textContent=el.getAttribute('aria-label');table.append(caption);
 const head=document.createElement('thead'),tr=document.createElement('tr');
 for(const field of fields){const th=document.createElement('th');th.scope='col';th.textContent=field;tr.append(th);}head.append(tr);table.append(head);
 const body=document.createElement('tbody');
 for(const row of rows){const tr=document.createElement('tr');tr.dataset.id=String(row.id);
  fields.forEach((field,i)=>{const td=document.createElement('td');
   if(i===0){const button=document.createElement('button');button.type='button';button.textContent=String(row[field]);button.setAttribute('aria-label','Select '+String(el.dataset.titleField?row[el.dataset.titleField]:row[field]));button.setAttribute('aria-pressed',String(selected===row.id));
    button.onclick=()=>{if(button.disabled)return;if(commit(editState(state,el.dataset.select,row.id))){const updated=el.querySelector('[data-id="'+row.id+'"] button');if(updated)updated.focus({preventScroll:true});}};td.append(button);
   }else td.textContent=String(row[field]);tr.append(td);
  });body.append(tr);
 }
 if(!rows.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=fields.length;td.textContent=el.dataset.queryEmpty||'No matching records';tr.append(td);body.append(tr);}
 table.append(body);fragment.append(table);
}

function renderEach(){
 document.querySelectorAll('[data-each]').forEach(el=>{
  const values=valuesOfState(),rows=queryRows(values[el.dataset.each].items,{title:el.dataset.titleField,search:el.dataset.querySearch?values[el.dataset.querySearch]:'',sort:el.dataset.querySort,where:el.dataset.queryWhere,equals:el.dataset.queryEquals?values[el.dataset.queryEquals]:false,active:el.dataset.queryActive?values[el.dataset.queryActive]:true});
  const list=el.querySelector('[data-each-items]'),template=el.querySelector('template'),fragment=document.createDocumentFragment();
  for(const row of rows){const item=document.createElement('div');item.setAttribute('role','listitem');item.dataset.rowId=String(row.id);item.dataset.rowSelect=el.dataset.select;item.dataset.rowCollection=el.dataset.each;item.append(template.content.cloneNode(true));
   item.querySelectorAll('[data-row-field]').forEach(node=>node.textContent=String(row[node.dataset.rowField]));
   item.querySelectorAll('[data-row-when]').forEach(node=>node.hidden=!row[node.dataset.rowWhen]);
   item.querySelectorAll('[data-state]').forEach(node=>node.textContent=String(values[node.dataset.state]));
   item.querySelectorAll('[data-when]').forEach(node=>node.hidden=!values[node.dataset.when]);
   item.querySelectorAll('button[data-action],button[data-pick]').forEach(button=>button.setAttribute('aria-label',button.textContent+' '+String(el.dataset.titleField?row[el.dataset.titleField]:row.id)));
   fragment.append(item);
  }
  if(!rows.length&&el.dataset.queryEmpty){const item=document.createElement('div');item.setAttribute('role','listitem');const note=document.createElement('p');note.setAttribute('role','status');note.textContent=el.dataset.queryEmpty;item.append(note);fragment.append(item);}
  list.replaceChildren(fragment);
 });
}
document.addEventListener('click',event=>{
 const button=event.target.closest('button[data-pick],button[data-action]');if(!button)return;
 const row=button.closest('[data-row-id]');if(!row||button.disabled)return;
 const identity=Number(row.dataset.rowId),collection=state[row.dataset.rowCollection];
 if(!collection.items.some(r=>r.id===identity)){showError('Record no longer exists');return;}
 try{
  const candidate=editState(state,row.dataset.rowSelect,identity);if(candidate===state){showError('Selection rejected');return;}
  const next=button.dataset.action?actions[button.dataset.action](candidate):candidate;
  if(button.dataset.action&&next===candidate){showError('Row action rejected');return;}
  const action=button.dataset.action,owner=row.closest('[data-each]');
  if(commit(next)){const updated=[...owner.querySelectorAll('[data-row-id]')].find(el=>el.dataset.rowId===String(identity));
   const focus=updated&&[...updated.querySelectorAll('button')].find(el=>action?el.dataset.action===action:el.hasAttribute('data-pick'));
   if(focus)focus.focus({preventScroll:true});
  }
 }catch(_){showError('Row action rejected: invalid value or overflow');}
});
document.querySelectorAll('[data-submit]').forEach(el=>el.addEventListener('submit',event=>{
  event.preventDefault();if(document.querySelector('[data-input][aria-invalid=true]'))return;
  try{commit(actions[el.dataset.submit](state));}catch(_){showError('Form rejected: invalid value or overflow');}
}));
document.querySelectorAll('[data-choice]').forEach(el=>{
  el.value=JSON.stringify(state[el.dataset.choice]);
  el.addEventListener('change',()=>{try{commit(editState(state,el.dataset.choice,JSON.parse(el.value)));}catch(_){showError('Choice rejected');}render();});
});
document.querySelectorAll('[data-open-dialog]').forEach(el=>el.addEventListener('click',()=>{
  const dialog=document.getElementById(el.dataset.openDialog);if(dialog&&!dialog.open)dialog.showModal();
}));
document.querySelectorAll('[data-close-dialog]').forEach(el=>el.addEventListener('click',()=>document.getElementById(el.dataset.closeDialog)?.close()));
'''
