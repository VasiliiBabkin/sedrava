"""Small deterministic scalar library; identical contracts in Python, JS and Kotlin."""
import datetime
import re

SIGNATURES={
    'text_length':((str,),int), 'trim':((str,),str), 'lower_ascii':((str,),str),
    'contains':((str,str),bool), 'concat':((str,str),str),
    'is_date':((str,),bool),'date_days':((str,),int),'date_add':((str,int),str),
    'text_at':((str,int),str), 'text_slice':((str,int,int),str),
    'text_index':((str,str),int), 'unicode_ord':((str,),int),
    'unicode_chr':((int,),str),
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
    if name=='text_at':
        value,index=args
        if not 0<=index<len(value):raise ValueError('Text index outside Unicode scalar bounds')
        return value[index]
    if name=='text_slice':
        value,start,end=args
        if not 0<=start<=end<=len(value):raise ValueError('Invalid Unicode scalar slice bounds')
        return value[start:end]
    if name=='text_index':return args[0].find(args[1])
    if name=='unicode_ord':
        if len(args[0])!=1:raise ValueError('unicode_ord needs exactly one Unicode scalar')
        return ord(args[0])
    if name=='unicode_chr':
        number=args[0]
        if not 0<=number<=0x10ffff or 0xd800<=number<=0xdfff:
            raise ValueError('Invalid Unicode scalar number')
        return chr(number)
    if name=='is_date':
        try:civil_date(args[0]);return True
        except ValueError:return False
    value=civil_date(args[0]);days=(value-datetime.date(1970,1,1)).days
    if name=='date_days':return days
    result=days+args[1]
    if not -719162<=result<=2932896:raise ValueError('Date outside 0001..9999')
    return (datetime.date(1970,1,1)+datetime.timedelta(days=result)).isoformat()

JS_RUNTIME=r'''
function sdrDate(value){const m=/^([0-9]{4})-([0-9]{2})-([0-9]{2})$/.exec(value);if(!m||m[0]!==value)throw RangeError('Expected YYYY-MM-DD');const y=Number(m[1]),month=Number(m[2]),day=Number(m[3]);const d=new Date(0);d.setUTCFullYear(y,month-1,day);if(y<1||y>9999||d.getUTCFullYear()!==y||d.getUTCMonth()!==month-1||d.getUTCDate()!==day)throw RangeError('Invalid civil date');return d;}
function sdrIsDate(value){try{sdrDate(value);return true;}catch(_){return false;}}
function sdrDateDays(value){return sdrDate(value).valueOf()/86400000;}
function sdrDateAdd(value,n){const days=sdrDateDays(value)+n;if(days< -719162||days>2932896)throw RangeError('Date outside 0001..9999');return new Date(days*86400000).toISOString().slice(0,10);}
function sdrConcat(a,b){const result=a+b;if(!validText(result))throw RangeError('Text limit');return result;}
function sdrTextAt(value,index){const chars=Array.from(value);if(!Number.isInteger(index)||index<0||index>=chars.length)throw RangeError('Text index outside Unicode scalar bounds');return chars[index];}
function sdrTextSlice(value,start,end){const chars=Array.from(value);if(!Number.isInteger(start)||!Number.isInteger(end)||start<0||start>end||end>chars.length)throw RangeError('Invalid Unicode scalar slice bounds');return chars.slice(start,end).join('');}
function sdrTextIndex(value,needle){const offset=value.indexOf(needle);return offset<0?-1:Array.from(value.slice(0,offset)).length;}
function sdrUnicodeOrd(value){const chars=Array.from(value);if(chars.length!==1)throw RangeError('unicode_ord needs exactly one Unicode scalar');return chars[0].codePointAt(0);}
function sdrUnicodeChr(value){if(!Number.isInteger(value)||value<0||value>0x10ffff||(value>=0xd800&&value<=0xdfff))throw RangeError('Invalid Unicode scalar number');return String.fromCodePoint(value);}
'''

KT_RUNTIME=r'''
internal fun sdrScalars(value:String):List<String> {val out=mutableListOf<String>();var i=0;while(i<value.length){val cp=value.codePointAt(i);out.add(String(Character.toChars(cp)));i+=Character.charCount(cp)};return out}

internal fun sdrTextLength(value:String):Int = value.codePointCount(0,value.length)
internal fun sdrTextAt(value:String,index:Int):String {val count=value.codePointCount(0,value.length);require(index>=0&&index<count){"Text index outside Unicode scalar bounds"};val at=value.offsetByCodePoints(0,index);return String(Character.toChars(value.codePointAt(at)))}
internal fun sdrTextSlice(value:String,start:Int,end:Int):String {val count=value.codePointCount(0,value.length);require(start>=0&&start<=end&&end<=count){"Invalid Unicode scalar slice bounds"};return value.substring(value.offsetByCodePoints(0,start),value.offsetByCodePoints(0,end))}
internal fun sdrTextIndex(value:String,needle:String):Int {val at=value.indexOf(needle);return if(at<0) -1 else value.codePointCount(0,at)}
internal fun sdrUnicodeOrd(value:String):Int {require(value.codePointCount(0,value.length)==1){"unicode_ord needs exactly one Unicode scalar"};return value.codePointAt(0)}
internal fun sdrUnicodeChr(value:Int):String {require(value>=0&&value<=0x10ffff&&value !in 0xd800..0xdfff){"Invalid Unicode scalar number"};return String(Character.toChars(value))}
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
      'text_at':lambda:'sdrTextAt('+','.join(args)+')',
      'text_slice':lambda:'sdrTextSlice('+','.join(args)+')',
      'text_index':lambda:'sdrTextIndex('+','.join(args)+')',
      'unicode_ord':lambda:'sdrUnicodeOrd('+','.join(args)+')',
      'unicode_chr':lambda:'sdrUnicodeChr('+','.join(args)+')',
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
      'text_at':lambda:'sdrTextAt('+','.join(args)+')',
      'text_slice':lambda:'sdrTextSlice('+','.join(args)+')',
      'text_index':lambda:'sdrTextIndex('+','.join(args)+')',
      'unicode_ord':lambda:'sdrUnicodeOrd('+','.join(args)+')',
      'unicode_chr':lambda:'sdrUnicodeChr('+','.join(args)+')',
    }[name]()
