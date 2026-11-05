"""Independent JVM and Compose tests beside an untouched generated application."""
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from android_codegen_v03 import generate,quoted
from sedrava_android_identity import project_identity,kotlin_path
from sedrava_core import parse
from sedrava_records import fingerprint
from core_conformance import reference
project=Path(sys.argv[1]);source=(ROOT/'examples/bounded_values_012.sdr').read_text();generate(source,project)
sequence=['scan','order','fail_bounds','fail_sum','remove','add','add','seed_rows','audit_a1','delete_rows','normalize','fold','expected_error','clear','scan']
expected=reference(source,sequence);package=project_identity(project)
lines=['package '+package,'import org.junit.Test','import org.junit.Assert.*','class CoreA2Test { @Test fun completeStateTrace(){var state=SedravaState()']
for i,(action,outcome) in enumerate(zip(sequence,expected)):
    snapshot=json.dumps({'schema':1,'signature':fingerprint(parse(source)),'state':outcome['state']},ensure_ascii=False,separators=(',',':'))
    lines+=['run {val before=state;state=transitionState(state,'+quoted(action)+');assertEquals('+str(outcome['accepted']).lower()+',state!==before);assertEquals('+quoted(snapshot)+',snapshotState(state,true))}']
lines+=['}}'];test=kotlin_path(project,'test','CoreA2Test.kt');test.parent.mkdir(parents=True,exist_ok=True);test.write_text('\n'.join(lines))
gradle=project/'app/build.gradle.kts';text=re.sub(r'(versionCode = [0-9]+;)',r'testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"; \1',gradle.read_text())
text+='\ndependencies { androidTestImplementation(platform("androidx.compose:compose-bom:2024.12.01")); androidTestImplementation("androidx.compose.ui:ui-test-junit4"); androidTestImplementation("androidx.test:runner:1.6.2"); androidTestImplementation("androidx.test.espresso:espresso-core:3.5.0"); androidTestImplementation("androidx.test.ext:junit:1.2.1"); debugImplementation("androidx.compose.ui:ui-test-manifest") }\n';gradle.write_text(text)
lines=['package '+package,'import androidx.compose.ui.test.*','import androidx.compose.ui.test.junit4.createAndroidComposeRule','import org.junit.Rule','import org.junit.Test','import org.junit.Assert.*','class CoreA2UiTest { @get:Rule val ui=createAndroidComposeRule<MainActivity>()','@Test fun buttonsRollbackAndRecreation(){']
for action,outcome in zip(sequence,expected):
    lines+=['ui.onNodeWithText('+quoted(action)+',substring=false).performScrollTo().performClick()','ui.waitForIdle()']
    # Only successful actions write; after rejected actions the preceding snapshot remains.
    lines+=['ui.runOnIdle {val prefs=ui.activity.getSharedPreferences("sedrava_state",0);val state=restoreSnapshot(requireNotNull(prefs.getString("snapshot",null)));assertEquals('+quoted(json.dumps(outcome['state'],ensure_ascii=False,separators=(',',':')))+',snapshotState(state,true).substringAfter("\\\"state\\\":").dropLast(1))}']
lines+=['ui.activityRule.scenario.recreate();ui.waitForIdle();ui.onNodeWithText("scan",substring=false).assertExists()','}}']
test=kotlin_path(project,'androidTest','CoreA2UiTest.kt');test.parent.mkdir(parents=True,exist_ok=True);test.write_text('\n'.join(lines))
print(project)
