#!/usr/bin/env bash
# Run inside android-emulator-runner, after generating the task manager test harness.
set -euo pipefail
sedrava_package=$(python -c "import json;print(json.load(open('build/tasks-android/sedrava-android.json'))['application_id'])")
# Isolate this suite from earlier emulator applications/tests: instrumentation must
# start with an empty app-data directory, not an inherited in-memory snapshot.
adb uninstall "$sedrava_package" >/dev/null 2>&1 || true
adb uninstall "${sedrava_package}.test" >/dev/null 2>&1 || true
gradle -p build/tasks-android --no-daemon -Pandroid.injected.androidTest.leaveApksInstalledAfterRun=true :app:connectedDebugAndroidTest
adb shell am force-stop "$sedrava_package"
adb shell run-as "$sedrava_package" cat shared_prefs/sedrava_state.xml > build/tasks-preferences.xml
python - <<'PY'
import json
import xml.etree.ElementTree as ET
root = ET.parse('build/tasks-preferences.xml').getroot()
snapshot = json.loads(next(node.text for node in root if node.attrib.get('name') == 'snapshot'))
assert snapshot['state']['tasks'] == {'next_id': 3, 'items': [{'id': 2, 'title': 'restart persisted', 'done': False}]}
PY
adb shell am start -W -n "$sedrava_package"/.MainActivity
relaunch_verified=0
for attempt in $(seq 1 10); do
  adb shell uiautomator dump /sdcard/sedrava-ui.xml
  adb shell cat /sdcard/sedrava-ui.xml > build/tasks-relaunch.xml
  python scripts/emulator_ui.py build/tasks-relaunch.xml "$sedrava_package"
  if python -c "from pathlib import Path; raise SystemExit('restart persisted' not in Path('build/tasks-relaunch.xml').read_text())"; then
    relaunch_verified=1
    break
  fi
done
test "$relaunch_verified" = 1
adb exec-out screencap -p > build/tasks-relaunch.png
python scripts/test_storage_rejection_emulator.py build/tasks-android
