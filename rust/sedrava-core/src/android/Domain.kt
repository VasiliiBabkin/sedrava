import java.time.DateTimeException
import java.time.LocalDate

internal typealias SdrState = Map<String, Any>

internal sealed interface SdrType {
    data object Integer : SdrType
    data object BooleanValue : SdrType
    data object Text : SdrType
    data class Record(val name: String) : SdrType
    data class Collection(val record: String, val capacity: Int) : SdrType
}

internal data class SdrRecord(val type: String, val fields: Map<String, Any>)
internal data class SdrRow(val id: Int, val record: SdrRecord)
internal data class SdrList(
    val record: String,
    val capacity: Int,
    val nextId: Int,
    val rows: List<SdrRow>,
)

internal fun checkedText(text: String): String {
    var index = 0
    var scalars = 0
    while (index < text.length) {
        val c = text[index++]
        if (c.isHighSurrogate()) {
            require(index < text.length && text[index++].isLowSurrogate())
        } else {
            require(!c.isLowSurrogate())
        }
        require(++scalars <= 1024)
    }
    return text
}

internal fun checkValue(value: Any, type: SdrType): Any {
    when (type) {
        SdrType.Integer -> require(value is Int)
        SdrType.BooleanValue -> require(value is Boolean)
        SdrType.Text -> { require(value is String); checkedText(value) }
        is SdrType.Record -> {
            require(value is SdrRecord && value.type == type.name)
            val fields = recordTypes.getValue(type.name)
            require(value.fields.keys == fields.keys)
            for ((name, fieldType) in fields) checkValue(value.fields.getValue(name), fieldType)
        }
        is SdrType.Collection -> {
            require(value is SdrList && value.record == type.record && value.capacity == type.capacity)
            require(value.nextId > 0 && value.rows.size <= type.capacity)
            val ids = mutableSetOf<Int>()
            for (row in value.rows) {
                require(row.id in 1 until value.nextId && ids.add(row.id))
                checkValue(row.record, SdrType.Record(type.record))
            }
        }
    }
    return value
}

internal fun record(name: String, fields: Map<String, Any>): SdrRecord =
    SdrRecord(name, fields.toMap()).also { checkValue(it, SdrType.Record(name)) }

internal fun builtin_text_length(value: String): Int = value.codePointCount(0, value.length)
internal fun builtin_trim(value: String): String = value.trim(' ', '\t', '\n', '\r')
internal fun builtin_lower_ascii(value: String): String =
    value.map { if (it in 'A'..'Z') it.lowercaseChar() else it }.joinToString("")
internal fun builtin_contains(value: String, part: String): Boolean = part in value
internal fun builtin_concat(a: String, b: String): String = checkedText(a + b)

private val datePattern = Regex("[0-9]{4}-[0-9]{2}-[0-9]{2}")

private fun civilDate(value: String): LocalDate {
    require(datePattern.matches(value))
    return try {
        LocalDate.parse(value).also { require(it.year in 1..9999) }
    } catch (e: DateTimeException) {
        throw IllegalArgumentException("Invalid civil date", e)
    }
}

internal fun builtin_is_date(value: String): Boolean = try {
    civilDate(value)
    true
} catch (_: IllegalArgumentException) {
    false
}

internal fun builtin_date_days(value: String): Int = civilDate(value).toEpochDay().toInt()

internal fun builtin_date_add(value: String, delta: Int): String = try {
    val result = civilDate(value).plusDays(delta.toLong())
    require(result.year in 1..9999)
    result.toString()
} catch (e: DateTimeException) {
    throw IllegalArgumentException("Civil date outside supported range", e)
}

internal sealed interface Widget {
    data class Text(val text: String) : Widget
    data class Display(val prefix: String, val evaluate: (SdrState) -> Any) : Widget
    data class Show(val condition: String, val label: String) : Widget
    data class Input(val key: String, val label: String, val numeric: Boolean) : Widget
    data class Button(val label: String, val command: String) : Widget
    data class Rows(
        val collection: String,
        val selected: String,
        val open: String?,
        val title: String?,
        val status: String?,
    ) : Widget
}

internal data class Screen(val guard: (SdrState) -> Boolean, val widgets: List<Widget>)
internal inline fun <T> validated(block: () -> T): T? = try {
    block()
} catch (_: IllegalArgumentException) {
    null
} catch (_: ArithmeticException) {
    null
}

internal fun resolve(state: SdrState): SdrState {
    require(state.keys == stateTypes.keys)
    for ((key, kind) in stateTypes) checkValue(state.getValue(key), kind)
    if (stateTypes.values.any { it is SdrType.Collection || it is SdrType.Record }) {
        require(encodeJson(state).length <= SNAPSHOT_LIMIT)
    }
    return derive(state)
}

internal fun validState(state: SdrState): Boolean = validated { rulesHold(resolve(state)) } == true

internal fun transition(current: SdrState, command: String): SdrState? = validated {
    val action = requireNotNull(actions[command])
    val values = resolve(current)
    require(rulesHold(values))
    val next = current.toMutableMap()
    action(next, values)
    require(validState(next))
    next.toMap()
}
