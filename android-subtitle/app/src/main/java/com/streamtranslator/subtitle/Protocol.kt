package com.streamtranslator.subtitle

import java.net.URI
import kotlin.math.abs

fun normalizeServerUrl(input: String): String {
    var value = input.trim().trimEnd('/')
    if (value.isEmpty()) return ""
    require(value.none { it.isWhitespace() || it.code < 32 })
    if (!value.contains("://")) {
        require(!Regex("^[a-zA-Z][\\w+.-]*:").containsMatchIn(value) ||
            Regex("^[^/:?#]+:\\d+(?:[/?#]|$)").containsMatchIn(value))
        value = "http://$value"
    }
    val uri = try { URI(value) } catch (_: Exception) { throw IllegalArgumentException() }
    val scheme = uri.scheme?.lowercase()
    require(scheme == "http" || scheme == "https")
    val authority = uri.rawAuthority ?: throw IllegalArgumentException()
    require(uri.rawUserInfo == null && '@' !in authority)
    val fallback = Regex("[A-Za-z0-9_.-]+(?::([0-9]+))?").matchEntire(authority)
    require(!uri.host.isNullOrEmpty() || fallback != null)
    val port = if (uri.host != null) uri.port else
        fallback!!.groupValues[1].takeIf { it.isNotEmpty() }?.let { it.toIntOrNull() ?: throw IllegalArgumentException() } ?: -1
    require(port in -1..65535)
    var path = (uri.rawPath ?: "").trimEnd('/')
    if (path.substringAfterLast('/').lowercase() in setOf("desktop", "mobile", "subtitle")) {
        path = path.substringBeforeLast('/', "").trimEnd('/')
    }
    require(!authority.endsWith(':'))
    return "$scheme://$authority${if (port == -1 && scheme == "http") ":8765" else ""}$path"
}

typealias Subtitle = Map<String, Any?>

object SubtitleHistory {
    const val TIMESTAMP_DRIFT_TOLERANCE_MS = 50
    private val clock = "\\d{1,2}:\\d{2}:\\d{2}[,.]\\d{1,3}"
    private val range = Regex("($clock)\\s*(?:-->|->|→)\\s*($clock)")
    private fun value(value: Any?): String? = value?.toString()?.takeIf { it.isNotEmpty() }
    private fun truthy(value: Any?): Boolean = value != null && value != "" && value != false && value != 0
    private fun timestamp(row: Subtitle): Any? = row["backend_timestamp"].takeIf(::truthy) ?: row["timestamp"]
    private fun original(row: Subtitle): String = row["original"].takeIf(::truthy)?.toString()?.trim() ?: ""
    private fun milliseconds(clock: String): Long {
        val parts = clock.split(':', ',', '.')
        return ((parts[0].toLong() * 60 + parts[1].toLong()) * 60 + parts[2].toLong()) * 1000 +
            parts[3].padEnd(3, '0').toLong()
    }
    private fun timeRange(row: Subtitle): Pair<Long, Long>? {
        val match = range.find(timestamp(row)?.toString() ?: return null) ?: return null
        return milliseconds(match.groupValues[1]) to milliseconds(match.groupValues[2])
    }
    fun identity(row: Subtitle): Pair<String, String>? {
        value(row["segment_id"])?.let { return "segment" to it }
        value(timestamp(row))?.let { return "timestamp" to it }
        return value(row["id"])?.let { "id" to it }
    }
    fun findIndex(lines: List<Subtitle>, incoming: Subtitle): Int {
        value(incoming["segment_id"])?.let { id ->
            lines.indexOfFirst { value(it["segment_id"]) == id }.takeIf { it >= 0 }?.let { return it }
        }
        value(timestamp(incoming))?.let { stamp ->
            lines.indexOfFirst { value(timestamp(it)) == stamp }.takeIf { it >= 0 }?.let { return it }
            val incomingRange = timeRange(incoming)
            val text = original(incoming)
            if (incomingRange != null && text.isNotEmpty()) {
                for (index in lines.indices.reversed()) {
                    val line = lines[index]
                    if (original(line) != text) continue
                    val existing = timeRange(line) ?: continue
                    if (abs(existing.first - incomingRange.first) <= TIMESTAMP_DRIFT_TOLERANCE_MS &&
                        abs(existing.second - incomingRange.second) <= TIMESTAMP_DRIFT_TOLERANCE_MS) return index
                }
            }
        }
        value(incoming["id"])?.let { id ->
            lines.indexOfFirst { value(it["id"]) == id }.takeIf { it >= 0 }?.let { return it }
        }
        return -1
    }
    fun merge(lines: List<Subtitle>, incoming: Subtitle, limit: Int = 500): List<Subtitle> {
        val result = lines.toMutableList()
        val index = findIndex(result, incoming)
        if (index < 0) result.add(incoming.toMap()) else result[index] = result[index] + incoming
        return result.takeLast(limit)
    }
}

data class SseEvent(val type: String, val data: String)

/** Input is one UTF-8 decoded line without its CR/LF. A blank line dispatches. */
class SseLineParser {
    private var event = "message"
    private val data = mutableListOf<String>()
    private var dataBytes = 0
    private var firstLine = true
    fun line(raw: String): SseEvent? {
        val line = if (firstLine) raw.removePrefix("\uFEFF") else raw
        firstLine = false
        if (line.isEmpty()) {
            val result = if (data.isNotEmpty()) SseEvent(event, data.joinToString("\n")) else null
            event = "message"
            data.clear()
            dataBytes = 0
            return result
        }
        if (line.startsWith(':')) return null
        val field = line.substringBefore(':')
        val value = line.substringAfter(':', "").removePrefix(" ")
        when (field) {
            "event" -> event = value.ifEmpty { "message" }
            "data" -> {
                dataBytes += value.toByteArray(Charsets.UTF_8).size + 1
                if (dataBytes > MAX_BODY_BYTES) throw PayloadTooLarge("SSE event too large")
                data.add(value)
            }
        }
        return null
    }
}

class ReconnectBackoff(private val delays: LongArray = longArrayOf(1000, 2000, 5000, 10000)) {
    private var attempt = 0
    fun reset() { attempt = 0 }
    fun nextDelayMs(): Long = delays[attempt.also { if (attempt < delays.lastIndex) attempt++ }]
}

class PayloadTooLarge(message: String) : java.io.IOException(message)

const val MAX_LINE_BYTES = 256L * 1024
const val MAX_BODY_BYTES = 1024 * 1024
fun readLimitedBody(source: okio.BufferedSource): String {
    if (source.request(MAX_BODY_BYTES.toLong() + 1)) throw PayloadTooLarge("Body too large")
    return source.readUtf8()
}
class ConnectionGeneration {
    private var current = 0L
    @Synchronized fun advance(): Long = ++current
    @Synchronized fun apply(generation: Long, update: () -> Unit) {
        if (generation == current) update()
    }
}
class StreamHealth(private val openedNanos: Long = System.nanoTime()) {
    private var reset = false
    fun shouldReset(eventType: String, nowNanos: Long = System.nanoTime()) =
        shouldReset(eventType == "subtitle", nowNanos)
    fun shouldReset(subtitle: Boolean, nowNanos: Long = System.nanoTime()): Boolean {
        if (reset || (!subtitle && nowNanos - openedNanos < 5_000_000_000L)) return false
        reset = true
        return true
    }
}
fun overlayActionAllowed(running: Boolean, action: String?) = running || action == "com.streamtranslator.subtitle.START"
fun releaseOverlaySafely(remove: () -> Unit, release: () -> Unit, finish: () -> Unit) {
    try { remove() } catch (_: RuntimeException) { }
    finally { try { release() } finally { finish() } }
}

/** Error details are advisory; never consume an unbounded error response. */
fun readErrorPrefix(source: okio.BufferedSource): String {
    source.request(4096)
    return source.readUtf8(minOf(source.buffer.size, 4096L))
}

fun autoConnectServer(savedServer: String, enabled: Boolean, freshLaunch: Boolean,
                      repositoryUnconfigured: Boolean): String? {
    if (!enabled || (!freshLaunch && !repositoryUnconfigured)) return null
    return try { normalizeServerUrl(savedServer).takeIf { it.isNotEmpty() } }
    catch (_: IllegalArgumentException) { null }
}
