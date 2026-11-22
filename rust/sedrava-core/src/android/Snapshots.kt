internal const val SNAPSHOT_LIMIT = 200_000

private class SnapshotParser(private val source: String) {
    private var position = 0

    fun parse(): Any? {
        require(source.length <= SNAPSHOT_LIMIT)
        val result = value(0)
        whitespace()
        require(position == source.length)
        return result
    }

    private fun whitespace() {
        while (position < source.length && source[position] in " \t\n\r") position++
    }

    private fun accept(char: Char): Boolean {
        if (source.getOrNull(position) != char) return false
        position++
        return true
    }

    private fun take(char: Char) = require(accept(char))

    private fun value(depth: Int): Any? {
        require(depth <= 32)
        whitespace()
        return when (source.getOrNull(position)) {
            '"' -> string()
            '{' -> objectValue(depth)
            '[' -> arrayValue(depth)
            't' -> { word("true"); true }
            'f' -> { word("false"); false }
            'n' -> { word("null"); null }
            else -> intValue()
        }
    }

    private fun word(token: String) {
        require(source.startsWith(token, position))
        position += token.length
    }

    private fun intValue(): Int {
        val start = position
        accept('-')
        if (!accept('0')) {
            require((source.getOrNull(position) ?: '\u0000') in '1'..'9')
            while ((source.getOrNull(position) ?: '\u0000') in '0'..'9') position++
        }
        return requireNotNull(source.substring(start, position).toIntOrNull())
    }

    private fun objectValue(depth: Int): Map<String, Any?> {
        take('{')
        whitespace()
        if (accept('}')) return emptyMap()
        val output = linkedMapOf<String, Any?>()
        do {
            whitespace()
            val key = string()
            require(key !in output)
            whitespace()
            take(':')
            output[key] = value(depth + 1)
            whitespace()
        } while (accept(','))
        take('}')
        return output
    }

    private fun arrayValue(depth: Int): List<Any?> {
        take('[')
        whitespace()
        if (accept(']')) return emptyList()
        val output = mutableListOf<Any?>()
        do {
            output.add(value(depth + 1))
            whitespace()
        } while (accept(','))
        take(']')
        return output
    }

    private fun string(): String {
        take('"')
        val output = StringBuilder()
        while (position < source.length) {
            val char = source[position++]
            if (char == '"') return output.toString()
            require(char >= ' ')
            if (char != '\\') {
                output.append(char)
                continue
            }
            require(position < source.length)
            val escaped = when (val escape = source[position++]) {
                '"', '\\', '/' -> escape
                'b' -> '\b'
                'f' -> '\u000c'
                'n' -> '\n'
                'r' -> '\r'
                't' -> '\t'
                'u' -> {
                    require(position + 4 <= source.length)
                    val hex = source.substring(position, position + 4)
                    require(hex.all { it in "0123456789abcdefABCDEF" })
                    position += 4
                    hex.toInt(16).toChar()
                }
                else -> throw IllegalArgumentException("Invalid snapshot escape")
            }
            output.append(escaped)
        }
        throw IllegalArgumentException("Unclosed JSON string")
    }
}

private fun jsonString(text: String): String = buildString {
    append('"')
    for (char in text) {
        when (char) {
            '"' -> append("\\\"")
            '\\' -> append("\\\\")
            '\b' -> append("\\b")
            '\u000c' -> append("\\f")
            '\n' -> append("\\n")
            '\r' -> append("\\r")
            '\t' -> append("\\t")
            else -> if (char < ' ') {
                append("\\u")
                append(char.code.toString(16).padStart(4, '0'))
            } else append(char)
        }
    }
    append('"')
}

internal fun encodeJson(value: Any?): String = when (value) {
    null -> "null"
    is String -> jsonString(value)
    is Int, is Boolean -> value.toString()
    is Map<*, *> -> value.entries.sortedBy { it.key as String }.joinToString(",", "{", "}") {
        jsonString(it.key as String) + ":" + encodeJson(it.value)
    }
    is List<*> -> value.joinToString(",", "[", "]") { encodeJson(it) }
    is SdrList -> encodeJson(mapOf(
        "next_id" to value.nextId,
        "items" to value.rows.map { row -> row.record.fields + ("id" to row.id) },
    ))
    is SdrRecord -> encodeJson(value.fields)
    else -> throw IllegalArgumentException("Invalid snapshot value")
}

private fun exactObject(value: Any?, expected: Set<String>): Map<*, *> {
    require(value is Map<*, *> && value.keys == expected)
    return value
}

private fun decodeRecord(value: Any?, name: String): SdrRecord {
    val fields = recordTypes.getValue(name)
    val raw = exactObject(value, fields.keys)
    return record(name, fields.mapValues { (key, kind) -> decode(raw[key], kind) })
}

private fun decode(value: Any?, type: SdrType): Any = when (type) {
    is SdrType.Record -> decodeRecord(value, type.name)
    is SdrType.Collection -> {
        val raw = exactObject(value, setOf("next_id", "items"))
        val items = raw["items"]
        val next = raw["next_id"]
        require(items is List<*> && items.size <= type.capacity && next is Int)
        val keys = recordTypes.getValue(type.record).keys + "id"
        val rows = items.map { item ->
            val row = exactObject(item, keys)
            val id = row["id"]
            require(id is Int)
            SdrRow(id, decodeRecord(row.filterKeys { it != "id" }, type.record))
        }
        checkValue(SdrList(type.record, type.capacity, next, rows), type)
    }
    else -> checkValue(requireNotNull(value), type)
}

internal fun snapshot(state: SdrState, full: Boolean = false): String {
    val values = if (full) state else state.filterKeys { it in persistent }
    return encodeJson(mapOf("schema" to 1, "signature" to snapshotSignature, "state" to values))
        .also { require(it.length <= SNAPSHOT_LIMIT) }
}

internal fun restoreSnapshot(raw: String, full: Boolean = false): SdrState {
    val root = exactObject(SnapshotParser(raw).parse(), setOf("schema", "signature", "state"))
    require(root["schema"] == 1 && root["signature"] == snapshotSignature)
    val keys = if (full) stateTypes.keys else persistent
    val saved = exactObject(root["state"], keys)
    val next = defaultState + keys.associateWith { key -> decode(saved[key], stateTypes.getValue(key)) }
    require(validState(next))
    return next
}

internal fun restorePythonPreferences(saved: Map<String, *>): SdrState {
    if (saved.isEmpty()) return defaultState
    if (!legacyScalarPreferences) {
        require(saved.keys == setOf("snapshot"))
        val raw = saved["snapshot"]
        require(raw is String)
        return restoreSnapshot(raw)
    }
    require(saved.keys.all { it in persistent })
    val restored = defaultState + saved.mapValues { (key, value) ->
        checkValue(requireNotNull(value), stateTypes.getValue(key))
    }
    require(validState(restored))
    return restored
}
