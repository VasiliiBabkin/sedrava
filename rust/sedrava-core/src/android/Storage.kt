import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.file.Files
import java.nio.file.StandardCopyOption

internal class SnapshotStore(
    private val file: File,
    private val legacy: () -> Map<String, *>,
) {
    private var expected: String? = null
    private var loaded = false

    private fun read(): String? {
        if (!file.exists()) return null
        // A UTF-16 code unit can account for at most three UTF-8 bytes.
        val limit = SNAPSHOT_LIMIT * 3
        val bytes = ByteArray(limit + 1)
        var count = 0
        file.inputStream().use { stream ->
            while (count < bytes.size) {
                val size = stream.read(bytes, count, bytes.size - count)
                if (size < 0) break
                count += size
            }
        }
        require(count <= limit)
        return Charsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
            .decode(ByteBuffer.wrap(bytes, 0, count)).toString()
    }

    fun load(): SdrState {
        loaded = false
        val raw = read()
        val state = if (raw == null) restorePythonPreferences(legacy()) else restoreSnapshot(raw)
        expected = raw
        loaded = true
        return state
    }

    fun save(raw: String) {
        require(loaded)
        if (read() != expected) throw IOException("Snapshot changed")
        val stage = File.createTempFile(".sedrava-", ".json", file.parentFile)
        try {
            FileOutputStream(stage).use { stream ->
                stream.write(raw.toByteArray(Charsets.UTF_8))
                stream.fd.sync()
            }
            Files.move(stage.toPath(), file.toPath(),
                StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
            expected = raw
        } finally {
            stage.delete()
        }
    }
}
