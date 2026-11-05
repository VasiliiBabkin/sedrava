"""Real buttons, rollback, persistence and rejected-storage protection."""
import functools,http.server,json,os,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from playwright.sync_api import sync_playwright
from core_conformance import reference
from web_codegen import generate
from sedrava_core import parse
from sedrava_records import plain
source=(ROOT/'examples/bounded_values_012.sdr').read_text();folder=ROOT/'build/core-a2';folder.mkdir(parents=True,exist_ok=True)
(folder/'index.html').write_text(generate(source))
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=folder));threading.Thread(target=server.serve_forever,daemon=True).start()
sequence=['scan','order','fail_bounds','fail_sum','remove','add','add','seed_rows','delete_rows','normalize','fold','expected_error','clear','scan']
expected=reference(source,sequence);errors=[];engine=os.environ.get('SEDRAVA_BROWSER','chromium')
try:
 with sync_playwright() as pw:
    launch={}
    if engine=='chromium' and Path('/usr/bin/chromium').exists():launch['executable_path']='/usr/bin/chromium'
    browser=getattr(pw,engine).launch(**launch);page=browser.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:'+str(server.server_port));page.keyboard.press('Tab');assert page.evaluate('document.activeElement.tagName')=='BUTTON'
    for action,outcome in zip(sequence,expected):
        before=page.evaluate('state');page.locator('[data-action="'+action+'"]').click()
        assert page.evaluate('state')==outcome['state'],action
        if not outcome['accepted']:assert page.evaluate('state')==before,action
    page.reload();assert page.evaluate('state')==expected[-1]['state']
    # Rejected bytes must survive both reload and attempted mutations.
    for raw in ('{broken',json.dumps({'schema':1,'signature':'incompatible','state':{}})):
        page.evaluate('(raw)=>localStorage.setItem(storageKey,raw)',raw);page.reload()
        assert page.evaluate('restoreError') is True
        page.locator('[data-action="scan"]').click()
        assert page.evaluate('localStorage.getItem(storageKey)')==raw
    page.screenshot(path=str(folder/(engine+'.png')),full_page=True)
    assert not errors,errors
    browser.close()
 (folder/(engine+'-results.json')).write_text(json.dumps({'engine':engine,'actions':len(sequence),'full_state_equal':True,'reload':True,'protected_rejected_storage':True,'pageerrors':errors},indent=2))
 print('PASS',engine,len(sequence),'full-state UI transitions, reload, keyboard and rejected storage')
finally:server.shutdown()
