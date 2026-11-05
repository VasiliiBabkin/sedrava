"""CI mirror selection preserves the apt trust configuration."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.configure_ci_apt import configure, rewrite_sources


class CiApt(unittest.TestCase):
    def test_only_ubuntu_uri_changes_and_signing_configuration_is_preserved(self):
        source='Types: deb\nURIs: http://azure.archive.ubuntu.com/ubuntu/\nSuites: noble noble-security\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n'
        self.assertEqual(rewrite_sources(source), source.replace('azure.archive.ubuntu.com','archive.ubuntu.com'))
        self.assertEqual(rewrite_sources(rewrite_sources(source)), rewrite_sources(source))

    def test_unrelated_hosts_and_non_source_fields_remain_unchanged(self):
        source='URIs: https://azure.archive.ubuntu.com.evil/ubuntu/\nURIs: https://packages.microsoft.com/repos/code\n# http://azure.archive.ubuntu.com/ubuntu/\nSigned-By: /keys/azure.archive.ubuntu.com.gpg\n'
        self.assertEqual(rewrite_sources(source), source)
        legacy='deb [signed-by=/keys/ubuntu.gpg] https://azure.archive.ubuntu.com/ubuntu noble main\n'
        self.assertEqual(rewrite_sources(legacy), legacy.replace('azure.archive.ubuntu.com','archive.ubuntu.com'))

    def test_configure_is_ci_only_and_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ubuntu.sources'
            source='URIs: http://azure.archive.ubuntu.com/ubuntu/\n'
            path.write_text(source)
            with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):
                with self.assertRaisesRegex(ValueError,'only for disposable'):
                    configure((path,))
            self.assertEqual(path.read_text(),source)
            with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):
                configure((path,));configure((path,))
            self.assertEqual(path.read_text(),source.replace('azure.archive.ubuntu.com','archive.ubuntu.com'))
