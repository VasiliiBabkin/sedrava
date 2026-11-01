"""Static .sdr site renderer: typed CSS, safe assets, deterministic directory builds."""
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import tempfile
from urllib.parse import urlsplit, urlunsplit
import xml.etree.ElementTree as ET
from sedrava_site import Site, COMPONENTS, BREAKPOINTS, parse_site, resolved, fail
from sedrava_version import VERSION

CSS = r'''
*,:before,:after{box-sizing:border-box}html{color-scheme:dark;scroll-behavior:smooth;scroll-padding-top:2rem}body{margin:0;background:radial-gradient(ellipse at 12% 0%,#292039 0%,transparent 48rem),var(--background);color:var(--foreground);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;font-size:1rem;line-height:1.65;-webkit-font-smoothing:antialiased}::selection{background:var(--accent);color:var(--background)}.s-page{min-height:100vh}.s-node{--s-margin:0px;--s-max:100%;min-inline-size:0;max-inline-size:min(var(--s-max),calc(100% - 2 * var(--s-margin)));overflow-wrap:anywhere}.s-container{width:100%;margin-inline:auto}.s-row{display:flex;flex-wrap:wrap;align-items:center}.s-column{display:flex;flex-direction:column}.s-grid{display:grid;grid-template-columns:minmax(0,1fr)}.s-card{border:1px solid var(--border);background:var(--surface);transition:transform .18s ease,border-color .18s ease;position:relative}.s-card:hover{border-color:var(--accent);transform:translateY(-3px)}.s-card.v-highlight{background:linear-gradient(125deg,#302541,var(--surface));border-color:var(--accent)}.s-card.v-muted{background:transparent}.s-heading{font-family:Georgia,"Times New Roman",serif;line-height:1.13;letter-spacing:-.035em;font-weight:500;margin:0;text-wrap:balance;white-space:pre-wrap}.s-heading:is(h1){font-size:clamp(2.6rem,6.5vw,6.3rem);letter-spacing:-.055em;line-height:1.03}.s-heading:is(h2){font-size:clamp(1.7rem,3.5vw,2.75rem)}.s-heading:is(h3,h4,h5,h6){font-size:1.45rem}.s-heading.v-display{font-size:clamp(2.6rem,6.5vw,6.3rem);letter-spacing:-.055em;line-height:1.03}.s-paragraph{margin:0;white-space:pre-wrap}.s-paragraph.v-lead{font-size:clamp(1.08rem,2vw,1.3rem);line-height:1.75;color:var(--muted);max-width:42rem}.s-paragraph.v-muted{color:var(--muted)}.s-paragraph.v-eyebrow{font-size:.75rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--gold)}.s-paragraph.v-brand{font-size:1.3rem;font-weight:750;letter-spacing:-.045em}.s-link{color:var(--accent);text-underline-offset:.28em;text-decoration-thickness:1px;transition:color .16s ease;white-space:normal}.s-link:hover{color:var(--gold)}.s-link.v-quiet{color:var(--muted);text-decoration:none}.s-link.v-quiet:hover{color:var(--foreground)}.s-button{display:inline-flex;align-items:center;justify-content:center;gap:.6rem;min-height:48px;padding:.75rem 1.4rem;border:1px solid transparent;border-radius:12px;background:var(--accent);color:var(--background);font-weight:650;font-size:.95rem;line-height:1.4;text-decoration:none;text-align:center;transition:background .16s ease,transform .16s ease,border-color .16s ease}.s-button:hover{background:var(--gold);transform:translateY(-2px)}.s-button.v-secondary{background:transparent;border-color:var(--border);color:var(--foreground)}.s-button.v-secondary:hover{border-color:var(--accent);background:var(--surface)}.s-button.v-ghost{background:transparent;color:var(--accent)}.s-button.v-ghost:hover{background:var(--surface)}a:focus-visible{outline:3px solid var(--gold);outline-offset:4px;border-radius:6px}.s-image{display:block;width:100%;height:auto;object-fit:contain}.s-spacer{flex-shrink:0}.s-divider{border:0;border-block-start:1px solid var(--border);margin:0;width:100%}.s-skip{position:fixed;inset-block-start:1rem;inset-inline-start:1rem;z-index:20;transform:translateY(-200%);background:var(--gold);color:var(--background);padding:.75rem 1rem;border-radius:10px;font-weight:700}.s-skip:focus{transform:none}main:focus{outline:none}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,:before,:after{animation:none!important;transition:none!important}.s-card:hover,.s-button:hover{transform:none}}
'''


def digest(data):return hashlib.sha256(data).hexdigest()

def css_color(value):return 'var(--'+value+')' if not value.startswith('#') else value


def declarations(kind,props):
    result=[]
    for key,value in props.items():
        if key in ('gap','height','radius'):
            result.append({'gap':'gap','height':'height','radius':'border-radius'}[key]+':'+str(value)+'px')
        elif key=='padding':result.append('padding:min('+str(value)+'px,10%)')
        elif key=='margin':result.extend(['--s-margin:min('+str(value)+'px,5%)','margin:var(--s-margin)'])
        elif key=='width':result.append('width:'+({'auto':'auto','full':'100%'}.get(value,'min(100%,'+str(value)+'px)')))
        elif key=='max':result.append('--s-max:'+str(value)+'px')
        elif key=='size':result.append(('height' if kind=='spacer' else 'font-size')+':'+str(value)+'px')
        elif key in ('color','background'):result.append(key+':'+css_color(value))
        elif key=='align':result.append('align-items:'+{'start':'flex-start','end':'flex-end','center':'center','stretch':'stretch'}[value])
        elif key=='justify':result.append('justify-content:'+{'start':'flex-start','end':'flex-end','center':'center','between':'space-between','around':'space-around','evenly':'space-evenly'}[value])
        elif key=='text-align':result.append('text-align:'+value)
        elif key=='weight':result.append('font-weight:'+{'normal':'400','medium':'500','semibold':'600','bold':'700'}[value])
        elif key=='shadow':result.append('box-shadow:'+{'none':'none','soft':'0 18px 50px #00000030','glow':'0 0 60px #b59bff18'}[value])
        elif key=='wrap':result.append('flex-wrap:'+('wrap' if value else 'nowrap'))
        elif key=='columns':result.append('grid-template-columns:repeat('+str(value)+',minmax(0,1fr))')
    return ';'.join(result)


SVG_TAGS={'svg','g','path','rect','circle','ellipse','line','polyline','polygon','text','tspan','title','desc'}
SVG_ATTRS={'viewBox','width','height','x','y','x1','x2','y1','y2','cx','cy','r','rx','ry','d','points','fill','stroke','stroke-width','stroke-linecap','stroke-linejoin','opacity','fill-opacity','stroke-opacity','transform','font-family','font-size','font-weight','text-anchor','dominant-baseline','id'}


def validate_image(data,suffix):
    if suffix=='.svg':
        try:xml=data.decode('utf-8-sig')
        except UnicodeDecodeError as exc:raise ValueError('SVG assets must use UTF-8') from exc
        if '\x00' in xml or '<!DOCTYPE' in xml.upper() or '<!ENTITY' in xml.upper() or re.search(r'<\?(?!xml\s)',xml):
            raise ValueError('SVG declarations/stylesheets/entities are not allowed')
        try:root=ET.fromstring(xml)
        except ET.ParseError as exc:raise ValueError('Invalid SVG XML') from exc
        if root.tag!='{http://www.w3.org/2000/svg}svg':raise ValueError('Expected an SVG namespace/root')
        for item in root.iter():
            if not item.tag.startswith('{http://www.w3.org/2000/svg}') or item.tag.rsplit('}',1)[-1] not in SVG_TAGS:
                raise ValueError('Unsafe/unsupported SVG element')
            for key,value in item.attrib.items():
                if key not in SVG_ATTRS or '\\' in value or '/*' in value or re.search(r'url\s*\(|https?:|data:|javascript:|@import',value,re.I):
                    raise ValueError('Unsafe/unsupported SVG attribute or resource reference')
    elif suffix=='.png':
        if not data.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('Invalid PNG signature')
    elif suffix in ('.jpg','.jpeg'):
        if not data.startswith(b'\xff\xd8\xff'):raise ValueError('Invalid JPEG signature')
    elif suffix=='.webp':
        if not (data.startswith(b'RIFF') and data[8:12]==b'WEBP'):raise ValueError('Invalid WebP signature')
    else:raise ValueError('Images support PNG, JPEG, WebP and safe SVG only')


class Assets:
    def __init__(self,root):
        self.root=Path(root).resolve();self.files={};self.paths=set();self.cache={};self.total=0

    def image(self,node,value):
        if urlsplit(value).scheme:return value
        if value in self.cache:return self.cache[value]
        path=self.root/value
        try:
            resolved_path=path.resolve(strict=True)
            if not resolved_path.is_relative_to(self.root) or not resolved_path.is_file():raise ValueError('Asset must be a file within the source directory')
            current=path
            while current!=self.root:
                if current.is_symlink():raise ValueError('Symlink image assets are not supported')
                current=current.parent
            if resolved_path.stat().st_size>2*1024*1024:raise ValueError('Image exceeds 2 MiB limit')
            with resolved_path.open('rb') as handle:data=handle.read(2*1024*1024+1)
            if len(data)>2*1024*1024:raise ValueError('Image exceeds 2 MiB limit')
            suffix=resolved_path.suffix.lower();validate_image(data,suffix)
            name='assets/'+digest(data)+suffix
            if name not in self.files:
                self.total+=len(data)
                if self.total>16*1024*1024:raise ValueError('Site assets exceed 16 MiB limit')
                self.files[name]=data
            self.paths.add(resolved_path);self.cache[value]=name
            return name
        except (OSError,ValueError) as exc:fail(node.properties['src'].span,'Image: '+str(exc))


def page_file(page):return page.path.lstrip('/')+'index.html'


def relative(target,page):return posixpath.relpath(target,posixpath.dirname(page_file(page)) or '.')


def generate_site(source,source_dir='.'):
    site=source if isinstance(source,Site) else parse_site(source)
    assets=Assets(source_dir);files={};styles=[];counter=0
    routes={p.path:p for p in site.pages}
    for page in site.pages:
        def href(value):
            url=urlsplit(value)
            if url.scheme:return value
            path=relative(page_file(routes[url.path]),page) if url.path else ''
            return urlunsplit(('', '',path,url.query,url.fragment))
        def render(node):
            nonlocal counter
            counter+=1;cls='n'+str(counter);props=resolved(node,site);definition=COMPONENTS[node.kind]
            base={k:v for k,v in props.items() if not any(k.startswith(b+'-') for b in BREAKPOINTS)}
            media={b:{k[len(b)+1:]:v for k,v in props.items() if k.startswith(b+'-')} for b in BREAKPOINTS}
            if node.kind=='grid':
                count=base.pop('columns',3);base['columns']=1
                media['md']={'columns':min(2,count),**media['md']}
                media['lg']={'columns':count,**media['lg']}
            css=declarations(node.kind,base)
            if css:styles.append('.s-node.'+cls+'{'+css+'}')
            for breakpoint,width in BREAKPOINTS.items():
                css=declarations(node.kind,media[breakpoint])
                if css:styles.append('@media(min-width:'+str(width)+'px){.s-node.'+cls+'{'+css+'}}')
            tag=definition.tag(props) if callable(definition.tag) else definition.tag
            attrs={'class':'s-node s-'+node.kind+' '+cls+' v-'+props.get('variant','default'),**definition.fixed_attributes}
            if 'id' in props:attrs['id']=props['id']
            if 'label' in props:attrs['aria-label']=props['label']
            for key,attribute in definition.attributes.items():
                if key in props:attrs[attribute]=props[key]
            if 'to' in props:attrs['href']=href(props['to'])
            if 'src' in props:
                src=assets.image(node,props['src']);attrs['src']=src if urlsplit(src).scheme else relative(src,page)
            if props.get('target')=='blank':attrs.update(target='_blank',rel='noopener noreferrer')
            opening='<'+tag+''.join(' '+key+'="'+html.escape(str(value),quote=True)+'"' for key,value in attrs.items())+'>'
            if definition.void:return opening
            return opening+html.escape(props.get('text',''))+''.join(render(c) for c in node.children)+'</'+tag+'>'
        body=''.join(render(n) for n in page.children)
        content='''<!doctype html>
<html lang="'''+html.escape(page.lang,quote=True)+'''">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self'; img-src 'self' https:; base-uri 'none'; form-action 'none'">
<title>'''+html.escape(page.title)+'''</title><meta name="description" content="'''+html.escape(page.description,quote=True)+'''">
<link rel="icon" href="'''+relative('favicon.svg',page)+'''">
<link rel="stylesheet" href="'''+relative('site.css',page)+'''">
</head><body><a class="s-skip" href="#content">'''+('К содержимому' if page.lang.startswith('ru') else 'Skip to content')+'''</a><main id="content" class="s-page" tabindex="-1">'''+body+'''</main></body></html>
'''
        files[page_file(page)]=content.encode('utf-8')
    # Keep the established dark rendering, but do not overlay dark-only effects on light themes.
    bg=site.theme['background'].lstrip('#')
    rgb=tuple(int(bg[i:i+2],16)/255 for i in (0,2,4))
    linear=tuple(v/12.92 if v<=0.04045 else ((v+0.055)/1.055)**2.4 for v in rgb)
    light_theme=sum(a*b for a,b in zip(linear,(0.2126,0.7152,0.0722)))>0.179
    page_css=CSS
    if light_theme:
        page_css=page_css.replace('html{color-scheme:dark;', 'html{color-scheme:light;')
        page_css=page_css.replace('background:radial-gradient(ellipse at 12% 0%,#292039 0%,transparent 48rem),var(--background)', 'background:var(--background)')
        page_css=page_css.replace('background:linear-gradient(125deg,#302541,var(--surface))', 'background:var(--surface)')
    if light_theme:
        files={name:data.replace(b'<meta name="color-scheme" content="dark">',b'<meta name="color-scheme" content="light">') for name,data in files.items()}
    theme=':root{'+''.join('--'+key+':'+value+';' for key,value in site.theme.items())+'}\n'
    files['favicon.svg']=('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"><rect width="48" height="48" rx="12" fill="'+site.theme['background']+'"/><path d="M24 7L40 24L24 41L8 24Z" fill="'+site.theme['accent']+'"/><circle cx="24" cy="24" r="5" fill="'+site.theme['gold']+'"/></svg>\n').encode('utf-8')
    files['site.css']=(theme+page_css+'\n'+'\n'.join(styles)+'\n').encode('utf-8')
    files.update(assets.files)
    return files,assets.paths


MARKER='sedrava-site.json'


def tree_bytes(output):
    result={}
    if output.is_symlink() or not output.is_dir():raise ValueError('Site output must be a real directory')
    for path in output.rglob('*'):
        if path.is_symlink():raise ValueError('Site output must not contain symlinks')
        if path.is_file():result[path.relative_to(output).as_posix()]=path.read_bytes()
    return result


def validate_existing(output):
    if output.is_symlink():raise ValueError('Site output must not be a symlink')
    if not output.exists():return
    files=tree_bytes(output)
    if not files:return
    if MARKER not in files or len(files[MARKER])>1024*1024:raise ValueError('Refusing to replace an unmanaged site directory')
    try:marker=json.loads(files.pop(MARKER))
    except (ValueError,UnicodeError) as exc:raise ValueError('Invalid site output manifest') from exc
    if type(marker) is not dict or marker.get('schema')!=1 or marker.get('mode')!='site' or marker.get('files')!={k:digest(v) for k,v in sorted(files.items())}:
        raise ValueError('Site output was modified; use a fresh output directory')


def build_site(source,output,source_path):
    output=Path(output);source_path=Path(source_path).resolve()
    files,inputs=generate_site(source,source_path.parent)
    if source_path.is_relative_to(output.resolve()) or any(p.is_relative_to(output.resolve()) for p in inputs):
        raise ValueError('Site output must not contain the source or source assets')
    validate_existing(output)
    files[MARKER]=(json.dumps({'schema':1,'mode':'site','compiler_version':VERSION,'source_sha256':digest(source.encode('utf-8')),'files':{k:digest(v) for k,v in sorted(files.items())}},sort_keys=True,indent=2)+'\n').encode('utf-8')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.sedrava-site-',dir=output.parent,ignore_cleanup_errors=True) as temporary:
        stage=Path(temporary)/'next';stage.mkdir();backup=Path(temporary)/'previous'
        for name,data in sorted(files.items()):
            target=stage.joinpath(*PurePosixPath(name).parts);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        previous=output.exists()
        if previous:os.replace(output,backup)
        try:os.replace(stage,output)
        except OSError:
            if previous:os.replace(backup,output)
            raise
    return output/'index.html'
