package com.streamtranslator.subtitle

import androidx.annotation.VisibleForTesting
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import okhttp3.Call
import okhttp3.Callback
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.json.JSONObject
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

enum class ConnectionStatus { UNCONFIGURED, STOPPED, WAITING, CONNECTING, CONNECTED, RECONNECTING, SHARING_DISABLED, TASK_ENDED, SERVICE_NOT_FOUND }
data class SubtitleState(
    val running: Boolean = false,
    val status: ConnectionStatus = ConnectionStatus.UNCONFIGURED,
    val ready: Boolean = false,
    val rows: List<Subtitle> = emptyList()
)

/** Process-wide holder. All ownership changes are performed on the main thread. */
object SubtitleRepository {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val client = OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS).followRedirects(false).followSslRedirects(false).build()
    private val streamClient = client.newBuilder().readTimeout(0, TimeUnit.MILLISECONDS).build()
    private val mutableState = MutableStateFlow(SubtitleState())
    val state = mutableState.asStateFlow()
    private var connection: Job? = null
    private var server = ""
    private val generations = ConnectionGeneration()
    private val mutableOverlay = MutableStateFlow(false)
    val overlay = mutableOverlay.asStateFlow()
    var overlayActive: Boolean
        get() = mutableOverlay.value
        set(value) { mutableOverlay.value = value }
    private var foregroundViews = 0
    @VisibleForTesting internal var statusPollIntervalMs = 2000L
    @VisibleForTesting internal var activeTaskPollIntervalMs = 5000L
    @VisibleForTesting internal var waitingPollIntervalMs = 3000L
    @VisibleForTesting internal var backoffDelaysMs = longArrayOf(1000, 2000, 5000, 10000)

    fun attachView() { foregroundViews++ }
    fun reconnectIfEnabled() {
        if (state.value.status !in setOf(ConnectionStatus.STOPPED, ConnectionStatus.UNCONFIGURED)) return
        autoConnectServer(Preferences.server, Preferences.autoConnect, true, true)?.let(::connect)
    }
    fun detachView(changingConfiguration: Boolean) {
        foregroundViews = (foregroundViews - 1).coerceAtLeast(0)
        if (!changingConfiguration && foregroundViews == 0 && !overlayActive) disconnect()
    }
    fun releaseOverlay(stop: Boolean) {
        overlayActive = false
        if (stop || foregroundViews == 0) disconnect()
    }
    fun connect(base: String) {
        if (base.isEmpty()) { disconnect(); mutableState.value = SubtitleState(); return }
        if (server == base && connection?.isActive == true) return
        val generation = generations.advance()
        val previous = connection
        previous?.cancel()
        server = base
        mutableState.value = SubtitleState(running = true, status = ConnectionStatus.CONNECTING)
        connection = scope.launch {
            previous?.join() // Never overlap streams, even when switching hosts.
            runConnection(base, generation)
        }
    }
    fun disconnect() {
        generations.advance()
        connection?.cancel()
        mutableState.update { it.copy(running = false, ready = false, status = ConnectionStatus.STOPPED) }
    }
    private fun update(generation: Long, change: (SubtitleState) -> SubtitleState) {
        generations.apply(generation) { mutableState.update(change) }
    }
    private fun status(generation: Long, status: ConnectionStatus) { update(generation) { it.copy(status = status) } }
    private fun ready(generation: Long, value: Boolean) { update(generation) { it.copy(ready = value) } }
    private fun request(base: String, path: String, task: String? = null): Request {
        val url = (base + path).toHttpUrl().newBuilder().apply { if (task != null) addPathSegment(task) }.build()
        return Request.Builder().url(url).header("Accept", "application/json, text/event-stream")
            .header("Cache-Control", "no-cache").build()
    }
    private class HttpFailure(val code: Int, val disabled: Boolean, val missingEndpoint: Boolean = false) : IOException()
    private fun validate(response: Response) {
        if (!response.isSuccessful) {
            val message = try { response.body?.source()?.let(::readErrorPrefix).orEmpty() } catch (_: IOException) { "" }
            // Only an explicit "Task not found" means the task ended. Any other 404 (FastAPI "Not Found",
            // the v1.6.0 SPA fallback "Not found", a proxy error page) means the endpoint is missing.
            val detail = try { JSONObject(message).optString("detail") } catch (_: Exception) { "" }
            val disabled = message.contains("sharing is disabled", ignoreCase = true)
            val missingEndpoint = response.code == 404 && !disabled && !detail.equals("Task not found", ignoreCase = true)
            throw HttpFailure(response.code, disabled, missingEndpoint)
        }
    }
    private suspend fun <T> withResponse(call: Call, block: suspend (Response) -> T): T = coroutineScope {
        // A separate child is cancelled immediately, including while the body read blocks on IO.
        val cancellation = launch(start = CoroutineStart.UNDISPATCHED) {
            try { awaitCancellation() } finally { call.cancel() }
        }
        try {
            val response = suspendCancellableCoroutine<Response> { continuation ->
                continuation.invokeOnCancellation { call.cancel() }
                call.enqueue(object : Callback {
                    override fun onFailure(call: Call, e: IOException) { if (continuation.isActive) continuation.resumeWithException(e) }
                    override fun onResponse(call: Call, response: Response) {
                        continuation.resume(response) { _, resource, _ -> resource.close() }
                    }
                })
            }
            response.use { block(it) }
        } finally { cancellation.cancelAndJoin() }
    }
    private suspend fun json(request: Request): JSONObject = withContext(Dispatchers.IO) {
        withResponse(client.newCall(request)) { response ->
            validate(response)
            JSONObject(response.body?.source()?.let(::readLimitedBody) ?: throw IOException())
        }
    }
    private suspend fun runConnection(base: String, generation: Long) {
        val backoff = ReconnectBackoff(backoffDelaysMs)
        var lastTask: String? = null
        var taskEnded = false
        val capability = StatusCapability()
        while (currentCoroutineContext().isActive) {
            var failureStatus = ConnectionStatus.RECONNECTING
            try {
                val active = json(request(base, "/api/translation/active-task"))
                val task = if (active.optBoolean("success") && !active.isNull("task_id")) active.optString("task_id") else ""
                if (task.isEmpty()) {
                    lastTask = null
                    ready(generation, false)
                    status(generation, if (taskEnded) ConnectionStatus.TASK_ENDED else ConnectionStatus.WAITING)
                    backoff.reset()
                    delay(waitingPollIntervalMs)
                    continue
                }
                if (lastTask != task) {
                    update(generation) { it.copy(rows = emptyList(), ready = false) }
                    lastTask = task
                }
                taskEnded = false
                status(generation, ConnectionStatus.CONNECTING)
                if (stream(base, task, backoff, generation, capability)) failureStatus = ConnectionStatus.TASK_ENDED
            } catch (e: CancellationException) { throw e
            } catch (e: TaskEnded) {
                failureStatus = ConnectionStatus.TASK_ENDED
            } catch (e: HttpFailure) {
                // A 404 that is neither "Task not found" nor "sharing disabled" means the address does not
                // reach a subtitle share server (e.g. a wrong reverse-proxy path), not that the task ended.
                if (e.code == 404) failureStatus = when {
                    e.disabled -> ConnectionStatus.SHARING_DISABLED
                    e.missingEndpoint -> ConnectionStatus.SERVICE_NOT_FOUND
                    else -> ConnectionStatus.TASK_ENDED
                }
            } catch (_: Exception) { /* A transport or malformed discovery response is retried. */ }
            currentCoroutineContext().ensureActive()
            ready(generation, false)
            taskEnded = failureStatus == ConnectionStatus.TASK_ENDED
            status(generation, failureStatus)
            delay(backoff.nextDelayMs())
        }
    }
    private class StatusCapability(var supported: Boolean = true)
    private class TaskEnded : IOException()
    private suspend fun taskAlive(base: String, task: String, capability: StatusCapability, generation: Long): Boolean {
        if (capability.supported) {
            try {
                val result = json(request(base, "/api/translation/status/", task))
                if (!result.optBoolean("success") || !result.has("is_running")) throw IOException("Invalid status")
                if (result.optBoolean("asr_ready")) ready(generation, true)
                return result.optBoolean("is_running")
            } catch (e: HttpFailure) {
                if (e.code != 404 || e.disabled) throw e
                if (!e.missingEndpoint) return false
                capability.supported = false
            }
        }
        val active = try { json(request(base, "/api/translation/active-task")) }
        catch (e: HttpFailure) {
            if (e.disabled) throw e
            throw IOException("Active task unavailable", e)
        }
        return active.optBoolean("success") && !active.isNull("task_id") && active.optString("task_id") == task
    }
    private suspend fun stream(base: String, task: String, backoff: ReconnectBackoff, generation: Long,
                               capability: StatusCapability) = coroutineScope {
        var completed = false
        var cleanEof = false
        var health: StreamHealth? = null
        val call = streamClient.newCall(request(base, "/api/translation/stream/", task))
        val readiness = launch {
            var failures = 0
            while (isActive) {
                delay(if (capability.supported) statusPollIntervalMs else activeTaskPollIntervalMs)
                try {
                    if (!taskAlive(base, task, capability, generation)) throw TaskEnded()
                    failures = 0
                } catch (e: CancellationException) { throw e
                } catch (e: TaskEnded) { throw e
                } catch (e: HttpFailure) {
                    if (e.disabled) throw e
                    if (++failures >= 3) throw IOException("Liveness unavailable", e)
                } catch (e: Exception) {
                    // Three failed health requests detect a half-open SSE socket.
                    if (++failures >= 3) throw IOException("Liveness unavailable", e)
                }
            }
        }
        try {
            withContext(Dispatchers.IO) {
                withResponse(call) { response ->
                    validate(response)
                    val source = response.body?.source() ?: throw IOException()
                    val parser = SseLineParser()
                    val streamHealth = StreamHealth()
                    health = streamHealth
                    while (currentCoroutineContext().isActive) {
                        if (source.exhausted()) { cleanEof = true; break }
                        val line = source.readUtf8LineStrict(MAX_LINE_BYTES)
                        currentCoroutineContext().ensureActive()
                        if (streamHealth.shouldReset(false)) backoff.reset()
                        val event = parser.line(line) ?: continue
                        if (event.type == "error") {
                            if (event.data.contains("sharing is disabled", true)) throw HttpFailure(404, true)
                            break
                        }
                        val payload = try { JSONObject(event.data) } catch (_: Exception) { continue }
                        if (event.type == "status" && payload.optString("status") in setOf("completed", "stopped", "error")) {
                            completed = true
                            break
                        }
                        if (event.type in setOf("subtitle", "status")) {
                            status(generation, ConnectionStatus.CONNECTED)
                            if (streamHealth.shouldReset(event.type)) backoff.reset()
                        }
                        when (event.type) {
                            "subtitle" -> {
                                val row = payload.keys().asSequence().associateWith { key -> payload.opt(key).takeUnless { it == JSONObject.NULL } }
                                update(generation) { it.copy(rows = SubtitleHistory.merge(it.rows, row), ready = true) }
                            }
                            "status" -> if (payload.optBoolean("asr_ready")) ready(generation, true)
                        }
                    }
                }
            }
        } finally {
            if (health?.shouldReset(false) == true) backoff.reset()
            readiness.cancelAndJoin()
        }
        if (cleanEof) {
            completed = !taskAlive(base, task, capability, generation)
        }
        completed
    }
}
