"""Real API35 same-key published-0.10 APK -> RC -> debug-only downgrade.

No uninstall/pm clear between transitions. Lower-version normal installation must
fail; -d is explicitly tested for debuggable APKs, not a production rollback claim.
"""
import argparse,hashlib,json,os,subprocess,sys,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.verify_apk import verify
from scripts.test_rc_upgrade import validate_update,raw_snapshot,snapshot
from scripts.emulator_ui import handle_launcher_dialog
from sedrava_android_identity import project_identity

def main(work):
    work=work.resolve();out=work/'android-evidence';out.mkdir(exist_ok=True)
    old=work/'generated/clean-old-wheel/task_manager_navigation-android';new=work/'generated/clean-rc-wheel/task_manager_navigation-android'
    log=(out/'commands.log').open('w')
    def call(*args,check=True):
        result=subprocess.run(list(map(str,args)),text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT);log.write(repr(list(map(str,args)))+'\n'+result.stdout+'\n');log.flush()
        if check and result.returncode:raise RuntimeError('Android command failed: '+str(args)+'; '+result.stdout)
        return result
    def run(*args):return call(*args).stdout
    props={key:run('adb','shell','getprop',key).strip() for key in ('ro.build.version.sdk','ro.kernel.qemu','ro.product.cpu.abi')}
    if props['ro.build.version.sdk']!='35' or props['ro.kernel.qemu']!='1':raise ValueError('Requires disposable API35 emulator; no installation performed')
    package=project_identity(old);assert project_identity(new)==package
    sdk=Path(os.environ['ANDROID_HOME']);apk=lambda project:project/'app/build/outputs/apk/debug/app-debug.apk'
    old_meta=verify(apk(old),sdk,package,'0.10.0');new_meta=verify(apk(new),sdk,package,'0.11.0rc1');validate_update(old_meta,new_meta)
    assert old_meta['version_code']==10003 and new_meta['version_code']==11001 and old_meta['debuggable'] and new_meta['debuggable']
    relative='shared_prefs/sedrava_state.xml'
    def prefs():return run('adb','shell','run-as',package,'cat',relative)
    def start(needle):
        run('adb','shell','am','start','-W','-n',package+'/.MainActivity')
        for _ in range(10):
            run('adb','shell','uiautomator','dump','/sdcard/upgrade011.xml');ui=run('adb','shell','cat','/sdcard/upgrade011.xml')
            if handle_launcher_dialog(ui,package):continue
            if needle in ui:return ui
            run('adb','shell','input','swipe','500','750','500','250','200')
        raise AssertionError('Actual UI did not show '+needle)
    def stop():run('adb','shell','am','force-stop',package)
    def write(raw):
        stop();subprocess.run(['adb','shell','-T','run-as',package,'tee',relative],input=raw.encode(),stdout=subprocess.DEVNULL,check=True)
    # Fresh disposable emulator is required; do not silently erase any app data.
    assert 'package:'+package not in run('adb','shell','pm','list','packages',package)
    run('gradle','-p',old,'--no-daemon',':app:connectedDebugAndroidTest')
    before=prefs();assert snapshot(before)['state']['tasks']=={'next_id':2,'items':[{'id':1,'title':'Upgrade kept','done':False}]}
    stop();assert 'Success' in run('adb','install','-r',apk(new));assert 'versionCode=11001' in run('adb','shell','dumpsys','package',package);start('Upgrade kept');assert snapshot(prefs())==snapshot(before)
    stop();start('Upgrade kept');assert snapshot(prefs())==snapshot(before)
    run('gradle','-p',new,'--no-daemon',':app:connectedDebugAndroidTest')
    edited=prefs();expected={'next_id':2,'items':[{'id':1,'title':'RC edited','done':True}]};assert snapshot(edited)['state']['tasks']==expected
    stop();start('RC edited');assert snapshot(prefs())==snapshot(edited)
    stop();rejected=call('adb','install','-r',apk(old),check=False)
    assert rejected.returncode!=0 and 'INSTALL_FAILED_VERSION_DOWNGRADE' in rejected.stdout
    assert raw_snapshot(prefs())==raw_snapshot(edited)
    assert 'Success' in run('adb','install','-r','-d',apk(old));ui=start('RC edited');assert snapshot(prefs())==snapshot(edited)
    stop();start('RC edited');assert snapshot(prefs())==snapshot(edited)
    dump=run('adb','shell','dumpsys','package',package);assert 'versionCode=10003' in dump and 'versionName=0.10.0' in dump
    (out/'rollback-ui.xml').write_text(ui)
    with (out/'rollback.png').open('wb') as stream:subprocess.run(['adb','exec-out','screencap','-p'],stdout=stream,check=True)
    bad_cases=[]
    for kind in ('malformed','incompatible'):
        tree=ET.fromstring(edited);bad='{broken' if kind=='malformed' else json.dumps({**snapshot(edited),'schema':2})
        next(n for n in tree if n.get('name')=='snapshot').text=bad;write(ET.tostring(tree,encoding='unicode'))
        assert 'Success' in run('adb','install','-r',apk(new));start('original retained');assert raw_snapshot(prefs())==bad
        stop();start('original retained');assert raw_snapshot(prefs())==bad
        stop();assert 'Success' in run('adb','install','-r','-d',apk(old));start('original retained');assert raw_snapshot(prefs())==bad
        bad_cases.append({'kind':kind,'sha256':hashlib.sha256(bad.encode()).hexdigest(),'original_retained_across_update_restart_debug_rollback':True});write(edited)
    start('RC edited');assert snapshot(prefs())==snapshot(edited)
    for label,raw in [('before',before),('after-rc',edited),('after-rollback',prefs())]:(out/(label+'.xml')).write_text(raw)
    receipt={'candidate_sha':json.loads((work/'upgrade-install.json').read_text())['candidate_sha'],'status':'PASS','emulator':props,'baseline_apk':old_meta,'candidate_apk':new_meta,'normal_downgrade':'INSTALL_FAILED_VERSION_DOWNGRADE; data unchanged','debug_only_rollback':'adb install -r -d; data retained; not a production guarantee','preserved_full_snapshot':snapshot(edited),'rejected_data':bad_cases,'transitions_without_uninstall_or_clear':True,'physical_device':'not tested'}
    (out/'android-upgrade.json').write_text(json.dumps(receipt,indent=2)+'\n');print('PASS: real published 0.10 -> RC update, rejected normal downgrade and actual debug rollback with data retained')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,required=True);main(p.parse_args().work)
