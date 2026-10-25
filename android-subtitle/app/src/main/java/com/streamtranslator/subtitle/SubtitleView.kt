package com.streamtranslator.subtitle

import android.content.Context
import android.graphics.*
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import android.view.View
import android.animation.ValueAnimator

fun Context.dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

fun ConnectionStatus.textResource(): Int = when (this) {
    ConnectionStatus.UNCONFIGURED -> R.string.unconfigured
    ConnectionStatus.STOPPED -> R.string.stopped
    ConnectionStatus.WAITING -> R.string.waiting
    ConnectionStatus.CONNECTING -> R.string.connecting
    ConnectionStatus.CONNECTED -> R.string.connected
    ConnectionStatus.RECONNECTING -> R.string.reconnecting
    ConnectionStatus.SHARING_DISABLED -> R.string.sharing_disabled
    ConnectionStatus.TASK_ENDED -> R.string.task_ended
    ConnectionStatus.SERVICE_NOT_FOUND -> R.string.service_not_found
}

/** Shared renderer: one background, then outlined text. No child surfaces or scrollback. */
class SubtitleView(context: Context, overlay: Boolean = true) : View(context) {
    var overlay: Boolean = overlay
        set(value) {
            if (field == value) return
            field = value
            fade?.cancel()
            oldestAlpha = 1f
            cacheSettings()
            layoutKey = null
            render(state, settings)
        }
    var onTap: (() -> Unit)? = null
    private var state = SubtitleState()
    private var settings = SubtitleSettings()
    private var rows = emptyList<Subtitle>()
    private val paint = TextPaint(Paint.ANTI_ALIAS_FLAG)
    private data class Line(val layout: StaticLayout, val color: Int, val row: Int)
    private var lines = emptyList<Line>()
    private var textHeight = 0
    private var oldestAlpha = 1f
    private var fade: ValueAnimator? = null
    @androidx.annotation.VisibleForTesting internal val fadeAnimator: ValueAnimator? get() = fade
    val hasText: Boolean get() = lines.isNotEmpty()
    private var pendingNext: List<Subtitle>? = null
    private data class LayoutKey(val width: Int, val rows: List<Subtitle>, val settings: SubtitleSettings, val overlay: Boolean)
    private var layoutKey: LayoutKey? = null
    private val inset = context.dp(16)
    private val verticalPadding = context.dp(24)
    private val halfPadding = context.dp(12)
    private val density = resources.displayMetrics.density
    private val scaledDensity = resources.displayMetrics.scaledDensity
    private val backgroundPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var originalColor = Color.CYAN
    private var translatedColor = Color.YELLOW
    private var stroke = 0f
    private var shadow = 0f
    init {
        setLayerType(if (android.os.Build.VERSION.SDK_INT < 28) LAYER_TYPE_SOFTWARE else LAYER_TYPE_NONE, null)
        cacheSettings()
        setOnClickListener { onTap?.invoke() }
    }
    private fun cacheSettings() {
        originalColor = Color.parseColor(settings.textColor)
        translatedColor = Color.parseColor(settings.translatedColor)
        backgroundPaint.color = Color.parseColor(settings.backgroundColor)
        val opacity = if (overlay) settings.overlayBackgroundOpacity else settings.backgroundOpacity
        backgroundPaint.alpha = opacity * 255 / 100
        stroke = settings.strokeWidth * density * 2
        shadow = settings.shadowRadius * density
        paint.typeface = if (settings.bold) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
    }
    fun render(state: SubtitleState, settings: SubtitleSettings) {
        this.state = state
        val next = state.rows.takeLast(if (overlay) settings.overlayDisplayCount else settings.maxDisplayCount)
        if (this.settings == settings && (pendingNext ?: rows) == next && layoutKey?.overlay == overlay) return
        val changedOldest = overlay && this.settings == settings && rows.isNotEmpty() && next.isNotEmpty() &&
            rows.first() != next.first() && SubtitleHistory.findIndex(next, rows.first()) < 0
        // Partial updates to the incoming rows keep the existing fade and its progress.
        if (fade != null && changedOldest) { pendingNext = next; return }
        fade?.cancel()
        if (this.settings != settings) { this.settings = settings; cacheSettings() }
        if (changedOldest && isLaidOut) {
            pendingNext = next
            fade = ValueAnimator.ofFloat(oldestAlpha, 0f).apply {
                duration = 180
                addUpdateListener { oldestAlpha = it.animatedValue as Float; invalidate() }
                addListener(object : android.animation.AnimatorListenerAdapter() {
                    private var cancelled = false
                    override fun onAnimationCancel(animation: android.animation.Animator) {
                        cancelled = true; pendingNext = null; fade = null
                    }
                    override fun onAnimationEnd(animation: android.animation.Animator) {
                        if (cancelled) return
                        rows = pendingNext ?: rows
                        pendingNext = null; fade = null; oldestAlpha = 1f
                        rebuild(width); requestLayout(); invalidate()
                    }
                })
                start()
            }
        } else { rows = next; oldestAlpha = 1f; rebuild(width); requestLayout(); invalidate() }
    }
    private fun rebuild(width: Int) {
        val key = LayoutKey(width, rows, settings, overlay)
        if (layoutKey == key) return
        layoutKey = key
        val available = (width - inset * 2).coerceAtLeast(1)
        val result = mutableListOf<Line>()
        fun line(text: String, color: Int, size: Float, row: Int) {
            if (text.isBlank()) return
            paint.textSize = size * scaledDensity
            val layout = StaticLayout.Builder.obtain(text, 0, text.length, TextPaint(paint), available)
                .setAlignment(Layout.Alignment.ALIGN_CENTER).setIncludePad(true).build()
            layout.paint.strokeJoin = Paint.Join.ROUND
            layout.paint.strokeWidth = stroke
            if (shadow > 0) layout.paint.setShadowLayer(shadow, 0f, density, Color.BLACK)
            result += Line(layout, color, row)
        }
        rows.forEachIndexed { index, row ->
            if (settings.showOriginal) line(row["original"]?.toString().orEmpty(), originalColor, settings.fontSize.toFloat(), index)
            if (settings.showTranslated) line(row["translated"]?.toString().orEmpty(), translatedColor, settings.translatedFontSize.toFloat(), index)
            if (settings.showLatency) row["total_latency_ms"]?.let {
                line(context.getString(R.string.latency_value, it.toString()), Color.WHITE, 12f, index)
            }
        }
        lines = result
        textHeight = lines.sumOf { it.layout.height }
        contentDescription = lines.joinToString("\n") { it.layout.text }
        alpha = if (overlay && lines.isEmpty()) 0f else 1f
    }
    override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
        val w = MeasureSpec.getSize(widthMeasureSpec)
        rebuild(w)
        setMeasuredDimension(w, resolveSize(if (hasText) textHeight + verticalPadding else 1, heightMeasureSpec))
    }
    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (!hasText) return
        val top = (height - textHeight - verticalPadding).toFloat()
        canvas.drawRoundRect(0f, top.coerceAtLeast(0f), width.toFloat(), height.toFloat(), inset.toFloat(), inset.toFloat(), backgroundPaint)
        canvas.save(); canvas.translate(inset.toFloat(), top + halfPadding)
        var index = 0
        while (index < lines.size) {
            val row = lines[index].row
            // Composite the whole row (outline, shadow and fill) before fading it.
            val rowAlpha = if (row == 0) (oldestAlpha * 255).toInt() else 255
            val layer = if (rowAlpha < 255) canvas.saveLayerAlpha(null, rowAlpha) else canvas.save()
            var rowHeight = 0
            while (index < lines.size && lines[index].row == row) {
                val line = lines[index++]
                val p = line.layout.paint
                p.color = Color.BLACK; p.alpha = 255; p.style = Paint.Style.STROKE
                if (stroke > 0) line.layout.draw(canvas)
                p.style = Paint.Style.FILL; p.color = line.color; p.alpha = 255
                line.layout.draw(canvas)
                rowHeight += line.layout.height
                canvas.translate(0f, line.layout.height.toFloat())
            }
            canvas.restoreToCount(layer)
            canvas.translate(0f, rowHeight.toFloat())
        }
        canvas.restore()
    }
    override fun onDetachedFromWindow() { fade?.cancel(); super.onDetachedFromWindow() }
}
