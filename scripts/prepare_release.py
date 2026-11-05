"""Prepare local candidate files and checksums; never publish or create a tag."""
import argparse
import hashlib
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_web_examples import application_examples
from web_codegen import generate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/release')
    args = parser.parse_args()
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    files = list((ROOT / 'dist').glob('*.whl')) + list((ROOT / 'dist').glob('*.tar.gz'))
    if len(files) != 2 or not args.apk.is_file():
        parser.error('Build exactly one wheel, one sdist and the checked APK first')
    for path in [*files, args.apk]:
        destination = output / ('app-debug.apk' if path == args.apk else path.name)
        if path.resolve() != destination.resolve():
            shutil.copyfile(path, destination)
    web = output / 'web-examples.zip'
    with zipfile.ZipFile(web, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, source in application_examples(ROOT):
            info = zipfile.ZipInfo(path.stem + '.html', date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, generate(source).encode('utf-8'))
    names = ['app-debug.apk', web.name, *(p.name for p in files)]
    lines = [hashlib.sha256((output / name).read_bytes()).hexdigest() + '  ' + name for name in sorted(names)]
    (output / 'SHA256SUMS').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
