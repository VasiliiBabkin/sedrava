"""A previous green job, missing device test or wrong-head report cannot authorize GO."""
import json,tempfile,unittest
from pathlib import Path
from scripts.report_upgrade_011 import report
class UpgradeReport(unittest.TestCase):
    def fixture(self,root):
        for name in ('upgrade-install.json','android-upgrade.json'):(root/name).write_text(json.dumps({'candidate_sha':'a'*40,'status':'PASS'}))
        for engine in ('chromium','firefox','webkit'):
            folder=root/engine;folder.mkdir();(folder/'web-upgrade.json').write_text(json.dumps({'candidate_sha':'a'*40,'status':'PASS','engine':engine,'tests':4}))
        return {name:{'result':'success'} for name in ('packages','browser','android')}
    def test_no_receipts_is_no_go_never_permission(self):
        with tempfile.TemporaryDirectory() as temp:
            value=report(temp,'a'*40,{},'test-only')
            self.assertEqual(value['upgrade_gate'],'NO-GO');self.assertFalse(value['publication_authorized'])
    def test_complete_exact_head_is_technical_go_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);jobs=self.fixture(root);value=report(root,'a'*40,jobs,'test-only')
            self.assertEqual(value['upgrade_gate'],'GO');self.assertFalse(value['publication_authorized'])
    def test_wrong_head_skipped_device_and_incomplete_browsers_block(self):
        for kind in ('wrong-head','skipped-device','missing-browser','failed-browser'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as temp:
                root=Path(temp);jobs=self.fixture(root);sha='a'*40
                if kind=='wrong-head':sha='b'*40
                elif kind=='skipped-device':jobs['android']['result']='skipped'
                elif kind=='missing-browser':(root/'webkit/web-upgrade.json').unlink()
                else:(root/'webkit/web-upgrade.json').write_text(json.dumps({'candidate_sha':sha,'status':'FAIL','engine':'webkit','tests':4}))
                self.assertEqual(report(root,sha,jobs,'test-only')['upgrade_gate'],'NO-GO')
