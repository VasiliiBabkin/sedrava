"""Independent JVM and Compose tests beside an untouched generated application."""
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from android_codegen_v03 import generate,quoted
from sedrava_android_identity import project_identity,kotlin_path
from sedrava_core import parse
from sedrava_records import fingerprint
from core_conformance import reference
project=Path(sys.argv[1]);source_path=Path(sys.argv[2]) if len(sys.argv)>2 else ROOT/'examples/bounded_values_012.sdr'
from sedrava_modules import expand
source=expand(source_path.read_text(),source_path)[0];program=parse(source);generate(source,project,_program=program)
sequence=['scan','order','fail_bounds','fail_sum','remove','add','add','seed_rows','audit_a1','delete_rows','normalize','fold','expected_error','clear','scan']
if len(sys.argv)>2:sequence=['scan','add','add','expected','seed','audit','scalars','break_rule','reject']
labels=sequence.copy()
sequence=[label if label in program.actions else next(k for k in program.actions if k.endswith('_'+label)) for label in labels]
expected=reference(source,sequence);package=project_identity(project)
lines=['package '+package,'import org.junit.Test','import org.junit.Assert.*','class CoreA2Test { @Test fun completeStateTrace(){var state=SedravaState()']
from sedrava_sequences import ValueList
vector=next((k for k,v in program.states.items() if isinstance(v,ValueList) and v.kind.element is int),None)
if vector:
    capacity=program.states[vector].kind.capacity
    lines+=['run {val invalid=state.copy(sdr_'+vector+'=SdrVector('+str(capacity)+',List('+str(capacity+1)+'){1}));assertSame(invalid,transitionState(invalid,'+quoted(sequence[0])+'))}']
for i,(action,outcome) in enumerate(zip(sequence,expected)):
    snapshot=json.dumps({'schema':1,'signature':fingerprint(parse(source)),'state':outcome['state']},ensure_ascii=False,separators=(',',':'))
    lines+=['run {val before=state;state=transitionState(state,'+quoted(action)+');assertEquals('+str(outcome['accepted']).lower()+',state!==before);assertEquals('+quoted(snapshot)+',snapshotState(state,true))}']
lines+=['}}'];test=kotlin_path(project,'test','CoreA2Test.kt');test.parent.mkdir(parents=True,exist_ok=True);test.write_text('\n'.join(lines))
gradle=project/'app/build.gradle.kts';text=re.sub(r'(versionCode = [0-9]+;)',r'testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"; \1',gradle.read_text())
text+='\ndependencies { androidTestImplementation(platform("androidx.compose:compose-bom:2024.12.01")); androidTestImplementation("androidx.compose.ui:ui-test-junit4"); androidTestImplementation("androidx.test:runner:1.6.2"); androidTestImplementation("androidx.test.espresso:espresso-core:3.5.0"); androidTestImplementation("androidx.test.ext:junit:1.2.1"); debugImplementation("androidx.compose.ui:ui-test-manifest") }\n';gradle.write_text(text)
lines=['package '+package,'import androidx.compose.ui.test.*','import androidx.compose.ui.test.junit4.createAndroidComposeRule','import org.junit.Rule','import org.junit.Test','import org.junit.Assert.*','class CoreA2UiTest { @get:Rule val ui=createAndroidComposeRule<MainActivity>()','@Test fun buttonsRollbackAndRecreation(){']
for action,label,outcome in zip(sequence,labels,expected):
    lines+=['ui.onNodeWithText('+quoted(label)+',substring=false).performScrollTo().performClick()','ui.waitForIdle()']
    # Only successful actions write; after rejected actions the preceding snapshot remains.
    lines+=['ui.runOnIdle {val prefs=ui.activity.getSharedPreferences("sedrava_state",0);val state=restoreSnapshot(requireNotNull(prefs.getString("snapshot",null)));assertEquals('+quoted(json.dumps(outcome['state'],ensure_ascii=False,separators=(',',':')))+',snapshotState(state,true).substringAfter("\\\"state\\\":").dropLast(1))}']
lines+=['ui.activityRule.scenario.recreate();ui.waitForIdle();ui.onNodeWithText("scan",substring=false).assertExists()']
for widget in program.widgets:
    if widget[0]=='value' and widget[1] in expected[-1]['state']:
        key=widget[1];value=expected[-1]['state'][key]
        if type(value) in (str,int,bool):lines+=['ui.onNodeWithText('+quoted((program.display_names or {}).get(key,key)+': '+(str(value).lower() if type(value) is bool else str(value)))+',substring=false).assertExists()']
lines+=['}}']
test=kotlin_path(project,'androidTest','CoreA2UiTest.kt');test.parent.mkdir(parents=True,exist_ok=True);test.write_text('\n'.join(lines))
print(project)
