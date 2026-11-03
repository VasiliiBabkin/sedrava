"""Integration acceptance against generated Sedrava sources, never patched output."""
import functools
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
    def log_message(self,*args):pass

class Platform(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory();cls.root=Path(cls.folder.name)
        source=ROOT/'examples/platform_tasks.sdr'
        build_webapp(source.read_text(),cls.root/'tasks',source)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=cls.folder.name))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.driver=sync_playwright().start();cls.browser=cls.driver.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
        cls.evidence=ROOT/'build/platform-evidence';cls.evidence.mkdir(parents=True,exist_ok=True)
    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.driver.stop();cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.folder.cleanup()
    def setUp(self):
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

if __name__=='__main__':unittest.main(verbosity=2)
