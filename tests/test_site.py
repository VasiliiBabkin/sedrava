"""Site-mode grammar, registry, resource safety and transactional build regressions."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from sedrava_frontend import parse_document
from sedrava_core import parse as parse_app
from sedrava_site import Site, COMPONENTS, Definition, Parameter, text, parse_site, resolved, walk
from sedrava_cli import main
from site_codegen import generate_site, build_site, validate_image

ROOT=Path(__file__).resolve().parents[1]
TINY='site "Test"\npage home at "/":\n    title "Title"\n    heading "Hello"\n'

class SiteTests(unittest.TestCase):
    def bad(self,source,message=None):
        with self.assertRaisesRegex(ValueError,message or r'Line \d+: column \d+:'):
            parse_site(source)

    def test_shared_frontend_and_legacy_mode_boundary(self):
        self.assertIsInstance(parse_document(TINY),Site)
        self.assertEqual(parse_document('app "Old"\nstate n=0\n').states,{'n':0})
        with self.assertRaisesRegex(ValueError,'build site'):parse_app(TINY)

    def test_landing_all_components_real_assets_and_routes(self):
        source=(ROOT/'examples/web_ui_011_landing.sdr').read_text()
        site=parse_site(source)
        used={n.kind for p in site.pages for n in walk(p.children)}
        self.assertEqual(used,set(COMPONENTS))
        files,inputs=generate_site(site,ROOT/'examples')
        self.assertIn('components/index.html',files);self.assertIn('site.css',files)
        self.assertEqual(len(inputs),1)
        self.assertEqual(len([n for n in files if n.startswith('assets/')]),1)
        home=files['index.html'].decode();gallery=files['components/index.html'].decode()
        self.assertIn('href="components/index.html"',home)
        self.assertIn('href="../site.css"',gallery)
        self.assertIn('href="../index.html"',gallery)
        self.assertNotIn('<script',home)

    def test_slice_b_landmarks_code_and_escaping(self):
        source=('site "Sample"\npage home at "/":\n    title "Sample"\n'
                '    navbar label "Main & links":\n'
                '        link "Home" to "/"\n'
                '    heading "Welcome"\n'
                '    callout variant warning:\n'
                '        paragraph "Be careful"\n'
                '    code "<script>alert(1)</script>\\nstate x = 0"\n'
                '    footer:\n'
                '        paragraph "End"\n')
        data,_=generate_site(source)
        html=data['index.html'].decode('utf-8')
        self.assertIn('<nav ',html)
        self.assertIn('aria-label="Main &amp; links"',html)
        self.assertIn('<aside ',html)
        self.assertIn('v-warning',html)
        self.assertIn('<pre ',html)
        self.assertIn('<code>&lt;script&gt;alert(1)&lt;/script&gt;',html)
        self.assertNotIn('<script>alert(1)',html)
        self.assertLess(html.index('</nav>'),html.index('<main '))
        self.assertLess(html.index('</main>'),html.index('<footer '))
        self.assertIn('.s-code code{font:inherit',data['site.css'].decode())
        self.assertNotIn('alert(1)',data['site.css'].decode())

    def test_slice_b_landmark_order_and_required_code(self):
        self.bad(TINY+'    navbar:\n        link "x" to "/"\n', 'first top-level')
        self.bad(TINY+'    footer:\n        paragraph "end"\n    paragraph "late"\n', 'last top-level')
        self.bad('site "x"\npage home at "/":\n    title "x"\n'
                 '    navbar:\n        link "x" to "/"\n'
                 '    navbar:\n        link "x" to "/"\n'
                 '    heading "Hello"\n', 'first top-level|Only one')
        self.bad(TINY+'    column:\n        navbar:\n            link "x" to "/"\n', 'top-level')
        self.bad(TINY+'    code ""\n', 'Accessible text')
        self.bad(TINY+'    code "state" onclick "evil"\n', 'Unknown parameter')
        self.bad(TINY+'    callout variant danger:\n        paragraph "x"\n', 'Expected one of')

    def test_unknown_component_property_duplicate_and_indentation(self):
        for line in ('    html "bad"','    paragraph "x" onclick "evil"','    paragraph "x" gap 1 gap 2','    heading "x":','      paragraph "x"','\tparagraph "x"','    column:'):
            self.bad(TINY+line+'\n',r'Line \d+:')
        self.bad(TINY.replace('Hello','bad\\q'))
        self.bad(TINY.replace('Hello','\ud800'))
        self.bad(TINY+'    paragraph "x" md-variant lead\n')

    def test_required_fields_and_accessible_names(self):
        for line in ('    image "x.svg"','    link "Go"','    button " " to "/"','    heading " "'):
            self.bad(TINY+line+'\n')
        self.bad(TINY.replace('    title "Title"\n',''))
        self.bad(TINY.replace('    heading "Hello"\n','    paragraph "No heading"\n'))
        self.bad(TINY+'    heading "Another" level 1\n')
        self.bad(TINY+'    heading "Jump" level 4\n')

    def test_safe_urls_and_control_rejection(self):
        for url in ('javascript:alert(1)','JaVaScRiPt:alert(1)','data:text/html,bad','file:///tmp/a','//evil.example/a','/../secret/','/%2e%2e/secret/','https://user:pass@example.com/','https://example.com/\\x','java%73cript:alert(1)','mailto:x@example.com?subject=test','https://[broken','https://example.com/%0a'):
            source=TINY+'    link "Go" to '+json.dumps(url)+'\n'
            self.bad(source)
        self.bad(TINY+'    paragraph "a\x00b"\n')
        for url in ('https://example.com/?a=1&b=2','http://localhost:8080/','mailto:hello@example.com','tel:+12025550123','#content'):
            parse_site(TINY+'    link "Go" to '+json.dumps(url)+'\n')

    def test_theme_and_css_parameters_are_typed(self):
        for prop in ('color "red; background: url(x)"','padding "20"','gap -1','width true','size 999','text-align diagonal','background "var(--bad)"'):
            self.bad(TINY+'    paragraph "x" '+prop+'\n')
        self.bad(TINY.replace('page home','theme:\n    accent "blue"\npage home'))
        self.bad(TINY.replace('page home','theme:\n    accent "#fff"\n    accent "#000"\npage home'))
        source=TINY.replace('page home','theme:\n    accent "#ABC"\npage home')
        self.assertEqual(parse_site(source).theme['accent'],'#aabbcc')

    def test_named_style_precedence_and_breakpoint_schema(self):
        source=TINY.replace('page home','style wide:\n    gap 12\n    md-gap 24\npage home')+'    column style wide gap 8:\n        paragraph "x"\n'
        site=parse_site(source);node=site.pages[0].children[-1]
        self.assertEqual(resolved(node,site)['gap'],8)
        self.assertEqual(resolved(node,site)['md-gap'],24)
        self.bad(TINY+'    paragraph "x" style missing\n')
        self.bad(TINY.replace('page home','style bad:\n    columns 2\npage home')+'    paragraph "x" style bad\n')

    def test_page_id_anchor_and_path_validation(self):
        for line in ('    paragraph "x" id content','    link "Go" to "#unknown"','    link "Go" to "/missing/"'):
            self.bad(TINY+line+'\n')
        self.bad(TINY+'    paragraph "x" id same\n    paragraph "y" id same\n')
        for path in ('/../','/docs','/a%20/','/a//','https://example.com/'):
            self.bad(TINY.replace('at "/"', 'at '+json.dumps(path)))
        self.bad(TINY+'page home at "/":\n    title "dup"\n    heading "dup"\n')

    def test_registry_extension_needs_no_parser_or_renderer_branch(self):
        definition=Definition('span',positional='text',required=('text',),parameters={'text':Parameter(text)})
        with patch.dict(COMPONENTS,{'badge':definition}):
            files,_=generate_site(TINY+'    badge "New primitive" color gold\n')
            self.assertIn('<span ',files['index.html'].decode())
            self.assertIn('New primitive</span>',files['index.html'].decode())

    def test_escaping_text_attributes_and_no_user_css(self):
        source=TINY+'    paragraph "<script>alert(1)</script>"\n    link "Go" to "https://example.com/?a=1&b=2" target blank label "A \\"quote\\""\n'
        files,_=generate_site(source)
        self.assertNotIn('<script',files['index.html'].decode())
        self.assertIn('&lt;script&gt;',files['index.html'].decode())
        self.assertIn('a=1&amp;b=2',files['index.html'].decode())
        self.assertIn('rel="noopener noreferrer"',files['index.html'].decode())
        self.assertNotIn('alert(',files['site.css'].decode())

    def test_resource_bounds_not_component_count_limit(self):
        parse_site(TINY+'    paragraph "x"\n'*600)
        self.bad('x'*100001,'Source exceeds')
        deep=TINY+'\n'.join('    '*i+'column:' for i in range(1,40))+'\n'+'    '*40+'paragraph "x"\n'
        self.bad(deep)

    def test_safe_svg_boundary_and_signatures(self):
        good=b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><path d="M0 0L10 10" stroke="#fff"/></svg>'
        validate_image(good,'.svg')
        bads=[good.replace(b'<path',b'<script'),good.replace(b'stroke=',b'onload='),good.replace(b'#fff',b'url(https://example.com/x)'),good.replace(b'#fff',b'u\\72l(x)'),b'<!DOCTYPE svg>'+good,b'<?xml-stylesheet href="x"?>'+good, ('<!DOCTYPE svg [<!ENTITY x "expanded">]><svg xmlns="http://www.w3.org/2000/svg"><text>&x;</text></svg>').encode('utf-16')]
        for data in bads:
            with self.subTest(data=data),self.assertRaises(ValueError):validate_image(data,'.svg')
        for suffix in ('.html','.js','.png','.webp','.jpg'):
            with self.assertRaises(ValueError):validate_image(b'not an image',suffix)

    def test_asset_missing_outside_symlink_and_size_do_not_touch_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'app.sdr';source.write_text(TINY)
            output=root/'out';build_site(TINY,output,source);before=self.snapshot(output)
            for src in ('missing.svg','../outside.svg'):
                bad=TINY+'    image '+json.dumps(src)+' alt "x"\n'
                with self.assertRaises(ValueError):build_site(bad,output,source)
                self.assertEqual(before,self.snapshot(output))
            (root/'huge.svg').write_bytes(b' '* (2*1024*1024+1))
            with self.assertRaises(ValueError):build_site(TINY+'    image "huge.svg" alt "x"\n',output,source)
            with tempfile.TemporaryDirectory() as outside:
                target=Path(outside)/'x.svg';target.write_text('<svg/>')
                (root/'link.svg').symlink_to(target)
                with self.assertRaises(ValueError):build_site(TINY+'    image "link.svg" alt "x"\n',output,source)

    def snapshot(self,root):return {p.relative_to(root).as_posix():p.read_bytes() for p in root.rglob('*') if p.is_file()}

    def test_build_determinism_and_managed_rebuild(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.sdr';source.write_text(TINY)
            for name in ('a','b'):build_site(TINY,root/name,source)
            self.assertEqual(self.snapshot(root/'a'),self.snapshot(root/'b'))
            before=self.snapshot(root/'a');build_site(TINY,root/'a',source)
            self.assertEqual(before,self.snapshot(root/'a'))
            changed=TINY.replace('Hello','Changed');build_site(changed,root/'a',source)
            self.assertIn(b'Changed',(root/'a/index.html').read_bytes())

    def test_unmanaged_modified_output_and_source_overlap_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.sdr';source.write_text(TINY);out=root/'out';out.mkdir();(out/'own.txt').write_text('mine')
            with self.assertRaisesRegex(ValueError,'unmanaged'):build_site(TINY,out,source)
            self.assertEqual((out/'own.txt').read_text(),'mine')
            with self.assertRaisesRegex(ValueError,'contain the source'):build_site(TINY,root,source)
            (out/'own.txt').unlink();build_site(TINY,out,source);(out/'site.css').write_text('edited')
            with self.assertRaisesRegex(ValueError,'modified'):build_site(TINY,out,source)
            self.assertEqual((out/'site.css').read_text(),'edited')

    def test_publish_failure_rolls_back_complete_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);src=root/'source.sdr';src.write_text(TINY);out=root/'out';build_site(TINY,out,src);before=self.snapshot(out)
            import os
            replace=os.replace;calls=0
            def fail_once(a,b):
                nonlocal calls
                calls+=1
                if calls==2:raise OSError('simulated directory rename failure')
                return replace(a,b)
            with patch('site_codegen.os.replace',side_effect=fail_once),self.assertRaises(OSError):build_site(TINY.replace('Hello','New'),out,src)
            self.assertEqual(before,self.snapshot(out))
            self.assertEqual(sorted(p.name for p in root.iterdir()),['out','source.sdr'])

    def test_cli_site_and_explicit_unsupported_app_targets(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'site.sdr';source.write_text(TINY)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['check',str(source)]),0)
                self.assertEqual(main(['build','site',str(source),'--output',str(root/'site')]),0)
            for args in (['build','web'],['build','android'],['run'],['test']):
                with contextlib.redirect_stderr(io.StringIO()):self.assertEqual(main(args+[str(source)]),1)
            source.write_text('app "Old"\nstate n=0\n')
            with contextlib.redirect_stderr(io.StringIO()):self.assertEqual(main(['build','site',str(source),'--output',str(root/'bad')]),1)
            self.assertFalse((root/'bad').exists())

    def test_legacy_candidate_packager_accepts_mixed_example_modes(self):
        import sys
        import zipfile
        from scripts import prepare_release
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'examples').mkdir();(root/'dist').mkdir()
            (root/'examples/site.sdr').write_text(TINY)
            app='app "Legacy"\nstate n=0\naction add: n=n+1\nscreen main:\n    value n\n'
            (root/'examples/app.sdr').write_text(app)
            (root/'dist/package.whl').write_bytes(b'checked wheel')
            (root/'dist/package.tar.gz').write_bytes(b'checked sdist')
            apk=root/'checked.apk';apk.write_bytes(b'checked apk')
            output=root/'kit'
            with patch.object(prepare_release,'ROOT',root), patch.object(sys,'argv',['prepare_release','--apk',str(apk),'--output',str(output)]), contextlib.redirect_stdout(io.StringIO()):
                prepare_release.main()
            with zipfile.ZipFile(output/'web-examples.zip') as archive:
                self.assertEqual(archive.namelist(),['app.html'])
                self.assertIn(b'Legacy',archive.read('app.html'))
            self.assertTrue((output/'SHA256SUMS').is_file())
