"""Native Web form/dialog adapter; state writes use the existing validated edit/action runtime."""
EXTRA_CSS = r'''
.s-remote-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,16rem),1fr));gap:16px}.s-remote-grid article{padding:20px;border-radius:16px;overflow-wrap:anywhere;min-width:0}
.s-webapp select{font:inherit;padding:12px;color:var(--foreground);background:var(--surface);border:1px solid var(--border);border-radius:10px;width:100%;max-width:100%}
.s-webapp form{display:grid;gap:16px}.s-webapp dialog{color:var(--foreground);background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:24px;width:min(34rem,calc(100% - 32px));max-height:85vh;overflow:auto}
.s-webapp dialog::backdrop{background:#0009}.s-webapp button{overflow-wrap:anywhere;min-height:44px;max-width:100%}
.s-webapp [data-view][hidden]{display:none!important}.s-webapp [data-view]{min-width:0}
'''
EXTRA_JS = r'''
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
