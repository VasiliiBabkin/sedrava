"""Validated WebApp route model shared by interpreter tests and browser generation."""
import re
from sedrava_core import edit_state, resolve


def route_parameters(path):
    if not re.fullmatch(r'/(?:[A-Za-z0-9_-]+|:[A-Za-z][A-Za-z0-9_]*)(?:/(?:[A-Za-z0-9_-]+|:[A-Za-z][A-Za-z0-9_]*))*|/', path):
        raise ValueError('Route must use literal segments or :integer_state parameters')
    names = re.findall(r':([A-Za-z][A-Za-z0-9_]*)', path)
    if len(names) != len(set(names)):
        raise ValueError('Duplicate route parameter')
    return names


def resolve_route(document, path, state):
    for name, spec in document.views.items():
        pattern = '^'+re.sub(r':[A-Za-z][A-Za-z0-9_]*', r'(-?[0-9]+)', spec['path'])+'$'
        match = re.fullmatch(pattern, path)
        if not match:
            continue
        candidate = state
        for key, raw in zip(route_parameters(spec['path']), match.groups()):
            if len(raw) > 11: return None
            candidate, accepted = edit_state(document.program, candidate, key, int(raw))
            if not accepted: return None
        if spec['guard'] and not resolve(candidate, document.program.derived)[spec['guard']]:
            return None
        return name, candidate
    return None


ROUTER_JS = r'''
let activeView='main';
function routePath(name, candidate=state){return viewConfig[name].path.replace(/:([A-Za-z][A-Za-z0-9_]*)/g,(_,key)=>String(candidate[key]));}
function canView(name,candidate=state){const spec=viewConfig[name];if(!spec)return false;const old=state;state=candidate;try{return !spec.guard||valuesOfState()[spec.guard]===true;}finally{state=old;}}
function focusView(){const node=document.querySelector('[data-view="'+activeView+'"] h1');if(node){node.tabIndex=-1;node.focus({preventScroll:true});}}
function showView(){document.querySelectorAll('[data-view]').forEach(el=>{el.hidden=el.dataset.view!==activeView;});document.querySelectorAll('[data-view][hidden] dialog[open]').forEach(d=>d.close());const hash='#'+routePath(activeView);if(routeReady&&location.hash!==hash)history.replaceState(history.state,'',hash);}
function goView(name, replace=false, candidate=state){
  if(!canView(name,candidate)){showError('View unavailable: missing data or invalid route');return false;}
  const depth=replace?0:(history.state?.sedravaDepth||0)+1;
  if(depth>32){showError('Navigation stack limit reached');return false;}
  state=candidate;activeView=name;
  history[replace?'replaceState':'pushState']({sedravaDepth:depth},'', '#'+routePath(name));
  render();focusView();return true;
}
function restoreRoute(){
  const path=location.hash.slice(1)||'/';let found=false;
  for(const [name,spec] of Object.entries(viewConfig)){
    const keys=[...spec.path.matchAll(/:([A-Za-z][A-Za-z0-9_]*)/g)].map(m=>m[1]);
    const pattern='^'+spec.path.replace(/:[A-Za-z][A-Za-z0-9_]*/g,'(-?[0-9]+)')+'$';
    const match=path.match(new RegExp(pattern));if(!match)continue;
    let candidate=state;let valid=true;
    keys.forEach((key,i)=>{const raw=match[i+1];const next=raw.length<=11?editState(candidate,key,Number(raw)):candidate;if(next===candidate)valid=false;candidate=next;});
    if(!valid||!canView(name,candidate))break;
    state=candidate;activeView=name;found=true;break;
  }
  if(!found){activeView='main';history.replaceState({sedravaDepth:0},'','#/');showError('Page not found or selected record no longer exists');}
  else if(!location.hash)history.replaceState({sedravaDepth:0},'','#/');
  routeReady=true;render();focusView();
}
window.addEventListener('popstate',restoreRoute);
document.querySelectorAll('[data-navigate]').forEach(el=>el.addEventListener('click',()=>{
  if(el.disabled)return;
  let candidate=state;
  try{if(el.dataset.routeAction)candidate=actions[el.dataset.routeAction](state);
    if(candidate===state&&el.dataset.routeAction){showError('Action rejected');return;}
    if(goView(el.dataset.navigate,false,candidate))persistAccepted();
  }catch(_){showError('Navigation action rejected');}
}));
document.querySelectorAll('[data-back]').forEach(el=>el.addEventListener('click',()=>{
  if((history.state?.sedravaDepth||0)>0)history.back();else goView('main',true);
}));
restoreRoute();
'''
