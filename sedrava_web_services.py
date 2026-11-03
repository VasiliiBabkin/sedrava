"""WebApp HTTP capabilities layered on API0 schemas; never compiler-side network I/O."""
from dataclasses import dataclass
import re
from sedrava_http import ApiService, JsonResponse
from sedrava_http_parser import parse_service
from sedrava_core import parse_expr, type_of
from sedrava_records import RecordType
from web_codegen import js_expr, json_script


@dataclass(frozen=True)
class WebService:
    service: object
    schema: object
    origin: str
    method: str
    body: object
    auto: bool
    cache: bool


def extract_services(source):
    lines=source.splitlines();kept=[];blocks={};i=0
    while i<len(lines):
        m=re.fullmatch(r'service ([A-Za-z][A-Za-z0-9_]*):',lines[i])
        if not m:kept.append(lines[i]);i+=1;continue
        name=m[1];block=[lines[i]];kept.append('');i+=1
        if name in blocks or len(blocks)>=16:raise ValueError(f'Line {i}: column 1: duplicate/excessive service')
        while i<len(lines) and (not lines[i].strip() or lines[i].startswith(' ')):
            block.append(lines[i]);kept.append('');i+=1
        blocks[name]='\n'.join(block)+'\n'
    return '\n'.join(kept)+'\n',blocks


def validate_services(blocks, program, types):
    services={}
    for name,source in blocks.items():
        props={};base=[]
        for n,line in enumerate(source.splitlines(),1):
            match=re.fullmatch(r'    (method|body|auto|cache|max-items) (.+)',line)
            if match:
                if match[1] in props:raise ValueError(f'Line {n}: column 5: duplicate HTTP property')
                props[match[1]]=match[2]
            else:base.append(line)
        own= '    origin self' in base
        if own:base[base.index('    origin self')]='    origin "https://same-origin.example"'
        if not any(line.startswith('    max-bytes ') for line in base):base.insert(1,'    max-bytes 65536')
        capability,schema=parse_service('\n'.join(base)+'\n')
        if capability.max_bytes>200000:raise ValueError('WebApp HTTP maximum is 200000 bytes')
        method=props.get('method','GET')
        if method not in ('GET','POST','PUT','PATCH','DELETE'):raise ValueError('Unsupported HTTP method')
        for key in ('auto','cache'):
            if props.get(key,'false') not in ('true','false'):raise ValueError('HTTP '+key+' requires bool literal')
        if (props.get('cache')=='true' or props.get('auto')=='true') and method!='GET':raise ValueError('Only GET may auto-load/cache')
        count=props.get('max-items','100')
        if not re.fullmatch('[0-9]{1,4}',count):raise ValueError('Invalid max-items')
        schema=JsonResponse(schema.fields,schema.many,int(count))
        body=None
        if 'body' in props:
            if method in ('GET','DELETE'):raise ValueError('GET/DELETE do not accept a request body')
            body=parse_expr(props['body'],{**program.records,**types})
            if not isinstance(type_of(body,{**program.records,**types}),RecordType):raise ValueError('HTTP body requires a typed record')
        elif method in ('POST','PUT','PATCH'):raise ValueError('Mutation requires a typed body')
        for key in re.findall(r':([A-Za-z][A-Za-z0-9_]*)',capability.path):
            if types.get(key) is not int:raise ValueError('HTTP path parameters require integer state')
        services[name]=WebService(capability,schema,'' if own else capability.origin.rstrip('/'),method,body,props.get('auto')=='true',props.get('cache')=='true')
    return services


def generate_services(services, program):
    configs={};bodies=[]
    names={key:'values['+json_script(key)+']' for key in (*program.states,*program.derived)}
    for name,item in services.items():
        configs[name]={'origin':item.origin,'path':item.service.path,'method':item.method,
                       'timeout':item.service.timeout_ms,'maxBytes':item.service.max_bytes,
                       'many':item.schema.many,'maxItems':item.schema.max_items,
                       'fields':{f.name:f.kind for f in item.schema.fields},'auto':item.auto,'cache':item.cache}
        if item.body is not None:bodies.append(json_script(name)+':()=>{const values=valuesOfState();return '+js_expr(item.body,names)+';}')
    return 'const serviceConfigs='+json_script(configs)+';\nconst serviceBodies={'+','.join(bodies)+'};\n'+HTTP_JS


HTTP_JS=r'''
const services=Object.create(null);
function checkRemote(data,config){
  const rows=config.many?data:[data];
  if(!Array.isArray(rows)||rows.length>config.maxItems)throw Error('Invalid response collection');
  for(const row of rows){
    if(!row||typeof row!=='object'||Array.isArray(row)||Object.keys(row).length!==Object.keys(config.fields).length)throw Error('Unexpected response fields');
    for(const [field,type] of Object.entries(config.fields)){
      if(!Object.hasOwn(row,field))throw Error('Missing response field');const v=row[field];
      if(type==='text'&&(!validText(v)||Array.from(v).some(c=>c.codePointAt(0)<32&&![9,10].includes(c.codePointAt(0)))))throw Error('Invalid text response');
      if(type==='int32'&&(!Number.isInteger(v)||v< -2147483648||v>2147483647))throw Error('Invalid integer response');
      if(type==='bool'&&typeof v!=='boolean')throw Error('Invalid boolean response');
    }
  }return data;
}
function renderRemote(){
  document.querySelectorAll('[data-remote]').forEach(el=>{
    const service=services[el.dataset.remote];if(!service)return;
    el.dataset.status=service.status;el.setAttribute('aria-busy',String(service.status==='loading'));
    el.querySelector('[data-remote-status]').textContent=service.status+(service.error?': '+service.error:'');
    const list=el.querySelector('[data-remote-results]');const fragment=document.createDocumentFragment();
    const config=serviceConfigs[el.dataset.remote];let rows=service.data===null?[]:(config.many?service.data:[service.data]);
    if(el.dataset.remoteSearch){const query=valuesOfState()[el.dataset.remoteSearch].toLowerCase();rows=rows.filter(row=>Object.values(row).some(v=>String(v).toLowerCase().includes(query)));}
    for(const row of rows){const card=document.createElement('article');card.className='s-card';
      for(const [key,value] of Object.entries(row)){const node=document.createElement(key===el.dataset.remoteTitle?'h3':'p');node.textContent=String(value);card.append(node);}fragment.append(card);}
    if(service.status==='success'&&!rows.length){const empty=document.createElement('p');empty.textContent='No matching data';fragment.append(empty);}
    list.replaceChildren(fragment);
  });
}
for(const [name,config] of Object.entries(serviceConfigs)){
  const current={status:'idle',data:null,error:'',sequence:0,controller:null};services[name]=current;
  const cacheKey='sedrava-api:'+document.title+':'+name+':'+JSON.stringify(config);let cacheRejected=false;
  if(config.cache){try{const raw=localStorage.getItem(cacheKey);if(raw!==null){current.data=checkRemote(strictJSON(raw),config);current.status='success';}}catch(_){cacheRejected=true;current.error='Saved API data rejected; original retained';}}
  current.cancel=()=>{current.sequence++;current.controller?.abort();current.controller=null;if(current.status==='loading'){current.status='idle';current.error='Request cancelled';}renderRemote();};
  current.load=async()=>{
    current.cancel();const sequence=++current.sequence;const controller=new AbortController();current.controller=controller;let expired=false;
    const timer=setTimeout(()=>{expired=true;controller.abort();},config.timeout);
    current.status='loading';current.error='';renderRemote();
    try{
      const values=valuesOfState();const path=config.path.replace(/:([A-Za-z][A-Za-z0-9_]*)/g,(_,key)=>String(values[key]));
      const target=new URL(config.origin+path,location.href);
      if(target.origin!==(config.origin||location.origin))throw Error('Origin capability mismatch');
      const body=serviceBodies[name]?JSON.stringify(serviceBodies[name]()):undefined;
      if(body!==undefined&&new TextEncoder().encode(body).length>config.maxBytes)throw Error('Request exceeds byte limit');
      const response=await fetch(target.href,{method:config.method,body,headers:body?{'Accept':'application/json','Content-Type':'application/json'}:{'Accept':'application/json'},credentials:'omit',redirect:'error',cache:'no-store',referrerPolicy:'no-referrer',signal:controller.signal});
      if(!response.ok)throw Error('HTTP '+response.status);
      let data;
      if(response.status===204)data=config.many?[]:null;
      else{
        if((response.headers.get('content-type')||'').split(';')[0].trim().toLowerCase()!=='application/json')throw Error('Expected JSON response');
        const reader=response.body?.getReader();if(!reader)throw Error('Missing response stream');let length=0;const chunks=[];
        try{while(true){const item=await reader.read();if(item.done)break;length+=item.value.byteLength;if(length>config.maxBytes)throw Error('Response exceeds byte limit');chunks.push(item.value);}}
        catch(error){await reader.cancel().catch(()=>{});throw error;}
        const bytes=new Uint8Array(length);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
        data=checkRemote(strictJSON(new TextDecoder('utf-8',{fatal:true}).decode(bytes)),config);
      }
      if(controller.signal.aborted)throw Error('Request aborted');
      if(sequence!==current.sequence)return;
      if(response.status===204&&!config.many)throw Error('Empty response requires a many schema');
      current.data=data;current.status='success';current.error='';
      if(config.cache&&!cacheRejected){try{const previous=localStorage.getItem(cacheKey);if(previous!==null)checkRemote(strictJSON(previous),config);localStorage.setItem(cacheKey,JSON.stringify(data));}catch(_){cacheRejected=true;current.error='Could not save API cache; original retained';}}
    }catch(error){if(sequence!==current.sequence)return;current.status='error';current.error=expired?'Request timed out':controller.signal.aborted?'Request cancelled':String(error.message||'Network error');}
    finally{clearTimeout(timer);if(sequence===current.sequence){current.controller=null;renderRemote();}}
  };
}
document.querySelectorAll('[data-request]').forEach(el=>el.addEventListener('click',()=>{if(!document.querySelector('[data-input][aria-invalid=true]'))services[el.dataset.request].load();}));
document.querySelectorAll('[data-cancel-request]').forEach(el=>el.addEventListener('click',()=>services[el.dataset.cancelRequest].cancel()));
function syncServiceViews(){
  for(const [name,service] of Object.entries(services)){
    const panels=[...document.querySelectorAll('[data-remote]')].filter(el=>el.dataset.remote===name);
    const visible=panels.some(el=>!el.closest('[data-view][hidden]'));
    if(!visible&&service.controller)service.cancel();
    if(visible&&serviceConfigs[name].auto&&service.status==='idle')service.load();
  }
}
window.addEventListener('sedrava:view',syncServiceViews);
window.addEventListener('pagehide',()=>{for(const service of Object.values(services))service.cancel();});
remoteReady=true;renderRemote();syncServiceViews();
'''
