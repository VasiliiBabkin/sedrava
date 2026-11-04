"""Actual same-origin old -> RC -> old Web storage transitions from installed wheels."""
import argparse,hashlib,json,os,shutil,subprocess,sys,threading,unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.test_platform_browser import Quiet
from playwright.sync_api import sync_playwright,expect
WORK=None
class Handler(Quiet):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(WORK/'generated'/args[2].phase),**kwargs)
    def end_headers(self):self.send_header('Cache-Control','no-store');super().end_headers()
class UpgradeBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.server.phase='clean-old-wheel';cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.pw=sync_playwright().start();cls.engine=os.environ.get('SEDRAVA_BROWSER','chromium');opts={}
        if cls.engine=='chromium' and shutil.which('chromium'):opts={'executable_path':shutil.which('chromium'),'args':['--no-sandbox']}
        cls.browser=getattr(cls.pw,cls.engine).launch(**opts);cls.base='http://127.0.0.1:'+str(cls.server.server_port);cls.observed=[];cls.evidence=WORK/('browser-'+cls.engine);cls.evidence.mkdir(exist_ok=True)
    @classmethod
    def tearDownClass(cls):
        (cls.evidence/'web-upgrade.json').write_text(json.dumps({'engine':cls.engine,'browser':cls.browser.version,'observations':cls.observed},ensure_ascii=False,indent=2)+'\n')
        cls.browser.close();cls.pw.stop();cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def setUp(self):
        self.context=self.browser.new_context();self.page=self.context.new_page();self.errors=[];self.page.on('pageerror',lambda e:self.errors.append(str(e)));self.context.tracing.start(screenshots=True,snapshots=True)
    def tearDown(self):
        self.context.tracing.stop(path=self.evidence/(self._testMethodName+'.zip'));self.context.close();self.assertEqual(self.errors,[])
    def goto(self,phase,app):
        self.server.phase=phase;response=self.page.goto(self.base+'/'+app+'/index.html');self.assertEqual(response.status,200)
    def stored(self,label):
        value=self.page.evaluate('Object.fromEntries(Object.entries(localStorage))');self.observed.append({'stage':label,'storage':value,'sha256':hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode()).hexdigest()});return value
    def seed(self):
        self.goto('clean-old-wheel','task_manager_navigation');self.page.get_by_label('New task',exact=True).fill('Сохранено 😀 é');self.page.get_by_role('button',name='Add task',exact=True).click()
        return self.stored('strict-old-seeded')
    def test_strict_navigation_update_edit_rollback_and_cold_reload(self):
        p=self.page;before=self.seed();self.goto('clean-rc-wheel','task_manager_navigation');expect(p.get_by_role('button',name='Open Сохранено 😀 é',exact=True)).to_be_visible();self.assertEqual(self.stored('strict-rc-restored'),before)
        p.get_by_role('button',name='Open Сохранено 😀 é',exact=True).click();p.get_by_label('Task title',exact=True).fill('Edited by RC 🦉');p.get_by_role('button',name='Save title',exact=True).click();p.get_by_role('button',name='Toggle completion',exact=True).click();changed=self.stored('strict-rc-edited')
        key=next(iter(changed));snapshot=json.loads(changed[key]);self.assertEqual(snapshot['state']['tasks'],{'next_id':2,'items':[{'id':1,'title':'Edited by RC 🦉','done':True}]})
        self.goto('in-place-rollback','task_manager_navigation');expect(p.get_by_role('button',name='Open Edited by RC 🦉',exact=True)).to_be_visible();self.assertEqual(self.stored('strict-old-rollback'),changed)
        p.reload();expect(p.get_by_role('button',name='Open Edited by RC 🦉',exact=True)).to_be_visible();self.assertEqual(self.stored('strict-old-cold'),changed)
        p.get_by_role('button',name='Open Edited by RC 🦉',exact=True).click();p.get_by_role('button',name='Delete task',exact=True).click();self.assertEqual(json.loads(self.stored('strict-old-delete')[key])['state']['tasks'],{'next_id':2,'items':[]});p.screenshot(path=self.evidence/'rollback-tasks.png')
    def test_legacy_unicode_scalar_update_and_rollback(self):
        p=self.page;self.goto('clean-old-wheel','text_profile');p.get_by_role('button',name='Rename to Алиса 😀',exact=True).click();before=self.stored('scalar-old-seeded')
        self.goto('clean-rc-wheel','text_profile');expect(p.locator('[data-state=name]')).to_have_text('Алиса 😀');self.assertEqual(self.stored('scalar-rc-restored'),before)
        p.get_by_role('button',name='Try rejected blank action',exact=True).click();self.assertEqual(self.stored('scalar-rc-rejected'),before)
        p.get_by_role('button',name='Rename to Алиса 😀',exact=True).click();after=self.stored('scalar-rc-edited');self.assertEqual(json.loads(next(iter(after.values()))),{'name':'Алиса 😀','visits':2,'saved':True})
        self.goto('in-place-rollback','text_profile');expect(p.locator('[data-state=visits]')).to_have_text('2');self.assertEqual(self.stored('scalar-old-rollback'),after)
    def test_corruption_and_incompatible_schema_preserve_original(self):
        p=self.page;valid=self.seed();key=next(iter(valid));snapshot=json.loads(valid[key])
        for label,raw in [('malformed','{broken'),('unknown-field',json.dumps({**snapshot,'fingerprint':'extra'})),('incompatible-signature',json.dumps({**snapshot,'signature':'incompatible'})),('duplicate','{"schema":1,"schema":2}')]:
            p.evaluate('([key,value])=>localStorage.setItem(key,value)',[key,raw]);self.goto('clean-rc-wheel','task_manager_navigation');expect(p.locator('#sedrava-error')).to_contain_text('Saved data could not be restored')
            p.get_by_label('New task',exact=True).fill('Must not overwrite');p.get_by_role('button',name='Add task',exact=True).click();self.assertEqual(self.stored(label+'-rc-locked')[key],raw)
            p.reload();expect(p.locator('#sedrava-error')).to_contain_text('Saved data could not be restored');self.assertEqual(self.stored(label+'-rc-restarted')[key],raw)
            self.goto('in-place-rollback','task_manager_navigation');expect(p.locator('#sedrava-error')).to_contain_text('Saved data could not be restored');self.assertEqual(self.stored(label+'-old-rollback')[key],raw)
        # Restore the actual backed-up bytes, never silently reset incompatible data.
        p.evaluate('([key,value])=>localStorage.setItem(key,value)',[key,valid[key]]);p.reload();expect(p.get_by_role('button',name='Open Сохранено 😀 é',exact=True)).to_be_visible();self.assertEqual(self.stored('backed-up-original-recovered'),valid)
        # A real recompiled source schema, not just a handcrafted invalid envelope.
        self.goto('incompatible-schema','task_manager_navigation');expect(p.locator('#sedrava-error')).to_contain_text('Saved data could not be restored')
        p.get_by_label('New task',exact=True).fill('Blocked schema write');p.get_by_role('button',name='Add task',exact=True).click();self.assertEqual(self.stored('capacity-100-to-99-rejected'),valid)
        self.goto('in-place-rollback','task_manager_navigation');expect(p.get_by_role('button',name='Open Сохранено 😀 é',exact=True)).to_be_visible();self.assertEqual(self.stored('capacity-rollback-recovered'),valid)
    def test_installed_candidate_new_web_examples(self):
        p=self.page;self.goto('clean-rc-wheel','platform_site');expect(p.get_by_role('heading',level=1)).to_be_visible()
        self.goto('clean-rc-wheel','platform_tasks');p.get_by_label('New task',exact=True).fill('Installed RC task');p.get_by_role('button',name='Add task',exact=True).click();expect(p.get_by_role('button',name='Select Installed RC task',exact=True)).to_be_visible();p.reload();expect(p.get_by_role('button',name='Select Installed RC task',exact=True)).to_be_visible()
        self.goto('clean-rc-wheel','platform_crm');expect(p.get_by_role('heading',level=1)).to_be_visible();p.get_by_role('button',name='Companies',exact=True).click();p.get_by_label('Company name',exact=True).fill('Installed Co');p.get_by_label('Industry',exact=True).fill('Testing');p.get_by_label('Industry',exact=True).press('Enter');expect(p.get_by_role('button',name='Select Installed Co',exact=True)).to_be_visible()
        Quiet.mode='normal';Quiet.rows=[{'id':1,'title':'A public product','available':True}];self.goto('clean-rc-wheel','platform_catalog');expect(p.get_by_text('A public product',exact=True)).to_be_visible();Quiet.mode='error';p.get_by_role('button',name='Refresh catalog',exact=True).click();expect(p.get_by_role('region',name='Product catalog').get_by_role('status').first).to_have_text('error: HTTP 500')
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--work',type=Path,required=True);args,extra=parser.parse_known_args();WORK=args.work.resolve();program=unittest.main(argv=[sys.argv[0],*extra],verbosity=2,exit=False)
    report=WORK/('browser-'+os.environ.get('SEDRAVA_BROWSER','chromium'))/'web-upgrade.json'
    data=json.loads(report.read_text()) if report.exists() else {}
    data.update({'status':'PASS' if program.result.wasSuccessful() else 'FAIL','tests':program.result.testsRun,'failures':len(program.result.failures),'errors':len(program.result.errors),'candidate_sha':json.loads((WORK/'upgrade-install.json').read_text())['candidate_sha']})
    report.parent.mkdir(exist_ok=True);report.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    raise SystemExit(0 if program.result.wasSuccessful() else 1)
