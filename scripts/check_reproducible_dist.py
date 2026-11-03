"""Compare archive payloads across clean builds; timestamps/compression are excluded."""
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile
ROOT=Path(__file__).resolve().parents[1]
def payload(path):
    if path.suffix=='.whl':
        with zipfile.ZipFile(path) as z:return {n:z.read(n) for n in z.namelist() if not n.endswith('/')}
    with tarfile.open(path) as t:
        return {n.name.split('/',1)[1]:t.extractfile(n).read() for n in t.getmembers() if n.isfile()}
if __name__=='__main__':
    dist=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else ROOT/'dist'
    archives=[*sorted(dist.glob('*.whl')),*sorted(dist.glob('*.tar.gz'))]
    assert len(archives)==2,'Expected one built wheel and sdist'
    with tempfile.TemporaryDirectory(prefix='sedrava rebuild ') as folder:
        subprocess.run([sys.executable,'-m','build','--outdir',folder],cwd=ROOT,check=True)
        for original in archives:
            if original.suffix=='.whl' or original.name.endswith('.tar.gz'):
                assert payload(original)==payload(Path(folder)/original.name),f'Non-reproducible payload: {original.name}'
        print('PASS: wheel/sdist archive payloads reproducible (timestamps and compression excluded)')
