package com.streamtranslator.subtitle

import android.app.NotificationManager
import android.content.Intent
import android.os.Looper
import android.text.InputType
import android.view.View
import android.view.ViewGroup
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.widget.EditText
import android.widget.TextView
import androidx.core.graphics.Insets
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import com.google.android.material.button.MaterialButton
import com.google.android.material.slider.Slider
import com.google.android.material.textfield.TextInputLayout
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowSettings

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class AndroidBehaviorTest {
    private val context get() = RuntimeEnvironment.getApplication()
    @Before fun setup() {
        Preferences.initialize(context)
        Preferences.server = ""
        Preferences.autoConnect = false
        Preferences.update(SubtitleSettings())
        SubtitleRepository.disconnect()
    }
    // Only the polling tests run on short intervals; other tests rely on the default request order.
    private var restorePolling: (() -> Unit)? = null
    private fun fastPolling() {
        val status = SubtitleRepository.statusPollIntervalMs
        val active = SubtitleRepository.activeTaskPollIntervalMs
        val waiting = SubtitleRepository.waitingPollIntervalMs
        val backoff = SubtitleRepository.backoffDelaysMs
        restorePolling = {
            SubtitleRepository.statusPollIntervalMs = status
            SubtitleRepository.activeTaskPollIntervalMs = active
            SubtitleRepository.waitingPollIntervalMs = waiting
            SubtitleRepository.backoffDelaysMs = backoff
        }
        SubtitleRepository.statusPollIntervalMs = 20L
        SubtitleRepository.activeTaskPollIntervalMs = 20L
        SubtitleRepository.waitingPollIntervalMs = 20L
        SubtitleRepository.backoffDelaysMs = longArrayOf(20, 20, 20, 20)
    }
    @After fun cleanup() {
        SubtitleRepository.disconnect()
        SubtitleRepository.overlayActive = false
        restorePolling?.invoke()
        shadowOf(Looper.getMainLooper()).idle()
    }
    private fun descendants(view: View): List<View> = listOf(view) +
        if (view is ViewGroup) (0 until view.childCount).flatMap { descendants(view.getChildAt(it)) } else emptyList()

    @Test fun returningToEitherActivityReconnectsOnlyWhenEnabled() {
        for (main in listOf(true, false)) for (enabled in listOf(true, false)) {
            Preferences.server = "http://127.0.0.1:1"
            Preferences.autoConnect = enabled
            SubtitleRepository.disconnect()
            if (main) {
                val controller = Robolectric.buildActivity(MainActivity::class.java).setup()
                assertEquals(enabled, SubtitleRepository.state.value.running)
                controller.pause().stop()
                assertEquals(ConnectionStatus.STOPPED, SubtitleRepository.state.value.status)
                controller.start().resume().visible()
                assertEquals(enabled, SubtitleRepository.state.value.running)
                controller.pause().stop().destroy()
            } else {
                val controller = Robolectric.buildActivity(SettingsActivity::class.java).setup()
                assertEquals(enabled, SubtitleRepository.state.value.running)
                controller.pause().stop()
                controller.start().resume().visible()
                assertEquals(enabled, SubtitleRepository.state.value.running)
                controller.pause().stop().destroy()
            }
        }
    }

    @Test fun transientSettingsUpdatePersistsOnlyAtGestureEnd() {
        val prefs = context.getSharedPreferences("subtitle", android.content.Context.MODE_PRIVATE)
        val sizes = mutableListOf<Int>()
        val listener = android.content.SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
            if (key == "fontSize") sizes += prefs.getInt(key, 0)
        }
        prefs.registerOnSharedPreferenceChangeListener(listener)
        try {
            for (size in 21..30) Preferences.update(Preferences.settings.value.copy(fontSize = size), persist = false)
            assertEquals(30, Preferences.settings.value.fontSize)
            assertEquals(20, prefs.getInt("fontSize", 0))
            assertTrue(sizes.isEmpty())
            Preferences.update(Preferences.settings.value)
            shadowOf(Looper.getMainLooper()).idle()
            assertEquals(listOf(30), sizes)
        } finally { prefs.unregisterOnSharedPreferenceChangeListener(listener) }
    }

    @Test fun legacyBackgroundOpacityMigratesToZeroOverlayOpacity() {
        val prefs = context.getSharedPreferences("subtitle", android.content.Context.MODE_PRIVATE)
        prefs.edit().clear().putInt("backgroundOpacity", 60).commit()
        Preferences.initialize(context)
        assertEquals(60, Preferences.settings.value.backgroundOpacity)
        assertEquals(0, Preferences.settings.value.overlayBackgroundOpacity)
        assertFalse(prefs.contains("backgroundOpacity"))
    }

    @Test fun taskNotFoundDoesNotDisableStatusForNextTask() {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("{\"success\":true,\"task_id\":\"one\"}"))
            server.enqueue(MockResponse().setBody(""))
            server.enqueue(MockResponse().setResponseCode(404).setBody("{\"detail\":\"Task not found\"}"))
            server.enqueue(MockResponse().setBody("{\"success\":true,\"task_id\":\"two\"}"))
            server.enqueue(MockResponse().setBody(""))
            server.enqueue(MockResponse().setBody("{\"success\":true,\"is_running\":false}"))
            try {
                SubtitleRepository.connect(server.url("/").toString().trimEnd('/'))
                awaitState { it.status == ConnectionStatus.TASK_ENDED }
                awaitCondition { server.requestCount >= 6 }
                awaitState { it.status == ConnectionStatus.TASK_ENDED }
                val paths = (1..6).map { server.takeRequest(1, java.util.concurrent.TimeUnit.SECONDS)?.path }
                assertEquals("/api/translation/status/one", paths[2])
                assertEquals("/api/translation/status/two", paths[5])
            } finally { SubtitleRepository.disconnect() }
        }
    }

    @Test fun uriGoConnectsAndSingleButtonDisconnects() {
        val controller = Robolectric.buildActivity(MainActivity::class.java).setup()
        val activity = controller.get()
        val views = descendants(activity.window.decorView)
        val address = views.filterIsInstance<EditText>().single()
        assertEquals(InputType.TYPE_TEXT_VARIATION_URI, address.inputType and InputType.TYPE_MASK_VARIATION)
        assertEquals(EditorInfo.IME_ACTION_GO, address.imeOptions)
        assertEquals(TextInputLayout.BOX_BACKGROUND_OUTLINE, views.filterIsInstance<TextInputLayout>().single().boxBackgroundMode)
        address.setText("http://127.0.0.1:1")
        address.onEditorAction(EditorInfo.IME_ACTION_GO)
        shadowOf(Looper.getMainLooper()).idle()
        assertTrue(SubtitleRepository.state.value.running)
        assertTrue(Preferences.autoConnect)
        val disconnect = views.filterIsInstance<MaterialButton>().single { it.text == activity.getString(R.string.disconnect) }
        disconnect.performClick()
        shadowOf(Looper.getMainLooper()).idle()
        assertFalse(SubtitleRepository.state.value.running)
        assertFalse(Preferences.autoConnect)
        assertEquals(activity.getString(R.string.connect), disconnect.text)
        val subtitle = views.filterIsInstance<SubtitleView>().single()
        val note = views.filterIsInstance<TextView>().single { it.text == activity.getString(R.string.overlay_active_note) }
        assertEquals(View.VISIBLE, subtitle.visibility)
        assertEquals(View.GONE, note.visibility)
        SubtitleRepository.overlayActive = true
        shadowOf(Looper.getMainLooper()).idle()
        assertTrue(views.filterIsInstance<MaterialButton>().any { it.text == activity.getString(R.string.close_overlay) })
        assertEquals(View.GONE, subtitle.visibility)
        assertEquals(View.VISIBLE, note.visibility)
        controller.pause().stop().destroy()
    }

    @Test fun savedAddressAutoConnectsAndInsetsSurviveImmersiveMode() {
        Preferences.server = "http://127.0.0.1:1"
        Preferences.autoConnect = true
        val controller = Robolectric.buildActivity(MainActivity::class.java).setup()
        val activity = controller.get()
        val root = activity.findViewById<ViewGroup>(android.R.id.content).getChildAt(0)
        assertEquals(Preferences.server, descendants(root).filterIsInstance<EditText>().single().text.toString())
        assertTrue(SubtitleRepository.state.value.running)
        val bars = WindowInsetsCompat.Type.systemBars()
        val insets = WindowInsetsCompat.Builder().setInsets(bars, Insets.of(0, 30, 0, 40))
            .setInsetsIgnoringVisibility(bars, Insets.of(0, 30, 0, 40)).build()
        ViewCompat.dispatchApplyWindowInsets(root, insets)
        assertEquals(30, root.paddingTop)
        assertEquals(40, root.paddingBottom)
        val subtitle = descendants(root).filterIsInstance<SubtitleView>().single()
        subtitle.onTap!!.invoke()
        ViewCompat.dispatchApplyWindowInsets(root, WindowInsetsCompat.Builder(insets)
            .setInsets(bars, Insets.NONE).setVisible(bars, false).build())
        assertEquals(40, root.paddingBottom)
        controller.pause().stop().destroy()
    }

    @Test fun overlayIsTextOnlyTransparentAndKeepsNewestTwoRows() {
        val view = SubtitleView(context)
        view.render(SubtitleState(status = ConnectionStatus.CONNECTED), SubtitleSettings())
        view.measure(View.MeasureSpec.makeMeasureSpec(600, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(1000, View.MeasureSpec.AT_MOST))
        assertFalse(view.hasText)
        assertEquals(0f, view.alpha, 0f)
        assertNull(view.background)
        val rows = (1..3).map { mapOf("id" to it, "original" to "original$it", "translated" to "translated$it") }
        view.render(SubtitleState(rows = rows), SubtitleSettings())
        assertEquals("original2\ntranslated2\noriginal3\ntranslated3", view.contentDescription.toString())
        assertTrue(view.hasText)
        assertEquals(1f, view.alpha, 0f)
        view.render(SubtitleState(rows = rows), SubtitleSettings(showOriginal = false, showTranslated = false))
        assertFalse(view.hasText)
        assertEquals(0f, view.alpha, 0f)
        view.render(SubtitleState(status = ConnectionStatus.TASK_ENDED), SubtitleSettings())
        assertEquals("", view.contentDescription.toString())
        val fullScreen = SubtitleView(context, overlay = false)
        fullScreen.render(SubtitleState(rows = rows), SubtitleSettings(maxDisplayCount = 3))
        assertTrue(fullScreen.contentDescription.contains("original1"))
    }

    @Test fun settingsPreviewUsesSharedRendererAndPersistsImmediately() {
        Preferences.update(SubtitleSettings(backgroundColor = "#123456"))
        val controller = Robolectric.buildActivity(SettingsActivity::class.java).setup()
        val views = descendants(controller.get().window.decorView)
        val preview = views.filterIsInstance<SubtitleView>().single()
        shadowOf(Looper.getMainLooper()).idle()
        assertTrue(preview.hasText)
        val sliders = views.filterIsInstance<Slider>()
        assertTrue(sliders.isNotEmpty() && sliders.all { !it.isTickVisible })
        assertTrue(views.any { it.contentDescription == "背景顏色 #000000" })
        assertTrue(views.any { it.contentDescription == "背景顏色 #123456" && it.visibility == View.VISIBLE && it.isSelected })
        val original = views.filterIsInstance<com.google.android.material.materialswitch.MaterialSwitch>().first()
        original.isChecked = false
        shadowOf(Looper.getMainLooper()).idle()
        assertFalse(Preferences.settings.value.showOriginal)
        assertFalse(preview.contentDescription.contains("\u307f\u306a\u3055\u3093"))
        assertEquals(6, views.filterIsInstance<com.google.android.material.card.MaterialCardView>().size)
        val fullscreenBtn = views.filterIsInstance<MaterialButton>().single { it.text == "全螢幕樣式" }
        fullscreenBtn.performClick()
        shadowOf(Looper.getMainLooper()).idle()
        assertFalse(preview.overlay)
        val overlayBtn = views.filterIsInstance<MaterialButton>().single { it.text == "懸浮樣式" }
        overlayBtn.performClick()
        shadowOf(Looper.getMainLooper()).idle()
        assertTrue(preview.overlay)
        Preferences.savePosition(false, 100, 200, true)
        Preferences.resetPosition()
        val rev = Preferences.settings.value.positionRevision
        assertTrue(rev > 0)
        Preferences.initialize(context)
        assertEquals(rev, Preferences.settings.value.positionRevision)
        assertEquals(Int.MIN_VALUE, Preferences.overlayX(false))
        assertEquals(Int.MIN_VALUE, Preferences.overlayY(false))
        controller.pause().stop().destroy()
    }

    @Test fun positionsAreIndependentAndVerticalDragPreservesCentering() {
        Preferences.resetPosition()
        Preferences.savePosition(false, 100, 200, false)
        assertEquals(Int.MIN_VALUE, Preferences.overlayX(false))
        assertEquals(200, Preferences.overlayY(false))
        Preferences.savePosition(true, 50, 80, true)
        assertEquals(50, Preferences.overlayX(true))
        assertEquals(Int.MIN_VALUE, Preferences.overlayX(false))
        Preferences.savePosition(false, 90, 220, true)
        assertEquals(50, Preferences.overlayX(true))
        assertEquals(90, Preferences.overlayX(false))
        Preferences.resetPosition()
        for (landscape in listOf(false, true)) {
            assertEquals(Int.MIN_VALUE, Preferences.overlayX(landscape))
            assertEquals(Int.MIN_VALUE, Preferences.overlayY(landscape))
        }
    }

    @Test fun settingsControlsFollowExternalLockAndPinchChanges() {
        val controller = Robolectric.buildActivity(SettingsActivity::class.java).setup()
        val views = descendants(controller.get().window.decorView)
        Preferences.update(Preferences.settings.value.copy(mousePassthrough = true, fontSize = 37, translatedFontSize = 43))
        shadowOf(Looper.getMainLooper()).idle()
        val lock = views.filterIsInstance<com.google.android.material.materialswitch.MaterialSwitch>().last()
        val sizes = views.filterIsInstance<com.google.android.material.slider.Slider>().filter { it.valueTo == 200f }
        assertTrue(lock.isChecked)
        assertEquals(listOf(37f, 43f), sizes.map { it.value })
        Preferences.update(Preferences.settings.value.copy(mousePassthrough = false))
        shadowOf(Looper.getMainLooper()).idle()
        assertFalse(lock.isChecked)
        controller.pause().stop().destroy()
    }

    @Test fun fadeKeepsPendingTargetAndCancellationNeverAppliesStaleRows() {
        val view = SubtitleView(context)
        val settings = SubtitleSettings(showTranslated = false)
        fun state(vararg ids: Int) = SubtitleState(rows = ids.map { mapOf("id" to it, "original" to "row$it") })
        view.render(state(1, 2), settings)
        view.measure(View.MeasureSpec.makeMeasureSpec(600, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(1000, View.MeasureSpec.AT_MOST))
        view.layout(0, 0, 600, view.measuredHeight)
        view.render(state(2, 3), settings)
        shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofMillis(64))
        view.render(state(2, 3).copy(ready = true), settings)
        view.render(SubtitleState(rows = listOf(mapOf("id" to 2, "original" to "updated"),
            mapOf("id" to 3, "original" to "row3"))), settings)
        shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofMillis(200))
        assertEquals("updated\nrow3", view.contentDescription.toString())
        view.render(state(3, 4), settings)
        view.render(SubtitleState(), settings)
        shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofMillis(200))
        assertFalse(view.hasText)
    }

    @Test fun repeatedMeasureReusesLayoutsAndHardwareTextOnModernAndroid() {
        val view = SubtitleView(context)
        view.render(SubtitleState(rows = listOf(mapOf("original" to "hello"))), SubtitleSettings())
        val width = View.MeasureSpec.makeMeasureSpec(600, View.MeasureSpec.EXACTLY)
        val height = View.MeasureSpec.makeMeasureSpec(1000, View.MeasureSpec.AT_MOST)
        view.measure(width, height)
        val heightBefore = view.measuredHeight
        val description = view.contentDescription
        view.forceLayout(); view.measure(width, height)
        assertEquals(heightBefore, view.measuredHeight)
        assertEquals(description, view.contentDescription)
        assertEquals(View.LAYER_TYPE_NONE, view.layerType)
        view.measure(View.MeasureSpec.makeMeasureSpec(400, View.MeasureSpec.EXACTLY), height)
        assertEquals(400, view.measuredWidth)
        assertEquals(description, view.contentDescription)
    }

    @Test @Config(sdk = [26]) fun oldAndroidUsesSoftwareTextShadow() {
        assertEquals(View.LAYER_TYPE_SOFTWARE, SubtitleView(context).layerType)
    }

    @Test fun overlaySlopDragDoubleTapAndLockedAlpha() {
        Preferences.resetPosition()
        ShadowSettings.setCanDrawOverlays(true)
        val controller = Robolectric.buildService(OverlayService::class.java).create()
        val service = controller.get()
        service.onStartCommand(Intent(context, OverlayService::class.java).setAction(OverlayService.ACTION_START), 0, 1)
        shadowOf(Looper.getMainLooper()).idle()
        val box = checkNotNull(service.overlayView)
        val params = box.layoutParams as WindowManager.LayoutParams
        assertEquals(0, params.flags and WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        var time = android.os.SystemClock.uptimeMillis()
        fun touch(action: Int, x: Float, y: Float) {
            val event = android.view.MotionEvent.obtain(time, time + 10, action, x, y, 0)
            box.dispatchTouchEvent(event); event.recycle(); time += 50
        }
        val x = params.x; val y = params.y
        touch(0, 100f, 100f); touch(2, 101f, 101f); touch(1, 101f, 101f)
        assertEquals(x, params.x); assertEquals(y, params.y)
        assertEquals(Int.MIN_VALUE, Preferences.overlayX(false))
        touch(0, 100f, 100f)
        assertNull(shadowOf(service).nextStartedActivity)
        touch(1, 100f, 100f)
        assertNotNull(shadowOf(service).nextStartedActivity)
        time += 1000
        touch(0, 100f, 100f); touch(1, 100f, 100f)
        touch(0, 100f, 100f); touch(2, 100f, 200f); touch(1, 100f, 200f)
        assertNull(shadowOf(service).nextStartedActivity)
        assertEquals(Int.MIN_VALUE, Preferences.overlayX(false))
        assertNotEquals(Int.MIN_VALUE, Preferences.overlayY(false))
        assertFalse(Preferences.settings.value.mousePassthrough)
        Preferences.update(Preferences.settings.value.copy(mousePassthrough = true))
        shadowOf(Looper.getMainLooper()).idle()
        assertEquals(0.79f, params.alpha, 0f)
        val manager = context.getSystemService(NotificationManager::class.java)
        val lockedText = shadowOf(manager).getNotification(100).extras.getCharSequence(android.app.Notification.EXTRA_TEXT).toString()
        assertTrue(lockedText.contains(context.getString(R.string.notification_locked)))
        controller.destroy()
    }

    @Test fun staleActionStopsWithoutWindowAndDismissalRepostsWhileRunning() {
        val stale = Robolectric.buildService(OverlayService::class.java).create()
        stale.get().onStartCommand(Intent(context, OverlayService::class.java).setAction("com.streamtranslator.subtitle.TOUCH"), 0, 1)
        assertFalse(SubtitleRepository.overlayActive)
        assertTrue(shadowOf(stale.get()).isStoppedBySelf)
        stale.destroy()

        ShadowSettings.setCanDrawOverlays(true)
        val live = Robolectric.buildService(OverlayService::class.java).create()
        live.get().onStartCommand(Intent(context, OverlayService::class.java).setAction(OverlayService.ACTION_START), 0, 2)
        assertTrue(SubtitleRepository.overlayActive)
        val box = checkNotNull(live.get().overlayView)
        assertNull(box.background)
        val params = box.layoutParams as WindowManager.LayoutParams
        assertEquals(WindowManager.LayoutParams.WRAP_CONTENT, params.height)
        val wm = box.context.getSystemService(WindowManager::class.java)
        val metrics = wm.currentWindowMetrics
        val bars = metrics.windowInsets.getInsetsIgnoringVisibility(android.view.WindowInsets.Type.systemBars())
        assertEquals((metrics.bounds.width() - bars.left - bars.right) * 92 / 100, params.width)
        val manager = context.getSystemService(NotificationManager::class.java)
        val notification = shadowOf(manager).getNotification(100)
        val unlockedText = notification.extras.getCharSequence(android.app.Notification.EXTRA_TEXT).toString()
        assertTrue(unlockedText.contains(context.getString(R.string.notification_unlocked)))
        assertNotNull(notification.deleteIntent)
        assertEquals(3, notification.actions.size)
        assertEquals(context.getString(R.string.settings), notification.actions[1].title.toString())
        assertEquals(SettingsActivity::class.java.name,
            shadowOf(notification.actions[1].actionIntent).savedIntent.component?.className)
        val open = shadowOf(notification.contentIntent).savedIntent
        assertEquals(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP,
            open.flags and (Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP))
        manager.cancel(100)
        live.get().onStartCommand(shadowOf(notification.deleteIntent).savedIntent, 0, 3)
        assertNotNull(shadowOf(manager).getNotification(100))
        live.destroy()
        assertFalse(SubtitleRepository.overlayActive)
    }

    @Test
    @org.robolectric.annotation.GraphicsMode(org.robolectric.annotation.GraphicsMode.Mode.NATIVE)
    fun backgroundHasOneUniformAlphaAndEmptyViewDrawsNothing() {
        val view = SubtitleView(context)
        fun bitmap(): android.graphics.Bitmap {
            view.measure(View.MeasureSpec.makeMeasureSpec(600, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(1000, View.MeasureSpec.AT_MOST))
            view.layout(0, 0, view.measuredWidth, view.measuredHeight)
            return android.graphics.Bitmap.createBitmap(view.width, view.height, android.graphics.Bitmap.Config.ARGB_8888)
                .also { view.draw(android.graphics.Canvas(it)) }
        }
        view.render(SubtitleState(rows = listOf(mapOf("original" to "hello", "translated" to "world"))),
            SubtitleSettings(overlayBackgroundOpacity = 50))
        val rendered = bitmap()
        val x = context.dp(8)
        assertEquals(127, android.graphics.Color.alpha(rendered.getPixel(x, rendered.height / 3)))
        assertEquals(rendered.getPixel(x, rendered.height / 3), rendered.getPixel(x, rendered.height * 2 / 3))
        view.render(SubtitleState(), SubtitleSettings(overlayBackgroundOpacity = 50))
        val empty = bitmap()
        assertEquals(0, android.graphics.Color.alpha(empty.getPixel(0, 0)))
    }

    @Test
    @org.robolectric.annotation.GraphicsMode(org.robolectric.annotation.GraphicsMode.Mode.NATIVE)
    fun fadingPreservesFillColorAndCompositesOutlineWithIt() {
        val view = SubtitleView(context)
        view.render(SubtitleState(rows = listOf(mapOf("original" to "MMMM"))),
            SubtitleSettings(textColor = "#FFFFFF", fontSize = 60, shadowRadius = 0, backgroundOpacity = 0))
        view.measure(View.MeasureSpec.makeMeasureSpec(600, View.MeasureSpec.EXACTLY),
            View.MeasureSpec.makeMeasureSpec(1000, View.MeasureSpec.AT_MOST))
        view.layout(0, 0, 600, view.measuredHeight)
        fun draw() = android.graphics.Bitmap.createBitmap(view.width, view.height,
            android.graphics.Bitmap.Config.ARGB_8888).also { view.draw(android.graphics.Canvas(it)) }
        val full = draw()
        view.render(SubtitleState(rows = listOf(mapOf("original" to "next"))),
            SubtitleSettings(textColor = "#FFFFFF", fontSize = 60, shadowRadius = 0, backgroundOpacity = 0))
        val fade = requireNotNull(view.fadeAnimator) { "the oldest row should start fading" }
        fade.pause(); fade.currentPlayTime = 80
        val faded = draw()
        var whitePixels = 0
        for (y in 0 until full.height) for (x in 0 until full.width) {
            if (full.getPixel(x, y) == android.graphics.Color.WHITE) {
                val pixel = faded.getPixel(x, y)
                assertTrue(android.graphics.Color.alpha(pixel) in 1..254)
                assertTrue(android.graphics.Color.red(pixel) >= 254)
                whitePixels++
            }
        }
        assertTrue(whitePixels > 0)
    }

    private fun awaitState(predicate: (SubtitleState) -> Boolean) {
        val deadline = System.nanoTime() + 5_000_000_000L
        while (!predicate(SubtitleRepository.state.value) && System.nanoTime() < deadline) {
            shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofMillis(10))
            java.util.concurrent.locks.LockSupport.parkNanos(1_000_000L)
        }
        assertTrue(SubtitleRepository.state.value.toString(), predicate(SubtitleRepository.state.value))
    }

    private fun awaitCondition(predicate: () -> Boolean) {
        val deadline = System.nanoTime() + 5_000_000_000L
        while (!predicate() && System.nanoTime() < deadline) {
            shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofMillis(10))
            java.util.concurrent.locks.LockSupport.parkNanos(1_000_000L)
        }
        assertTrue(predicate())
    }

    @Test fun releasedServerWithoutStatusKeepsOneStreamAndSubtitleProvesReadiness() {
        fastPolling()
        MockWebServer().use { server ->
            val statusRequests = java.util.concurrent.atomic.AtomicInteger()
            val streams = java.util.concurrent.atomic.AtomicInteger()
            val activeRequests = java.util.concurrent.atomic.AtomicInteger()
            server.dispatcher = object : okhttp3.mockwebserver.Dispatcher() {
                override fun dispatch(request: okhttp3.mockwebserver.RecordedRequest): MockResponse =
                    when (request.path) {
                        "/api/translation/active-task" -> {
                            activeRequests.incrementAndGet()
                            MockResponse().setBody("{\"success\":true,\"task_id\":\"one\"}")
                        }
                        "/api/translation/status/one" -> {
                            statusRequests.incrementAndGet()
                            MockResponse().setResponseCode(404).setBody("{\"detail\":\"Not found\"}")
                        }
                        "/api/translation/stream/one" -> {
                            streams.incrementAndGet()
                            val event = "event: subtitle\ndata: {\"id\":1,\"original\":\"hello\"}\n\n" +
                                "event: status\ndata: {\"asr_ready\":false}\n\n"
                            MockResponse().setHeader("Content-Type", "text/event-stream")
                                .setBody(event + ": heartbeat\n\n".repeat(10000))
                                .throttleBody(event.toByteArray().size.toLong(), 1, java.util.concurrent.TimeUnit.SECONDS)
                        }
                        else -> MockResponse().setResponseCode(404).setBody("{\"detail\":\"Not Found\"}")
                    }
            }
            try {
                SubtitleRepository.connect(server.url("/").toString().trimEnd('/'))
                awaitState { it.status == ConnectionStatus.CONNECTED && it.ready && it.rows.size == 1 }
                awaitCondition { activeRequests.get() >= 5 }
                assertEquals(ConnectionStatus.CONNECTED, SubtitleRepository.state.value.status)
                assertTrue(SubtitleRepository.state.value.ready)
                assertEquals(1, streams.get())
                assertEquals(1, statusRequests.get())
            } finally { SubtitleRepository.disconnect(); shadowOf(Looper.getMainLooper()).idle() }
        }
    }

    @Test fun cleanEofOnLegacyServerUsesActiveTaskAndRemembersMissingEndpoint() {
        MockWebServer().use { server ->
            val statusRequests = java.util.concurrent.atomic.AtomicInteger()
            val streams = java.util.concurrent.atomic.AtomicInteger()
            server.dispatcher = object : okhttp3.mockwebserver.Dispatcher() {
                override fun dispatch(request: okhttp3.mockwebserver.RecordedRequest): MockResponse =
                    when {
                        request.path == "/api/translation/active-task" ->
                            MockResponse().setBody("{\"success\":true,\"task_id\":\"one\"}")
                        request.path == "/api/translation/status/one" -> {
                            statusRequests.incrementAndGet(); MockResponse().setResponseCode(404).setBody("{\"detail\":\"Not Found\"}")
                        }
                        else -> {
                            streams.incrementAndGet(); MockResponse().setBody("")
                        }
                    }
            }
            try {
                SubtitleRepository.connect(server.url("/").toString().trimEnd('/'))
                awaitState { it.status == ConnectionStatus.RECONNECTING }
                assertEquals(1, statusRequests.get())
                shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofSeconds(1))
                awaitCondition { streams.get() == 2 }
                awaitState { it.status == ConnectionStatus.RECONNECTING }
                assertEquals(1, statusRequests.get())
            } finally { SubtitleRepository.disconnect(); shadowOf(Looper.getMainLooper()).idle() }
        }
    }

    @Test fun legacyPollingDetectsTaskReplacementAbsenceAndThreeFailures() {
        fastPolling()
        for (mode in listOf("replacement", "absent", "failures", "transport")) {
            MockWebServer().use { server ->
                val checks = java.util.concurrent.atomic.AtomicInteger()
                server.dispatcher = object : okhttp3.mockwebserver.Dispatcher() {
                    override fun dispatch(request: okhttp3.mockwebserver.RecordedRequest): MockResponse =
                        when (request.path) {
                            "/api/translation/active-task" -> {
                                val check = checks.getAndIncrement()
                                when {
                                    check == 0 -> MockResponse().setBody("{\"success\":true,\"task_id\":\"one\"}")
                                    mode == "replacement" -> MockResponse().setBody("{\"success\":true,\"task_id\":\"two\"}")
                                    mode == "absent" -> MockResponse().setBody("{\"success\":false,\"task_id\":null}")
                                    mode == "transport" -> MockResponse().setSocketPolicy(okhttp3.mockwebserver.SocketPolicy.DISCONNECT_AFTER_REQUEST)
                                    else -> MockResponse().setResponseCode(503)
                                }
                            }
                            "/api/translation/status/one" -> MockResponse().setResponseCode(404).setBody("{\"detail\":\"Not Found\"}")
                            else -> {
                                val event = "event: subtitle\ndata: {\"original\":\"hello\"}\n\n"
                                MockResponse().setBody(event + ": ping\n\n".repeat(10000))
                                    .throttleBody(event.length.toLong(), 1, java.util.concurrent.TimeUnit.SECONDS)
                            }
                        }
                }
                try {
                    SubtitleRepository.connect(server.url("/").toString().trimEnd('/'))
                    awaitState { it.status == ConnectionStatus.CONNECTED && it.ready }
                    if (mode == "failures" || mode == "transport") {
                        awaitCondition { checks.get() >= 4 }
                        awaitState { it.status == ConnectionStatus.RECONNECTING && !it.ready }
                        assertTrue(checks.get() >= 4)
                    } else {
                        awaitCondition { checks.get() >= 2 }
                        awaitState { it.status == ConnectionStatus.TASK_ENDED && !it.ready }
                    }
                    assertFalse(SubtitleRepository.state.value.ready)
                } finally { SubtitleRepository.disconnect(); shadowOf(Looper.getMainLooper()).idle() }
            }
        }
    }

    @Test fun completedStreamShowsTaskEndedAndReturnsToDiscovery() {
        for (endStatus in listOf("completed", "stopped", "error")) {
            MockWebServer().use { server ->
                server.enqueue(MockResponse().setBody("{\"success\":true,\"task_id\":\"one\"}"))
                server.enqueue(MockResponse().setBody("event: status\ndata: {\"status\":\"$endStatus\"}\n\n"))
                server.enqueue(MockResponse().setBody("{\"success\":false,\"task_id\":null}"))
                SubtitleRepository.connect(server.url("/").toString().trimEnd('/'))
                awaitState { it.status == ConnectionStatus.TASK_ENDED }
                shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofSeconds(1))
                val deadline = System.nanoTime() + 3_000_000_000L
                while (server.requestCount < 3 && System.nanoTime() < deadline) {
                    shadowOf(Looper.getMainLooper()).idle()
                    java.util.concurrent.locks.LockSupport.parkNanos(1_000_000L)
                }
                assertEquals(3, server.requestCount)
                assertEquals("/api/translation/active-task", server.takeRequest().path)
                assertEquals("/api/translation/stream/one", server.takeRequest().path)
                assertEquals("/api/translation/active-task", server.takeRequest().path)
                assertEquals(ConnectionStatus.TASK_ENDED, SubtitleRepository.state.value.status)
                SubtitleRepository.disconnect()
            }
        }
    }

    @Test fun cleanEofRechecksTaskAndPollsDiscoveryWhenEnded() {
        for (missing in listOf(false, true)) {
            MockWebServer().use { server ->
                server.enqueue(MockResponse().setBody("{\"success\":true,\"task_id\":\"one\"}"))
                server.enqueue(MockResponse().setBody("event: status\ndata: {\"asr_ready\":true}\n\n"))
                server.enqueue(if (missing) MockResponse().setResponseCode(404).setBody("{\"detail\":\"Not Found\"}")
                    else MockResponse().setBody("{\"success\":true,\"is_running\":false}"))
                server.enqueue(MockResponse().setBody("{\"success\":false,\"task_id\":null}"))
                SubtitleRepository.connect(server.url("/").toString().trimEnd('/'))
                awaitState { it.status == ConnectionStatus.TASK_ENDED }
                assertFalse(SubtitleRepository.state.value.ready)
                shadowOf(Looper.getMainLooper()).idleFor(java.time.Duration.ofSeconds(1))
                assertEquals("/api/translation/active-task", server.takeRequest(3, java.util.concurrent.TimeUnit.SECONDS)?.path)
                assertEquals("/api/translation/stream/one", server.takeRequest(3, java.util.concurrent.TimeUnit.SECONDS)?.path)
                assertEquals("/api/translation/status/one", server.takeRequest(3, java.util.concurrent.TimeUnit.SECONDS)?.path)
                assertEquals("/api/translation/active-task", server.takeRequest(3, java.util.concurrent.TimeUnit.SECONDS)?.path)
                awaitState { it.status == ConnectionStatus.TASK_ENDED }
                SubtitleRepository.disconnect()
            }
        }
    }

    @Test fun cleanEofWhileTaskRunsStillReconnects() {
        MockWebServer().use { server ->
            server.enqueue(MockResponse().setBody("{\"success\":true,\"task_id\":\"one\"}"))
            server.enqueue(MockResponse().setBody(""))
            server.enqueue(MockResponse().setBody("{\"success\":true,\"is_running\":true}"))
            SubtitleRepository.connect(server.url("/").toString().trimEnd('/'))
            awaitState { it.status == ConnectionStatus.RECONNECTING }
            assertEquals(3, server.requestCount)
            SubtitleRepository.disconnect()
        }
    }

    @Test fun freshLaunchHonorsPersistedDisconnectAndIgnoresInvalidSavedServer() {
        for ((server, enabled) in listOf("http://127.0.0.1:1" to false, "http://invalid:" to true)) {
            Preferences.server = server
            Preferences.autoConnect = enabled
            val controller = Robolectric.buildActivity(MainActivity::class.java).setup()
            assertFalse(SubtitleRepository.state.value.running)
            assertNull(descendants(controller.get().window.decorView).filterIsInstance<EditText>().single().error)
            controller.pause().stop().destroy()
        }
    }

    @Test fun oversizedHttpErrorRetainsStatusCodeAndDisabledDetail() {
        for (disabled in listOf(false, true)) {
            MockWebServer().use { server ->
                server.enqueue(MockResponse().setResponseCode(404).setBody("{\"detail\":\"Not Found\"}").setBody(
                    (if (disabled) "sharing is disabled" else "missing") + "x".repeat(MAX_BODY_BYTES + 1)))
                SubtitleRepository.connect(server.url("/").toString().trimEnd('/'))
                awaitState { it.status == if (disabled) ConnectionStatus.SHARING_DISABLED else ConnectionStatus.SERVICE_NOT_FOUND }
                SubtitleRepository.disconnect()
            }
        }
    }

    @Test fun restoredUnsavedAddressNeverControlsAutoConnect() {
        for (enabled in listOf(false, true)) {
            Preferences.server = "http://127.0.0.1:1"
            Preferences.autoConnect = enabled
            SubtitleRepository.connect("") // A new process starts UNCONFIGURED.
            val saved = android.os.Bundle().apply { putString("address", "http://invalid:") }
            val controller = Robolectric.buildActivity(MainActivity::class.java).setup(saved)
            val address = descendants(controller.get().window.decorView).filterIsInstance<EditText>().single()
            assertNull(address.error)
            assertEquals(enabled, SubtitleRepository.state.value.running)
            assertEquals("http://127.0.0.1:1", Preferences.server)
            controller.pause().stop().destroy()
        }
    }

    @Test fun oversizedDiscoveryAndStreamUseNormalReconnectPath() {
        for (stream in listOf(false, true)) {
            MockWebServer().use { server ->
                if (stream) server.enqueue(MockResponse().setBody("{\"success\":true,\"task_id\":\"one\"}"))
                server.enqueue(MockResponse().setBody("x".repeat(if (stream) MAX_LINE_BYTES.toInt() + 1 else MAX_BODY_BYTES + 1)))
                SubtitleRepository.connect(server.url("/").toString().trimEnd('/'))
                awaitState { it.status == ConnectionStatus.RECONNECTING }
                assertTrue(SubtitleRepository.state.value.running)
                SubtitleRepository.disconnect()
            }
        }
    }
}
