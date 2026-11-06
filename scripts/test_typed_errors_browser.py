"""Real generated UI actions, full snapshots, reload and rejected-storage retention."""
import functools,http.server,json,os,subprocess,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from core_conformance import reference
from sedrava_modules import expand
from playwright.sync_api import sync_playwright
folder=ROOT/'build/typed-errors-browser';folder.mkdir(parents=True,exist_ok=True)
fixtures=[(ROOT/'examples/typed_errors_012.sdr',['success','failure','details','adapt','rejected','success']),
          (ROOT/'examples/typed_errors_modules_012/main.sdr',['inspect','arithmetic.inspect'])]
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=folder));threading.Thread(target=server.serve_forever,daemon=True).start()
# A real error payload must remain text even when it contains HTML/script tokens.
hostile=folder/'hostile.sdr'
hostile.write_text((ROOT/'examples/typed_errors_012.sdr').read_text().replace('/offline.txt','</script><img src=x onerror=globalThis.pwned=true>'))
fixtures.append((hostile,['failure']))
engine=os.environ.get('SEDRAVA_BROWSER','chromium');results=[]
try:
 with sync_playwright() as pw:
    launch={'executable_path':'/usr/bin/chromium'} if engine=='chromium' and Path('/usr/bin/chromium').exists() else {}
    browser=getattr(pw,engine).launch(**launch)
    for index,(path,actions) in enumerate(fixtures):
        source,_=expand(path.read_text(),path)
        sequence=[getattr(source,'public_symbols',{}).get(a,a) for a in actions]
        expected=reference(source,sequence)
        from sedrava_core import parse
        program=parse(source)
        labels=[next(w[1] for w in program.widgets if w[0]=='button' and w[2]==a) for a in sequence]
        subprocess.run([sys.executable,str(ROOT/'sedrava_cli.py'),'build','web',str(path),'--output',str(folder/str(index)/'index.html')],check=True)
        page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f'http://127.0.0.1:{server.server_port}/{index}/index.html')
        page.keyboard.press('Tab');assert page.evaluate('document.activeElement.tagName')=='BUTTON'
        for label,outcome in zip(labels,expected):
            page.get_by_role('button',name=label,exact=True).click()
            assert page.evaluate('state')==outcome['state'],(index,label,outcome)
        assert page.evaluate('globalThis.pwned') is None
        assert page.locator('img').count()==0
        page.reload()
        # Only declared persistent fields survive; the entry module example has
        # nonpersistent local total and persistent imported total.
        restored={**program.states,**{k:expected[-1]['state'][k] for k in program.persistent}}
        from sedrava_records import plain
        assert page.evaluate('state')=={k:plain(v) for k,v in restored.items()}
        page.screenshot(path=str(folder/f'{engine}-{index}.png'),full_page=True)
        for raw in ('{broken',json.dumps({'schema':1,'signature':'wrong','state':{}})):
            page.evaluate('(raw)=>localStorage.setItem(storageKey,raw)',raw);page.reload()
            assert page.evaluate('restoreError') is True
            page.get_by_role('button',name=labels[0],exact=True).click()
            assert page.evaluate('localStorage.getItem(storageKey)')==raw
        assert not errors,errors
        results.append({'fixture':str(path.relative_to(ROOT)),'actions':len(actions),'full_state':True,'reload':True,'retained_rejected_storage':True,'pageerrors':errors})
        page.close()
    (folder/f'{engine}-results.json').write_text(json.dumps({'engine':engine,'version':browser.version,'results':results},indent=2)+'\n')
    browser.close()
 print('PASS',engine,'typed Result/match real UI, full snapshots and rejected storage')
finally:server.shutdown()
