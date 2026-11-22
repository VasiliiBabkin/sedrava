package androidx.compose.material3
fun MaterialTheme(content: () -> Unit) { content() }
fun Text(text: String) {}
fun Button(onClick: () -> Unit, content: () -> Unit) { content() }
fun OutlinedTextField(value: String, onValueChange: (String) -> Unit,
                      label: () -> Unit) { label() }
