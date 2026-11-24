package ru.ladokod.bench.counter

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                var count by rememberSaveable { mutableIntStateOf(0) }
                Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text("Sedrava Counter")
                    Text(count.toString())
                    Button(onClick = { if (count < Int.MAX_VALUE) count++ }) { Text("Add") }
                    Button(onClick = { if (count > 0) count-- }) { Text("Subtract") }
                    Button(onClick = { count = 0 }) { Text("Reset") }
                }
            }
        }
    }
}
