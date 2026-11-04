"""Real-browser acceptance of the compiler's optional documentation contract."""
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parents[1]/'tests')]
import functools
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import os,shutil,tempfile,threading,unittest
from playwright.sync_api import sync_playwright,expect
from test_native_docs import NativeDocs,SOURCE,COUNTER
from site_codegen import build_site
class Browser(unittest.TestCase):
    def test_search_embedded_counter_persistence_source_and_scoped_reset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);NativeDocs().fixture(root);build_site(SOURCE,root/'out',root/'site.sdr')
            handler=functools.partial(SimpleHTTPRequestHandler,directory=str(root/'out'))
            server=ThreadingHTTPServer(('127.0.0.1',0),handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with sync_playwright() as p:
                    engine=os.environ.get('SEDRAVA_BROWSER','chromium');options={'executable_path':shutil.which('chromium'),'args':['--no-sandbox']} if engine=='chromium' else {}
                    browser=getattr(p,engine).launch(**options);page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto('http://127.0.0.1:'+str(server.server_port)+'/');page.locator('iframe').scroll_into_view_if_needed();frame=page.frame_locator('iframe')
                    frame.get_by_role('button',name='Add',exact=True).click();self.assertEqual(frame.locator('output:visible').inner_text(),'1')
                    frame.locator('body').evaluate('()=>{window.originalHistoryReplace=history.replaceState;history.replaceState=()=>{throw Error("simulated history failure")};}')
                    frame.get_by_role('button',name='Details',exact=True).click()
                    expect(frame.locator('output:visible')).to_have_text('1')
                    expect(frame.locator('#sedrava-error')).to_contain_text('browser history rejected')
                    frame.locator('body').evaluate('()=>{history.replaceState=window.originalHistoryReplace;}')
                    frame.get_by_role('button',name='Details',exact=True).click()
                    with page.expect_event('framenavigated',predicate=lambda f:f.parent_frame is not None):page.get_by_role('button',name='Reload / Перезагрузить').click()
                    self.assertTrue(frame.get_by_role('heading',name='Details',exact=True).is_visible());self.assertEqual(frame.locator('output:visible').inner_text(),'2')
                    frame.get_by_role('button',name='Home',exact=True).click()
                    self.assertEqual(page.locator('.doc-demo code').text_content(),COUNTER)
                    page.evaluate('localStorage.setItem("unrelated","keep")');page.get_by_role('button',name='Reset this demo / Сбросить пример').click()
                    frame.get_by_role('button',name='Add',exact=True).wait_for();expect(frame.locator('output:visible')).to_have_text('0')
                    self.assertEqual(page.evaluate('localStorage.getItem("unrelated")'),'keep')
                    page.get_by_label('Search',exact=True).fill('ПРИВЕТ');self.assertEqual(page.locator('[data-search-results] a').count(),2)
                    page.get_by_label('Search',exact=True).press('ArrowDown');self.assertEqual(page.evaluate('document.activeElement.tagName'),'A')
                    page.keyboard.press('Escape');self.assertEqual(page.locator('[data-search-results] a').count(),0)
                    # Frame-owned routes must not consume the host page's Back history.
                    base='http://127.0.0.1:'+str(server.server_port)
                    page.goto(base+'/ru/');page.goto(base+'/');page.locator('iframe').scroll_into_view_if_needed()
                    frame.get_by_role('button',name='Details',exact=True).click()
                    page.go_back();self.assertTrue(page.url.endswith('/ru/'))
                    self.assertEqual(errors,[]);browser.close()
            finally:server.shutdown();server.server_close();thread.join()
if __name__=='__main__':unittest.main(verbosity=2)
