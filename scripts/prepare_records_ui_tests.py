"""Add emulator Compose interaction/rotation checks to a generated task manager."""
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sedrava_android_identity import project_identity, kotlin_path

project=Path(sys.argv[1])
gradle=project/'app/build.gradle.kts'
text=re.sub(r'(versionCode = [0-9]+;)', r'testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"; \1', gradle.read_text())
text+='\ndependencies { androidTestImplementation(platform("androidx.compose:compose-bom:2024.12.01")); androidTestImplementation("androidx.compose.ui:ui-test-junit4"); androidTestImplementation("androidx.test:runner:1.6.2"); androidTestImplementation("androidx.test.ext:junit:1.2.1"); debugImplementation("androidx.compose.ui:ui-test-manifest") }\n'
gradle.write_text(text)
path=kotlin_path(project, 'androidTest', 'RecordsUiTest.kt');path.parent.mkdir(parents=True,exist_ok=True)
path.write_text('''package org.sedrava.generated
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import org.junit.Rule
import org.junit.Test
class RecordsUiTest {
  @get:Rule val ui = createAndroidComposeRule<MainActivity>()
  @Test fun rejectedSnapshotIsRetainedOnSave() {
    val prefs=ui.activity.getSharedPreferences("sedrava_state",android.content.Context.MODE_PRIVATE)
    val original=prefs.getString("snapshot",null)
    try {
      for((index,raw) in listOf("{broken",snapshotState(SedravaState()).replace("\\\"schema\\\":1","\\\"schema\\\":2")).withIndex()) {
        prefs.edit().clear().putString("snapshot",raw).commit()
        ui.activityRule.scenario.recreate()
        ui.onNodeWithText("Saved data rejected; original retained").assertExists()
        ui.onNode(hasSetTextAction()).performTextReplacement("recovery edit $index")
        ui.onNodeWithText("Add / Добавить").performScrollTo().performClick()
        ui.onNodeWithText("title: recovery edit $index · done: false").assertExists()
        org.junit.Assert.assertEquals(raw,prefs.getString("snapshot",null))
        ui.activityRule.scenario.recreate()
        ui.onNodeWithText("title: recovery edit $index · done: false").assertExists()
        org.junit.Assert.assertEquals(raw,prefs.getString("snapshot",null))
      }
      prefs.edit().clear().putInt("legacy",7).commit()
      org.junit.Assert.assertFalse(persistState(prefs,SedravaState()))
      org.junit.Assert.assertEquals(7,prefs.getInt("legacy",0))
    } finally {
      prefs.edit().clear().apply { if(original!=null) putString("snapshot",original) }.commit()
    }
  }
  private fun assertRowWithEvidence(expected: String) {
    try {
      ui.waitUntil(timeoutMillis = 5000L) {
        ui.onAllNodesWithText(expected).fetchSemanticsNodes().isNotEmpty()
      }
      ui.onNodeWithText(expected).assertExists()
    } catch (failure: Throwable) {
      ui.onRoot(useUnmergedTree = true).printToLog("SedravaUiFailure")
      val prefs=ui.activity.getSharedPreferences("sedrava_state",android.content.Context.MODE_PRIVATE)
      android.util.Log.e("SedravaUiFailure","Missing row: "+expected+
        " snapshot="+prefs.getString("snapshot",null))
      throw failure
    }
  }
  @Test fun addEditCompleteRotateDeleteAndReject() {
    ui.onNodeWithText("No tasks yet / Список пуст").assertExists()
    ui.onNode(hasSetTextAction()).performTextReplacement("first 😀")
    ui.onNode(hasSetTextAction()).assertTextContains("first 😀")
    ui.waitForIdle()
    ui.onNodeWithText("Add / Добавить").performScrollTo().performClick()
    assertRowWithEvidence("title: first 😀 · done: false")
    ui.onNodeWithText("Select / Выбрать").performScrollTo().performClick()
    ui.onNodeWithText("Complete / Выполнено").performScrollTo().performClick()
    ui.onNodeWithText("title: first 😀 · done: true").assertExists()
    ui.onNode(hasSetTextAction()).performTextReplacement("renamed")
    ui.onNodeWithText("Rename / Переименовать").performScrollTo().performClick()
    ui.activityRule.scenario.onActivity { it.requestedOrientation = android.content.pm.ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE }
    ui.waitForIdle()
    ui.activityRule.scenario.recreate()
    ui.onNodeWithText("title: renamed · done: true").assertExists()
    ui.onNodeWithText("selected: 1").assertExists()
    ui.onNode(hasSetTextAction()).performTextReplacement("😀".repeat(1025))
    ui.onNodeWithText("Add / Добавить").performScrollTo().performClick()
    ui.onNodeWithText("title: renamed · done: true").assertExists()
    ui.onNodeWithText("Delete / Удалить").performScrollTo().performClick()
    ui.onNodeWithText("No tasks yet / Список пуст").assertExists()
    ui.activityRule.scenario.recreate()
    ui.onNodeWithText("No tasks yet / Список пуст").assertExists()
    ui.onNode(hasSetTextAction()).performTextReplacement("restart persisted")
    ui.onNodeWithText("Add / Добавить").performScrollTo().performClick()
    ui.onNodeWithText("title: restart persisted · done: false").assertExists()
  }
}
'''.replace('org.sedrava.generated', project_identity(project)),encoding='utf-8')
print(path)
