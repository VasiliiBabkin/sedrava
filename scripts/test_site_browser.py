"""Real static-site Chromium scenarios; no deployment or production-site access."""
import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from site_codegen import build_site

SOURCE=(ROOT/'examples/web_ui_011_landing.sdr').read_text(encoding='utf-8')

class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

class SiteBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix='sedrava-site-browser-')
        cls.root=Path(cls.folder.name)
        build_site(SOURCE,cls.root/'site',ROOT/'examples/web_ui_011_landing.sdr')
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=cls.folder.name))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.driver=sync_playwright().start()
        binary=os.environ.get('SEDRAVA_CHROMIUM') or shutil.which('chromium')
        cls.browser=cls.driver.chromium.launch(executable_path=binary,args=['--no-sandbox'])
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
        cls.evidence=ROOT/'build/site-evidence';cls.evidence.mkdir(parents=True,exist_ok=True)
        (cls.evidence/'toolchain.json').write_text(json.dumps({'chromium':cls.browser.version,'playwright':importlib.metadata.version('playwright')},indent=2)+'\n')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close();cls.driver.stop();cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.folder.cleanup()

    def setUp(self):
        self.context=self.browser.new_context();self.context.tracing.start(screenshots=True,snapshots=True)
        self.page=self.context.new_page();self.errors=[]
        self.page.on('pageerror',lambda e:self.errors.append(str(e)))
        self.page.on('response',lambda r:self.errors.append(str(r.status)+' '+r.url) if r.status>=400 else None)

    def tearDown(self):
        self.context.tracing.stop(path=str(self.evidence/(self._testMethodName+'.zip')))
        self.context.close();self.assertEqual(self.errors,[])

    def open(self,path='/site/index.html',width=1440):
        self.page.set_viewport_size({'width':width,'height':900})
        self.page.goto(self.url+path);self.page.evaluate('document.fonts.ready')
        self.page.wait_for_function('Array.from(document.images).every(i=>i.complete&&i.naturalWidth>0)')

    def no_overflow(self):
        size=self.page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})')
        self.assertLessEqual(size['scroll'],size['width']+1)
        overflow=self.page.locator('main *').evaluate_all('(els)=>els.filter(el=>el.getBoundingClientRect().right>innerWidth+1||el.getBoundingClientRect().left < -1).map(e=>({tag:e.tagName,cls:e.className}))')
        self.assertEqual(overflow,[])

    def test_responsive_landing_and_gallery_screenshots(self):
        for width in (360,768,1440):
            for path,label in (('/site/index.html','landing'),('/site/components/index.html','components')):
                self.open(path,width);self.no_overflow()
                self.page.screenshot(path=str(self.evidence/(label+'-'+str(width)+'.png')),full_page=True)
                self.assertEqual(self.page.locator('h1').count(),1)
                self.assertEqual(self.page.locator('main').count(),1)
                self.assertEqual(self.page.locator('script').count(),0)

    def test_slice_b_landmarks_and_code_no_overflow(self):
        for width in (360,768,1440):
            self.open(width=width)
            self.no_overflow()
            self.assertEqual(self.page.locator('nav[aria-label="Primary navigation"]').count(),1)
            self.assertEqual(self.page.locator('footer[aria-label="Site footer"]').count(),1)
            self.assertTrue(self.page.evaluate(
                'document.querySelector("nav").compareDocumentPosition(document.querySelector("main")) & Node.DOCUMENT_POSITION_FOLLOWING'))
            self.open('/site/components/index.html',width=width)
            self.no_overflow()
            self.assertEqual(self.page.locator('aside.s-callout').count(),1)
            self.assertEqual(self.page.locator('pre.s-code code').count(),1)
            code=self.page.locator('pre.s-code code')
            self.assertIn('persist value',code.inner_text())
            self.assertEqual(self.page.locator('script').count(),0)
            self.assertEqual(self.page.locator('pre.s-code script').count(),0)

    def test_grid_breakpoints_and_property_override(self):
        for width,expected in ((360,(1,1)),(768,(1,2)),(1440,(2,3))):
            self.open(width=width)
            counts=self.page.locator('.s-grid').evaluate_all('(els)=>els.map(e=>getComputedStyle(e).gridTemplateColumns.split(" ").length)')
            self.assertEqual(counts,list(expected))
            self.assertEqual(self.page.locator('.s-card h2').first.evaluate('e=>getComputedStyle(e).fontSize'),'26px')

        source='site "Typography"\npage home at "/":\n    title "Typography"\n    heading "Title"\n    heading "Default section" level 2\n    heading "Display section" level 2 variant display\n'
        file=self.root/'typography.sdr';file.write_text(source)
        build_site(source,self.root/'typography',file)
        self.open('/typography/index.html',1440)
        sizes=self.page.locator('h2').evaluate_all('els=>els.map(e=>parseFloat(getComputedStyle(e).fontSize))')
        self.assertGreater(sizes[1],sizes[0])

    def test_keyboard_skip_focus_and_enter_navigation(self):
        self.open(width=360)
        self.page.keyboard.press('Tab')
        self.assertEqual(self.page.evaluate('document.activeElement.textContent'),'Skip to content')
        self.page.keyboard.press('Enter')
        self.assertEqual(self.page.evaluate('document.activeElement.id'),'content')
        target='Explore the primitives →'
        for _ in range(20):
            self.page.keyboard.press('Tab')
            if self.page.evaluate('document.activeElement.textContent')==target:break
        self.assertEqual(self.page.evaluate('document.activeElement.textContent'),target)
        self.assertEqual(self.page.evaluate('getComputedStyle(document.activeElement).outlineStyle'),'solid')
        self.page.screenshot(path=str(self.evidence/'keyboard-focus.png'))
        self.page.keyboard.press('Enter');self.page.wait_for_url('**/components/index.html')
        self.assertIn('A small vocabulary.',self.page.locator('h1').inner_text())
        self.page.go_back();self.assertTrue(self.page.url.endswith('index.html#content'))
        self.page.go_forward();self.assertTrue(self.page.url.endswith('/components/index.html'))

    def test_reduced_motion_no_animation_or_hover_transform(self):
        self.page.emulate_media(reduced_motion='reduce');self.open()
        link=self.page.locator('.s-button').first;link.hover()
        state=link.evaluate('e=>({transition:getComputedStyle(e).transitionDuration,transform:getComputedStyle(e).transform,scroll:getComputedStyle(document.documentElement).scrollBehavior})')
        self.assertEqual(state,{'transition':'0s','transform':'none','scroll':'auto'})

    def test_semantics_alt_labels_and_no_external_resource_requests(self):
        requests=[];self.page.on('request',lambda r:requests.append(r.url));self.open()
        self.assertTrue(all(url.startswith(self.url) for url in requests))
        self.assertEqual(self.page.locator('img:not([alt])').count(),0)
        self.assertEqual(self.page.locator('button').count(),0) # Static navigation is honest anchors.
        for name in self.page.locator('a').all_text_contents():self.assertTrue(name.strip())
        (self.evidence/'accessibility-home.txt').write_text(self.page.locator('body').aria_snapshot(),encoding='utf-8')

    def test_long_unbroken_unicode_text_and_safe_markup(self):
        source='site "Escaping"\npage home at "/":\n    title "Escaping"\n    heading "Long text"\n    paragraph "'+'x'*1024+'"\n    paragraph "<script>alert(1)</script> <img src=x onerror=alert(1)> é 😀"\n'
        file=self.root/'escaped.sdr';file.write_text(source)
        build_site(source,self.root/'escaped',file)
        for width in (360,768,1440):
            self.open('/escaped/index.html',width);self.no_overflow()
            self.assertEqual(self.page.locator('script,img').count(),0)
            self.assertIn('<script>alert(1)</script>',self.page.locator('body').inner_text())

    def test_default_text_contrast(self):
        self.open()
        pairs=self.page.locator('main :is(h1,h2,p,a)').evaluate_all('els=>els.map(el=>{let bg="rgba(0, 0, 0, 0)",p=el;while(p&&bg==="rgba(0, 0, 0, 0)"){bg=getComputedStyle(p).backgroundColor;p=p.parentElement;}return [getComputedStyle(el).color,bg]})')
        def luminance(color):
            import re
            rgb=[int(n)/255 for n in re.findall(r'\d+',color)[:3]]
            values=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb]
            return sum(v*w for v,w in zip(values,(.2126,.7152,.0722)))
        ratios=[]
        for fg,bg in pairs:
            first,second=sorted((luminance(fg),luminance(bg)))
            ratios.append((second+.05)/(first+.05))
        self.assertGreaterEqual(min(ratios),4.5)
        (self.evidence/'contrast.json').write_text(json.dumps({'minimum_text_ratio':min(ratios),'checked_pairs':len(ratios)},indent=2)+'\n')

if __name__=='__main__':unittest.main(verbosity=2)
