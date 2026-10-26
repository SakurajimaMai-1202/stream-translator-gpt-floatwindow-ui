package com.streamtranslator.subtitle

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Intent
import android.content.res.Configuration
import android.content.pm.ServiceInfo
import android.graphics.PixelFormat
import android.os.Build
import android.provider.Settings
import android.view.GestureDetector
import android.view.ScaleGestureDetector
import android.view.Gravity
import android.view.Display
import android.hardware.display.DisplayManager
import android.view.MotionEvent
import android.view.WindowInsets
import android.content.Context
import android.graphics.Rect
import android.view.WindowManager
import android.view.ViewConfiguration
import kotlin.math.abs
import android.widget.*
import androidx.annotation.VisibleForTesting
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch

// shortSide is the physical screen short side (system bars included), so landscape is exactly 1.5x the portrait width.
internal fun overlayWidthPx(usableWidth: Int, usableHeight: Int, percent: Int, shortSide: Int = minOf(usableWidth, usableHeight)): Int {
    val base = shortSide * percent / 100
    val width = minOf(usableWidth, if (usableWidth <= usableHeight) base else base * 3 / 2)
    return width.coerceAtLeast(1)
}

class OverlayService : LifecycleService() {
    private lateinit var overlayContext: Context
    private lateinit var manager: WindowManager
    private lateinit var box: SubtitleView
    private lateinit var params: WindowManager.LayoutParams
    private lateinit var subtitles: SubtitleView
    @VisibleForTesting internal val overlayView: SubtitleView? get() = if (added) box else null
    // Same source as the width rule, so the saved position and the width always agree on orientation.
    private val landscape: Boolean get() = usableBounds().let { it.width() > it.height() }
    private var added = false
    // Bottom offset the user chose. params.y is this clamped to the current text height,
    // so a long line moves the window only while it is shown instead of ratcheting it down.
    private var wantedY = Int.MIN_VALUE
    private var stopConnection = false
    private var touchThrough = false
    private var positionRevision = -1
    private var recomputeOnNextLayout = false
    private var lastNotification: Pair<ConnectionStatus, Boolean>? = null

    override fun onCreate() {
        super.onCreate()
        Preferences.initialize(this)
        getSystemService(NotificationManager::class.java).createNotificationChannel(
            NotificationChannel(CHANNEL, getString(R.string.notification_channel), NotificationManager.IMPORTANCE_LOW)
        )
    }
    private fun createOverlay() {
        val notification = notification(SubtitleRepository.state.value)
        if (Build.VERSION.SDK_INT >= 34) startForeground(NOTIFICATION, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        else startForeground(NOTIFICATION, notification)
        if (!Settings.canDrawOverlays(this)) { stopSelf(); return }
        // A Service has no display; derive a display context first, or createWindowContext throws.
        overlayContext = if (Build.VERSION.SDK_INT >= 30) {
            val display = getSystemService(DisplayManager::class.java).getDisplay(Display.DEFAULT_DISPLAY)
            createDisplayContext(display).createWindowContext(WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY, null)
        } else this
        manager = overlayContext.getSystemService(WindowManager::class.java)
        subtitles = SubtitleView(overlayContext)
        box = subtitles
        params = WindowManager.LayoutParams(
            overlayWidth(), WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                (if (SubtitleRepository.state.value.status == ConnectionStatus.CONNECTED) WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON else 0),
            PixelFormat.TRANSLUCENT
        ).apply { gravity = Gravity.BOTTOM or Gravity.LEFT; x = Preferences.overlayX(landscape) }
        wantedY = Preferences.overlayY(landscape)
        clampPosition()
        var downX = 0f
        var downY = 0f
        var originX = 0
        var originY = 0
        var scaled = false
        var dragging = false
        var horizontal = false
        val slop = ViewConfiguration.get(this).scaledTouchSlop
        var originalSize = 20f
        var translatedSize = 24f
        val pinch = ScaleGestureDetector(this, object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScaleBegin(detector: ScaleGestureDetector): Boolean {
                scaled = true
                originalSize = Preferences.settings.value.fontSize.toFloat()
                translatedSize = Preferences.settings.value.translatedFontSize.toFloat()
                return true
            }
            override fun onScale(detector: ScaleGestureDetector): Boolean {
                originalSize = (originalSize * detector.scaleFactor).coerceIn(10f, 200f)
                translatedSize = (translatedSize * detector.scaleFactor).coerceIn(10f, 200f)
                Preferences.update(Preferences.settings.value.copy(fontSize = originalSize.toInt(), translatedFontSize = translatedSize.toInt()), persist = false)
                return true
            }
            override fun onScaleEnd(detector: ScaleGestureDetector) {
                Preferences.update(Preferences.settings.value)
            }
        })
        pinch.isQuickScaleEnabled = false
        val gestures = GestureDetector(this, object : GestureDetector.SimpleOnGestureListener() {
            override fun onDown(event: MotionEvent) = true
            override fun onDoubleTapEvent(event: MotionEvent): Boolean {
                if (event.actionMasked == MotionEvent.ACTION_UP && !dragging && !scaled &&
                    abs(event.rawX - downX) <= slop && abs(event.rawY - downY) <= slop) startActivity(Intent(this@OverlayService, MainActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP))
                return true
            }
            override fun onLongPress(event: MotionEvent) {
                if (scaled || dragging) return
                if (notificationsAllowed()) {
                    Preferences.update(Preferences.settings.value.copy(mousePassthrough = true))
                    Toast.makeText(this@OverlayService, R.string.overlay_locked, Toast.LENGTH_SHORT).show()
                } else Toast.makeText(this@OverlayService, R.string.notification_needed, Toast.LENGTH_LONG).show()
            }
        })
        box.setOnTouchListener { view, event ->
            if (event.actionMasked == MotionEvent.ACTION_DOWN) {
                scaled = false; dragging = false; horizontal = false
                gestures.setIsLongpressEnabled(true)
                downX = event.rawX; downY = event.rawY; originX = params.x; originY = params.y
            }
            if (event.pointerCount > 1) scaled = true
            val dx = event.rawX - downX
            val dy = event.rawY - downY
            if (!scaled && event.actionMasked == MotionEvent.ACTION_MOVE &&
                (dragging || dx * dx + dy * dy > slop * slop)) {
                if (!dragging) {
                    dragging = true
                    gestures.setIsLongpressEnabled(false)
                    val cancel = MotionEvent.obtain(event).apply { action = MotionEvent.ACTION_CANCEL }
                    gestures.onTouchEvent(cancel); cancel.recycle()
                }
                horizontal = horizontal || abs(dx) > slop
                if (horizontal) params.x = originX + dx.toInt()
                wantedY = originY - dy.toInt()
                clampPosition(); wantedY = params.y; updateWindow()
            }
            pinch.onTouchEvent(event)
            if (!dragging && !scaled) gestures.onTouchEvent(event)
            else gestures.setIsLongpressEnabled(false)
            when (event.actionMasked) {
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> {
                    if (dragging) Preferences.savePosition(landscape, params.x, params.y, horizontal)
                    if (event.actionMasked == MotionEvent.ACTION_UP && !dragging && !scaled) view.performClick()
                }
            }
            true
        }
        box.addOnLayoutChangeListener { _, _, _, _, _, _, _, _, _ ->
            if (recomputeOnNextLayout) {
                recomputeOnNextLayout = false
                recomputeBoundsAndPosition()
            } else {
                val oldY = params.y
                clampPosition()
                if (oldY != params.y) updateWindow()
            }
        }
        try {
            manager.addView(box, params)
            added = true
        } catch (_: RuntimeException) {
            Toast.makeText(this, R.string.overlay_failed, Toast.LENGTH_LONG).show()
            stopSelf(); return
        }
        SubtitleRepository.overlayActive = true
        lifecycleScope.launch {
            while (isActive) {
                delay(2000)
                if (!Settings.canDrawOverlays(this@OverlayService)) { stopSelf(); break }
                if (Preferences.settings.value.mousePassthrough && !notificationsAllowed()) {
                    Preferences.update(Preferences.settings.value.copy(mousePassthrough = false))
                    Toast.makeText(this@OverlayService, R.string.notification_needed, Toast.LENGTH_LONG).show()
                }
            }
        }
        lifecycleScope.launch {
            combine(SubtitleRepository.state, Preferences.settings) { state, settings -> state to settings }
                .collect { (state, settings) ->
                    val notificationsAllowed = notificationsAllowed()
                    if (settings.mousePassthrough && !notificationsAllowed) {
                        Preferences.update(settings.copy(mousePassthrough = false))
                        Toast.makeText(this@OverlayService, R.string.notification_needed, Toast.LENGTH_LONG).show()
                    }
                    touchThrough = settings.mousePassthrough && notificationsAllowed
                    params.flags = WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                        (if (state.status == ConnectionStatus.CONNECTED) WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON else 0) or
                        (if (touchThrough) WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE else 0)
                    // Leave margin below Android 12's 0.8 obscured-touch threshold.
                    // Text/outline stay fully opaque inside the view; window compositing still
                    // reduces their final opacity to 79%, a trade-off required for touch-through.
                    params.alpha = if (touchThrough) 0.79f else 1f
                    if (positionRevision != settings.positionRevision || params.width != overlayWidth()) {
                        params.width = overlayWidth()
                        params.x = Preferences.overlayX(landscape)
                        wantedY = Preferences.overlayY(landscape)
                        positionRevision = settings.positionRevision
                    }
                    clampPosition()
                    subtitles.render(state, settings)
                    updateWindow()
                    val key = state.status to touchThrough
                    if (key != lastNotification) {
                        getSystemService(NotificationManager::class.java).notify(NOTIFICATION, notification(state))
                        lastNotification = key
                    }
                }
        }
    }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)
        if (!overlayActionAllowed(added, intent?.action)) { stopSelf(); return START_NOT_STICKY }
        if (!added) createOverlay()
        when (intent?.action) {
            ACTION_REPOST -> if (added) getSystemService(NotificationManager::class.java).notify(NOTIFICATION, notification(SubtitleRepository.state.value))
            ACTION_STOP -> { Preferences.autoConnect = false; stopConnection = true; stopSelf() }
            ACTION_TOUCH -> {
                val settings = Preferences.settings.value
                Preferences.update(settings.copy(mousePassthrough = !settings.mousePassthrough))
            }
            else -> if (added) SubtitleRepository.connect(Preferences.server)
        }
        return START_NOT_STICKY
    }
    private fun notificationsAllowed(): Boolean {
        if (!NotificationManagerCompat.from(this).areNotificationsEnabled()) return false
        return getSystemService(NotificationManager::class.java).getNotificationChannel(CHANNEL)?.importance != NotificationManager.IMPORTANCE_NONE
    }
    private fun usableBounds(): Rect {
        if (Build.VERSION.SDK_INT >= 30) {
            val wm = overlayContext.getSystemService(WindowManager::class.java) ?: manager
            val metrics = wm.currentWindowMetrics
            val bars = metrics.windowInsets.getInsetsIgnoringVisibility(WindowInsets.Type.systemBars())
            return Rect(metrics.bounds.left + bars.left, metrics.bounds.top + bars.top,
                metrics.bounds.right - bars.right, metrics.bounds.bottom - bars.bottom)
        }
        val metrics = overlayContext.resources.displayMetrics
        return Rect(0, 0, metrics.widthPixels, metrics.heightPixels)
    }
    private fun screenShortSide(): Int {
        if (Build.VERSION.SDK_INT >= 30) {
            val wm = overlayContext.getSystemService(WindowManager::class.java) ?: manager
            val bounds = wm.currentWindowMetrics.bounds
            return minOf(bounds.width(), bounds.height())
        }
        val metrics = overlayContext.resources.displayMetrics
        return minOf(metrics.widthPixels, metrics.heightPixels)
    }
    private fun overlayWidth(): Int {
        val bounds = usableBounds()
        return overlayWidthPx(bounds.width(), bounds.height(), Preferences.settings.value.overlayWidth, screenShortSide())
    }
    private fun clampPosition() {
        val screen = usableBounds()
        if (params.x == Int.MIN_VALUE) params.x = (screen.width() - params.width) / 2
        if (wantedY == Int.MIN_VALUE) wantedY = dp(48)
        params.x = params.x.coerceIn(0, (screen.width() - params.width).coerceAtLeast(0))
        params.y = wantedY.coerceIn(0, (screen.height() - box.height).coerceAtLeast(0))
    }
    private fun updateWindow() {
        if (!added) return
        try { manager.updateViewLayout(box, params) } catch (_: RuntimeException) { stopSelf() }
    }
    private fun recomputeBoundsAndPosition() {
        if (!added) return
        params.width = overlayWidth(); params.height = WindowManager.LayoutParams.WRAP_CONTENT
        params.x = Preferences.overlayX(landscape); wantedY = Preferences.overlayY(landscape)
        clampPosition(); updateWindow()
    }
    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        if (!added) return
        recomputeOnNextLayout = true
        recomputeBoundsAndPosition()
        box.post { recomputeBoundsAndPosition() }
    }
    private fun notification(state: SubtitleState): Notification {
        fun action(action: String, code: Int) = PendingIntent.getService(this, code,
            Intent(this, OverlayService::class.java).setAction(action), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val settingsIntent = PendingIntent.getActivity(this, 4, Intent(this, SettingsActivity::class.java), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val statusText = getString(state.status.textResource())
        val hintText = getString(if (touchThrough) R.string.notification_locked else R.string.notification_unlocked)
        return NotificationCompat.Builder(this, CHANNEL)
            .setSmallIcon(R.drawable.ic_subtitle).setContentTitle(getString(R.string.overlay))
            .setContentText("$statusText・$hintText").setContentIntent(open)
            .setDeleteIntent(action(ACTION_REPOST, 3))
            .setOngoing(true).setSilent(true).setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .addAction(0, getString(if (touchThrough) R.string.passthrough_on else R.string.passthrough_off), action(ACTION_TOUCH, 1))
            .addAction(0, getString(R.string.settings), settingsIntent)
            .addAction(0, getString(R.string.stop), action(ACTION_STOP, 2)).build()
    }
    override fun onDestroy() {
        releaseOverlaySafely(
            remove = { if (added) manager.removeView(box) },
            release = { added = false; SubtitleRepository.releaseOverlay(stopConnection) },
            finish = { stopForeground(STOP_FOREGROUND_REMOVE); super.onDestroy() }
        )
    }
    companion object {
        const val ACTION_START = "com.streamtranslator.subtitle.START"
        private const val ACTION_REPOST = "com.streamtranslator.subtitle.REPOST"
        private const val CHANNEL = "subtitle_overlay"
        private const val NOTIFICATION = 100
        private const val ACTION_TOUCH = "com.streamtranslator.subtitle.TOUCH"
        private const val ACTION_STOP = "com.streamtranslator.subtitle.STOP"
    }
}
