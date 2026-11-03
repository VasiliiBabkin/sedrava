"""RC version, provenance, archive and delivery integrity negative regressions."""
import contextlib
import io
import json
from pathlib import Path
import re
import stat
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import zipfile

from sedrava_version import VERSION,ANDROID_VERSION_CODE
from sedrava_cli import VERSION as CLI_VERSION
from android_codegen_v03 import generate
from scripts.rc_archive import read_zip,read_sdist,inspect_payload,deterministic_zip,sha256
from scripts.rc_api import SafeRedirect
from scripts.prepare_rc import validate_run,artifact,write_bundle,verify_bundle,checked_wheel_inventory,verify_uploaded_kit
from scripts.audit_release_security import audit, approved_publisher

ROOT=Path(__file__).resolve().parents[1]
SHA='a'*40
REPO='VasiliiBabkin/sedrava'

class RCPreparationTests(unittest.TestCase):
    def test_version_and_unchanged_android_identity(self):
        import sedrava
        self.assertEqual(VERSION,CLI_VERSION);self.assertEqual(VERSION,sedrava.__version__)
        self.assertRegex(VERSION,r'^0\.10\.0$');self.assertEqual(ANDROID_VERSION_CODE,10003)
        expected={'task_manager_navigation':'org.sedrava.app.af44c2608593529f9c803c46e60a5a99d','task_manager':'org.sedrava.app.ae42ed66f07aefa1c223e4fbcec5fa57b'}
        for name,package in expected.items():
            with self.subTest(name=name),tempfile.TemporaryDirectory() as folder:
                target=generate((ROOT/'examples'/ (name+'.sdr')).read_text(),folder)
                self.assertIn('package '+package,target.read_text())
                gradle=(Path(folder)/'app/build.gradle.kts').read_text()
                self.assertIn('versionName = "'+VERSION+'"',gradle)
                self.assertIn('versionCode = '+str(ANDROID_VERSION_CODE)+';',gradle)
    def test_zip_paths_and_duplicates(self):
        for name in ('../oops','/absolute','a/../../b','C:/bad','a\\bad'):
            with self.subTest(name=name),self.assertRaises(ValueError):read_zip(deterministic_zip({name:b'x'}))
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:
            archive.writestr('same',b'one')
            with self.assertWarns(UserWarning):archive.writestr('same',b'two')
        with self.assertRaises(ValueError):read_zip(data.getvalue())
    def test_zip_symlink_and_expansion_bound(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:
            item=zipfile.ZipInfo('link');item.external_attr=(stat.S_IFLNK|0o777)<<16;archive.writestr(item,b'other')
        with self.assertRaises(ValueError):read_zip(data.getvalue())
        raw=deterministic_zip({'large.txt':b'x'*100})
        with patch('scripts.rc_archive.MAX_BYTES',50),self.assertRaises(ValueError):read_zip(raw)
    def test_source_archive_links_rejected(self):
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w:gz') as archive:
            item=tarfile.TarInfo('root/link');item.type=tarfile.SYMTYPE;item.linkname='/outside';archive.addfile(item)
        with self.assertRaises(ValueError):read_sdist(data.getvalue())
    def test_credential_and_local_file_scan(self):
        for name,data in [('private.key',('-----BEGIN '+'PRIVATE KEY-----').encode()),('notes.txt',('ghp_'+'X'*36).encode()),('notes.txt',('pypi-'+'AgEIcHlwaS5vcmc'+'X'*40).encode()),('local.properties',b'sdk.dir=/local'),('.env',b'something'),('debug.keystore',b'key')]:
            with self.subTest(name=name),self.assertRaises(ValueError):inspect_payload(name,data)
        inspect_payload('docs/guide.md',b'Use GH_TOKEN from the read-only Actions token; do not print its value.')
    def test_run_provenance(self):
        good={'head_sha':SHA,'head_repository':{'full_name':REPO},'status':'completed','conclusion':'success'}
        self.assertEqual(validate_run(good,SHA,REPO),good)
        for override in [{'head_sha':'b'*40},{'head_repository':{'full_name':'other/repo'}},{'status':'in_progress'},{'conclusion':'failure'}]:
            with self.subTest(override=override),self.assertRaises(ValueError):validate_run({**good,**override},SHA,REPO)
    def test_artifact_digest_and_sha_verified_before_use(self):
        raw=deterministic_zip({'result.txt':b'actual bytes'})
        metadata={'id':42,'name':'evidence','digest':'sha256:'+sha256(raw),'expired':False,'workflow_run':{'head_sha':SHA}}
        class Api:
            repo=REPO
            def pages(self,*args):return [metadata]
            def get(self,*args,**kwargs):return raw
        files,info,_=artifact(Api(),{'id':7},'evidence',SHA)
        self.assertEqual(files,{'result.txt':b'actual bytes'});self.assertEqual(info['sha256'],sha256(raw))
        for key,value in [('digest','sha256:'+'0'*64),('expired',True),('workflow_run',{'head_sha':'b'*40})]:
            previous=metadata[key];metadata[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):artifact(Api(),{'id':7},'evidence',SHA)
            metadata[key]=previous
    def test_unexpected_install_time_wheel_script_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'inventory'):
            checked_wheel_inventory({'sedrava-'+VERSION+'.data/scripts/sedrava':b'not reviewed code'})
    def test_uploaded_kit_roundtrip_is_bound_to_source_run_and_bytes(self):
        files={'data.txt':b'checked bytes'};raw=deterministic_zip(files)
        metadata={'expired':False,'workflow_run':{'head_sha':SHA,'id':7},'digest':'sha256:'+sha256(raw)}
        class Api:
            def get(self,path,**kwargs):return raw if path.endswith('/zip') else metadata
        result=verify_uploaded_kit(Api(),42,SHA,7,sha256(raw),files)
        self.assertTrue(result['download_roundtrip_verified'])
        with self.assertRaises(ValueError):verify_uploaded_kit(Api(),42,SHA,7,sha256(raw),{'data.txt':b'changed'})
        with self.assertRaises(ValueError):verify_uploaded_kit(Api(),42,SHA,8,sha256(raw),files)
    def test_cross_host_redirect_drops_token(self):
        req=urllib.request.Request('https://api.github.com/repos/x/y/actions/artifacts/42/zip',headers={'Authorization':'Bearer example'})
        redirected=SafeRedirect().redirect_request(req,None,302,'',{},'https://example.blob.core.windows.net/artifact')
        self.assertIsNone(redirected.get_header('Authorization'))
        same=SafeRedirect().redirect_request(req,None,302,'',{},'https://api.github.com/other')
        self.assertEqual(same.get_header('Authorization'),'Bearer example')
        with self.assertRaises(ValueError):SafeRedirect().redirect_request(req,None,302,'',{},'http://example/artifact')
    def test_bundle_inventory_detects_modified_missing_and_extra_files(self):
        manifest={'version':VERSION,'git_sha':SHA,'status':'GO_FOR_OWNER_REVIEW','publication_authorized':False,'build':{'url':'unit-test-only'},'ci':[]}
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'kit'
            with contextlib.redirect_stdout(io.StringIO()):write_bundle(output,{'payload.txt':b'checked'},manifest)
            for variant in ('modified','extra','missing'):
                with self.subTest(variant=variant):
                    if variant=='modified':(output/'payload.txt').write_bytes(b'changed')
                    elif variant=='extra':(output/'unexpected').write_bytes(b'x')
                    else:(output/'payload.txt').unlink()
                    with self.assertRaises(ValueError):verify_bundle(output)
                    (output/'payload.txt').write_bytes(b'checked')
                    if (output/'unexpected').exists():(output/'unexpected').unlink()
    def test_safe_readonly_workflow_policy(self):
        result=audit()
        self.assertEqual(result['publication_steps'],1)
        self.assertGreaterEqual(result['workflow_count'],19)
        source=(ROOT/'.github/workflows/publish-pypi.yml').read_bytes()
        self.assertTrue(approved_publisher(source))
        with self.assertRaisesRegex(ValueError,'Unreviewed'):
            approved_publisher(source.replace(b'v0.10.0',b'v*',1))

if __name__=='__main__':unittest.main()
