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
