"""Deterministic presentation queries. They never mutate collection identity/state."""
def query_rows(rows, *, search='', title=None, sort=None, where=None, equals=False, active=True):
    result=list(rows)
    if where and active: result=[r for r in result if type(r[where]) is type(equals) and r[where] == equals]
    if search:
        needle=search.lower()
        def string(value):return ('true' if value else 'false') if type(value) is bool else str(value)
        result=[r for r in result if needle in (string(r[title]) if title else ' · '.join(k+': '+string(v) for k,v in r.items() if k!='id')).lower()]
    if sort: result.sort(key=lambda row:row[sort])
    return result

QUERY_JS = r'''
function queryRows(rows, config){
  let result=[...rows];
  if(config.where && config.active)result=result.filter(row=>row[config.where]===config.equals);
  if(config.search){const needle=config.search.toLowerCase();result=result.filter(row=>(config.title?String(row[config.title]):Object.entries(row).filter(([k])=>k!=='id').map(([k,v])=>k+': '+String(v)).join(' · ')).toLowerCase().includes(needle));}
  function compare(a,b){if(typeof a!=='string')return a<b?-1:a>b?1:0;const x=Array.from(a,c=>c.codePointAt(0)),y=Array.from(b,c=>c.codePointAt(0));for(let i=0;i<Math.min(x.length,y.length);i++){if(x[i]!==y[i])return x[i]<y[i]?-1:1;}return x.length-y.length;}
  if(config.sort)result.sort((a,b)=>compare(a[config.sort],b[config.sort]));return result;
}
'''
