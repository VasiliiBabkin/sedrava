"""Real Chromium tests. Install playwright and its Chromium before running this file."""
import functools
import importlib.metadata
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from web_codegen import generate


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class BrowserAlpha(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory(prefix='sedrava web ')
        handler = functools.partial(QuietHandler, directory=cls.directory.name)
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.playwright = sync_playwright().start()
        executable = os.environ.get('SEDRAVA_CHROMIUM') or shutil.which('chromium')
        cls.browser = cls.playwright.chromium.launch(executable_path=executable, args=['--no-sandbox'])
        evidence=ROOT/'build/browser'
        evidence.mkdir(parents=True,exist_ok=True)
        (evidence/'toolchain.json').write_text(json.dumps({'engine':'chromium','browser_version':cls.browser.version,'playwright_version':importlib.metadata.version('playwright'),'executable_source':'configured/system' if executable else 'playwright-bundled'},sort_keys=True,indent=2)+'\n',encoding='utf-8')
        cls.counter = 0

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.directory.cleanup()

    def setUp(self):
        self.context = self.browser.new_context()
        self.context.tracing.start(screenshots=True, snapshots=True)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))

    def tearDown(self):
        output = ROOT / 'build/browser'
        output.mkdir(parents=True, exist_ok=True)
        self.context.tracing.stop(path=str(output / (self._testMethodName + '.zip')))
        self.context.close()
        self.assertEqual(self.errors, [], 'Unhandled browser exceptions')

    def open(self, source, storage=None):
        type(self).counter += 1
        name = f'app-{self.counter}.html'
        (Path(self.directory.name) / name).write_text(generate(source), encoding='utf-8')
        if storage is not None:
            import json
            self.context.add_init_script('localStorage.setItem("sedrava:" + location.pathname + ":Sedrava 0.9 Lab", ' + json.dumps(storage) + ');')
        self.page.goto(f'http://127.0.0.1:{self.server.server_port}/{name}')

    def state(self, name):
        return self.page.locator(f'output[data-state="{name}"]').inner_text()

    def test_stability_duplicate_scalar_editors_have_distinct_errors(self):
        source='app "Duplicate scalar editors"\nstate n = 0\nrule n >= 0\naction reset: n = 0\nscreen main:\n    input n\n    input n\n    button "Reset" -> reset\n'
        self.open(source)
        fields=self.page.locator('[data-input]')
        ids=[fields.nth(i).get_attribute('aria-describedby') for i in range(2)]
        self.assertEqual(len(set(ids)),2)
        fields.nth(1).fill('-1')
        self.assertTrue(self.page.locator('#'+ids[1]).is_visible())
        self.assertFalse(self.page.locator('#'+ids[0]).is_visible())

    def test_stability_rejected_snapshot_survives_edits_and_reload(self):
        for filename in ('task_manager.sdr','task_manager_navigation.sdr','text_profile.sdr'):
            self.open((ROOT/'examples'/filename).read_text(encoding='utf-8'))
            self.page.evaluate("localStorage.setItem(storageKey,'{broken')")
            self.page.reload()
            self.assertTrue(self.page.locator('#sedrava-error').is_visible())
            field=self.page.locator('[data-input]').first
            field.fill('new accepted draft')
            self.assertEqual(self.page.evaluate('localStorage.getItem(storageKey)'),'{broken')
            self.assertTrue(self.page.locator('#sedrava-error').is_visible())
            self.page.reload()
            self.assertEqual(self.page.evaluate('localStorage.getItem(storageKey)'),'{broken')

    def test_stability_schema_mismatch_is_not_destroyed_by_actions(self):
        self.open((ROOT/'examples/task_manager_navigation.sdr').read_text(encoding='utf-8'))
        self.page.get_by_label('New task',exact=True).fill('original task')
        self.page.get_by_role('button',name='Add task',exact=True).click()
        raw=self.page.evaluate("localStorage.getItem(storageKey).replace('\"schema\":1','\"schema\":2')")
        self.page.evaluate('(raw)=>localStorage.setItem(storageKey,raw)',raw)
        self.page.reload()
        self.page.get_by_label('New task',exact=True).fill('replacement')
        self.page.get_by_role('button',name='Add task',exact=True).click()
        self.assertEqual(self.page.evaluate('localStorage.getItem(storageKey)'),raw)
        self.assertIn('original task',raw)

    def test_readiness_invalid_draft_blocks_actions_and_recovers(self):
        self.open((ROOT/'examples/task_manager_navigation.sdr').read_text(encoding='utf-8'))
        page=self.page;field=page.get_by_label('New task',exact=True)
        field.fill('accepted');field.fill('😀'*1025)
        self.assertTrue(page.get_by_role('button',name='Add task',exact=True).is_disabled())
        self.assertEqual(page.evaluate('session.state.tasks.items.length'),0)
        self.assertTrue(page.get_by_role('alert').filter(has_text='Enter a valid').is_visible())
        field.fill('corrected');page.get_by_role('button',name='Add task',exact=True).click()
        page.get_by_role('button',name='Open corrected',exact=True).click()
        page.get_by_label('Task title',exact=True).fill('😀'*1025)
        self.assertTrue(page.get_by_role('button',name='Save title',exact=True).is_disabled())
        self.assertTrue(page.get_by_role('button',name='Back to tasks',exact=True).is_enabled())
        page.get_by_role('button',name='Back to tasks',exact=True).click()
        page.wait_for_function("session.stack.length===1 && !traversing")
        self.assertTrue(page.get_by_role('button',name='Add task',exact=True).is_enabled())
        self.assertEqual(page.evaluate('session.state.tasks.items[0].title'),'corrected')

    def test_readiness_large_fonts_long_content_and_status_description(self):
        source=(ROOT/'examples/task_manager_navigation.sdr').read_text(encoding='utf-8')
        self.open(source.replace('Daybook · Tasks','Задачи'+('X'*120)))
        page=self.page;page.set_viewport_size({'width':320,'height':640})
        page.add_style_tag(content=':root{font-size:200%}')
        title='LongTitle'+('a'*1015)
        page.get_by_label('New task',exact=True).fill(title)
        page.get_by_role('button',name='Add task',exact=True).click()
        button=page.get_by_role('button',name='Open '+title,exact=True)
        self.assertEqual(page.locator('#'+button.get_attribute('aria-describedby')).inner_text(),'In progress')
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),320)
        button.click();page.get_by_role('button',name='Toggle completion',exact=True).click()
        page.get_by_role('button',name='Back to tasks',exact=True).click()
        page.wait_for_function("session.stack.length===1 && !traversing")
        button=page.get_by_role('button',name='Open '+title,exact=True)
        self.assertEqual(page.locator('#'+button.get_attribute('aria-describedby')).inner_text(),'Completed')
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),320)
        self.assertFalse(self.errors,self.errors)

    def test_navigation_numeric_editing_and_additional_text(self):
        source='''app "Numeric pages"
state n = 0
derive positive = n > 0
screen main:
    text "One\\nTwo"
    text "Subtitle"
    text "More\\ntext"
    input n label "Count"
    value n
    show positive : text "Positive value"
    button "Next" -> open_page
screen other:
    text "Other"
    value n
    display n * n
    button "Back" -> previous
navigation:
    initial main
    action open_page -> other
    action previous -> pop
'''
        self.open(source);page=self.page;field=page.get_by_label('Count',exact=True)
        self.assertEqual(page.locator('h1').text_content(),'One\nTwo')
        self.assertEqual(page.get_by_text('More\ntext',exact=True).count(),1)
        self.assertEqual(page.locator('h1').evaluate('(el)=>getComputedStyle(el).whiteSpace'),'pre-wrap')
        native_editor=field.element_handle()
        field.fill('12');self.assertEqual(page.evaluate('session.state.n'),12)
        self.assertTrue(native_editor.evaluate('(el)=>el.isConnected'))
        self.assertTrue(page.get_by_text('Positive value',exact=True).is_visible())
        self.assertEqual(field.input_value(),'12');self.assertEqual(page.evaluate('document.activeElement.id'),field.get_attribute('id'))
        field.fill('1.5');self.assertEqual(field.get_attribute('aria-invalid'),'true');self.assertEqual(page.evaluate('session.state.n'),12)
        page.get_by_role('button',name='Next',exact=True).click()
        self.assertEqual(page.locator('main').get_attribute('data-screen'),'other')
        self.assertIn('n: 12',page.locator('main').inner_text())
        page.get_by_role('button',name='Back',exact=True).click()
        page.wait_for_function("document.querySelector('main').dataset.screen==='main' && !document.querySelector('main').inert")
        page.get_by_label('Count',exact=True).fill('-0')
        self.assertEqual(page.get_by_label('Count',exact=True).input_value(),'-0')
        page.get_by_label('Count',exact=True).press('End');page.get_by_label('Count',exact=True).press('1')
        self.assertEqual(page.evaluate('session.state.n'),-1)
        self.assertFalse(page.get_by_text('Positive value',exact=True).is_visible())
        self.assertEqual(page.get_by_label('Count',exact=True).input_value(),'-01')
        page.get_by_label('Count',exact=True).fill('2147483647')
        page.get_by_role('button',name='Next',exact=True).click()
        self.assertEqual(page.evaluate('session.state.n'),2147483647)
        self.assertIn('Unavailable',page.locator('main').inner_text())

    def test_navigation_repeated_screen_keeps_keyboard_focus(self):
        self.open((ROOT/'tests/fixtures/navigation_pages.sdr').read_text(encoding='utf-8'))
        page=self.page
        page.get_by_role('button',name='Next',exact=True).click()
        page.get_by_role('button',name='Again',exact=True).focus();page.keyboard.press('Enter')
        self.assertEqual(page.evaluate('session.stack'),['main','other','other'])
        self.assertEqual(page.evaluate('document.activeElement.tagName'),'H1')
        page.get_by_role('button',name='Back',exact=True).click()
        page.wait_for_function("session.stack.length===2 && !document.querySelector('main').inert")
        self.assertEqual(page.locator('main').get_attribute('data-screen'),'other')
        self.assertEqual(page.evaluate('document.activeElement.tagName'),'H1')

    def test_navigation_crud_browser_history_focus_and_reload(self):
        self.open((ROOT/'examples/task_manager_navigation.sdr').read_text(encoding='utf-8'))
        page=self.page
        self.assertEqual(page.locator('main').get_attribute('data-screen'),'main')
        page.get_by_label('New task',exact=True).fill('First 😀')
        page.get_by_role('button',name='Add task',exact=True).click()
        page.get_by_role('button',name='Open First 😀',exact=True).focus()
        page.keyboard.press('Enter')
        self.assertEqual(page.locator('main').get_attribute('data-screen'),'details')
        self.assertEqual(page.evaluate('document.activeElement.tagName'),'H1')
        self.assertEqual(page.get_by_label('Task title',exact=True).input_value(),'First 😀')
        page.get_by_label('Task title',exact=True).fill('Renamed')
        page.get_by_role('button',name='Save title',exact=True).click()
        page.get_by_role('button',name='Toggle completion',exact=True).click()
        self.assertIn('Completed',page.locator('main').inner_text())
        self.assertTrue(page.get_by_role('button',name='Toggle completion',exact=True).evaluate('(el)=>el===document.activeElement'))
        page.go_back()
        page.wait_for_function("document.querySelector('main').dataset.screen==='main'")
        self.assertEqual(page.evaluate('document.activeElement.tagName'),'H1')
        self.assertEqual(page.get_by_role('button',name='Open Renamed',exact=True).count(),1)
        page.go_forward()
        page.wait_for_function("document.querySelector('main').dataset.screen==='details'")
        self.assertEqual(page.get_by_label('Task title',exact=True).input_value(),'Renamed')
        page.get_by_role('button',name='Back to tasks',exact=True).click()
        page.wait_for_function("document.querySelector('main').dataset.screen==='main' && !document.querySelector('main').inert")
        page.get_by_role('button',name='Open Renamed',exact=True).click()
        page.get_by_role('button',name='Delete task',exact=True).click()
        page.wait_for_function("document.querySelector('main').dataset.screen==='main' && !document.querySelector('main').inert")
        self.assertEqual(page.locator('[data-list] li').count(),0)
        page.go_forward()
        page.wait_for_function("document.querySelector('main').dataset.screen==='main' && !document.querySelector('main').inert")
        self.assertEqual(page.locator('[data-list] li').count(),0)
        page.get_by_label('New task',exact=True).fill('Reload me')
        page.get_by_role('button',name='Add task',exact=True).click()
        page.get_by_role('button',name='Open Reload me',exact=True).click()
        page.reload()
        self.assertEqual(page.locator('main').get_attribute('data-screen'),'main')
        self.assertEqual(page.get_by_role('button',name='Open Reload me',exact=True).count(),1)
        self.assertEqual(page.evaluate('session.state.tasks.items[0].id'),2)

    def test_navigation_rejected_open_and_inputs_are_atomic(self):
        self.open((ROOT/'examples/task_manager_navigation.sdr').read_text(encoding='utf-8'))
        page=self.page
        self.assertFalse(page.evaluate("commitSession(dispatchSession(session,'open_details'),session)"))
        self.assertEqual(page.locator('main').get_attribute('data-screen'),'main')
        page.get_by_label('New task',exact=True).fill('one')
        page.get_by_role('button',name='Add task',exact=True).click()
        page.get_by_role('button',name='Open one',exact=True).click()
        field=page.get_by_label('Task title',exact=True)
        field.fill('')
        before=page.evaluate('JSON.stringify(session)')
        page.get_by_role('button',name='Save title',exact=True).click()
        self.assertEqual(page.evaluate('JSON.stringify(session)'),before)
        field.fill('😀'*1025)
        self.assertEqual(field.get_attribute('aria-invalid'),'true')
        self.assertEqual(page.evaluate('JSON.stringify(session)'),before)
        page.set_viewport_size({'width':375,'height':812})
        self.assertLessEqual(page.evaluate('document.documentElement.scrollWidth'),375)

    def test_records_task_manager_crud_reload_and_corruption(self):
        self.open((ROOT / 'examples/task_manager.sdr').read_text(encoding='utf-8'))
        page=self.page; field=page.locator('textarea'); rows=page.locator('[data-list] li')
        self.assertEqual(rows.count(),0)
        page.get_by_role('button',name='Add / Добавить',exact=True).click()
        self.assertFalse(page.locator('#sedrava-error').is_hidden())
        field.fill('Привет 😀'); page.get_by_role('button',name='Add / Добавить',exact=True).click()
        self.assertEqual(rows.count(),1);self.assertIn('Привет 😀',rows.inner_text())
        page.get_by_role('button',name='Select 1',exact=True).click()
        page.get_by_role('button',name='Complete / Выполнено',exact=True).click()
        self.assertIn('done: true',rows.inner_text())
        field.fill('renamed');page.get_by_role('button',name='Rename / Переименовать',exact=True).click()
        self.assertIn('title: renamed',rows.inner_text())
        page.reload();self.assertIn('title: renamed',rows.inner_text());self.assertIn('done: true',rows.inner_text())
        field.fill('second');page.get_by_role('button',name='Add / Добавить',exact=True).click()
        page.get_by_role('button',name='Select 1',exact=True).click();page.get_by_role('button',name='Delete / Удалить',exact=True).click()
        self.assertEqual(rows.count(),1);self.assertEqual(rows.get_attribute('data-id'),'2')
        page.get_by_role('button',name='Select 2',exact=True).click();page.get_by_role('button',name='Delete / Удалить',exact=True).click()
        self.assertEqual(rows.count(),0)
        page.evaluate("localStorage.setItem(storageKey, '{bad')");page.reload()
        self.assertEqual(rows.count(),0);self.assertIn('rejected',page.locator('#sedrava-error').inner_text())

    def test_records_capacity_invalid_input_and_atomicity(self):
        source=(ROOT / 'examples/task_manager.sdr').read_text(encoding='utf-8').replace('max=100','max=1')
        self.open(source);page=self.page;field=page.locator('textarea');rows=page.locator('[data-list] li')
        field.fill('one');page.get_by_role('button',name='Add / Добавить',exact=True).click()
        field.fill('two');before=page.evaluate('JSON.stringify(state)')
        page.get_by_role('button',name='Add / Добавить',exact=True).click()
        self.assertEqual(page.evaluate('JSON.stringify(state)'),before)
        self.assertEqual(rows.count(),1);self.assertFalse(page.locator('#sedrava-error').is_hidden())
        field.fill('😀'*1025);self.assertEqual(field.get_attribute('aria-invalid'),'true')
        self.assertEqual(page.evaluate('JSON.stringify(state)'),before)
        page.get_by_role('button',name='Delete / Удалить',exact=True).click()
        self.assertEqual(page.evaluate('JSON.stringify(state)'),before)
        page.reload();self.assertIn('title: one',rows.inner_text())

    def test_reference_input_constraints_and_reload(self):
        self.open((ROOT / 'examples/reference_09.sdr').read_text())
        self.assertEqual(self.state('goal'), '5')
        self.assertEqual(self.state('progress'), '0')
        field = self.page.locator('input')
        for raw in ('55', '-1', '2147483648', '1.5'):
            field.fill(raw)
            self.assertEqual(field.get_attribute('aria-invalid'), 'true')
            self.assertEqual(self.state('goal'), '5')
        field.fill('3')
        self.assertEqual(field.get_attribute('aria-invalid'), 'false')
        for _ in range(3):
            self.page.get_by_role('button', name='Add progress', exact=True).click()
        self.assertEqual(self.state('progress'), '3')
        self.assertTrue(self.page.get_by_text('Goal reached!', exact=True).is_visible())
        field.fill('2')
        self.assertEqual(self.state('goal'), '3')
        self.assertEqual(self.state('progress'), '3')
        field.fill('')
        self.page.locator('h1').first.click()
        self.assertEqual(field.input_value(), '3')
        self.page.reload()
        self.assertEqual(self.state('goal'), '3')
        self.assertEqual(self.state('progress'), '3')
        self.assertEqual(self.state('sessions'), '3')

    def test_corrupt_and_rule_invalid_storage(self):
        source = (ROOT / 'examples/reference_09.sdr').read_text()
        for saved in ('{broken', '{"goal":0,"progress":10}', '{"goal":2147483648}', 'null', '[1]', '{"goal":"oops"}'):
            self.open(source, saved)
            self.assertEqual(self.state('goal'), '5')
            self.assertEqual(self.state('progress'), '0')

    def test_overflow_action_is_atomic_and_visible(self):
        source = '''app "Overflow"
state n = 2147483647
state flag = false
action bad:
    flag = true
    n = n + 1
screen main:
    value n
    value flag
    button "Overflow" -> bad
'''
        self.open(source)
        self.page.get_by_role('button').click()
        self.assertEqual(self.state('n'), '2147483647')
        self.assertEqual(self.state('flag'), 'false')
        self.assertIn('overflow', self.page.locator('#sedrava-error').inner_text())

    def test_input_derived_overflow_is_rejected(self):
        self.open('''app "Derived input"
state n = 1
derive doubled = n * 2
screen main:
    input n
    value n
    value doubled
''')
        self.page.locator('input').fill('2147483647')
        self.assertEqual(self.state('n'), '1')
        self.assertEqual(self.page.locator('input').get_attribute('aria-invalid'), 'true')

    def test_html_script_injection_is_escaped(self):
        self.open('app "</script><script>globalThis.injected=true</script>"\nstate n = 0\nscreen main:\n    text "Safe"\n    value n\n')
        self.assertFalse(self.page.evaluate('globalThis.injected === true'))
        self.assertEqual(self.state('n'), '0')

    def test_prototype_identifier_and_signed_minimum(self):
        self.open('''app "Names"
state n = -2147483648
derive __proto__ = n + 1
screen main:
    value n
    value __proto__
''')
        self.assertEqual(self.state('n'), '-2147483648')
        self.assertEqual(self.state('__proto__'), '-2147483647')

    def test_all_ui_examples_launch_without_errors(self):
        from sedrava_frontend import parse_document
        from sedrava_site import Site
        from sedrava_webapp import WebApp
        for path in sorted((ROOT / 'examples').glob('*.sdr')):
            source = path.read_text()
            document=parse_document(source,path)
            if isinstance(document,(Site,WebApp)) or not hasattr(document, 'widgets'):
                continue # Site, WebApp and host documents have dedicated suites.
            if document.widgets:
                self.open(source)
                self.assertTrue(self.page.locator('body').is_visible())

    def test_text_profile_input_actions_and_reload(self):
        self.open((ROOT / 'examples/text_profile.sdr').read_text(encoding='utf-8'))
        field = self.page.locator('textarea')
        self.assertEqual(field.input_value(), 'Guest')
        self.assertEqual(self.state('name'), 'Guest')
        field.fill('Мария 😀')
        self.assertEqual(self.state('name'), 'Мария 😀')
        self.assertEqual(field.get_attribute('aria-invalid'), 'false')
        self.assertFalse(self.page.get_by_text('Choose your own name', exact=True).is_visible())
        self.page.reload()
        self.assertEqual(field.input_value(), 'Мария 😀')
        self.assertEqual(self.state('name'), 'Мария 😀')
        self.page.get_by_role('button', name='Rename to Алиса 😀', exact=True).click()
        self.assertEqual(self.state('name'), 'Алиса 😀')
        self.assertEqual(self.state('visits'), '1')
        self.assertEqual(self.state('saved'), 'true')
        self.page.get_by_role('button', name='Try rejected blank action', exact=True).click()
        self.assertEqual(self.state('name'), 'Алиса 😀')
        self.assertEqual(self.state('visits'), '1')
        self.assertEqual(self.state('saved'), 'true')
        self.assertTrue(self.page.locator('#sedrava-error').is_visible())
        self.page.reload()
        self.assertEqual(self.state('name'), 'Алиса 😀')
        self.assertEqual(self.state('visits'), '1')

    def test_text_blank_draft_error_and_correction(self):
        self.open((ROOT / 'examples/text_profile.sdr').read_text(encoding='utf-8'))
        field = self.page.locator('textarea')
        field.fill('')
        self.assertEqual(self.state('name'), 'Guest')
        self.assertEqual(field.get_attribute('aria-invalid'), 'true')
        self.assertTrue(self.page.locator('#error-name').is_visible())
        self.page.locator('h1').first.click()
        self.assertEqual(field.input_value(), '')
        field.fill('  exact whitespace  ')
        self.assertEqual(self.state('name'), '  exact whitespace  ')
        self.assertEqual(field.get_attribute('aria-invalid'), 'false')
        self.assertTrue(self.page.locator('#error-name').is_hidden())
        self.page.reload()
        self.assertEqual(field.input_value(), '  exact whitespace  ')

    def test_text_scalar_limit_and_unpaired_surrogate_input(self):
        self.open((ROOT / 'examples/text_profile.sdr').read_text(encoding='utf-8'))
        field = self.page.locator('textarea')
        for char in ('a', '😀'):
            field.fill(char * 1024)
            self.assertEqual(self.state('name'), char * 1024)
            self.page.reload()
            self.assertEqual(self.state('name'), char * 1024)
            field.fill(char * 1025)
            self.assertEqual(field.get_attribute('aria-invalid'), 'true')
            self.assertEqual(self.state('name'), char * 1024)
        for unit in (0xD800, 0xDFFF):
            self.page.evaluate("unit => { const el = document.querySelector('textarea'); el.value = String.fromCharCode(unit); el.dispatchEvent(new Event('input', {bubbles:true})); }", unit)
            self.assertEqual(field.get_attribute('aria-invalid'), 'true')
            self.assertEqual(self.state('name'), '😀' * 1024)
        field.fill('Corrected 😀')
        self.assertEqual(self.state('name'), 'Corrected 😀')
        self.assertEqual(field.get_attribute('aria-invalid'), 'false')

    def test_text_restore_malformed_snapshots(self):
        import json
        from sedrava_core import parse, restore_state
        source = (ROOT / 'examples/text_profile.sdr').read_text(encoding='utf-8')
        program = parse(source)
        self.open(source)
        values = [None, 1, True, [], {}, '', '😀' * 1025, '\ud800', '\udfff', '😀' * 1024, 'exact é']
        for value in values:
            saved = {'name': value, 'visits': 7, 'saved': True}
            self.page.evaluate("value => localStorage.setItem('sedrava:' + location.pathname + ':Text profile', value)", json.dumps(saved))
            self.page.reload()
            actual = self.page.evaluate('({...state})')
            self.assertEqual(actual, restore_state(program, saved))
        self.page.evaluate("localStorage.setItem('sedrava:' + location.pathname + ':Text profile', '{broken')")
        self.page.reload()
        self.assertEqual(self.page.evaluate('({...state})'), program.states)

    def test_text_is_rendered_as_data_and_not_normalized(self):
        self.open((ROOT / 'examples/text_profile.sdr').read_text(encoding='utf-8'))
        values = ['</script><script>globalThis.injected=true</script>', '${context} $name',
                  '<img src=x onerror="globalThis.injected=true">', 'a"quote" \\ path',
                  'true false', 'é', 'é', 'line1\nline2\t😀']
        for value in values:
            self.page.locator('textarea').fill(value)
            self.assertEqual(self.state('name'), value)
            self.page.reload()
            self.assertEqual(self.state('name'), value)
            self.assertFalse(self.page.evaluate('globalThis.injected === true'))
            self.assertEqual(self.page.locator('img').count(), 0)

    def test_text_empty_value_is_valid_without_a_nonempty_rule(self):
        self.open('app "Empty text"\nstate title = "seed"\npersist title\nscreen main:\n    input title\n    value title\n')
        field = self.page.locator('textarea')
        field.fill('')
        self.assertEqual(field.get_attribute('aria-invalid'), 'false')
        self.assertEqual(self.state('title'), '')
        self.page.reload()
        self.assertEqual(self.state('title'), '')

    def test_text_native_line_endings_and_model_scalar_equality(self):
        self.open((ROOT / 'examples/text_profile.sdr').read_text(encoding='utf-8'))
        # HTML textarea normalizes native draft line endings. The state model and
        # persisted/source strings themselves preserve scalar sequences, including CR.
        self.page.evaluate("() => { const el=document.querySelector('textarea'); el.value='a\\rb\\r\\nc'; el.dispatchEvent(new Event('input')); }")
        self.assertEqual(self.state('name'), 'a\nb\nc')
        self.assertEqual(self.page.evaluate("editState(state, 'name', 'a\\rb\\r\\nc').name"), 'a\rb\r\nc')

    def test_text_escaping_source_literals_and_labels(self):
        from sedrava_core import parse, transition
        source = (ROOT / 'tests/fixtures/text_escaping.sdr').read_text(encoding='utf-8')
        program = parse(source)
        expected, accepted = transition(program, program.states, 'escape')
        self.assertTrue(accepted)
        self.open(source)
        self.page.get_by_role('button', name='Escape "now" ${context}', exact=True).click()
        self.assertEqual(self.page.evaluate('({...state})'), expected)
        self.assertEqual(self.page.locator('output[data-state="echoed"]').text_content(), expected['title'])
        self.assertFalse(self.page.evaluate('globalThis.injected === true'))
        self.page.reload()
        self.assertEqual(self.page.evaluate('({...state})'), expected)


if __name__ == '__main__':
    unittest.main(verbosity=2)
