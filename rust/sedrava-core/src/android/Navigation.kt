internal data class Route(val target: String, val action: String?)
internal data class Session(val state: SdrState = defaultState, val stack: List<String> = listOf(initialScreen))

internal fun visible(state: SdrState, name: String): Boolean =
    validated { screens[name]?.guard?.invoke(resolve(state)) == true } == true

private fun normalize(state: SdrState, stack: List<String>): Session {
    var path = stack
    while (path.size > 1 && !visible(state, path.last())) path = path.dropLast(1)
    return Session(state, path)
}

internal fun restoreSession(state: SdrState, stack: List<String>): Session {
    val valid = stack.size in 1..32 && stack.first() == initialScreen && stack.all { it in screens }
    return normalize(state, if (valid) stack else listOf(initialScreen))
}

internal fun restoreConfiguration(state: SdrState, raw: String?, stack: List<String>): Session {
    val saved = raw?.let { validated { restoreSnapshot(it, full = true) } } ?: return Session(state)
    if (persistent.any { key -> state[key] != saved[key] }) return Session(state)
    return restoreSession(saved, stack)
}

internal fun dispatch(current: Session, command: String): Session? {
    if (command == "\$back") {
        return normalize(current.state, current.stack.dropLast(1).ifEmpty { listOf(initialScreen) })
    }
    val route = routes[command] ?: return transition(current.state, command)?.let {
        normalize(it, current.stack)
    }
    val candidate = if (route.action == null) current.state else transition(current.state, route.action) ?: return null
    if (route.target == "pop") {
        return normalize(candidate, current.stack.dropLast(1).ifEmpty { listOf(initialScreen) })
    }
    if (current.stack.size >= 32 || !visible(candidate, route.target)) return null
    return normalize(candidate, current.stack + route.target)
}

internal fun edit(current: Session, key: String, value: Any?): Session? {
    if (value == null || key !in stateTypes) return null
    val next = current.state + (key to value)
    return if (validState(next)) normalize(next, current.stack) else null
}

internal fun select(current: Session, widget: Widget.Rows, id: Int): Session? {
    val list = resolve(current.state)[widget.collection] as SdrList
    if (!builtin_has(list, id)) return null
    val candidate = edit(current, widget.selected, id) ?: return null
    return if (widget.open == null) candidate else dispatch(candidate, widget.open)
}
