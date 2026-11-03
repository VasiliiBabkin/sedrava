"""Typed static-presentation AST and registry-driven .sdr site-mode parser."""
from dataclasses import dataclass, field
import re
from urllib.parse import unquote, urlsplit
from sedrava_core import read_literal, LiteralError
from sedrava_navigation import Span
from sedrava_syntax import source_lines, MAX_BLOCK_DEPTH


@dataclass(frozen=True)
class Token:
    value: object
    span: Span
    quoted: bool = False


@dataclass(frozen=True)
class Property:
    value: object
    span: Span


@dataclass(frozen=True)
class Component:
    kind: str
    properties: dict
    children: tuple
    span: Span


@dataclass(frozen=True)
class Style:
    name: str
    properties: dict
    span: Span


@dataclass(frozen=True)
class Page:
    name: str
    path: str
    title: str
    description: str
    lang: str
    children: tuple
    span: Span


@dataclass(frozen=True)
class Site:
    name: str
    theme: dict
    styles: dict
    pages: tuple
    mode: str = field(default='site', init=False)


@dataclass(frozen=True)
class Parameter:
    validate: object
    flag: bool = False


@dataclass(frozen=True)
class Definition:
    tag: object
    children: bool = False
    positional: str | None = None
    required: tuple = ()
    parameters: dict = field(default_factory=dict)
    defaults: dict = field(default_factory=dict)
    attributes: dict = field(default_factory=dict)
    fixed_attributes: dict = field(default_factory=dict)
    void: bool = False
    variants: tuple = ('default',)


def fail(span, message):
    raise ValueError(f'Line {span.line}: column {span.column}: {message}')


def text(value):
    if type(value) is not str or any((ord(c) < 32 and c not in '\n\r\t') or ord(c) in (0xFFFE,0xFFFF) for c in value):
        raise ValueError('Expected HTML-safe text without nonprinting controls')
    return value


def identifier(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', value):
        raise ValueError('Expected an ASCII name, at most 64 characters')
    return value


def integer(low, high):
    def validate(value):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'Expected integer in {low}..{high}')
        return value
    return validate


def choice(*values):
    def validate(value):
        if value not in values or type(value) is not str:
            raise ValueError('Expected one of: '+', '.join(values))
        return value
    return validate


def boolean(value):
    if type(value) is not bool:raise ValueError('Expected true or false')
    return value


THEME = {'background':'#10101a','surface':'#1c1a2b','foreground':'#f7f4ff',
         'accent':'#b59bff','gold':'#f3d087','muted':'#bfb6d3','border':'#49415d'}
BREAKPOINTS = {'sm':640, 'md':768, 'lg':1024}


def color(value):
    if type(value) is not str:raise ValueError('Expected a theme token or opaque hex color')
    if value in THEME:return value
    if not re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?',value):
        raise ValueError('Expected a theme token or #RGB/#RRGGBB color')
    value=value.lower()
    return '#'+''.join(c*2 for c in value[1:]) if len(value)==4 else value


def dimension(value):
    return value if value in ('auto','full') and type(value) is str else integer(1,4096)(value)


def safe_url(value, image=False):
    if type(value) is not str or not value:raise ValueError('Expected a nonempty URL')
    decoded=value
    for _ in range(3):decoded=unquote(decoded)
    if any(ord(c)<33 or ord(c)==127 or c.isspace() for c in decoded) or any(c in decoded for c in '\\<>"\''):
        raise ValueError('Unsafe URL characters')
    if decoded.startswith('//') or any(p in ('.','..') for p in urlsplit(decoded).path.split('/')):
        raise ValueError('Protocol-relative URLs and path traversal are not allowed')
    try:
        parsed=urlsplit(decoded)
        _=parsed.port
    except ValueError as exc:raise ValueError('Invalid URL') from exc
    scheme=parsed.scheme.lower()
    if scheme in ('http','https'):
        if image and scheme!='https':raise ValueError('Remote images require HTTPS')
        if not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise ValueError('URL requires a host and no embedded credentials')
        return value
    if scheme=='mailto' and not image and re.fullmatch(r'[^@?\s]+@[^@?\s]+\.[^@?\s]+',parsed.path) and not parsed.query:return value
    if scheme=='tel' and not image and re.fullmatch(r'\+?[0-9()-]+',parsed.path):return value
    if scheme or ':' in decoded:raise ValueError('Unsafe or unsupported URL scheme')
    if image:
        if decoded.startswith(('/', '#')) or parsed.query or parsed.fragment:
            raise ValueError('Local images require a relative asset path')
        if '%' in value:raise ValueError('Local asset paths must not use percent encoding')
        return value
    if decoded.startswith('#'):
        identifier(decoded[1:]);return value
    if not decoded.startswith('/'):raise ValueError('Use a /site/ route, #anchor or supported absolute URL')
    return value


COMMON = {
    'id':Parameter(identifier), 'style':Parameter(identifier), 'label':Parameter(text),
    'gap':Parameter(integer(0,4096)), 'padding':Parameter(integer(0,4096)),
    'margin':Parameter(integer(0,4096)), 'width':Parameter(dimension), 'max':Parameter(integer(1,4096)),
    'height':Parameter(integer(0,4096)), 'size':Parameter(integer(10,160)),
    'radius':Parameter(integer(0,256)), 'color':Parameter(color),'background':Parameter(color),
    'align':Parameter(choice('start','center','end','stretch')),
    'justify':Parameter(choice('start','center','end','between','around','evenly')),
    'text-align':Parameter(choice('start','center','end','left','right')),
    'weight':Parameter(choice('normal','medium','semibold','bold')),
    'shadow':Parameter(choice('none','soft','glow')),
}
COMPONENTS = {
    'container':Definition('div',children=True,defaults={'max':1160}),
    'row':Definition('div',children=True,parameters={'wrap':Parameter(boolean,True)},defaults={'gap':16,'wrap':True}),
    'column':Definition('div',children=True,defaults={'gap':16}),
    'grid':Definition('div',children=True,parameters={'columns':Parameter(integer(1,12))},defaults={'columns':3,'gap':20}),
    'heading':Definition(lambda p:'h'+str(p['level']),positional='text',required=('text',),parameters={'text':Parameter(text),'level':Parameter(integer(1,6))},variants=('default','display')),
    'paragraph':Definition('p',positional='text',required=('text',),parameters={'text':Parameter(text)},variants=('default','lead','eyebrow','muted','brand')),
    'link':Definition('a',positional='text',required=('text','to'),parameters={'text':Parameter(text),'to':Parameter(safe_url),'target':Parameter(choice('self','blank'))},attributes={'to':'href'},variants=('default','quiet')),
    'button':Definition('a',positional='text',required=('text','to'),parameters={'text':Parameter(text),'to':Parameter(safe_url),'target':Parameter(choice('self','blank'))},attributes={'to':'href'},defaults={'variant':'primary'},variants=('primary','secondary','ghost')),
    'card':Definition('article',children=True,defaults={'padding':28,'radius':24},variants=('default','highlight','muted')),
    'image':Definition('img',positional='src',required=('src','alt'),parameters={'src':Parameter(lambda v:safe_url(v,image=True)),'alt':Parameter(text)},attributes={'src':'src','alt':'alt'},fixed_attributes={'loading':'lazy','decoding':'async','referrerpolicy':'no-referrer'},void=True),
    'spacer':Definition('div',parameters={'size':Parameter(integer(0,4096))},defaults={'size':24},fixed_attributes={'aria-hidden':'true'}),
    'divider':Definition('hr',void=True),
    'navbar':Definition('nav',children=True,defaults={'gap':16,'padding':20},
                        fixed_attributes={'aria-label':'Primary navigation'}),
    'footer':Definition('footer',children=True,defaults={'padding':24}),
    'callout':Definition('aside',children=True,defaults={'padding':24,'radius':16},
                         variants=('default','info','warning')),
    'code':Definition('pre',positional='text',required=('text',),
                      parameters={'text':Parameter(text)},
                      defaults={'padding':20,'radius':12}),

}
STYLE_PARAMETERS = {**COMMON,'columns':Parameter(integer(1,12)),'wrap':Parameter(boolean,True),'variant':Parameter(text)}
STYLE_PARAMETERS = {k:v for k,v in STYLE_PARAMETERS.items() if k not in ('id','style','label')}


def tokens(line,number,indent):
    result=[];i=0
    while i<len(line):
        if line[i]==' ':i+=1;continue
        span=Span(number,indent+i+1)
        if line[i]=='"':
            try:value,end=read_literal(line,i)
            except LiteralError as exc:fail(Span(number,indent+exc.offset+1),str(exc))
            result.append(Token(value,span,True));i=end;continue
        if line[i]==':':result.append(Token(':',span));i+=1;continue
        end=i
        while end<len(line) and line[end] not in ' :':end+=1
        value=line[i:end]
        if re.fullmatch(r'-?[0-9]+',value):
            if len(value)>11:fail(span,'Integer outside supported bounds')
            value=int(value)
        elif value in ('true','false'):value=value=='true'
        elif not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*',value):fail(span,'Invalid token; quote text, colors and URLs')
        result.append(Token(value,span));i=end
    return result


def parameter_for(name,parameters):
    prefix,sep,base=name.partition('-')
    if sep and prefix in BREAKPOINTS:
        if base not in STYLE_PARAMETERS or base=='variant' or base not in parameters:return None
        return parameters[base]
    return parameters.get(name)


def properties(items,parameters):
    result={};i=0
    while i<len(items):
        key=items[i]
        spec=parameter_for(key.value,parameters) if type(key.value) is str and not key.quoted else None
        if spec is None:fail(key.span,'Unknown parameter '+str(key.value))
        if key.value in result:fail(key.span,'Duplicate parameter '+key.value)
        i+=1
        if spec.flag and (i==len(items) or type(items[i].value) is not bool):value=True;span=key.span
        else:
            if i==len(items):fail(key.span,'Missing value for '+key.value)
            value=items[i].value;span=items[i].span;i+=1
        try:value=spec.validate(value)
        except ValueError as exc:fail(span,str(exc)+' ('+key.value+')')
        result[key.value]=Property(value,span)
    return result


def resolved(node,site):
    definition=COMPONENTS[node.kind]
    result=dict(definition.defaults)
    if 'style' in node.properties:
        name=node.properties['style'].value
        if name not in site.styles:fail(node.properties['style'].span,'Unknown style '+name)
        for key,prop in site.styles[name].properties.items():
            spec=parameter_for(key,{**COMMON,**definition.parameters,'variant':Parameter(choice(*definition.variants))})
            if spec is None:fail(node.span,'Style parameter '+key+' is not supported by '+node.kind)
            try:result[key]=spec.validate(prop.value)
            except ValueError as exc:fail(node.span,str(exc))
    result.update({k:p.value for k,p in node.properties.items() if k!='style'})
    return result


def walk(nodes):
    for node in nodes:
        yield node
        yield from walk(node.children)


def route(value):
    if type(value) is not str or not re.fullmatch(r'/(?:[A-Za-z0-9_-]+/)*',value):
        raise ValueError('Page path must be / or /safe/segments/ with trailing slash')
    return value


def parse_site(source):
    from sedrava_modules import components
    source = components(source)
    lines=source_lines(source)
    if not lines:raise ValueError('Line 1: column 1: Missing site')
    lex=[(depth,tokens(line,n,depth),n) for depth,line,n in lines]
    def header(pos,keyword,length):
        depth,t,n=lex[pos]
        if depth or len(t)!=length or t[0].value!=keyword:fail(Span(n,depth+1),'Invalid '+keyword+' declaration')
        return t
    first=header(0,'site',2)
    if not first[1].quoted or not first[1].value.strip():fail(first[1].span,'Site requires a nonempty quoted name')
    theme=dict(THEME);styles={};pages=[];i=1;theme_seen=False
    def body(pos,indent):
        children=[]
        while pos<len(lex) and lex[pos][0]>=indent:
            depth,t,n=lex[pos]
            if depth!=indent:fail(Span(n,depth+1),'Expected indentation of '+str(indent)+' spaces')
            if depth//4>MAX_BLOCK_DEPTH:fail(Span(n,depth+1),'Site nesting limit exceeded')
            kind=t[0].value
            if kind not in COMPONENTS:fail(t[0].span,'Unknown site component '+str(kind))
            definition=COMPONENTS[kind];block=t[-1].value==':' and not t[-1].quoted
            if block!=definition.children:fail(t[0].span,'Container requires : and children' if definition.children else 'Leaf component must not have a block')
            args=t[1:-1] if block else t[1:];props={}
            if args and args[0].quoted and definition.positional:
                props[definition.positional]=Property(args[0].value,args[0].span);args=args[1:]
            params={**COMMON,**definition.parameters,'variant':Parameter(choice(*definition.variants))}
            extra=properties(args,params)
            if set(extra)&set(props):fail(t[0].span,'Duplicate positional parameter')
            props.update(extra)
            for key in definition.required:
                if key not in props:fail(t[0].span,'Missing required parameter '+key)
                try:params[key].validate(props[key].value)
                except ValueError as exc:fail(props[key].span,str(exc))
            if kind in ('heading','link','button','code') and not props['text'].value.strip():fail(t[0].span,'Accessible text must not be empty')
            pos+=1;desc=()
            if block:
                desc,pos=body(pos,indent+4)
                if not desc:fail(t[0].span,'Empty component block')
            children.append(Component(kind,props,tuple(desc),t[0].span))
        return tuple(children),pos
    while i<len(lex):
        depth,t,n=lex[i]
        if depth:fail(Span(n,depth+1),'Unexpected indentation')
        if t[0].value=='theme':
            header(i,'theme',2)
            if t[1].value!=':' or theme_seen:fail(t[0].span,'Expected a unique theme block')
            theme_seen=True;i+=1;count=0;theme_keys=set()
            while i<len(lex) and lex[i][0]>0:
                d,v,k=lex[i]
                if d!=4 or len(v)!=2 or v[0].value not in THEME:fail(Span(k,d+1),'Invalid theme token')
                key=v[0].value
                if key in theme_keys:fail(v[0].span,'Duplicate theme token '+key)
                theme_keys.add(key)
                try:
                    c=color(v[1].value)
                    if not c.startswith('#'):raise ValueError('Theme definitions require opaque hex colors')
                except ValueError as exc:fail(v[1].span,str(exc))
                theme[key]=c;count+=1;i+=1
            if not count:fail(t[0].span,'Empty theme block')
        elif t[0].value=='style':
            header(i,'style',3)
            if t[-1].value!=':':fail(t[-1].span,'Expected :')
            name=t[1].value
            try:identifier(name)
            except ValueError as exc:fail(t[1].span,str(exc))
            if name in styles:fail(t[1].span,'Duplicate style '+name)
            i+=1;props={}
            while i<len(lex) and lex[i][0]>0:
                d,v,k=lex[i]
                if d!=4:fail(Span(k,d+1),'Style properties require 4-space indentation')
                parsed=properties(v,STYLE_PARAMETERS)
                if len(parsed)!=1:fail(v[0].span,'One property per style line')
                if set(parsed)&set(props):fail(v[0].span,'Duplicate style property')
                props.update(parsed);i+=1
            if not props:fail(t[0].span,'Empty style block')
            styles[name]=Style(name,props,t[0].span)
        elif t[0].value=='page':
            header(i,'page',5)
            if t[2].value!='at' or not t[3].quoted or t[4].value!=':':fail(t[0].span,'Expected page name at "/path/":')
            try:name=identifier(t[1].value);path=route(t[3].value)
            except ValueError as exc:fail(t[1].span,str(exc))
            if any(p.name==name or p.path==path for p in pages):fail(t[1].span,'Duplicate page name or path')
            i+=1;meta={}
            while i<len(lex) and lex[i][0]==4 and lex[i][1][0].value in ('title','description','lang'):
                _,v,k=lex[i]
                if len(v)!=2 or v[0].value in meta:fail(v[0].span,'Invalid or duplicate page metadata')
                key=v[0].value
                if key!='lang' and not v[1].quoted:fail(v[1].span,'Metadata requires quoted text')
                try:meta[key]=text(v[1].value)
                except ValueError as exc:fail(v[1].span,str(exc))
                i+=1
            if not meta.get('title','').strip():fail(t[0].span,'Page requires a title')
            lang=meta.get('lang','en')
            if not re.fullmatch(r'[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*',lang) or len(lang)>35:fail(t[0].span,'Invalid page language')
            children,i=body(i,4)
            if not children:fail(t[0].span,'Empty page')
            pages.append(Page(name,path,meta['title'],meta.get('description',''),lang,children,t[0].span))
        else:fail(t[0].span,'Expected theme, style or page in site mode')
    if not pages or not any(p.path=='/' for p in pages):fail(first[0].span,'Site requires a page at /')
    site=Site(first[1].value,theme,styles,tuple(pages));ids={}
    for page in pages:
        root=page.children
        for index,node in enumerate(root):
            if node.kind=='navbar' and index!=0:
                fail(node.span,'Navbar must be the first top-level component')
            if node.kind=='footer' and index!=len(root)-1:
                fail(node.span,'Footer must be the last top-level component')
            if node.kind in ('navbar','footer') and sum(n.kind==node.kind for n in root)>1:
                fail(node.span,'Only one '+node.kind+' is allowed per page')
            for nested in walk(node.children):
                if nested.kind in ('navbar','footer'):
                    fail(nested.span,'Navbar and footer must be top-level components')
    for page in pages:
        ids[page.path]={'content'};h1=0;previous=0
        for node in walk(page.children):
            props=resolved(node,site)
            if 'id' in props:
                if props['id'] in ids[page.path]:fail(node.span,'Duplicate or reserved id '+props['id'])
                ids[page.path].add(props['id'])
            if node.kind=='heading':
                level=props.get('level',1 if previous==0 else 2)
                if level>previous+1:fail(node.span,'Heading levels must not skip a level')
                node.properties.setdefault('level',Property(level,node.span));previous=level;h1+=level==1
        if h1!=1:fail(page.span,'Each page requires exactly one h1')
    for page in pages:
        for node in walk(page.children):
            props=resolved(node,site)
            if 'to' not in props:continue
            url=urlsplit(props['to'])
            if url.scheme:continue
            target=url.path or page.path
            if target not in ids:fail(node.span,'Unknown site route '+target)
            if url.fragment and url.fragment not in ids[target]:fail(node.span,'Unknown anchor '+url.fragment)
    return site
