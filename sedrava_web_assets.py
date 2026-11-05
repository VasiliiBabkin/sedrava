"""Author-trusted local CSS/fonts/assets and static publishing metadata.

CSS can change presentation; it cannot grant script/network/server capabilities.
"""
from sedrava_syntax import physical_lines
import hashlib
import html
import re
from pathlib import Path
from urllib.parse import urlsplit, unquote
from sedrava_core import read_literal


def read_directives(source):
    settings={'stylesheets':[],'licenses':[]};lines=[]
    for number,line in enumerate(physical_lines(source),1):
        match=re.fullmatch(r'(stylesheet|license|origin|social-image|favicon) (".*")',line)
        if match:
            value,end=read_literal(match[2])
            if end!=len(match[2]):raise ValueError(f'Line {number}: column 1: invalid presentation directive')
            key=match[1]
            if key in ('stylesheet','license'):
                group='stylesheets' if key=='stylesheet' else 'licenses'
                if len(settings[group])>=8:raise ValueError('At most eight local '+group)
                settings[group].append(value)
            else:
                if key in settings:raise ValueError(f'Line {number}: column 1: duplicate {key}')
                settings[key]=value
            lines.append('');continue
        match=re.fullmatch(r'theme-state ([A-Za-z][A-Za-z0-9_]*)',line)
        if match:
            if 'theme-state' in settings:raise ValueError('Duplicate theme-state')
            settings['theme-state']=match[1];lines.append('');continue
        match=re.fullmatch(r'robots (true|false)',line)
        if match:
            if 'robots' in settings:raise ValueError(f'Line {number}: column 1: duplicate robots')
            settings['robots']=match[1]=='true';lines.append('');continue
        lines.append(line)
    if 'origin' in settings:
        from sedrava_site import safe_url
        value=safe_url(settings['origin']);url=urlsplit(value)
        if url.scheme!='https' or url.path not in ('','/') or url.query or url.fragment:raise ValueError('Publishing origin must be a bare HTTPS origin')
        settings['origin']=value.rstrip('/')
    return '\n'.join(lines)+'\n',settings


def theme_styles(theme,css):
    value=theme['background'].lstrip('#');rgb=[int(value[i:i+2],16)/255 for i in (0,2,4)]
    linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in rgb]
    light=sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)))>.179
    if light:
        css=css.replace('color-scheme:dark','color-scheme:light').replace('background:radial-gradient(ellipse at 12% 0%,#292039 0%,transparent 48rem),var(--background)','background:var(--background)').replace('background:linear-gradient(125deg,#302541,var(--surface))','background:var(--surface)')
    return css


def collect(settings, source_dir):
    from site_codegen import validate_image, digest
    root=Path(source_dir).resolve();files={};inputs=set();sheets=[]
    def local(value,base,suffixes):
        if urlsplit(value).scheme or value.startswith(('/', '\\')) or '\\' in value or '%' in value or '?' in value:raise ValueError('Assets must be explicit local paths')
        path=base/value;resolved=path.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():raise ValueError('Missing or outside-root presentation asset')
        current=path
        while current!=root and current!=current.parent:
            if current.is_symlink():raise ValueError('Symlink presentation asset')
            current=current.parent
        if resolved.suffix.lower() not in suffixes:raise ValueError('Unsupported presentation asset type')
        if resolved.stat().st_size>2*1024*1024:raise ValueError('Presentation asset exceeds 2 MiB')
        with resolved.open('rb') as f:data=f.read(2*1024*1024+1)
        if len(data)>2*1024*1024:raise ValueError('Presentation asset exceeds 2 MiB')
        inputs.add(resolved);return resolved,data
    def resource(value,base):
        path,data=local(value,base,{'.svg','.png','.jpg','.jpeg','.webp','.woff','.woff2'})
        suffix=path.suffix.lower()
        if suffix in ('.woff','.woff2'):
            if not data.startswith(b'wOFF' if suffix=='.woff' else b'wOF2'):raise ValueError('Invalid font signature')
        else:validate_image(data,suffix)
        name='assets/'+digest(data)+suffix;files[name]=data;return name
    for value in settings.get('stylesheets',[]):
        path,data=local(value,root,{'.css'})
        if len(data)>262144:raise ValueError('Stylesheet exceeds 256 KiB')
        css=data.decode('utf-8')
        clean=re.sub(r'/\*.*?\*/','',css,flags=re.S)
        if '\\' in css or '\x00' in css or re.search(r'@import|expression\s*\(|-moz-binding',clean,re.I):raise ValueError('CSS imports, escapes or executable legacy constructs are not supported')
        pattern=r'url\(\s*(["\']?)([^)"\']+)\1\s*\)'
        if len(re.findall(r'url\s*\(',clean,re.I))!=len(re.findall(pattern,css,re.I)):raise ValueError('Unsupported CSS URL syntax')
        def replace(match):
            target=match[2].strip()
            if target.startswith('#'):
                if not re.fullmatch('#[A-Za-z][A-Za-z0-9_-]*',target):raise ValueError('Invalid CSS fragment')
                return 'url('+target+')'
            name=resource(target,path.parent)
            return 'url("'+name.split('/')[-1]+'")'
        css=re.sub(pattern,replace,css,flags=re.I)
        name='assets/'+digest(css.encode())+'.css';files[name]=css.encode();sheets.append(name)
    for value in settings.get('licenses',[]):
        path,data=local(value,root,{'.txt'})
        if len(data)>65536:raise ValueError('License exceeds 64 KiB')
        data.decode('utf-8')
        files['assets/license-'+digest(data)+'.txt']=data
    images={key:resource(settings[key],root) for key in ('favicon','social-image') if key in settings}
    if sum(len(v) for v in files.values())>16*1024*1024:raise ValueError('Presentation assets exceed 16 MiB')
    return files,inputs,sheets,images


def attach(files, settings, source_dir, pages=None):
    from site_codegen import relative
    extras,inputs,sheets,images=collect(settings,source_dir)
    origin=settings.get('origin')
    for path,data in list(files.items()):
        if not path.endswith('.html'):continue
        page=next((p for p in pages if p.path.lstrip('/')+'index.html'==path),None) if pages else None
        def link(target):
            import posixpath
            return posixpath.relpath(target,posixpath.dirname(path) or '.')
        head=''.join('<link rel="stylesheet" href="'+link(name)+'">' for name in sheets)
        head+=''.join('<link rel="license" href="'+link(name)+'">' for name in sorted(extras) if name.startswith('assets/license-'))
        if 'favicon' in images:
            head+='<link rel="icon" href="'+link(images['favicon'])+'">'
        if origin and page:
            canonical=origin+page.path
            head+='<link rel="canonical" href="'+html.escape(canonical,quote=True)+'"><meta property="og:url" content="'+html.escape(canonical,quote=True)+'">'
            head+='<meta property="og:title" content="'+html.escape(page.title,quote=True)+'"><meta property="og:description" content="'+html.escape(page.description,quote=True)+'"><meta property="og:type" content="website">'
            if 'social-image' in images:head+='<meta property="og:image" content="'+html.escape(origin+'/'+images['social-image'],quote=True)+'">'
        text=data.decode().replace('</head>',head+'</head>').replace("style-src 'self';", "style-src 'self'; font-src 'self';")
        files[path]=text.encode()
    if origin and pages:
        urls=''.join('<url><loc>'+html.escape(origin+p.path)+'</loc></url>' for p in pages)
        extras['sitemap.xml']=('<?xml version="1.0" encoding="utf-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'+urls+'</urlset>\n').encode()
        extras['robots.txt']=('User-agent: *\n'+('Allow: /\n' if settings.get('robots',True) else 'Disallow: /\n')+'Sitemap: '+origin+'/sitemap.xml\n').encode()
    files.update(extras)
    if sum(len(data) for name,data in files.items() if name.startswith('assets/'))>16*1024*1024:raise ValueError('Combined presentation assets exceed 16 MiB')
    return inputs
