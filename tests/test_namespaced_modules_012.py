"""Real compiler regression tests for experimental aliased namespaces."""
import tempfile
from pathlib import Path
import unittest
from sedrava_frontend import parse_document
from sedrava_modules import expand
from sedrava_webapp import generate_webapp
from site_codegen import generate_site

class Namespaces(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
    def put(self,name,code):
        p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(code);return p
    def parse(self,code):
        return parse_document(code,self.root/'main.sdr')
    def test_two_equal_export_names(self):
        for name in ('first','second'):
            self.put(name+'.sdr',f'module demo.{name}\nexport component Panel:\n    card:\n        paragraph "{name}"\n')
        src='site "x"\nimport "first.sdr" as a\nimport "second.sdr" as b\npage home at "/":\n    title "x"\n    heading "x"\n    use a.Panel\n    use b.Panel\n'
        html=generate_site(self.parse(src))[0]['index.html'].decode()
        self.assertIn('first',html);self.assertIn('second',html)
    def test_private_public_functions_and_real_webapp(self):
        self.put('math.sdr','module math.tools\nfn inc(x: int) -> int = x + 1\nexport fn twice(x: int) -> int = inc(x) * 2\n')
        src='webapp "x"\nimport "math.sdr" as math\nstate count=3\nderive result=math.twice(count)\nview main:\n    heading "x"\n    value result\n'
        self.assertIn(b'data-state="result"',generate_webapp(self.parse(src))['index.html'])
        with self.assertRaisesRegex(ValueError,'not an exported symbol'):
            self.parse(src.replace('math.twice','math.inc'))
    def test_namespaced_styles_and_private_component(self):
        self.put('ui.sdr','module ui.controls\nexport style panel:\n    padding 24\ncomponent Secret:\n    card style panel:\n        paragraph "Private"\nexport component Badge:\n    use Secret\n')
        src='site "x"\nimport "ui.sdr" as ui\npage home at "/":\n    title "x"\n    heading "x"\n    use ui.Badge\n    card style ui.panel:\n        paragraph "Public"\n'
        h=generate_site(self.parse(src))[0]['index.html'].decode()
        self.assertIn('Private',h);self.assertIn('Public',h)
        with self.assertRaisesRegex(ValueError,'not an exported symbol'):
            self.parse(src.replace('ui.Badge','ui.Secret'))
    def test_qualified_record_and_string_safety(self):
        self.put('r.sdr','module example.records\nexport record Item:\n    title: text\n    done: bool\n')
        src='webapp "x"\nimport "r.sdr" as rec\nstate items: list<rec.Item>(max=5) = []\nview main:\n    heading "x"\n    paragraph "rec.Item is literal"\n'
        lowered,deps=expand(src,self.root/'main.sdr')
        self.assertIn('record M_',lowered);self.assertIn('"rec.Item is literal"',lowered)
        self.assertEqual(len(deps),1);self.parse(src)
    def test_nested_import_same_module_deduplicated(self):
        self.put('base.sdr','module shared.base\nexport component Panel:\n    paragraph "ok"\n')
        self.put('wrap.sdr','module shared.wrap\nimport "base.sdr" as base\nexport component Wrapper:\n    use base.Panel\n')
        src='site "x"\nimport "wrap.sdr" as first\nimport "wrap.sdr" as second\npage home at "/":\n    title "x"\n    heading "x"\n    use first.Wrapper\n    use second.Wrapper\n'
        html=generate_site(self.parse(src))[0]['index.html'].decode()
        self.assertEqual(html.count('ok'),2)
    def test_cycle_duplicate_alias_and_symlink(self):
        self.put('a.sdr','module sample.a\nimport "b.sdr" as b\nexport fn a(x: int) -> int = x + 1\n')
        self.put('b.sdr','module sample.b\nimport "a.sdr" as a\nexport fn b(x: int) -> int = x + 1\n')
        src='site "x"\nimport "a.sdr" as one\npage home at "/":\n    title "x"\n    heading "x"\n'
        with self.assertRaisesRegex(ValueError,'cyclic'):self.parse(src)
        with self.assertRaisesRegex(ValueError,'within'):self.parse(src.replace('a.sdr','../secret.sdr'))
        self.put('a.sdr','module sample.a\nexport component Panel:\n    paragraph "hi"\n')
        with self.assertRaisesRegex(ValueError,'duplicate/reserved import alias'):
            self.parse(src.replace('page home','import "a.sdr" as one\npage home'))
        (self.root/'linked.sdr').symlink_to(self.root/'a.sdr')
        with self.assertRaisesRegex(ValueError,'symlink'):self.parse(src.replace('a.sdr','linked.sdr'))
    def test_legacy_import_and_reserved_hidden_symbols(self):
        self.put('old.sdr','component Panel:\n    paragraph "old"\n')
        src='site "x"\nimport "old.sdr"\npage home at "/":\n    title "x"\n    heading "x"\n    use Panel\n'
        self.assertIn('old',generate_site(self.parse(src))[0]['index.html'].decode())
        self.put('new.sdr','module sample.new\nexport fn echo(x: int) -> int = x\n')
        src='webapp "x"\nimport "new.sdr" as m\nstate n=1\nderive x=m.echo(n)\nview main:\n    heading "x"\n    value x\n'
        with self.assertRaisesRegex(ValueError,'reserved generated symbol identifier'):
            self.parse(src.replace('m.echo(n)','M_0123456789ab_echo(n)'))
if __name__=='__main__':unittest.main()
