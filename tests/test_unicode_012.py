"""Pinned UCD conformance; never compare against a host normalizer."""
import gzip,json,subprocess,tempfile,unittest,shutil
from pathlib import Path
from sedrava_unicode import normalize,casefold
from core_conformance import reference,javascript,kotlin
ROOT=Path(__file__).resolve().parents[1]
SOURCE='''app "Unicode 15"
state text = "é Straße 😀"
state values: list<int>(max=1) = []
persist text
action normalize:
    text = unicode_nfc(text)
action fold:
    text = text_casefold(text)
action compatibility:
    text = unicode_nfkc("𞀰ﬃ")
action overflow:
    text = unicode_nfd("'''+('각'*400)+'''")
screen main:
    value text
    button "Normalize" -> normalize
    button "Fold" -> fold
'''
def vectors():
    with gzip.open(ROOT/'unicode_data/15.0.0/NormalizationTest.txt.gz','rt') as f:
        for line in f:
            line=line.split('#')[0].strip()
            if not line or line.startswith('@'):continue
            yield [''.join(chr(int(cp,16)) for cp in item.split()) for item in line.split(';')[:5]]
def cases():
    for row in vectors():
        for i,value in enumerate(row):
            yield value,[row[1] if i<3 else row[3],row[2] if i<3 else row[4],row[3],row[4]]
class Unicode012(unittest.TestCase):
    def test_official_python_normalization(self):
        count=0
        for value,expected in cases():
            self.assertEqual([normalize(value,form) for form in ('NFC','NFD','NFKC','NFKD')],expected)
            count+=1
        self.assertGreater(count,90000)
    def test_official_javascript_normalization(self):
        from web_codegen import generate
        js=generate(SOURCE,_domain_only=True)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'check.js'
            path.write_text(js+'\nconst fs=require("node:fs");const rows=JSON.parse(fs.readFileSync(0,"utf8"));for(const [value,expected] of rows){const actual=["NFC","NFD","NFKC","NFKD"].map(f=>sdrNormalize(value,f));if(JSON.stringify(actual)!==JSON.stringify(expected))throw Error(JSON.stringify([value,expected,actual]));}console.log(rows.length);')
            out=subprocess.check_output(['node',str(path)],input=json.dumps(list(cases())),text=True,timeout=90)
            self.assertGreater(int(out),90000)
    def test_official_kotlin_normalization(self):
        import base64
        from android_codegen_v03 import generate
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=generate(SOURCE,root/'app',_domain_only=True)
            code='\n'.join(line for line in path.read_text().splitlines() if not line.startswith(('package ','import ')))
            code+='\nfun main(args:Array<String>){var count=0;java.io.File(args[0]).forEachLine{line->val p=line.split("\\t").map{String(java.util.Base64.getDecoder().decode(it),Charsets.UTF_8)};val actual=listOf("NFC","NFD","NFKC","NFKD").map{sdrNormalize(p[0],it)};check(actual==p.drop(1)){"Normalization mismatch at $count"};count++};println(count)}'
            file=root/'Run.kt';file.write_text(code);jar=root/'run.jar';data=root/'cases.txt'
            data.write_text('\n'.join('\t'.join(base64.b64encode(v.encode()).decode() for v in [value,*expected]) for value,expected in cases()))
            compiler=shutil.which('kotlinc') or '/workspace/toolchains/kotlinc/bin/kotlinc'
            result=subprocess.run([compiler,str(file),'-include-runtime','-d',str(jar)],capture_output=True,text=True,timeout=90)
            self.assertEqual(result.returncode,0,result.stderr)
            out=subprocess.check_output(['java','-jar',str(jar),str(data)],text=True,timeout=90)
            self.assertGreater(int(out),90000)
    def test_complete_state_and_rollback_all_targets(self):
        seq=['normalize','fold','compatibility','overflow']
        expected=reference(SOURCE,seq)
        self.assertEqual(expected,javascript(SOURCE,seq))
        self.assertEqual(expected,kotlin(SOURCE,seq))
        self.assertFalse(expected[-1]['accepted'])
        self.assertEqual(expected[-1]['state']['text'],'аffi')
    def test_official_default_full_folding(self):
        with gzip.open(ROOT/'unicode_data/15.0.0/CaseFolding.txt.gz','rt') as f:
            for line in f:
                fields=line.split('#')[0].split(';')
                if len(fields)<3 or fields[1].strip() not in ('C','F'):continue
                self.assertEqual(casefold(chr(int(fields[0],16))),''.join(chr(int(cp,16)) for cp in fields[2].split()))
