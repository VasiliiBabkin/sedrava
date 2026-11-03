"""Small deterministic scalar library; identical contracts in Python, JS and Kotlin."""
import datetime
import re

SIGNATURES={
    'text_length':((str,),int), 'trim':((str,),str), 'lower_ascii':((str,),str),
    'contains':((str,str),bool), 'concat':((str,str),str),
    'is_date':((str,),bool),'date_days':((str,),int),'date_add':((str,int),str),
}


def civil_date(value):
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value):raise ValueError('Expected YYYY-MM-DD')
    try:return datetime.date.fromisoformat(value)
    except (ValueError,OverflowError) as exc:raise ValueError('Invalid civil date') from exc


def apply(name,args):
    if name=='text_length':return len(args[0])
    if name=='trim':return args[0].strip(' \t\r\n')
    if name=='lower_ascii':return args[0].translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'))
    if name=='contains':return args[1] in args[0]
    if name=='concat':return args[0]+args[1]
    if name=='is_date':
        try:civil_date(args[0]);return True
        except ValueError:return False
    value=civil_date(args[0]);days=(value-datetime.date(1970,1,1)).days
    if name=='date_days':return days
    result=days+args[1]
    if not -719162<=result<=2932896:raise ValueError('Date outside 0001..9999')
    return (datetime.date(1970,1,1)+datetime.timedelta(days=result)).isoformat()

JS_RUNTIME=r'''
function sdrDate(value){const m=/^([0-9]{4})-([0-9]{2})-([0-9]{2})$/.exec(value);if(!m)throw RangeError('Expected YYYY-MM-DD');const y=Number(m[1]),month=Number(m[2]),day=Number(m[3]);const d=new Date(0);d.setUTCFullYear(y,month-1,day);if(y<1||y>9999||d.getUTCFullYear()!==y||d.getUTCMonth()!==month-1||d.getUTCDate()!==day)throw RangeError('Invalid civil date');return d;}
function sdrIsDate(value){try{sdrDate(value);return true;}catch(_){return false;}}
function sdrDateDays(value){return sdrDate(value).valueOf()/86400000;}
function sdrDateAdd(value,n){const days=sdrDateDays(value)+n;if(days< -719162||days>2932896)throw RangeError('Date outside 0001..9999');return new Date(days*86400000).toISOString().slice(0,10);}
function sdrConcat(a,b){const result=a+b;if(!validText(result))throw RangeError('Text limit');return result;}
'''

KT_RUNTIME=r'''
internal fun sdrTextLength(value:String):Int = value.codePointCount(0,value.length)
internal fun sdrDate(value:String):java.time.LocalDate = try {
 require(Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}").matches(value))
 java.time.LocalDate.parse(value).also{require(it.year in 1..9999)}
} catch (_:java.time.DateTimeException){throw IllegalArgumentException("Invalid civil date")}
internal fun sdrIsDate(value:String):Boolean = try{sdrDate(value);true}catch(_:IllegalArgumentException){false}
internal fun sdrDateDays(value:String):Int = sdrDate(value).toEpochDay().toInt()
internal fun sdrDateAdd(value:String,n:Int):String = try {val result=sdrDate(value).plusDays(n.toLong());require(result.year in 1..9999);result.toString()}catch(_:java.time.DateTimeException){throw IllegalArgumentException("Invalid civil date")}
'''


def js_call(name,args):
    a=args[0]
    return {
      'text_length':lambda:'Array.from('+a+').length',
      'trim':lambda:'('+a+').replace(/^[ \\t\\r\\n]+|[ \\t\\r\\n]+$/g, "")',
      'lower_ascii':lambda:'('+a+').replace(/[A-Z]/g,c=>c.toLowerCase())',
      'contains':lambda:'('+a+').includes('+args[1]+')',
      'concat':lambda:'sdrConcat('+','.join(args)+')',
      'is_date':lambda:'sdrIsDate('+a+')','date_days':lambda:'sdrDateDays('+a+')',
      'date_add':lambda:'sdrDateAdd('+','.join(args)+')',
    }[name]()


def kt_call(name,args):
    a=args[0]
    return {
      'text_length':lambda:'sdrTextLength('+a+')',
      'trim':lambda:'('+a+").trim(' ', '\\t', '\\r', '\\n')",
      'lower_ascii':lambda:'('+a+').map{if(it in \'A\'..\'Z\') (it.code+32).toChar() else it}.joinToString("")',
      'contains':lambda:'('+a+').contains('+args[1]+')',
      'concat':lambda:'checkedText('+a+' + '+args[1]+')',
      'is_date':lambda:'sdrIsDate('+a+')','date_days':lambda:'sdrDateDays('+a+')',
      'date_add':lambda:'sdrDateAdd('+','.join(args)+')',
    }[name]()
