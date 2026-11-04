"""Add installation-test instrumentation beside unchanged wheel-generated app sources."""
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from sedrava_android_identity import kotlin_path,project_identity
old,new=map(Path,sys.argv[1:3])
for project in (old,new):subprocess.run([sys.executable,ROOT/'scripts/prepare_navigation_ui_tests.py',project,'--seed-upgrade'],check=True)
kotlin_path(new,'androidTest','NavigationUiTest.kt').write_text('''package PACKAGE
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import android.content.pm.ActivityInfo
import org.junit.Rule
import org.junit.Test
class UpgradeObserveTest {
 @get:Rule val ui=createAndroidComposeRule<MainActivity>()
 @Test fun editRestoredPublishedDataAndRecreate() {
  ui.onNodeWithContentDescription("Open Upgrade kept").performScrollTo().performClick()
  ui.onNodeWithTag("input-title").performTextReplacement("RC edited")
  androidx.test.espresso.Espresso.closeSoftKeyboard()
  ui.onNodeWithText("Save title").performScrollTo().performClick()
  ui.onNodeWithText("Toggle completion").performScrollTo().performClick()
  ui.onNodeWithText("Completed · nicely done").assertExists()
  ui.activityRule.scenario.onActivity { it.requestedOrientation=ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE }
  ui.waitForIdle()
  ui.onNodeWithTag("screen-details").assertExists()
  ui.activityRule.scenario.recreate()
  ui.onNodeWithTag("input-title").assertTextContains("RC edited")
  UiDevice.getInstance(InstrumentationRegistry.getInstrumentation()).pressBack()
  ui.waitForIdle()
  ui.onNodeWithTag("screen-main").assertExists()
  ui.onNodeWithContentDescription("Open RC edited").assertExists()
 }
}
'''.replace('PACKAGE',project_identity(new)))
