package androidx.activity.compose
import androidx.activity.ComponentActivity
fun ComponentActivity.setContent(content: () -> Unit) { content() }
