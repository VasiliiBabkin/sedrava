import org.sedrava.demo.MainActivity

fun main() {
    val topLevel = Class.forName("org.sedrava.demo.MainActivityKt")
    val stateClass = Class.forName("org.sedrava.demo.SdrState")
    val ctor = stateClass.getDeclaredConstructor(Int::class.javaPrimitiveType, String::class.java)
    val count = stateClass.getDeclaredMethod("getSdr_count")
    val change = topLevel.getDeclaredMethod("transition", stateClass, String::class.java)
    change.isAccessible = true
    val initial = ctor.newInstance(1, "Проверка 😀")
    val plus = change.invoke(null,initial,"increase")
    require(count.invoke(plus)==2) {"Rust-generated Kotlin action did not increment"}
    val minus = change.invoke(null,plus,"decrease")
    require(count.invoke(minus)==1) {"Rust-generated Kotlin action did not decrement"}
    val zero = change.invoke(null,minus,"decrease")
    require(count.invoke(zero)==0)
    val rejected = change.invoke(null,zero,"decrease")
    require(count.invoke(rejected)==0) {"Invariant allowed negative count"}
    val max = ctor.newInstance(Int.MAX_VALUE,"ok")
    val overflow = change.invoke(null,max,"increase")
    require(count.invoke(overflow)==Int.MAX_VALUE) {"Overflow mutated state"}
    MainActivity().onCreate(null)
    println("PASS: Rust-generated Kotlin compiled and JVM domain logic correctly rejected overflow/invalid states")
}
