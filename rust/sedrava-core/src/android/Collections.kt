internal fun builtin_count(list: SdrList): Int = list.rows.size
internal fun builtin_next_id(list: SdrList): Int = list.nextId
internal fun builtin_has(list: SdrList, id: Int): Boolean = list.rows.any { it.id == id }
internal fun builtin_get(list: SdrList, id: Int): SdrRecord =
    requireNotNull(list.rows.firstOrNull { it.id == id }) { "Unknown record identity" }.record

internal fun builtin_append(list: SdrList, record: SdrRecord): SdrList {
    require(list.rows.size < list.capacity && list.nextId < Int.MAX_VALUE)
    checkValue(record, SdrType.Record(list.record))
    return list.copy(nextId = list.nextId + 1, rows = list.rows + SdrRow(list.nextId, record))
}

internal fun builtin_update(list: SdrList, id: Int, record: SdrRecord): SdrList {
    require(builtin_has(list, id))
    checkValue(record, SdrType.Record(list.record))
    return list.copy(rows = list.rows.map { if (it.id == id) SdrRow(id, record) else it })
}

internal fun builtin_remove(list: SdrList, id: Int): SdrList {
    require(builtin_has(list, id))
    return list.copy(rows = list.rows.filterNot { it.id == id })
}

private fun compareText(left: String, right: String): Int {
    val a = left.codePoints().iterator()
    val b = right.codePoints().iterator()
    while (a.hasNext() && b.hasNext()) {
        val order = a.nextInt().compareTo(b.nextInt())
        if (order != 0) return order
    }
    return a.hasNext().compareTo(b.hasNext())
}

private fun compare(a: Any, b: Any): Int = when (a) {
    is Int -> a.compareTo(b as Int)
    is Boolean -> a.compareTo(b as Boolean)
    is String -> compareText(a, b as String)
    else -> error("Invalid generated sort key")
}

internal fun query(operation: String, list: SdrList, select: (SdrRow) -> Any): Any =
    when (operation) {
        "find" -> list.rows.firstOrNull { select(it) as Boolean }?.id ?: 0
        "any" -> list.rows.any { select(it) as Boolean }
        "all" -> list.rows.all { select(it) as Boolean }
        "filter" -> list.copy(rows = list.rows.filter { select(it) as Boolean })
        "sum" -> list.rows.fold(0) { total, row -> Math.addExact(total, select(row) as Int) }
        "sort" -> {
            val keyed = list.rows.map { it to select(it) }
            list.copy(rows = keyed.sortedWith { a, b -> compare(a.second, b.second) }.map { it.first })
        }
        else -> error("Unknown generated query operation")
    }

internal fun mapRows(list: SdrList, type: String, select: (SdrRow) -> SdrRecord): SdrList =
    list.copy(record = type, rows = list.rows.map { row -> SdrRow(row.id, select(row)) })
