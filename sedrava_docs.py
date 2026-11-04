"""Bounded local documentation and trusted-author WebApp embedding for native sites.

Never evaluates source, accepts raw HTML or loads build-time network resources.
"""
import hashlib
import html
import json
import posixpath
import re
from pathlib import Path
from urllib.parse import urlsplit


def local_file(root,value,suffixes,limit=262144):
    root=Path(root).resolve();path=root/value
    if not isinstance(value,str) or not value or '\\' in value or Path(value).is_absolute() or '..' in Path(value).parts:raise ValueError('Documentation sources must be explicit root-contained local paths')
    resolved=path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file() or resolved.suffix not in suffixes:raise ValueError('Missing or unsupported local documentation source')
    for current in (path,*path.parents):
        if current==root:break
        if current.is_symlink():raise ValueError('Symlink documentation sources are forbidden')
    if resolved.stat().st_size>limit:raise ValueError('Documentation source exceeds byte limit')
    data=resolved.read_bytes()
    if len(data)>limit:raise ValueError('Documentation source exceeds byte limit')
    data.decode('utf-8');return resolved,data


def dependencies():
    try:
        from markdown_it import MarkdownIt
        from pygments import highlight
        return MarkdownIt,highlight
    except ImportError as exc:raise ValueError('Documentation components require sedrava[docs] (markdown-it-py and Pygments)') from exc


def code_panel(source,language='text',label='Source',source_url=None):
    _,highlight=dependencies()
    from pygments.lexers import get_lexer_by_name,TextLexer
    from pygments.lexer import RegexLexer
    from pygments.token import Keyword,String,Comment,Number,Text
    from pygments.formatters import HtmlFormatter
    class SedravaLexer(RegexLexer):
        tokens={'root':[(r'#[^\n]*',Comment),(r'"(?:[^"\\]|\\.)*"',String),(r'\b(?:site|page|webapp|app|state|persist|derive|action|rule|test|screen|view|record|fn|let|if|else|true|false|component|slot|use|import|service|require)\b',Keyword),(r'\b[0-9]+\b',Number),(r'[^"#\n]+|\n',Text)]}
    language=language.lower();language={'sdr':'sedrava','shell':'sh','bash':'sh','py':'python'}.get(language,language)
    if language not in ('sedrava','sh','python','text','json','typescript','javascript'):language='text'
    lexer=SedravaLexer(stripnl=False,ensurenl=False) if language=='sedrava' else get_lexer_by_name(language,stripnl=False,ensurenl=False) if language!='text' else TextLexer(stripnl=False,ensurenl=False)
    rendered=highlight(source,lexer,HtmlFormatter(nowrap=True))
    # Pygments must never change the bytes represented by the panel.
    from html.parser import HTMLParser
    class Plain(HTMLParser):
        def __init__(self):super().__init__();self.parts=[]
        def handle_data(self,data):self.parts.append(data)
    check=Plain();check.feed(rendered)
    if ''.join(check.parts)!=source:raise ValueError('Syntax highlighter changed displayed source')
    digest=hashlib.sha256(source.encode()).hexdigest()
    link='<a href="'+html.escape(source_url,quote=True)+'" download>Full source / Исходник</a>' if source_url else ''
    lines='\n'.join(str(i) for i in range(1,max(1,len(source.splitlines()))+1))
    return '<figure class="doc-code"><figcaption>'+html.escape(label)+' <span class="code-language">'+language+'</span> '+link+' <button type="button" data-copy>Copy / Копировать</button><span data-copy-status role="status"></span></figcaption><div class="code-scroll"><div class="code-table"><pre class="code-lines" aria-hidden="true">'+lines+'</pre><pre tabindex="0" aria-label="'+html.escape(label,quote=True)+'"><code data-source-sha256="'+digest+'">'+rendered+'</code></pre></div></div></figure>'


def slug(text):
    value=re.sub(r'[^\w\s-]','',text.lower());return re.sub(r'\s+','-',value.strip()) or 'section'


class Docs:
    def __init__(self,site,root,files,inputs):
        self.site=site;self.root=Path(root).resolve();self.files=files;self.inputs=inputs;self.entries=[];self.demos={};self.active=False;self.used_bytes=0
        self.routes={p.path for p in site.pages};self.page_ids={}
    def read(self,value,suffixes):
        path,data=local_file(self.root,value,suffixes);self.inputs.add(path);self.used_bytes+=len(data)
        if self.used_bytes>4*1024*1024 or len(self.inputs)>512:raise ValueError('Documentation dependency budget exceeded')
        return path,data
    def markdown(self,props,page,href):
        self.active=True;path,data=self.read(props['src'],{'.md'})
        source=data.decode();source=re.sub(r'\A---\n.*?\n---\n','',source,count=1,flags=re.S)
        MarkdownIt,_=dependencies();parser=MarkdownIt('commonmark',{'html':True,'linkify':False}).enable('table')
        parser.validateLink=lambda value:True
        tokens=parser.parse(source)
        if len(tokens)>10000:raise ValueError("Markdown token budget exceeded")
        def inspect(items):
            for token in items:
                if token.type in ('html_inline','html_block'):raise ValueError('Raw HTML is forbidden in documentation; migrate reviewed content to Markdown/Sedrava')
                if token.type=='image':raise ValueError('Use the checked Sedrava image component for local documentation images')
                if token.type=='link_open':
                    from sedrava_site import safe_url
                    value=token.attrGet('href');safe_url(value)
                    try:token.attrSet('href',href(value))
                    except KeyError as exc:raise ValueError('Unknown documentation route '+value) from exc
                if token.children:inspect(token.children)
        inspect(tokens);headings=[];used=self.page_ids.setdefault(page.path,{'content'});plain=[]
        for index,token in enumerate(tokens):
            if token.type=='heading_open':
                if token.tag=='h1':raise ValueError('Markdown starts at h2; the containing Sedrava page owns h1')
                text=tokens[index+1].content;ident=slug(text);base=ident;i=0
                while ident in used:i+=1;ident=base+'-'+str(i)
                used.add(ident);token.attrSet('id',ident);headings.append((ident,text))
            if token.type in ('inline','fence','code_block'):plain.append(token.content)
        def fence(ts,index,options,env):
            token=ts[index];info=token.info.split();language=info[0] if info else 'text'
            if language=='text' and token.content.startswith(('app ','webapp ','site ')):language='sedrava'
            return code_panel(token.content,language,'Code / Код')
        parser.renderer.rules['fence']=fence
        parser.renderer.rules['code_block']=lambda ts,i,o,e:code_panel(ts[i].content,'text','Code / Код')
        result=parser.renderer.render(tokens,parser.options,{})
        toc='<details class="doc-toc"><summary>'+('На этой странице' if page.lang=='ru' else 'On this page')+'</summary><nav aria-label="'+('Оглавление' if page.lang=='ru' else 'Table of contents')+'"><ul>'+''.join('<li><a href="#'+ident+'">'+html.escape(text)+'</a></li>' for ident,text in headings)+'</ul></nav></details>' if headings else ''
        self.entries.append({'url':page.path,'title':page.title,'lang':page.lang,'headings':[text for _,text in headings],'text':'\n'.join(plain)})
        return '<article class="doc-markdown" data-document-source="'+html.escape(props['src'],quote=True)+'">'+toc+result+'</article>'
    def demo(self,props,page,rel):
        self.active=True;route=props['at'];path,data=self.read(props['src'],{'.sdr'})
        if route in self.routes or any(p.startswith(route) or route.startswith(p) for p in self.routes if p!='/'):raise ValueError('Demo route collides with a site page')
        if route in self.demos and self.demos[route]['path']!=path:raise ValueError('Different demos cannot own the same route')
        if route not in self.demos:
            if any(route.startswith(p) or p.startswith(route) for p in self.demos):raise ValueError('Overlapping demo routes')
            from sedrava_modules import expand
            from sedrava_webapp import parse_webapp,generate_webapp
            from sedrava_web_assets import attach
            expanded,modules=expand(data.decode(),path);doc=parse_webapp(expanded)
            generated=generate_webapp(doc,path.parent,modules);modules.update(attach(generated,doc.settings,path.parent))
            self.inputs.update(modules)
            if len(self.demos)>=16:raise ValueError('At most sixteen trusted demos')
            prefix=route.lstrip('/')
            source_path='sources/'+hashlib.sha256(data).hexdigest()+'.sdr';self.files[source_path]=data
            for name,value in generated.items():
                destination=prefix+name
                if destination in self.files:raise ValueError('Demo output collision')
                self.files[destination]=value
            self.demos[route]={'path':path,'source_sha256':hashlib.sha256(data).hexdigest(),'source_url':source_path,'app':doc.name,'files':{key:hashlib.sha256(value).hexdigest() for key,value in sorted(generated.items())}}
        demo=self.demos[route];src=rel(route.lstrip('/')+'index.html');label=props['label']
        trusted='Доверенный пример автора, общий origin; это не изоляция недоверенного кода.' if page.lang=='ru' else 'Trusted author code, shared origin; this is not isolation for untrusted programs.'
        return '<section class="doc-demo"'+(' id="'+html.escape(props['id'],quote=True)+'"' if 'id' in props else '')+' data-demo="'+html.escape(route,quote=True)+'" data-app="'+html.escape(demo['app'],quote=True)+'"><h2>'+html.escape(label)+'</h2><p class="demo-trust">'+trusted+'</p><div class="demo-toolbar"><button type="button" data-demo-reload>Reload / Перезагрузить</button><button type="button" data-demo-reset>Reset this demo / Сбросить пример</button><span role="status" data-demo-status></span></div><iframe src="'+src+'" title="'+html.escape(label,quote=True)+'" loading="lazy" referrerpolicy="no-referrer" allow="camera \'none\'; microphone \'none\'; geolocation \'none\'; payment \'none\'" class="demo-frame"></iframe>'+code_panel(data.decode(),'sedrava',props['src'],rel(demo['source_url']))+'</section>'
    def search(self,props):
        self.active=True
        return '<section class="doc-search" role="search"><label>'+html.escape(props['label'])+'<input type="search" data-doc-search autocomplete="off" maxlength="160"></label><p data-search-status role="status"></p><ul data-search-results></ul></section>'
    def head(self,page):
        if not self.active:return ''
        from site_codegen import relative
        return '<link rel="stylesheet" href="'+relative('docs.css',page)+'"><script src="'+relative('docs.js',page)+'" defer></script>'
    def finish(self):
        if not self.active:return
        from web_codegen import json_script
        # Deterministic in-memory index: works after load with the network disabled.
        grouped={}
        for entry in self.entries:
            if entry['url'] in grouped:
                grouped[entry['url']]['text']+='\n'+entry['text'];grouped[entry['url']]['headings'].extend(entry['headings'])
            else:grouped[entry['url']]=dict(entry,headings=entry['headings'][:])
        index=sorted(grouped.values(),key=lambda x:x['url'])
        raw=json.dumps(index,ensure_ascii=False,separators=(',',':'))
        if len(raw.encode())>2*1024*1024:raise ValueError('Documentation search index exceeds 2 MiB')
        self.files['docs.js']=('const documentationIndex=JSON.parse('+json_script(raw)+');\n'+JS).encode()
        self.files['docs.css']=CSS.encode()
        self.files['docs-index.json']=raw.encode()
        self.files['docs-demos.json']=(json.dumps({route:{key:value for key,value in demo.items() if key!='path'} for route,demo in sorted(self.demos.items())},sort_keys=True,indent=2)+'\n').encode()

CSS=r'''
.doc-markdown{min-width:0;line-height:1.8}.doc-markdown h2,.doc-markdown h3{line-height:1.25;margin-block:2.4rem 1rem;scroll-margin-top:6rem}.doc-markdown a,.doc-toc a,.doc-search a{color:var(--accent);text-underline-offset:.2em}.doc-markdown table{border-collapse:collapse;width:100%;display:block;overflow:auto}.doc-markdown td,.doc-markdown th{padding:10px;border:1px solid var(--border);text-align:start}.doc-markdown blockquote{border-inline-start:3px solid var(--gold);padding-inline-start:1rem;margin-inline:0}.doc-markdown :not(pre)>code{background:var(--surface);padding:.1em .3em;border-radius:4px;overflow-wrap:anywhere}
.doc-code{margin:1.5rem 0;min-width:0;border:1px solid var(--border);border-radius:14px;overflow:hidden;background:var(--surface)}.doc-code figcaption{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:12px 16px;font-size:.85rem;border-bottom:1px solid var(--border)}.code-scroll{overflow:auto;max-height:44rem}.code-table{display:grid;grid-template-columns:3.8rem max-content;min-width:100%;width:max-content}.doc-code pre.code-lines{position:sticky;left:0;padding-inline:8px;text-align:end;user-select:none;color:var(--muted);background:var(--surface);border-inline-end:1px solid var(--border)}.doc-code pre{margin:0;padding:18px;white-space:pre;font: .85rem/1.75 ui-monospace,Consolas,monospace;min-width:0}.doc-code code{font:inherit}.doc-code .k{color:#634294;font-weight:700}.doc-code .s{color:#216342}.doc-code .c,.doc-code .c1{color:#655d70}.doc-code .m{color:#8a4b06}.doc-code button,.demo-toolbar button{font:inherit;border:1px solid var(--border);border-radius:8px;padding:8px 12px;min-height:44px;background:var(--background);color:var(--foreground);cursor:pointer}.doc-code button:hover,.demo-toolbar button:hover{border-color:var(--accent)}button:focus-visible,input:focus-visible,pre:focus-visible{outline:3px solid var(--gold);outline-offset:3px}.demo-toolbar{display:flex;gap:12px;flex-wrap:wrap;margin-block:16px}.doc-demo{min-width:0;margin-block:2rem}.demo-frame{display:block;width:100%;height:640px;border:1px solid var(--border);border-radius:18px;background:var(--surface)}.demo-trust{font-size:.85rem;color:var(--muted)}.doc-search input{display:block;width:100%;padding:12px;font:inherit;border:1px solid var(--border);border-radius:10px;background:var(--surface);color:var(--foreground)}.doc-search ul{padding:0;list-style:none}.doc-search li{padding:12px 0;border-bottom:1px solid var(--border)}.doc-search a{display:block;font-weight:650}.doc-search .search-excerpt{display:block;font-weight:400;color:var(--muted);font-size:.9rem}.doc-toc{padding:16px;border:1px solid var(--border);border-radius:12px;margin-block:1rem 2rem}.doc-toc summary{cursor:pointer;font-weight:600}.doc-toc ul{padding-inline-start:20px}.s-sidebar summary{font-weight:700;cursor:pointer;min-height:44px}.s-sidebar a{display:block;padding:6px 0}@media(min-width:1000px){.s-sidebar summary{display:none}}.s-sidebar a[aria-current=page]{font-weight:750;color:var(--foreground);border-inline-start:3px solid var(--gold);padding-inline-start:10px}
@media(min-width:1200px){.doc-demo{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:16px}.doc-demo>h2,.doc-demo>.demo-trust,.doc-demo>.demo-toolbar{grid-column:1/-1}.doc-demo>.doc-code{margin:0}.doc-demo .code-scroll{max-height:640px}}
@media(max-width:599px){.demo-frame{height:620px}.code-table{grid-template-columns:3rem max-content}.doc-code pre{font-size:.78rem;padding:12px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
'''
JS=r'''
const scriptURL=new URL(document.currentScript.src),siteRoot=new URL('.',scriptURL);
for(const sidebar of document.querySelectorAll('details.s-sidebar'))if(matchMedia('(max-width: 999px)').matches)sidebar.open=false;
for(const panel of document.querySelectorAll('.doc-code')){
 const button=panel.querySelector('[data-copy]'),status=panel.querySelector('[data-copy-status]');
 button.addEventListener('click',async()=>{try{await navigator.clipboard.writeText(panel.querySelector('code').textContent);status.textContent='Copied / Скопировано';}catch(_){status.textContent='Copy unavailable; select the code / Выделите код';}});
}
for(const demo of document.querySelectorAll('[data-demo]')){
 const frame=demo.querySelector('iframe'),status=demo.querySelector('[data-demo-status]');let observer=null;
 const connect=()=>{observer?.disconnect();try{
  const document=frame.contentDocument;if(!document){status.textContent='Preview unavailable: unexpected origin';return;}if(document.URL==='about:blank')return;status.textContent='Loaded / Загружено';
  observer=new MutationObserver(records=>{if(records.some(record=>record.target.tagName==='DIALOG'&&record.target.open))frame.scrollIntoView({block:'center',behavior:'instant'});});
  observer.observe(document.documentElement,{attributes:true,attributeFilter:['open'],subtree:true});
 }catch(_){status.textContent='Preview unavailable: unexpected origin';}};
 frame.addEventListener('load',connect);window.addEventListener('pageshow',connect);connect();
 window.addEventListener('pagehide',()=>observer?.disconnect());
 demo.querySelector('[data-demo-reload]').addEventListener('click',()=>{try{const current=new URL(frame.contentWindow.location.href),expected=new URL(frame.src);if(current.origin!==location.origin||current.pathname!==expected.pathname)throw Error('unexpected demo location');frame.contentWindow.location.reload();}catch(_){status.textContent='Reload refused: unexpected demo origin/path';}});
 demo.querySelector('[data-demo-reset]').addEventListener('click',()=>{
  const url=new URL(frame.src);if(url.origin!==location.origin){status.textContent='Reset refused: wrong origin';return;}
  try{localStorage.removeItem('sedrava:'+url.pathname+':'+demo.dataset.app);
   const prefix='sedrava-api:'+url.pathname+':'+demo.dataset.app+':';for(const key of Object.keys(localStorage))if(key.startsWith(prefix))localStorage.removeItem(key);
   frame.contentWindow.location.replace(url.href);status.textContent='Reset / Сброшено';
  }catch(_){status.textContent='Storage reset failed / Ошибка хранилища';}
 });
}
for(const search of document.querySelectorAll('.doc-search')){
 const input=search.querySelector('input'),results=search.querySelector('ul'),status=search.querySelector('[role=status]');
 const fold=value=>value.normalize('NFKC').toLowerCase();
 input.addEventListener('input',()=>{
  const query=fold(input.value.trim()),terms=query.split(/\s+/);results.replaceChildren();if(!query){status.textContent='';return;}
  const matches=documentationIndex.map(entry=>({entry,hay:fold(entry.title+' '+entry.headings.join(' ')+' '+entry.text)})).filter(({hay})=>terms.every(term=>hay.includes(term))).slice(0,30);
  status.textContent=matches.length?String(matches.length)+' results / результатов':'No results / Ничего не найдено';
  for(const {entry} of matches){const li=document.createElement('li'),a=document.createElement('a'),excerpt=document.createElement('span');a.href=new URL(entry.url.replace(/^\//,''),siteRoot).href;a.textContent=entry.title+' · '+entry.lang;excerpt.className='search-excerpt';
   const index=Math.max(0,fold(entry.text).indexOf(terms[0])-45);excerpt.textContent=entry.text.slice(index,index+180);a.append(excerpt);li.append(a);results.append(li);}
 });
 search.addEventListener('keydown',event=>{const links=[...results.querySelectorAll('a')],index=links.indexOf(document.activeElement);
  if(event.key==='Escape'){input.value='';results.replaceChildren();status.textContent='';input.focus();event.preventDefault();}
  if(event.key==='ArrowDown'&&links.length){links[Math.min(index+1,links.length-1)].focus();event.preventDefault();}
  if(event.key==='ArrowUp'&&index>=0){(index===0?input:links[index-1]).focus();event.preventDefault();}
 });
}
'''
