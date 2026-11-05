"""Kotlin/Compose navigation adapter sharing the existing emitted domain model."""
from dataclasses import replace
from android_codegen_v03 import generate, kt, quoted as q, platform_persistence


def navigation_functions(program):
    names={key:'domain.sdr_'+key for key in program.states}
    for key,expr in program.derived.items(): names[key]='('+kt(expr,names)+')'
    initial=q(program.initial_screen)
    lines=[
        'internal data class SdrSession(val state: SedravaState = SedravaState(), val stack: List<String> = listOf('+initial+'))',
        'internal fun screenVisible(domain: SedravaState, screen: String): Boolean = try { when(screen) {',
    ]
    for screen in program.screens.values(): lines.append('  '+q(screen.name)+' -> '+(kt(screen.guard,names) if screen.guard else 'true'))
    lines += ['  else -> false', '} } catch (_: IllegalArgumentException) { false } catch (_: ArithmeticException) { false }',
              'internal fun validStack(stack: List<String>): Boolean = stack.size in 1..32 && stack.first()=='+initial+' && stack.all { it in setOf('+','.join(q(k) for k in program.screens)+') }',
              'internal fun normalizeSession(domain: SedravaState, original: List<String>): SdrSession { var stack=original.toList(); while(stack.size>1 && !screenVisible(domain,stack.last())) stack=stack.dropLast(1);return SdrSession(domain,stack) }',
              'internal fun initialSession(domain: SedravaState = SedravaState()): SdrSession { require(validState('+','.join('domain.sdr_'+k for k in program.states)+'));return SdrSession(domain,listOf('+initial+')) }',
              'internal fun restoreSession(domain: SedravaState, stack: List<String>): SdrSession { val initial=initialSession(domain);return if(validStack(stack)) normalizeSession(domain,stack) else initial }',
              'internal fun dispatchSession(current: SdrSession, command: String): SdrSession {',
              '  if(!validStack(current.stack) || !validState('+','.join('current.state.sdr_'+k for k in program.states)+')) return current',
              '  var domain=current.state; var stack=current.stack.toList()',
              '  when(command) {',
              '    "\\$back" -> if(stack.size>1) stack=stack.dropLast(1)',
    ]
    for binding in program.navigation.values():
        lines += ['    '+q(binding.name)+' -> {']
        if binding.action: lines += ['      val next=transitionState(domain,'+q(binding.action)+'); if(next===domain) return current;domain=next']
        if binding.target=='pop': lines += ['      if(stack.size>1) stack=stack.dropLast(1)']
        else: lines += ['      if(stack.size>=32 || !screenVisible(domain,'+q(binding.target)+')) return current', '      stack=stack+'+q(binding.target)]
        lines += ['    }']
    for action in program.actions:
        lines += ['    '+q(action)+' -> { val next=transitionState(domain,command);if(next===domain)return current;domain=next }']
    lines += ['    else -> return current', '  }','  return normalizeSession(domain,stack)','}',
              'internal fun editSession(current: SdrSession, key: String, value: Any?): SdrSession { if(!validStack(current.stack))return current;val next=editState(current.state,key,value);return if(next===current.state) current else normalizeSession(next,current.stack) }',
              'internal fun selectItem(current: SdrSession, collection: String, key: String, id: Int, command: String? = null): SdrSession {',
              '  val exists=when(collection) {']
    from sedrava_records import ListValue
    for key,value in program.states.items():
        if isinstance(value,ListValue): lines.append('    '+q(key)+' -> current.state.sdr_'+key+'.items.any { it.id==id }')
    lines += ['    else -> false','  }',
              '  if(!exists || key !in setOf<String>('+','.join(q(k) for k,v in program.states.items() if type(v) is int)+'))return current',
              '  val selected=editSession(current,key,id);if(selected===current)return current',
              '  if(command==null)return selected',
              '  val next=dispatchSession(selected,command);return if(next===selected)current else next','}']
    lines += ['internal fun restoreSessionSnapshot(saved: List<String>, fallback: SedravaState): SdrSession = try { if(saved.isEmpty()) initialSession(fallback) else restoreSession(restoreSnapshot(saved[0],true),saved.drop(1)) } catch (_: IllegalArgumentException) { initialSession(fallback) }']
    return '\n'.join(lines)+'\n'


def generate_navigation(source, output, program, application_id=None):
    target=generate(source,output,_program=replace(program,widgets=(("text",program.name),)),_domain_only=True, application_id=application_id)
    base=target.read_text(encoding='utf-8')+'\n'.join(platform_persistence(program))+'\n'
    imports='''import androidx.activity.compose.BackHandler
import androidx.compose.runtime.saveable.Saver
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.contentDescription
'''
    base=base.replace('import android.os.Bundle','import android.os.Bundle\n'+imports)
    names={key:'session.state.sdr_'+key for key in program.states}
    for key,expr in program.derived.items(): names[key]='('+kt(expr,names)+')'
    ui=['private fun sessionSaver(fallback: SedravaState) = Saver<SdrSession,ArrayList<String>>(',
        '  save={ arrayListOf(snapshotState(it.state,true)).apply { addAll(it.stack) } },',
        '  restore={ restoreSessionSnapshot(it,fallback) }',
        ')',
        'class MainActivity : ComponentActivity() { override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState);setContent { MaterialTheme(colorScheme=lightColorScheme(primary=Color(0xFF245D4E),onPrimary=Color.White,background=Color(0xFFF4F3EE),surface=Color(0xFFFFFEFA))) { NavigationScreen() } } } }',
        '@Composable fun NavigationScreen() {',
        '  val context=LocalContext.current',
        '  val prefs=remember { context.getSharedPreferences("sedrava_state",android.content.Context.MODE_PRIVATE) }',
        '  val restored=remember { restoreState(prefs.all) }',
        '  var session by rememberSaveable(stateSaver=sessionSaver(restored)) { mutableStateOf(initialSession(restored)) }',
        '  var error by remember { mutableStateOf(if(prefs.all.isNotEmpty() && !snapshotValid(prefs.all["snapshot"])) "Saved data rejected; original retained." else "") }',
        '  var invalidFields by remember { mutableStateOf(setOf<String>()) }',
        '  val commit: (SdrSession)->Boolean = { next ->',
        '    if(next===session) { error="Could not complete this action. Check the task, title and list capacity.";false } else {',
        '      if(next.stack!=session.stack) invalidFields=emptySet()',
        '      session=next;error=""',
    ]
    if program.persistent: ui.append('      if(!persistState(prefs,next.state)) error="Could not save your changes on this device."')
    ui += ['      true','    }','  }',
           '  BackHandler(enabled=session.stack.size>1) { commit(dispatchSession(session,"\\$back")) }',
           '  val active=session.stack.last();val focus=remember { FocusRequester() }; val focusManager=LocalFocusManager.current',
           '  LaunchedEffect(session.stack) { focusManager.clearFocus(force=true);focus.requestFocus() }',
           '  Box(Modifier.fillMaxSize().safeDrawingPadding().imePadding().background(MaterialTheme.colorScheme.background)) {',
           '    Column(Modifier.widthIn(max=800.dp).fillMaxWidth().align(Alignment.TopCenter).verticalScroll(rememberScrollState()).padding(24.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {',
           '      Text('+q(program.name)+',style=MaterialTheme.typography.titleMedium,color=MaterialTheme.colorScheme.primary,fontWeight=FontWeight.Bold)',
           '      if(error.isNotEmpty()) Text(error,color=MaterialTheme.colorScheme.error,modifier=Modifier.testTag("action-error").semantics { liveRegion=LiveRegionMode.Polite })',
           '      key(active) { when(active) {']
    for screen in program.screens.values():
        texts=[w for w in screen.widgets if w.kind=='text']
        title=texts[0].args[0] if texts else screen.name
        subtitle=texts[1].args[0] if len(texts)>1 else None
        ui += ['        '+q(screen.name)+' -> {',
               '          Text('+q(title)+',fontFamily=FontFamily.Serif,fontSize=38.sp,lineHeight=42.sp,modifier=Modifier.testTag('+q('screen-'+screen.name)+').focusRequester(focus).focusable().semantics { heading() })']
        if subtitle: ui.append('          Text('+q(subtitle)+',color=Color(0xFF526459),style=MaterialTheme.typography.bodyLarge)')
        ui += ['          Surface(shape=RoundedCornerShape(24.dp),color=MaterialTheme.colorScheme.surface,shadowElevation=2.dp) {',
               '            Column(Modifier.fillMaxWidth().padding(20.dp),verticalArrangement=Arrangement.spacedBy(14.dp)) {']
        for index,w in enumerate(screen.widgets):
            args=w.args;pad='              '
            if w.kind=='text':
                if w not in texts[:2]: ui.append(pad+'Text('+q(args[0])+')')
                continue
            if w.kind.startswith('input'):
                key=args[0]; label=args[1] if len(args)>1 else (program.display_names or {}).get(key,key)
                ident=screen.name+':'+str(index)
                ui += [pad+'NavigationInput('+q(key)+','+q(label)+','+names[key]+'.toString(),'+str(w.kind=='input_text').lower()+',onInvalid={ bad -> invalidFields=if(bad) invalidFields+'+q(ident)+' else invalidFields-'+q(ident)+' }) { value -> commit(editSession(session,'+q(key)+',value)) }']
            elif w.kind=='button':
                binding=program.navigation.get(args[1]); allow_invalid=bool(binding and not binding.action)
                ui += [pad+'Button(enabled='+('true' if allow_invalid else 'invalidFields.isEmpty()')+',onClick={ commit(dispatchSession(session,'+q(args[1])+')) },modifier=Modifier.fillMaxWidth().heightIn(min=48.dp),shape=RoundedCornerShape(14.dp)) { Text('+q(args[0])+') }']
            elif w.kind=='display':
                ui += [pad+'Text(try { '+kt(args[0],names)+'.toString() } catch (_: IllegalArgumentException) { "Unavailable" } catch (_: ArithmeticException) { "Unavailable" },style=MaterialTheme.typography.headlineSmall,fontFamily=FontFamily.Serif)']
            elif w.kind=='value': ui += [pad+'Text('+q((program.display_names or {}).get(args[0],args[0])+': ')+'+'+names[args[0]]+'.toString())']
            elif w.kind=='show_text': ui += [pad+'if('+names[args[0]]+') Text('+q(args[1])+',color=Color(0xFF526459))']
            elif w.kind in ('list','list_open'):
                collection,selected=args[:2];command=args[2] if w.kind=='list_open' else None;title_field=args[3] if w.kind=='list_open' else None;status_field=args[4] if w.kind=='list_open' else None
                label='row.record.sdr_'+title_field if title_field else 'row.record.fields().entries.joinToString(" · ") { it.key+": "+it.value.toString() }'
                description='contentDescription='+q('Open ' if command else 'Select ')+'+rowTitle'+('; stateDescription=if(row.record.sdr_'+status_field+') "Completed" else "In progress"' if status_field else '')
                ui += [pad+'for(row in '+names[collection]+'.items) { key(row.id) {',
                       pad+'  val rowTitle='+label,
                       pad+'  Card(enabled=invalidFields.isEmpty(),onClick={ commit(selectItem(session,'+q(collection)+','+q(selected)+',row.id,'+(q(command) if command else 'null')+')) },modifier=Modifier.fillMaxWidth().testTag("item-"+row.id).semantics { '+description+' },shape=RoundedCornerShape(16.dp),colors=CardDefaults.cardColors(containerColor=Color(0xFFF1F5ED))) {',
                       pad+'    Column(Modifier.fillMaxWidth().padding(18.dp),verticalArrangement=Arrangement.spacedBy(5.dp)) {',
                       pad+'      Text(rowTitle,style=MaterialTheme.typography.titleMedium)']
                if status_field: ui.append(pad+'      Text(if(row.record.sdr_'+status_field+') "Completed" else "In progress",style=MaterialTheme.typography.labelMedium,color=Color(0xFF526459))')
                ui += [pad+'    }',pad+'  }',pad+'} }']
        ui += ['            }','          }','        }']
    ui += ['      } }','      Text("Offline by design. A little progress, every day.",style=MaterialTheme.typography.labelSmall,color=Color(0xFF526459))','    }','  }','}',
           '@Composable private fun NavigationInput(key: String,label: String,value: String,text: Boolean,onInvalid: (Boolean)->Unit,onValue: (Any?)->Boolean) {',
           '  var draft by remember(key) { mutableStateOf(value) };var invalid by remember(key) { mutableStateOf(false) }',
           '  LaunchedEffect(value) { draft=value;invalid=false;onInvalid(false) }',
           '  OutlinedTextField(value=draft,onValueChange={ raw -> draft=raw;val parsed:Any?=if(text) raw else raw.trim().takeIf { it.matches(Regex("-?[0-9]+")) }?.toIntOrNull();invalid=!onValue(parsed);onInvalid(invalid) },label={ Text(label) },isError=invalid,supportingText={ if(invalid)Text("Enter a valid value that satisfies the app rules.") },modifier=Modifier.fillMaxWidth().testTag("input-"+key),shape=RoundedCornerShape(14.dp),keyboardOptions=KeyboardOptions(keyboardType=if(text)KeyboardType.Text else KeyboardType.Number))',
           '}']
    target.write_text(base+navigation_functions(program)+'\n'.join(ui)+'\n',encoding='utf-8')
    return target
