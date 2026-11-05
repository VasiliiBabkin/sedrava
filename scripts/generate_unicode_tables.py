"""Generate pinned Unicode 15 tables from checked official UCD files, never host UCD."""
import argparse,gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'unicode_data/15.0.0'
def generate():
    manifest=json.loads((DATA/'manifest.json').read_text());assert manifest['version']=='15.0.0'
    def read(name):
        raw=gzip.decompress((DATA/(name+'.gz')).read_bytes())
        if hashlib.sha256(raw).hexdigest()!=manifest['files'][name]['sha256']:raise ValueError('Changed official Unicode input: '+name)
        return raw.decode('utf-8')
    exclusions=set()
    for line in read('DerivedNormalizationProps.txt').splitlines():
        data=line.split('#')[0].strip()
        if not data:continue
        fields=[s.strip() for s in data.split(';')]
        if fields[1]!='Full_Composition_Exclusion':continue
        bounds=fields[0].split('..');exclusions.update(range(int(bounds[0],16),int(bounds[-1],16)+1))
    rows={}
    for line in read('UnicodeData.txt').splitlines():
        fields=line.split(';');cp=int(fields[0],16);ccc=int(fields[3]);parts=fields[5].split();compat=bool(parts and parts[0].startswith('<'))
        if compat:parts=parts[1:]
        decomposition=[int(s,16) for s in parts]
        if ccc or decomposition:rows[cp]=[ccc,int(compat)|(2 if len(decomposition)==2 and not compat and cp not in exclusions else 0),decomposition,[]]
    for line in read('CaseFolding.txt').splitlines():
        line=line.split('#')[0].strip()
        if not line:continue
        cp,status,mapping,*_=map(str.strip,line.split(';'))
        if status not in ('C','F'):continue
        code=int(cp,16);rows.setdefault(code,[0,0,[],[]])[3]=[int(s,16) for s in mapping.split()]
    # Validate the finite decomposition DAG and calculate a checked memory bound.
    def expand(cp,path=()):
        if cp in path:raise ValueError('Cyclic Unicode table')
        ds=rows.get(cp,[0,0,[],[]])[2]
        return sum((expand(x,(*path,cp)) for x in ds),[]) if ds else [cp]
    max_expansion=max(3,max(len(expand(cp)) for cp in rows));assert max_expansion==18
    raw='|'.join(format(cp,'x')+':'+str(c)+':'+str(flags)+':'+','.join(format(x,'x') for x in ds)+':'+','.join(format(x,'x') for x in fold) for cp,(c,flags,ds,fold) in sorted(rows.items()))
    license=(ROOT/manifest['license']).read_text()
    text='''"""Generated Unicode 15.0.0 data; DO NOT EDIT. Unicode License V3 (below).
Source: unicode-org/unicodetools @ ad1deaee8697c99107bafeceaebdfb22a51706ed.
Regenerate with scripts/generate_unicode_tables.py; no host Unicode dependency.
"""\n'''
    text+='VERSION = "15.0.0"\nMAX_EXPANSION = '+str(max_expansion)+'\nDATA_SHA256 = '+repr(hashlib.sha256(raw.encode()).hexdigest())+'\nLICENSE_TEXT = '+repr(license)+'\nDATA = (\n'
    for i in range(0,len(raw),8192):text+='    '+repr(raw[i:i+8192])+'\n'
    return text+')\n'
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');args=parser.parse_args();target=ROOT/'sedrava_unicode_data.py';content=generate()
    if args.check:
        if target.read_text()!=content:raise SystemExit('Unicode generated tables differ')
        print('PASS: pinned Unicode 15 tables regenerated identically')
    else:target.write_text(content);print(target)
