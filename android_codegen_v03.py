"""Sedrava Android backend: shared typed state semantics and Compose adapters."""
import argparse
import ast
from pathlib import Path
from sedrava_android_identity import application_id as resolve_id, prepare_identity, kotlin_path, write_title
from sedrava_records import ListValue,structured
from sedrava_sequences import ValueList,ValueListType
from sedrava_records_codegen import kt_support, kt_persistence
from sedrava_errors import Match
from sedrava_core import parse, run, Assign, If, Require, Let, Repeat, ForEach
from android_codegen import generate as scaffold

def kt(node, names):
    if isinstance(node,ast.List) and hasattr(node,'literal_kind'):
        from sedrava_functions import kotlin_type
        return 'SdrVector<'+kotlin_type(node.literal_kind.element)+'>(capacity='+str(node.literal_kind.capacity)+',items=listOf('+','.join(kt(item,names) for item in node.elts)+'))'
    if isinstance(node, ast.Subscript):
        base=kt(node.value,names)
        kind=node.subscript_kind
        if isinstance(node.slice,ast.Slice):
            start=kt(node.slice.lower,names)
            end=kt(node.slice.upper,names)
            return ('sdrTextSlice' if kind is str else 'sdrVector_list_slice' if isinstance(kind,ValueListType) else 'sdr_list_slice')+'('+','.join((base,start,end))+')'
        index=kt(node.slice,names)
        return ('sdrTextAt' if kind is str else 'sdrVector_list_at' if isinstance(kind,ValueListType) else 'sdr_list_at')+'('+','.join((base,index))+')'
    if isinstance(node, ast.Attribute): return '(' + kt(node.value, names) + ').sdr_' + node.attr
    if isinstance(node, ast.Call):
        if hasattr(node,'error_type'):
            fields={kw.arg:kw.value for kw in node.keywords}
            return 'SdrTypedError('+quoted(node.error_type.identity+'.'+node.error_variant)+','+quoted(node.error_variant)+',mapOf<String,Any>('+','.join(quoted(key)+' to '+kt(fields[key],names) for key,_ in node.error_fields)+'))'
        if hasattr(node,"result_operation"):
            from sedrava_results import kt as result_emit
            return result_emit(node,[kt(arg,names) for arg in node.args])
        if hasattr(node,"collection_query"):
            from sedrava_queries import kt_query
            return kt_query(node,kt,names)
        if hasattr(node,"pure_builtin"):
            from sedrava_stdlib import kt_call
            return kt_call(node.pure_builtin,[kt(arg,names) for arg in node.args])
        if hasattr(node,'pure_function'):
            function=node.pure_function
            params={key:'_sdr_arg'+str(i) for i,(key,_) in enumerate(function.parameters)}
            from sedrava_functions import kotlin_type as parameter_kind
            declaration=','.join(params[key]+':'+parameter_kind(kind) for key,kind in function.parameters)
            return '({'+declaration+' -> '+kt(function.body,params)+'})('+','.join(kt(arg,names) for arg in node.args)+')'

        if hasattr(node, 'record_type'): return 'SdrRecord_' + node.record_type.name + '(' + ','.join('sdr_'+k.arg+'='+kt(k.value,names) for k in node.keywords) + ')'
        return ('sdrVector_' if isinstance(node.collection_type,ValueListType) else 'sdr_')+node.func.id+'('+','.join(kt(a,names) for a in node.args)+')'
    if isinstance(node,ast.IfExp):return "(if ("+kt(node.test,names)+") "+kt(node.body,names)+" else "+kt(node.orelse,names)+")"
    if isinstance(node, ast.Constant):
        if type(node.value) is str: return quoted(node.value)
        return str(node.value).lower() if type(node.value) is bool else str(node.value)
    if isinstance(node, ast.Name): return names[node.id]
    if isinstance(node, ast.UnaryOp):
        return ("!(" + kt(node.operand, names) + ")" if isinstance(node.op, ast.Not) else "Math.negateExact(" + kt(node.operand, names) + ")")
    if isinstance(node, ast.BinOp):
        return f"Math.{ {ast.Add: 'addExact', ast.Sub: 'subtractExact', ast.Mult: 'multiplyExact'}[type(node.op)] }({kt(node.left,names)}, {kt(node.right,names)})"
    if isinstance(node, ast.BoolOp):
        op = " && " if isinstance(node.op, ast.And) else " || "
        return "(" + op.join(kt(v,names) for v in node.values) + ")"
    if isinstance(node, ast.Compare):
        op = {ast.Eq:"==", ast.NotEq:"!=", ast.Gt:">", ast.GtE:">=", ast.Lt:"<", ast.LtE:"<="}[type(node.ops[0])]
        return f"({kt(node.left,names)} {op} {kt(node.comparators[0],names)})"
    raise ValueError("Unsupported AST")

def quoted(value):
    escapes = {"\\": "\\\\", '"': '\\"', "$": "\\$", "\n": "\\n", "\r": "\\r", "\t": "\\t"}
    return '"' + "".join(escapes.get(char, "\\u%04x" % ord(char) if ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF or ord(char) in (0x2028, 0x2029) else char) for char in value) + '"'


def kind(value):
    if isinstance(value,ValueList):
        from sedrava_functions import kotlin_type
        return 'SdrVector<'+kotlin_type(value.kind.element)+'>'
    if isinstance(value, ListValue): return 'SdrList<SdrRecord_' + value.kind.record.name + '>'
    return {int:'Int',bool:'Boolean',str:'String'}[type(value)]


def literal(value):
    if isinstance(value,ValueList):return kind(value)+'(capacity='+str(value.kind.capacity)+',items=listOf('+','.join(literal(item) for item in value.items)+'))'
    if isinstance(value, ListValue): return 'SdrList<SdrRecord_' + value.kind.record.name + '>(capacity=' + str(value.kind.capacity) + ')'
    return quoted(value) if type(value) is str else str(value).lower()


def platform_persistence(program):
    lines=[]
    user={key:"sdr_"+key for key in program.states}
    if program.persistent:
        condition = '(prefs.all.isEmpty() || snapshotValid(prefs.all["snapshot"]))' if (structured(program)) else 'savedStateValid(prefs.all)'
        lines += ['internal fun persistState(prefs: android.content.SharedPreferences, state: SedravaState): Boolean = try {',
                  '  if (!'+condition+') false else prefs.edit().apply {']
        if structured(program):
            lines.append('    putString("snapshot", snapshotState(state))')
        else:
            for key in program.persistent:
                method={int:'putInt',bool:'putBoolean',str:'putString'}[type(program.states[key])]
                lines.append('    '+method+'('+quoted(key)+', state.'+user[key]+')')
        lines += ['  }.commit()', '} catch (_: Exception) { false }']
    return lines

def generate(source, output, _program=None, _domain_only=False, application_id=None):
    program = _program or parse(source)
    if program.has_navigation and _program is None:
        from sedrava_navigation_android import generate_navigation
        return generate_navigation(source, output, program, application_id=application_id)
    run(program)
    if not program.widgets:
        raise ValueError("Missing screen main")
    output = Path(output)
    package = resolve_id(program.name, application_id)
    prepare_identity(output, package, program.name)
    scaffold('app "Scaffold"\nstate ready = false\naction start: ready = true\nscreen main:\n    text "Scaffold"\n    button "Start" -> start\n', output, application_id=package)
    prepare_identity(output, package, program.name)
    write_title(output, program.name)
    from sedrava_unicode import required as needs_unicode
    if needs_unicode(program):
        from sedrava_unicode_data import LICENSE_TEXT
        notice=output/'app/src/main/res/raw/sedrava_unicode_license.txt'
        notice.parent.mkdir(parents=True,exist_ok=True);notice.write_text(LICENSE_TEXT,encoding='utf-8')
    target = kotlin_path(output)
    # One pure state adapter supplies both Compose callbacks and JVM conformance.
    kinds = {int: "Int", bool: "Boolean", str: "String"}
    keys = list(program.states)
    user = {key: "sdr_" + key for key in (*keys, *(program.derived or {}))}
    next_names = {key: "next_" + key for key in keys}
    for key, expr in (program.derived or {}).items():
        next_names[key] = "(" + kt(expr, next_names) + ")"
    params = ", ".join("next_" + key + ": " + kind(val) for key, val in program.states.items())
    next_args = ", ".join("next_" + key for key in keys)
    user_args = ", ".join(user[key] for key in keys)
    def state_args(prefix):
        return ", ".join(prefix + "." + user[key] for key in keys)
    guard = " && ".join(kt(rule, next_names) for rule in program.rules) or "true"
    from sedrava_stdlib import KT_RUNTIME
    from sedrava_results import KT_RUNTIME as RESULT_RUNTIME
    KT_RUNTIME+=RESULT_RUNTIME
    from sedrava_unicode import required as unicode_required,runtime as unicode_runtime
    if unicode_required(program):KT_RUNTIME+=unicode_runtime('kt')
    lines = [
        "package " + package,
        "import android.os.Bundle",
        "import androidx.activity.ComponentActivity",
        "import androidx.activity.compose.setContent",
        "import androidx.compose.foundation.layout.*",
        "import androidx.compose.foundation.rememberScrollState",
        "import androidx.compose.foundation.verticalScroll",
        "import androidx.compose.material3.*",
        "import androidx.compose.runtime.*",
        "import androidx.compose.runtime.saveable.rememberSaveable",
        "import androidx.compose.ui.Modifier",
        "import androidx.compose.ui.unit.dp",
        "import androidx.compose.ui.platform.LocalContext",
        "import androidx.compose.ui.semantics.semantics",
        "import androidx.compose.ui.semantics.heading",
        "import androidx.compose.foundation.text.KeyboardOptions",
        "import androidx.compose.ui.text.input.KeyboardType",
        "internal fun validText(value: String): Boolean {",
        "  var i = 0; var count = 0",
        "  while (i < value.length) {",
        "    val cp = Character.codePointAt(value, i)",
        "    if (cp in 0xD800..0xDFFF || ++count > 1024) return false",
        "    i += Character.charCount(cp)",
        "  }",
        "  return true",
        "}",
        'internal fun checkedText(value: String): String { require(validText(value)) { "Invalid text value" }; return value }',
        KT_RUNTIME,
        *kt_support(program, quoted),
        "internal " + ("data " if keys else "") + "class SedravaState(" + ", ".join("val " + user[key] + ": " + kind(val) + " = " + literal(val) for key, val in program.states.items()) + ")",
        "internal fun checkDerivedState(" + params + ") {",
    ]
    for key, val in program.states.items():
        if type(val) is str:
            lines.append("  checkedText(next_" + key + ")")
        elif isinstance(val, (ListValue,ValueList)):
            lines.append("  next_" + key + ".check(); require(next_" + key + ".capacity == " + str(val.kind.capacity) + ")")
    for key in (program.derived or {}):
        lines.append("  val checked_" + key + " = " + next_names[key])
    lines += ["}", "internal fun validState(" + params + "): Boolean = try {", "  checkDerivedState(" + next_args + ")", ("  snapshotState(SedravaState(" + next_args + "), true); " if (structured(program)) else "  ") + guard,
              "} catch (_: ArithmeticException) { false } catch (_: IllegalArgumentException) { false }",
              "internal fun restoreState(saved: Map<String, *>): SedravaState {"]
    if (structured(program)):
        lines += ['  return try { val raw=saved["snapshot"]; if(raw is String) restoreSnapshot(raw) else SedravaState() } catch (_: IllegalArgumentException) { SedravaState() }', '}',
                  'internal fun editState(state: SedravaState, key: String, value: Any?): SedravaState {', '  val next = when(key) {']
    else:
        for key, val in program.states.items():
            if key in program.persistent:
                lines.append("  val saved_" + key + " = saved[" + quoted(key) + "]")
                condition = "saved_" + key + " is " + kind(val)
                if type(val) is str:
                    condition += " && validText(saved_" + key + ")"
                lines.append("  val next_" + key + " = if (" + condition + ") saved_" + key + " else " + literal(val))
            else:
                lines.append("  val next_" + key + " = " + literal(val))
        lines += ["  return if (validState(" + next_args + ")) SedravaState(" + next_args + ") else SedravaState()", "}",
                  "internal fun editState(state: SedravaState, key: String, value: Any?): SedravaState {", "  val next = when (key) {"]
    for key, val in program.states.items():
        if isinstance(val, (ListValue,ValueList)): continue
        lines.append("    " + quoted(key) + " -> if (value is " + kind(val) + ") state.copy(" + user[key] + " = value) else return state")
    lines += ["    else -> return state", "  }", "  return if (validState(" + state_args("next") + ")) next else state", "}",
              "internal fun transitionState(state: SedravaState, action: String): SedravaState {",
              "  if (!validState(" + state_args("state") + ")) return state"]
    for key in keys:
        lines.append("  var next_" + key + " = state." + user[key])
    from sedrava_cost import MAX_ACTION_WORK,statement_work,base_work
    lines += ["  return try {",f"    var _sdr_workLeft={MAX_ACTION_WORK-base_work(program.derived,program.rules)}", "    fun _sdr_spend(n:Int){_sdr_workLeft-=n;require(_sdr_workLeft>=0){\"Action exceeds execution work limit\"}}", "    when (action) {"]
    def emit(body, depth, scope=None):
        scope=dict(next_names if scope is None else scope)
        for stmt in body:
            lines.append(" "*depth+"_sdr_spend("+str(statement_work(stmt,program.derived))+")")
            if isinstance(stmt, Let):
                local="_sdr_local_"+stmt.name
                lines.append(" "*depth+"val "+local+" = "+kt(stmt.expr,scope))
                scope[stmt.name]=local
            elif isinstance(stmt, Require):
                lines.append(' ' * depth + 'require(' + kt(stmt.condition, scope) + ')')
            elif isinstance(stmt, Assign):
                lines.append(" " * depth + scope[stmt.name] + " = " + kt(stmt.expr, scope))
                lines.append(" " * depth + "checkDerivedState(" + next_args + ")")
            elif isinstance(stmt,Match):
                from sedrava_functions import kotlin_type
                lines.extend([' '*depth+'run {',' '*(depth+2)+'val _sdr_match='+kt(stmt.expr,scope)])
                for index,arm in enumerate(stmt.arms):
                    cond='sdrResultOk(_sdr_match)' if arm.tag=='Ok' else '!sdrResultOk(_sdr_match)' if arm.tag=='Err' else '(!sdrResultOk(_sdr_match)&&_sdr_match.error?.variant=='+quoted(arm.tag)+')'
                    lines.append(' '*(depth+2)+('if' if index==0 else 'else if')+' ('+cond+') {')
                    payload='requireNotNull(_sdr_match.value)' if arm.tag=='Ok' else 'requireNotNull(_sdr_match.error)' if stmt.kind.error is not None else '_sdr_match.code'
                    inner=dict(scope)
                    fields=dict(dict(stmt.kind.error.variants).get(arm.tag,())) if stmt.kind.error else {}
                    for key,field in arm.bindings:
                        local='_sdr_pattern_'+key
                        value='('+payload+'.fields.getValue('+quoted(field)+') as '+kotlin_type(fields[field])+')' if field else payload
                        lines.append(' '*(depth+4)+'val '+local+'='+value);inner[key]=local
                    emit(arm.body,depth+4,inner);lines.append(' '*(depth+2)+'}')
                lines.append(' '*depth+'}')
            elif isinstance(stmt,ForEach):
                source=kt(stmt.collection,scope)
                snapshot='sdrScalars('+source+')' if stmt.kind is str else '('+source+').items.toList()'
                lines.append(' '*depth+'run {')
                lines.append(' '*(depth+2)+'val _sdr_eachValues='+snapshot)
                lines.append(' '*(depth+2)+'for((_sdr_eachIndex,_sdr_eachItem) in _sdr_eachValues.withIndex()){')
                item='_sdr_eachItem' if stmt.kind is str or isinstance(stmt.kind,ValueListType) else '_sdr_eachItem.record'
                lines.append(' '*(depth+4)+'val _sdr_eachValue='+item)
                inner={**scope,stmt.name:'_sdr_eachValue'}
                if stmt.index:inner[stmt.index]='_sdr_eachIndex'
                emit(stmt.body,depth+4,inner);lines.extend([' '*(depth+2)+'}',' '*depth+'}'])
            elif isinstance(stmt, Repeat):
                local="_sdr_repeat_"+stmt.name
                ordinal=local+"_ordinal"
                lines.append(" " * depth + "for (" + ordinal + " in 0 until " + str(stmt.count) + ") {")
                lines.append(" "*(depth+2)+"val "+local+" = ("+str(stmt.start)+"L+"+ordinal+".toLong()*("+str(stmt.step)+"L)).toInt()")
                emit(stmt.body, depth + 2, {**scope,stmt.name:local})
                lines.append(" " * depth + "}")
            elif isinstance(stmt, If):
                lines.append(" " * depth + "if (" + kt(stmt.condition, scope) + ") {")
                emit(stmt.yes, depth + 2, scope)
                if stmt.no:
                    lines.append(" " * depth + "} else {")
                    emit(stmt.no, depth + 2, scope)
                lines.append(" " * depth + "}")
    for key, body in program.actions.items():
        lines.append("      " + quoted(key) + " -> {")
        emit(body, 8)
        lines.append("      }")
    lines += ["      else -> return state", "    }", "    if (validState(" + next_args + ")) SedravaState(" + next_args + ") else state",
              "  } catch (_: ArithmeticException) { state } catch (_: IllegalArgumentException) { state }", "}"]
    if (structured(program)):
        lines += kt_persistence(program, quoted, literal)
    if program.persistent:
        if not (structured(program)):
            lines += ['internal fun savedStateValid(saved: Map<String, *>): Boolean {',
                      '  val restored=restoreState(saved)',
                      '  return saved.all { (key,value) -> when(key) {']
            for key in program.persistent:
                val=program.states[key]
                lines.append('    '+quoted(key)+' -> value is '+kind(val)+' && value == restored.'+user[key])
            lines += ['    else -> false', '  } }', '}']
    if not _domain_only:lines += platform_persistence(program)
    if _domain_only:
        target.write_text("\n".join(lines)+"\n",encoding="utf-8")
        return target
    lines += ["class MainActivity : ComponentActivity() {", "  override fun onCreate(savedInstanceState: Bundle?) {", "    super.onCreate(savedInstanceState)",
              "    setContent { MaterialTheme { SedravaScreen() } }", "  }", "}", "@Composable fun SedravaScreen() {"]
    if program.persistent:
        lines += ["  val context = LocalContext.current", '  val prefs = remember { context.getSharedPreferences("sedrava_state", android.content.Context.MODE_PRIVATE) }',
                  "  val restoredState = remember { restoreState(prefs.all) }"]
    else:
        lines.append("  val restoredState = remember { SedravaState() }")
    if (structured(program)):
        lines += ['  var savedSnapshot by rememberSaveable { mutableStateOf(snapshotState(restoredState, true)) }',
                  '  val recreatedState = remember { try { restoreSnapshot(savedSnapshot, true) } catch (_: IllegalArgumentException) { restoredState } }']
    for key in keys:
        if (structured(program)):
            lines.append("  var " + user[key] + " by remember { mutableStateOf(recreatedState." + user[key] + ") }")
            continue
        lines.append("  var " + user[key] + " by rememberSaveable { mutableStateOf(restoredState." + user[key] + ") }")
    if (structured(program)) and program.persistent:
        lines.append('  var actionError by remember { mutableStateOf(if (prefs.all.isNotEmpty() && !snapshotValid(prefs.all["snapshot"])) "Saved data rejected; original retained" else "") }')
    else:
        lines.append('  var actionError by remember { mutableStateOf('+('if (!savedStateValid(prefs.all)) "Saved data rejected; original retained" else ""' if program.persistent else '""')+') }')
    for key, expr in (program.derived or {}).items():
        lines.append("  val " + user[key] + " = " + kt(expr, user))
    lines += ["  Column(modifier = Modifier.fillMaxSize().safeDrawingPadding().imePadding().verticalScroll(rememberScrollState()).padding(24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {",
              '    if (actionError.isNotEmpty()) Text(actionError, color = MaterialTheme.colorScheme.error)']
    title_seen = False
    for widget in program.widgets:
        if widget[0] == "list":
            key, selected = widget[1:]
            lines += ["    for (row in " + user[key] + ".items) {", "      key(row.id) {", '        Text(row.record.fields().entries.joinToString(" · ") { it.key + ": " + it.value.toString() })', '        Button(onClick = {', "          val current=SedravaState(" + user_args + ")", '          val next=editState(current,' + quoted(selected) + ',row.id)', '          if(next !== current) {', '            ' + user[selected] + ' = next.' + user[selected], '            savedSnapshot = snapshotState(next, true)']
            if program.persistent: lines.append('            if (!persistState(prefs,next)) actionError = "Could not save state"')
            lines += ['          } else { actionError = "Selection rejected" }', '        }) { Text("Select / Выбрать") }', '      }', '    }']
        elif widget[0] == "text":
            style = "bodyLarge" if title_seen else "headlineLarge"
            semantics = "" if title_seen else ", modifier=Modifier.semantics { heading() }"
            lines.append("    Text(" + quoted(widget[1]) + ", style = MaterialTheme.typography." + style + semantics + ")")
            title_seen = True
        elif widget[0] == "value":
            lines.append("    Text(" + quoted((program.display_names or {}).get(widget[1],widget[1]) + ": ") + " + " + user[widget[1]] + ".toString())")
        elif widget[0] in ("input_int", "input_text"):
            key = widget[1]
            text = widget[0] == "input_text"
            parse_draft = "draft_" + key if text else 'draft_' + key + '.trim().takeIf { it.matches(Regex("-?[0-9]+")) }?.toIntOrNull()'
            parse_raw = "raw" if text else 'raw.trim().takeIf { it.matches(Regex("-?[0-9]+")) }?.toIntOrNull()'
            lines += ["    run {", "      val current = SedravaState(" + user_args + ")",
                      "      var draft_" + key + " by remember { mutableStateOf(" + user[key] + ".toString()) }",
                      "      LaunchedEffect(" + user[key] + ") { draft_" + key + " = " + user[key] + ".toString() }",
                      "      val parsed_" + key + " = " + parse_draft,
                      "      val valid_" + key + " = editState(current, " + quoted(key) + ", parsed_" + key + ") !== current",
                      "      val error_" + key + " = " + ("" if text else "draft_" + key + ".isNotEmpty() && ") + "!valid_" + key,
                      "      OutlinedTextField(value = draft_" + key + ", onValueChange = { raw ->",
                      "        draft_" + key + " = raw", "        val next = editState(current, " + quoted(key) + ", " + parse_raw + ")",
                      "        if (next !== current) {", "          " + user[key] + " = next." + user[key]]
            if (structured(program)):
                lines.append("          savedSnapshot = snapshotState(next, true)")
            if program.persistent:
                lines.append('          if (!persistState(prefs,next)) actionError = "Could not save state"' if (structured(program)) else '          if (!persistState(prefs,next)) actionError = "Could not save state; changes may be temporary"')
            message = "Text must contain at most 1024 Unicode scalar values and satisfy the declared rules" if text else "Value does not satisfy the declared rules"
            lines += ["        }", "      }, isError = error_" + key + ", supportingText = { if (error_" + key + ") Text(" + quoted(message) + ") }, modifier = Modifier.fillMaxWidth(), label = { Text(" + quoted((program.display_names or {}).get(key,key)) + ") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType." + ("Text" if text else "Number") + "))", "    }"]
        elif widget[0] == "show_text":
            lines.append("    if (" + user[widget[1]] + ") { Text(" + quoted(widget[2]) + ") }")
        else:
            _, label, action = widget
            lines += ["    Button(onClick = {", "      val current = SedravaState(" + user_args + ")", "      val next = transitionState(current, " + quoted(action) + ")",
                      "      if (next !== current) {"]
            for key in keys:
                lines.append("        " + user[key] + " = next." + user[key])
            if (structured(program)):
                lines.append("        savedSnapshot = snapshotState(next, true)")
            if program.persistent:
                lines.append('        actionError = if (persistState(prefs,next)) "" else "Could not save state"' if (structured(program)) else '        if (!persistState(prefs,next)) actionError = "Could not save state; changes may be temporary"')
            lines += [('' if program.persistent else '        actionError = ""'), '      } else { actionError = "Action rejected: constraints or arithmetic/value error" }', "    }, modifier=Modifier.fillMaxWidth().heightIn(min=48.dp)) { Text(" + quoted(label) + ") }"]
    lines += ["  }", "}"]
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target

if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("source")
    cli.add_argument("--application-id")
    cli.add_argument("--output",default="build/generated-android")
    args = cli.parse_args()
    print(generate(Path(args.source).read_text(encoding="utf-8"),args.output, application_id=args.application_id))
