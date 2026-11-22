import android.app.Application
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import java.io.File
import java.io.IOException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    private lateinit var model: AppModel

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        model = ViewModelProvider(this)[AppModel::class.java]
        model.initialize(savedInstanceState)
        setContent { MaterialTheme { AppScreen(model) } }
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        model.saveSession(outState)
    }
}

internal class AppModel(app: Application) : AndroidViewModel(app) {
    var session by mutableStateOf(Session())
        private set
    var loading by mutableStateOf(true)
        private set
    var saving by mutableStateOf(false)
        private set
    var error by mutableStateOf("")
        private set

    private val store = SnapshotStore(File(app.filesDir, "sedrava-state.json")) {
        app.getSharedPreferences("sedrava_state", android.content.Context.MODE_PRIVATE).all
    }
    private var initialized = false
    private var blocked = false
    private var savedValues: SdrState = emptyMap()

    fun initialize(bundle: Bundle?) {
        if (initialized) return
        initialized = true
        viewModelScope.launch {
            val restored = if (persistent.isEmpty()) defaultState else {
                try {
                    withContext(Dispatchers.IO) { store.load() }
                } catch (_: IllegalArgumentException) {
                    blockStorage()
                } catch (_: IOException) {
                    blockStorage()
                } catch (_: SecurityException) {
                    blockStorage()
                }
            }
            savedValues = persisted(restored)
            session = if (blocked) Session(restored) else restoreConfiguration(
                restored, bundle?.getString("sdr-state"),
                bundle?.getStringArrayList("sdr-stack") ?: emptyList(),
            )
            loading = false
        }
    }

    private fun blockStorage(): SdrState {
        blocked = true
        error = "Saved data could not be read. The original data was retained."
        return defaultState
    }

    private fun persisted(state: SdrState): SdrState = state.filterKeys { it in persistent }

    fun saveSession(bundle: Bundle) {
        if (loading) return
        val raw = validated { snapshot(session.state, full = true) } ?: return
        bundle.putString("sdr-state", raw)
        bundle.putStringArrayList("sdr-stack", ArrayList(session.stack))
    }

    fun accept(next: Session?): Boolean {
        if (loading || saving) return false
        if (next == null) {
            error = "Change rejected by the app rules or limits."
            return false
        }
        val retained = persisted(next.state)
        // Keep a restorable configuration snapshot for every accepted session.
        if (validated { snapshot(next.state, full = true) } == null) {
            error = "The app state exceeds its storage limit."
            return false
        }
        if (retained == savedValues) {
            session = next
            if (!blocked) error = ""
            return true
        }
        if (blocked) {
            error = "Saved data was rejected. The original data was retained."
            return false
        }
        val raw = validated { snapshot(next.state) } ?: run {
            error = "The app state exceeds its storage limit."
            return false
        }
        saving = true
        viewModelScope.launch {
            try {
                withContext(Dispatchers.IO) { store.save(raw) }
                savedValues = retained
                session = next
                error = ""
            } catch (_: IOException) {
                error = "Could not save changes. The previous state was retained."
            } catch (_: IllegalArgumentException) {
                error = "Could not save changes. The previous state was retained."
            } catch (_: SecurityException) {
                error = "Could not save changes. The previous state was retained."
            } finally {
                saving = false
            }
        }
        return true
    }
}

@Composable
private fun AppScreen(model: AppModel) {
    val session = model.session
    BackHandler(enabled = session.stack.size > 1 || model.saving) {
        if (!model.saving) model.accept(dispatch(model.session, "\$back"))
    }
    Surface(Modifier.fillMaxSize()) {
        Box(Modifier.fillMaxSize().safeDrawingPadding().imePadding(), contentAlignment = Alignment.TopCenter) {
            if (model.loading) {
                Text("Loading saved data…", Modifier.padding(24.dp).semantics { liveRegion = LiveRegionMode.Polite })
            } else {
                key(session.stack.last()) { ScreenBody(model, session) }
            }
        }
    }
}

@Composable
private fun ScreenBody(model: AppModel, session: Session) {
    val name = session.stack.last()
    val screen = screens.getValue(name)
    val values = remember(session.state) { resolve(session.state) }
    val headingIndex = screen.widgets.indexOfFirst { it is Widget.Text }
    val headingText = (screen.widgets.getOrNull(headingIndex) as? Widget.Text)?.text ?: name
    val focus = remember { FocusRequester() }
    val focusManager = LocalFocusManager.current
    var invalidFields by remember { mutableStateOf(emptySet<Int>()) }
    var resetToken by remember { mutableIntStateOf(0) }
    val enabled = !model.saving && invalidFields.isEmpty()

    var headingFocused by remember { mutableStateOf(false) }
    LazyColumn(
        modifier = Modifier.widthIn(max = 800.dp).fillMaxWidth().testTag("screen-$name"),
        contentPadding = PaddingValues(horizontal = 20.dp, vertical = 24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item("heading") {
            Text(
                headingText, Modifier.focusRequester(focus).focusable().semantics { heading() },
                style = MaterialTheme.typography.headlineMedium,
            )
            LaunchedEffect(focus) {
                if (!headingFocused) {
                    focusManager.clearFocus(force = true)
                    focus.requestFocus()
                    headingFocused = true
                }
            }
        }
        item("status") {
            val status = if (model.saving) "Saving…" else model.error
            if (status.isNotEmpty()) {
                Text(status, Modifier.testTag("action-error").semantics { liveRegion = LiveRegionMode.Polite },
                    color = if (model.saving) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.error)
            }
        }
        for ((index, widget) in screen.widgets.withIndex()) {
            if (index == headingIndex) continue
            if (widget is Widget.Rows) {
                val rows = (values.getValue(widget.collection) as SdrList).rows
                items(rows, key = { "list-$index-${it.id}" }) { row ->
                    RecordRow(widget, row, session.state[widget.selected] == row.id, enabled) {
                        model.accept(select(model.session, widget, row.id))
                    }
                }
            } else {
                item("widget-$index") {
                    when (widget) {
                        is Widget.Text -> Text(widget.text)
                        is Widget.Display -> Text(widget.prefix + (validated { widget.evaluate(values) } ?: "Unavailable"))
                        is Widget.Show -> if (values[widget.condition] == true) Text(widget.label) else Unit
                        is Widget.Button -> Button(
                            enabled = !model.saving && (enabled || routes[widget.command]?.action == null && widget.command in routes),
                            onClick = {
                                if (model.accept(dispatch(model.session, widget.command))) resetToken++
                            },
                            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("action-${widget.command}"),
                        ) { Text(widget.label) }
                        is Widget.Input -> Field(widget, values.getValue(widget.key).toString(), resetToken, !model.saving,
                            onInvalid = { invalidFields = if (it) invalidFields + index else invalidFields - index },
                            onValue = { next -> model.accept(edit(model.session, widget.key, next)) })
                        is Widget.Rows -> Unit
                    }
                }
            }
        }
    }
}

@Composable
private fun Field(
    widget: Widget.Input,
    accepted: String,
    resetToken: Int,
    enabled: Boolean,
    onInvalid: (Boolean) -> Unit,
    onValue: (Any?) -> Boolean,
) {
    var draft by rememberSaveable { mutableStateOf(accepted) }
    var invalid by rememberSaveable { mutableStateOf(false) }
    var wasFocused by remember { mutableStateOf(false) }
    fun reset() {
        draft = accepted
        invalid = false
        onInvalid(false)
    }
    LaunchedEffect(accepted, resetToken) { reset() }
    DisposableEffect(Unit) { onDispose { onInvalid(false) } }
    OutlinedTextField(
        value = draft,
        onValueChange = { raw ->
            draft = raw.take(4096)
            val candidate: Any? = if (raw.length > 4096) null else if (widget.numeric) {
                raw.trim().takeIf { it.matches(Regex("-?[0-9]+")) }?.toIntOrNull()
            } else raw
            invalid = !onValue(candidate)
            onInvalid(invalid)
        },
        enabled = enabled,
        label = { Text(widget.label) },
        isError = invalid,
        supportingText = { if (invalid) Text("Enter a value of the declared type that satisfies the app rules.") },
        keyboardOptions = KeyboardOptions(keyboardType = if (widget.numeric) KeyboardType.Number else KeyboardType.Text),
        modifier = Modifier.fillMaxWidth().testTag("input-${widget.key}").onFocusChanged {
            if (!it.isFocused && wasFocused && invalid) reset()
            wasFocused = it.isFocused
        },
    )
}

@Composable
private fun RecordRow(widget: Widget.Rows, row: SdrRow, selected: Boolean, enabled: Boolean, onClick: () -> Unit) {
    val title = widget.title?.let { row.record.fields.getValue(it).toString() }
        ?: row.record.fields.entries.joinToString(" · ") { "${it.key}: ${it.value}" }
    val status = widget.status?.let { if (row.record.fields[it] == true) "Completed" else "In progress" }
    Surface(
        modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("item-${row.id}")
            .selectable(selected = selected, enabled = enabled, onClick = onClick)
            .semantics { if (status != null) stateDescription = status },
        shape = MaterialTheme.shapes.medium,
        color = if (selected) MaterialTheme.colorScheme.secondaryContainer else MaterialTheme.colorScheme.surfaceVariant,
    ) {
        Column(Modifier.padding(16.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium)
            if (status != null) Text(status, style = MaterialTheme.typography.bodySmall)
        }
    }
}
