package androidx.compose.ui.unit
data class Dp(val value: Int)
val Int.dp get() = Dp(this)
