"""Integration acceptance against generated Sedrava sources, never patched output."""
import functools
import json
import time
from urllib.parse import urlsplit
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sedrava_webapp import build_webapp
from playwright.sync_api import sync_playwright

class Quiet(SimpleHTTPRequestHandler):
    mode='normal';calls=[];rows=[{'id':1,'title':'A public product','available':True}]
    def reply(self,data,status=200):
        payload=(data if isinstance(data,str) else json.dumps(data)).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers()
        try:self.wfile.write(payload)
        except (BrokenPipeError,ConnectionResetError):pass
    def do_GET(self):
        if urlsplit(self.path).path!='/api/products':return super().do_GET()
        Quiet.calls.append(('GET',self.path,None))
        if Quiet.mode in ('slow','timeout'):time.sleep(.5 if Quiet.mode=='slow' else 1.5)
        if Quiet.mode=='error':return self.reply({'error':'unavailable'},500)
        if Quiet.mode=='invalid':return self.reply([{'id':True,'title':'bad','available':True}])
        if Quiet.mode=='duplicate':return self.reply('[{"id":1,"id":2,"title":"bad","available":true}]')
        if Quiet.mode=='large':return self.reply([{'id':1,'title':'x'*20000,'available':True}])
        return self.reply(Quiet.rows)
    def mutation(self):
        size=int(self.headers.get('Content-Length','0'));data=json.loads(self.rfile.read(size)) if size else None
        Quiet.calls.append((self.command,self.path,data))
        if self.command=='DELETE':Quiet.rows=[];return self.reply('',204)
        row={'id':1,**data};Quiet.rows=[row];return self.reply(row)
    do_POST=mutation
    do_PATCH=mutation
    do_PUT=mutation
    do_DELETE=mutation
    def log_message(self,*args):pass

class Platform(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory();cls.root=Path(cls.folder.name)
        source=ROOT/'examples/platform_tasks.sdr'
        build_webapp(source.read_text(),cls.root/'tasks',source)
        source=ROOT/'examples/platform_catalog.sdr'
        build_webapp(source.read_text(),cls.root/'catalog',source)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=cls.folder.name))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.driver=sync_playwright().start();cls.browser=cls.driver.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
        cls.evidence=ROOT/'build/platform-evidence';cls.evidence.mkdir(parents=True,exist_ok=True)
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.driver.stop();cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.folder.cleanup()
    def setUp(self):
        Quiet.mode='normal';Quiet.calls=[];Quiet.rows=[{'id':1,'title':'A public product','available':True}]
        self.context=self.browser.new_context();self.page=self.context.new_page();self.errors=[]
        self.context.on('page',lambda p:p.on('pageerror',lambda e:self.errors.append(str(e))))
        self.page.on('pageerror',lambda e:self.errors.append(str(e)))
        self.page.goto(self.url+'/tasks/index.html')
    def tearDown(self):
        self.context.close();self.assertEqual(self.errors,[])
    def add(self,title):
        self.page.get_by_label('New task',exact=True).fill(title);self.page.get_by_role('button',name='Add task',exact=True).click()
    def select(self,title):self.page.get_by_role('button',name='Select '+title,exact=True).click()
    def test_crud_routes_history_dialog_and_reload(self):
        p=self.page;self.add('First task');self.add('Second task');self.select('First task')
        p.get_by_role('button',name='Open selected task').click();self.assertTrue(p.url.endswith('#/tasks/1'))
        p.get_by_label('Rename selected task').fill('Renamed');p.get_by_role('button',name='Rename task',exact=True).click()
        p.get_by_role('button',name='Toggle completion').click();p.reload();self.assertTrue(p.url.endswith('#/tasks/1'))
        p.get_by_role('button',name='Back to tasks').click();p.wait_for_url('**#/')
        self.assertIn('Completed',p.get_by_role('button',name='Select Renamed',exact=True).inner_text())
        p.go_forward();p.wait_for_url('**#/tasks/1')
        p.get_by_role('button',name='Delete task',exact=True).click();self.assertTrue(p.locator('dialog').evaluate('e=>e.open'))
        p.keyboard.press('Escape');self.assertFalse(p.locator('dialog').evaluate('e=>e.open'))
        p.get_by_role('button',name='Delete task',exact=True).click();p.get_by_role('button',name='Confirm delete').click()
        p.wait_for_url('**#/');self.assertFalse(p.locator('dialog').evaluate('e=>e.open'))
        self.assertEqual(p.get_by_role('button',name='Select Renamed',exact=True).count(),0)
        p.goto(self.url+'/tasks/index.html#/tasks/999');self.assertIn('no longer exists',p.locator('#sedrava-error').inner_text())
    def test_search_filter_and_all_required_viewports(self):
        p=self.page;self.add('Alpha');self.add('Zulu');self.select('Zulu');p.get_by_role('button',name='Open selected task').click();p.get_by_role('button',name='Toggle completion').click();p.get_by_role('button',name='Back to tasks').click();p.wait_for_url('**#/')
        p.get_by_label('Search tasks').fill('ALP');self.assertEqual(p.locator('[data-list] button').count(),1)
        p.get_by_label('Search tasks').fill('');p.get_by_label('Filter by completion').check();p.get_by_label('Completion status',exact=True).select_option('true')
        self.assertEqual(p.locator('[data-list] button').count(),1);self.assertIn('Zulu',p.locator('[data-list]').inner_text())
        for width in (320,360,390,768,1024,1440):
            p.set_viewport_size({'width':width,'height':900})
            self.assertLessEqual(p.evaluate('document.documentElement.scrollWidth'),width+1)
            p.screenshot(path=str(self.evidence/f'tasks-{width}.png'),full_page=True)
        p.get_by_label('Search tasks').fill('missing');self.assertIn('No matching tasks',p.locator('[data-list]').inner_text())
        p.get_by_label('Search tasks').fill('');p.get_by_label('Filter by completion').uncheck()
        self.select('Alpha');p.get_by_role('button',name='Open selected task').click();p.get_by_role('button',name='Delete task',exact=True).click()
        p.screenshot(path=str(self.evidence/'tasks-dialog.png'),full_page=True)

    def test_real_http_methods_schema_limits_timeout_cancel_and_offline_cache(self):
        p=self.page;p.goto(self.url+'/catalog/index.html')
        panel=p.locator('[data-remote="catalog"]')
        panel.locator('[data-remote-status]').get_by_text('success',exact=True).wait_for()
        self.assertIn('A public product',panel.inner_text())
        for width in (320,360,390,768,1024,1440):
            p.set_viewport_size({'width':width,'height':900});self.assertLessEqual(p.evaluate('document.documentElement.scrollWidth'),width+1)
            p.screenshot(path=str(self.evidence/f'catalog-{width}.png'),full_page=True)
        for mode,text in [('invalid','Invalid integer'),('duplicate','Duplicate'),('large','byte limit'),('error','HTTP 500'),('timeout','timed out')]:
            Quiet.mode=mode;p.get_by_role('button',name='Refresh catalog',exact=True).click()
            panel.locator('[data-remote-status]').filter(has_text=text).wait_for()
            self.assertIn('A public product',panel.inner_text())
        p.screenshot(path=str(self.evidence/'catalog-error.png'),full_page=True)
        Quiet.mode='slow';p.get_by_role('button',name='Refresh catalog',exact=True).click()
        panel.locator('[data-remote-status]').get_by_text('loading',exact=True).wait_for()
        p.get_by_role('button',name='Cancel loading',exact=True).click()
        self.assertIn('cancelled',panel.locator('[data-remote-status]').inner_text())
        Quiet.mode='normal';p.get_by_role('button',name='Refresh catalog',exact=True).click()
        panel.locator('[data-remote-status]').get_by_text('success',exact=True).wait_for()
        p.get_by_role('button',name='Manage products',exact=True).click()
        p.get_by_label('Product name',exact=True).fill('<img src=x onerror=alert(1)>')
        for button,service in [('Create product','create_product'),('Update product','update_product'),('Replace product','replace_product')]:
            p.get_by_role('button',name=button,exact=True).click()
            result=p.locator('[data-remote="'+service+'"]');result.locator('[data-remote-status]').get_by_text('success',exact=True).wait_for()
            self.assertEqual(result.locator('img').count(),0);self.assertIn('<img src=x',result.inner_text())
        p.get_by_role('button',name='Delete product',exact=True).click()
        p.locator('[data-remote="delete_product"] [data-remote-status]').get_by_text('success',exact=True).wait_for()
        methods={method for method,_,_ in Quiet.calls};self.assertEqual(methods,{'GET','POST','PUT','PATCH','DELETE'})
        self.assertEqual(next(body for method,_,body in Quiet.calls if method=='POST')['title'],'<img src=x onerror=alert(1)>')
        p.get_by_role('button',name='Back to catalog',exact=True).click();p.wait_for_url('**#/')
        Quiet.mode='error';p.reload();self.assertIn('A public product',p.locator('[data-remote="catalog"]').inner_text())
        (self.evidence/'http-calls.json').write_text(json.dumps(Quiet.calls,indent=2))

if __name__=='__main__':unittest.main(verbosity=2)
