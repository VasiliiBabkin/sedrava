package org.sedrava.benchmark.kotlin

import android.app.Activity
import android.os.Bundle
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/** Independent, hand-written Kotlin reference for counter-v0 (not agent output). */
class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs = getSharedPreferences("counter-v0", MODE_PRIVATE)
        var count = prefs.getInt("count", 0)
        val density = resources.displayMetrics.density
        val padding = (24 * density).toInt()
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(padding, padding, padding, padding)
        }
        val value = TextView(this).apply {
            textSize = 24f
            text = "count: $count"
        }
        layout.addView(value, LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ))
        fun commit(next: Int) {
            if (prefs.edit().putInt("count", next).commit()) {
                count = next
                value.text = "count: $count"
            }
        }
        fun button(label: String, action: () -> Unit) {
            val control = Button(this).apply {
                text = label
                isAllCaps = false
                setOnClickListener { action() }
            }
            layout.addView(control, LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
            ))
        }
        button("Add") { try { commit(Math.addExact(count, 1)) } catch (_: ArithmeticException) {} }
        button("Subtract") { try { commit(Math.subtractExact(count, 1)) } catch (_: ArithmeticException) {} }
        button("Reset") { commit(0) }
        setContentView(layout)
    }
}
