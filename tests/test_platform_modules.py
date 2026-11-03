import tempfile
from pathlib import Path
import unittest
from sedrava_modules import expand
from sedrava_site import parse_site
from sedrava_webapp import parse_webapp

TEMPLATE='''component Panel(title: text, space: int):
    card padding $space:
        column:
            heading $title
            slot
'''

class Modules(unittest.TestCase):
    def test_typed_composition_and_slots_in_both_modes(self):
        for header,view in [('site "x"','page home at "/":\n    title "x"'),('webapp "x"\nstate n=0','view main:')]:
            source=header+'\n'+TEMPLATE+view+'\n    use Panel title "<safe>" space 24:\n        paragraph "body"\n'
            value=parse_site(source) if header.startswith('site') else parse_webapp(source)
            self.assertEqual(value.name,'x')
        with self.assertRaisesRegex(ValueError,'typed'):
            expand('site "x"\n'+TEMPLATE+'page home at "/":\n    use Panel title "x" space "24":\n        paragraph "x"\n')

    def test_imports_bounded_and_no_domain_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'ui.sdr';p.write_text(TEMPLATE)
            expanded,paths=expand('site "x"\nimport "ui.sdr"\npage home at "/":\n    title "x"\n    use Panel title "Hello" space 20:\n        paragraph "ok"\n',root/'main.sdr')
            parse_site(expanded);self.assertEqual(paths,{p})
            p.write_text('state forbidden=1\n')
            with self.assertRaisesRegex(ValueError,'only export'):expand('site "x"\nimport "ui.sdr"',root/'main.sdr')
            p.write_text('import "ui.sdr"\n')
            with self.assertRaisesRegex(ValueError,'cyclic'):expand('site "x"\nimport "ui.sdr"',root/'main.sdr')
            with self.assertRaisesRegex(ValueError,'within'):expand('site "x"\nimport "../out.sdr"',root/'main.sdr')

    def test_recursive_component_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'recursive'):
            expand('component Loop:\n    use Loop\nsite "x"\npage home at "/":\n    use Loop\n')

    def test_reference_parameters_bind_through_the_existing_typed_ui(self):
        source='webapp "Bindings"\ncomponent Metric(label: text, data: ref):\n    column:\n        value $data label $label\nstate count=0\naction add: count=count+1\nview main:\n    heading "Bindings"\n    use Metric label "First" data count\n    use Metric label "Second" data count\n    button "Add" action add\n'
        doc=parse_webapp(source)
        from sedrava_webapp import generate_webapp
        self.assertEqual(generate_webapp(doc)['index.html'].count(b'data-state="count"'),2)
        for old,new in [('data count','data unknown'),('data count','data "count"'),('data count','data count.value')]:
            with self.subTest(new=new),self.assertRaises(ValueError):parse_webapp(source.replace(old,new))
