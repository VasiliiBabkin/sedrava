"""Actual compiled modular app + WebApp transitions, persistence and lock gates."""
import functools,http.server,json,os,sys,subprocess,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from sedrava_modules import expand
from sedrava_core import parse
from core_conformance import reference
folder=ROOT/'build/namespace-core';folder.mkdir(parents=True,exist_ok=True)
source_path=ROOT/'examples/modules_core_012/main.sdr';source=expand(source_path.read_text(),source_path)[0];program=parse(source)
labels=['scan','add','add','expected','seed','audit','reject'];sequence=[next(k for k in program.actions if k.endswith('_'+label)) for label in labels];expected=reference(source,sequence)
subprocess.run([sys.executable,'-m','sedrava_cli','build','web',str(source_path),'--output',str(folder/'app/index.html')],check=True,cwd=ROOT)
subprocess.run([sys.executable,'-m','sedrava_cli','build','webapp',str(source_path.with_name('site.sdr')),'--output',str(folder/'webapp')],check=True,cwd=ROOT)
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=folder));threading.Thread(target=server.serve_forever,daemon=True).start()
engine=os.environ.get('SEDRAVA_BROWSER','chromium');results=[]
try:
 with sync_playwright() as pw:
    launch={}
    if engine=='chromium' and Path('/usr/bin/chromium').exists():launch['executable_path']='/usr/bin/chromium'
    browser=getattr(pw,engine).launch(**launch)
    for mode in ('app','webapp'):
        page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:'+str(server.server_port)+'/'+mode+'/index.html');page.keyboard.press('Tab');assert page.evaluate('document.activeElement.tagName')=='BUTTON'
        for label,outcome in zip(labels,expected):
            page.get_by_role('button',name=label,exact=True).click();assert page.evaluate('state')==outcome['state'],(mode,label)
        page.reload();assert page.evaluate('state')==expected[-1]['state']
        page.screenshot(path=str(folder/(engine+'-'+mode+'.png')),full_page=True)
        for raw in ('{broken',json.dumps({'schema':1,'signature':'wrong','state':{}})):
            page.evaluate('(raw)=>localStorage.setItem(storageKey,raw)',raw);page.reload();assert page.evaluate('restoreError') is True
            page.get_by_role('button',name='scan',exact=True).click();assert page.evaluate('localStorage.getItem(storageKey)')==raw
        assert not errors,errors;results.append({'mode':mode,'actions':len(labels),'complete_state':True,'restore':True,'rejected_store_retained':True,'pageerrors':errors});page.close()
    (folder/(engine+'-results.json')).write_text(json.dumps({'engine':engine,'browser_version':browser.version,'results':results},indent=2));browser.close()
 print('PASS',engine,'modular app and WebApp, complete-state traces/reload/rejected storage')
finally:server.shutdown()
