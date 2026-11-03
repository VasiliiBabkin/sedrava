"""Generate a real app and JVM full-state oracle for the new common expression IR."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from android_codegen_v03 import generate,quoted
from sedrava_android_identity import project_identity,kotlin_path
from sedrava_core import parse
from sedrava_records import fingerprint
from test_platform_domain_queries import SOURCE,SEQUENCE,reference

def main():
    project=Path(sys.argv[1]);generate(SOURCE,project)
    program=parse(SOURCE)
    code=['package '+project_identity(project),'import org.junit.Test','import org.junit.Assert.*','class PlatformLogicTest {','@Test fun completePythonOracle(){','var state=SedravaState()']
    for index,(action,expected) in enumerate(zip(SEQUENCE,reference())):
        raw=json.dumps({'schema':1,'signature':fingerprint(program),'state':expected},ensure_ascii=False,separators=(',',':'))
        code+=['state=transitionState(state,'+quoted(action)+')','assertEquals("Complete state '+str(index)+'",restoreSnapshot('+quoted(raw)+',true),state)','assertEquals(state,restoreSnapshot(snapshotState(state,true),true))']
    code+=['}','}']
    path=kotlin_path(project,'test','PlatformLogicTest.kt');path.parent.mkdir(parents=True,exist_ok=True);path.write_text('\n'.join(code)+'\n');print(path)
if __name__=='__main__':main()
