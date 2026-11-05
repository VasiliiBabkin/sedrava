"""Reproducible offline vendored packages, tested with the actual Sedrava CLI."""
import contextlib
import os
from unittest.mock import patch
import json
import tempfile
import unittest
from pathlib import Path

from sedrava_cli import main
from sedrava_packages import lock, verify, snapshot
from sedrava_frontend import parse_document


class LocalPackages(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.write('sedrava.toml', '''[package]
name="sample.site"
version="0.1.0"

[dependencies]
"example.cards" = {path="vendor/example.cards", version="1.2.3"}
''')
        self.write('vendor/example.cards/sedrava.toml', '''[package]
name="example.cards"
version="1.2.3"
''')
        self.write('vendor/example.cards/card.sdr', '''module example.cards
export component Panel:
    card:
        heading "Locked UI module"
''')
        self.write('site.sdr', '''site "Locked"
import "vendor/example.cards/card.sdr" as cards
page home at "/":
    title "Locked"
    heading "Locked"
    use cards.Panel
''')

    def write(self, rel, content):
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding='utf-8')
        return p

    def test_repeatable_lock_and_actual_compilation(self):
        self.assertEqual(main(['lock', str(self.root)]), 0)
        before = (self.root / 'sedrava.lock').read_bytes()
        self.assertEqual(main(['lock', str(self.root)]), 0)
        self.assertEqual((self.root / 'sedrava.lock').read_bytes(), before)
        self.assertEqual(main(['verify', str(self.root)]), 0)
        source = str(self.root / 'site.sdr')
        self.assertEqual(main(['check', source]), 0)
        self.assertEqual(main(['build','site',source,'--output',str(self.root / 'dist')]), 0)
        self.assertIn('Locked UI module', (self.root / 'dist/index.html').read_text())
        manifest = json.loads((self.root / 'dist/sedrava-site.json').read_text())
        self.assertIn('sedrava.lock', manifest['inputs'])
        self.assertIn('sedrava.toml', manifest['inputs'])
        self.assertIn('vendor/example.cards/card.sdr', manifest['inputs'])

    def test_missing_lock_rejects_implicit_build(self):
        with self.assertRaisesRegex(ValueError, 'sedrava.lock'):
            parse_document((self.root/'site.sdr').read_text(), self.root/'site.sdr')
        self.assertEqual(main(['check', str(self.root/'site.sdr')]), 1)

    def test_tamper_rejected_without_rewriting_lock(self):
        lock(self.root)
        previous=(self.root/'sedrava.lock').read_bytes()
        self.write('vendor/example.cards/card.sdr','module example.cards\nexport component Panel:\n    heading "TAMPER"\n')
        with self.assertRaisesRegex(ValueError,'lock mismatch'):verify(self.root)
        self.assertEqual((self.root/'sedrava.lock').read_bytes(),previous)
        with self.assertRaisesRegex(ValueError,'lock mismatch'):
            parse_document((self.root/'site.sdr').read_text(), self.root/'site.sdr')

    def test_version_mismatch(self):
        self.write('vendor/example.cards/sedrava.toml','[package]\nname="example.cards"\nversion="1.2.4"\n')
        with self.assertRaisesRegex(ValueError,'version mismatch'):snapshot(self.root)

    def test_traversal_symlink_and_unlocked_extra_file(self):
        src=(self.root/'sedrava.toml').read_text()
        self.write('sedrava.toml',src.replace('vendor/example.cards','../outside'))
        with self.assertRaisesRegex(ValueError,'must not escape'):snapshot(self.root)
        self.write('sedrava.toml',src)
        linked=self.root/'vendor/example.cards/linked.sdr'
        linked.symlink_to(self.root/'vendor/example.cards/card.sdr')
        with self.assertRaisesRegex(ValueError,'Symlinks'):snapshot(self.root)
        linked.unlink()
        lock(self.root)
        self.write('vendor/example.cards/extra.sdr','module example.extra\nexport fn id(x: int) -> int = x\n')
        with self.assertRaisesRegex(ValueError,'lock mismatch'):verify(self.root)

    def test_transitive_dependencies_and_cycles(self):
        self.write('vendor/other.math/sedrava.toml','[package]\nname="other.math"\nversion="2.0.0"\n')
        self.write('vendor/other.math/math.sdr','module other.math\nexport fn inc(x: int) -> int = x+1\n')
        self.write('vendor/example.cards/sedrava.toml','''[package]
name="example.cards"
version="1.2.3"
[dependencies]
"other.math"={path="vendor/other.math",version="2.0.0"}
''')
        model=snapshot(self.root)
        self.assertEqual([p['name'] for p in model['packages']],['example.cards','other.math'])
        self.write('vendor/other.math/sedrava.toml','''[package]
name="other.math"
version="2.0.0"
[dependencies]
"example.cards"={path="vendor/example.cards",version="1.2.3"}
''')
        with self.assertRaisesRegex(ValueError,'Cyclic'):snapshot(self.root)

    def test_lockfile_duplicate_json_key(self):
        lock(self.root)
        (self.root/'sedrava.lock').write_text('{"schema":1,"schema":1}')
        with self.assertRaisesRegex(ValueError,'Invalid sedrava.lock JSON'):verify(self.root)

    def test_enumeration_is_bounded_before_materialization_and_lock_replacement(self):
        lock(self.root)
        before = (self.root/'sedrava.lock').read_bytes()
        folder = self.root/'vendor/example.cards'
        for index in range(10):
            (folder/('empty'+str(index))).mkdir()
        original = os.scandir
        visited = []
        @contextlib.contextmanager
        def counted(path):
            with original(path) as entries:
                def track():
                    for entry in entries:
                        visited.append(entry.name)
                        yield entry
                yield track()
        with patch('sedrava_packages.MAX_ENTRIES', 3), patch('sedrava_packages.os.scandir', counted), patch.object(Path, 'rglob', side_effect=AssertionError('Unbounded tree enumeration')):
            with self.assertRaisesRegex(ValueError, 'directory entry resource limit'):
                lock(self.root)
        self.assertEqual(len(visited), 4)
        self.assertEqual((self.root/'sedrava.lock').read_bytes(), before)

    def test_empty_directory_depth_and_path_limits(self):
        folder = self.root/'vendor/example.cards'
        for limit, value, path in [('MAX_DEPTH', 2, 'a/b/c'), ('MAX_PATH_CHARS', 20, 'x'*21)]:
            with self.subTest(limit=limit):
                directory = folder/path
                directory.mkdir(parents=True)
                with patch('sedrava_packages.'+limit, value):
                    with self.assertRaisesRegex(ValueError, 'path resource limit'):
                        snapshot(self.root)
                while directory != folder:
                    parent = directory.parent
                    directory.rmdir()
                    directory = parent

    def test_existing_lock_ignores_bounded_empty_directories(self):
        lock(self.root)
        before = (self.root/'sedrava.lock').read_bytes()
        (self.root/'vendor/example.cards/empty/nested').mkdir(parents=True)
        verify(self.root)
        lock(self.root)
        self.assertEqual((self.root/'sedrava.lock').read_bytes(), before)

    def test_hidden_empty_directory_rejected(self):
        (self.root/'vendor/example.cards/.hidden').mkdir()
        with self.assertRaisesRegex(ValueError, 'Hidden entries'):
            snapshot(self.root)

    def test_file_limit_boundary_is_preserved(self):
        with patch('sedrava_packages.MAX_FILES', 2):
            snapshot(self.root)
            self.write('vendor/example.cards/extra.sdr', '# extra source\n')
            with self.assertRaisesRegex(ValueError, 'Too many files'):
                snapshot(self.root)


if __name__ == '__main__':
    unittest.main()
