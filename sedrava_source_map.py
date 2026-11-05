"""Character-level original-source provenance, retained through lexical lowering."""
from pathlib import Path
import re
_ERROR=re.compile(r'^Line ([1-9][0-9]*):(?: column ([1-9][0-9]*):)?[ ]*(.*)',re.S)
class Origin(tuple):
    def __new__(cls,path,line,columns=None):
        value=super().__new__(cls,(path,line));value.columns=tuple(columns) if columns is not None else None;return value
    def column(self,col):
        return self.columns[min(max(col-1,0),len(self.columns)-1)]+1 if self.columns else col
class MappedLine(str):
    def __new__(cls,text,columns=None):
        value=super().__new__(cls,text);value.columns=tuple(range(len(text)+1)) if columns is None else tuple(columns)
        if len(value.columns)!=len(text)+1:raise ValueError('Character provenance length mismatch')
        return value
    def __getitem__(self,key):
        result=super().__getitem__(key)
        if isinstance(key,slice):
            start,end,step=key.indices(len(self))
            if step==1:return MappedLine(result,self.columns[start:end]+(self.columns[end],))
        return result
    def __add__(self,other):
        cols=other.columns if isinstance(other,MappedLine) else (self.columns[-1],)*(len(other)+1)
        return MappedLine(str(self)+str(other),self.columns[:-1]+cols)
    def __radd__(self,other):
        return MappedLine(str(other)+str(self),(self.columns[0],)*len(other)+self.columns)
def replace_span(line,start,end,value):
    line=line if isinstance(line,MappedLine) else MappedLine(line)
    return MappedLine(str(line[:start])+value+str(line[end:]),line.columns[:start]+(line.columns[start],)*len(value)+line.columns[end:])
def origin_for(line,origin):return Origin(*origin,getattr(line,'columns',getattr(origin,'columns',None)))
class ExpandedSource(str):
    def __new__(cls,text,origins):
        value=super().__new__(cls,text);value.origins=tuple(origins);return value
class LocatedError(ValueError):
    def __init__(self,message,source,line,column=None,expanded=None):
        self.message=message;self.source=str(source);self.line=line;self.column=column
        super().__init__(f'{source}:{line}'+(f':{column}' if column else '')+f': {message}'+(f' (expanded line {expanded})' if expanded else ''))
def locations(source,source_path):
    path=Path(source_path).resolve() if source_path else None
    return tuple(Origin(path,i) for i,_ in enumerate(source.splitlines(),1))
def source_error(exc,source_map):
    if isinstance(exc,LocatedError):return exc
    match=_ERROR.match(str(exc))
    if not match or int(match[1])>len(source_map):return exc
    number=int(match[1]);origin=source_map[number-1];path,line=origin
    if path is None:return exc
    col=int(match[2]) if match[2] else 1
    if col is not None and isinstance(origin,Origin):col=origin.column(col)
    return LocatedError(match[3],path,line,col,number)
def mapped_lines(source,origins):
    return [MappedLine(line,getattr(origin,'columns',None)) for line,origin in zip(source.splitlines(),origins)]
