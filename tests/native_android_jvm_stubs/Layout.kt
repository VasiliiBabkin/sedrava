package androidx.compose.foundation.layout
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Dp
fun Modifier.fillMaxSize(): Modifier = this
fun Modifier.padding(all: Dp): Modifier = this
object Arrangement {
    fun spacedBy(space: Dp): Any = Any()
}
fun Column(modifier: Modifier, verticalArrangement: Any, content: () -> Unit) { content() }
