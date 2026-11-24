import os,sys,json,subprocess,time,hashlib,zipfile
from pathlib import Path
H=Path(__file__).resolve().parent
SDK=Path(os.environ['ANDROID_HOME'])
gradle=Path.home()/'.cache/sedrava-rust-verify/tooling/gradle-8.11.1/bin/gradle'
env={**os.environ,'GRADLE_USER_HOME':str(Path.home()/'.cache/sedrava-rust-verify/gradle')}
report={}
for k in ['sedrava','kotlin']:
    d=H/('android-'+k)
    (d/'local.properties').write_text('sdk.dir='+str(SDK)+'\n')
    kt=list((d/'app/src/main/java').rglob('*.kt'))
    start=time.perf_counter()
    with (H/('android-'+k+'.log')).open('w') as log:
        r=subprocess.run([str(gradle),'--offline','--no-daemon','--max-workers=2','assembleDebug'],cwd=d,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240)
    elapsed=time.perf_counter()-start
    if r.returncode:
        report[k]={"status":"FAIL","tail":(H/('android-'+k+'.log')).read_text()[-2500:]}
        print(k,report[k],flush=True);continue
    apk=d/'app/build/outputs/apk/debug/app-debug.apk'
    assert apk.is_file()
    badging=subprocess.check_output([str(SDK/'build-tools/35.0.0/aapt'),'dump','badging',str(apk)],text=True)
    sig=subprocess.check_output([str(SDK/'build-tools/35.0.0/apksigner'),'verify','--verbose',str(apk)],text=True)
    assert "name='ru.ladokod.bench.counter'" in badging and "sdkVersion:'26'" in badging and "targetSdkVersion:'35'" in badging and "launchable-activity:" in badging and "Verifies" in sig
    with zipfile.ZipFile(apk) as z:
        assert z.testzip() is None
        dex=sum(i.file_size for i in z.infolist() if i.filename.endswith('.dex'))
    report[k]={"status":"PASS","build_seconds":elapsed,"apk_bytes":apk.stat().st_size,"dex_uncompressed_bytes":dex,"kotlin_files":len(kt),"kotlin_lines":sum(len(p.read_bytes().splitlines()) for p in kt),"kotlin_bytes":sum(p.stat().st_size for p in kt),"apk_sha256":hashlib.sha256(apk.read_bytes()).hexdigest(),"device_runtime_test":False}
    print(k,json.dumps(report[k]),flush=True)
(H/'android.json').write_text(json.dumps(report,indent=2))
