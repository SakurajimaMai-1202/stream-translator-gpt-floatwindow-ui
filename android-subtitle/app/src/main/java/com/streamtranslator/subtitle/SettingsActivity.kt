package com.streamtranslator.subtitle

import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.graphics.drawable.LayerDrawable
import android.os.Bundle
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.button.MaterialButton
import com.google.android.material.button.MaterialButtonToggleGroup
import com.google.android.material.card.MaterialCardView
import com.google.android.material.materialswitch.MaterialSwitch
import com.google.android.material.slider.Slider
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.collect

class SettingsActivity : AppCompatActivity() {
    private val controls = mutableListOf<(SubtitleSettings) -> Unit>()
    private var syncing = false
    private val swatches = mutableListOf<() -> Unit>()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Preferences.initialize(this)
        WindowCompat.setDecorFitsSystemWindows(window, false)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(MaterialToolbar(this).apply {
            title = "字幕設定"; setNavigationIcon(R.drawable.ic_back)
            setNavigationContentDescription("返回"); setNavigationOnClickListener { finish() }
        })
        val form = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val gutter = resources.getDimensionPixelSize(R.dimen.screen_gutter)
            setPadding(gutter, gutter, gutter, gutter)
        }
        root.addView(ScrollView(this).apply { addView(form) }, LinearLayout.LayoutParams(-1, 0, 1f))
        setContentView(root)
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val bars = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom)
            insets
        }
        fun label(text: String, appearance: Int = com.google.android.material.R.style.TextAppearance_Material3_BodyLarge) = TextView(this).apply {
            this.text = text; setTextAppearance(appearance); setPadding(0, dp(8), 0, dp(4))
        }
        fun section(title: String): LinearLayout {
            val body = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(8), dp(16), dp(16))
                addView(label(title, com.google.android.material.R.style.TextAppearance_Material3_TitleMedium))
            }
            form.addView(MaterialCardView(this).apply {
                radius = resources.getDimension(R.dimen.card_radius); addView(body)
            }, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(16) })
            return body
        }
        val preview = SubtitleView(this)
        val previewSection = section("即時預覽")
        val overlayPreviewId = View.generateViewId()
        val fullscreenPreviewId = View.generateViewId()
        previewSection.addView(MaterialButtonToggleGroup(this).apply {
            isSingleSelection = true; isSelectionRequired = true
            listOf(overlayPreviewId to "懸浮樣式", fullscreenPreviewId to "全螢幕樣式").forEach { (key, title) ->
                addView(MaterialButton(this@SettingsActivity, null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
                    id = key; this.text = title
                }, LinearLayout.LayoutParams(0, -2, 1f))
            }
            check(overlayPreviewId)
            addOnButtonCheckedListener { _, id, checked -> if (checked) preview.overlay = id == overlayPreviewId }
        }, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(8) })
        previewSection.addView(FrameLayout(this).apply {
            background = GradientDrawable(GradientDrawable.Orientation.TL_BR,
                intArrayOf(Color.parseColor("#EC9F66"), Color.parseColor("#334C71"), Color.parseColor("#8BAE8D"), Color.parseColor("#1D2440")))
            addView(preview, FrameLayout.LayoutParams(-1, -2, Gravity.CENTER))
            minimumHeight = dp(160)
        }, LinearLayout.LayoutParams(-1, dp(160)))
        fun change(transform: (SubtitleSettings) -> SubtitleSettings) = Preferences.update(transform(Preferences.settings.value))
        fun toggle(parent: LinearLayout, title: String, description: String, selected: (SubtitleSettings) -> Boolean, update: (Boolean) -> Unit) {
            val switchView = MaterialSwitch(this).apply {
                contentDescription = title
                isChecked = selected(Preferences.settings.value)
                controls += { isChecked = selected(it) }
                setOnCheckedChangeListener { _, checked -> if (!syncing) update(checked) }
            }
            val textColumn = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(0, 0, dp(12), 0)
                addView(TextView(this@SettingsActivity).apply {
                    text = title
                    setTextAppearance(com.google.android.material.R.style.TextAppearance_Material3_BodyLarge)
                })
                addView(TextView(this@SettingsActivity).apply {
                    text = description
                    setTextAppearance(com.google.android.material.R.style.TextAppearance_Material3_BodySmall)
                })
            }
            parent.addView(LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(0, dp(8), 0, dp(8))
                addView(textColumn, LinearLayout.LayoutParams(0, -2, 1f))
                addView(switchView, LinearLayout.LayoutParams(-2, -2))
                setOnClickListener { switchView.toggle() }
            }, LinearLayout.LayoutParams(-1, -2))
        }
        fun slider(parent: LinearLayout, name: String, low: Int, high: Int, selected: (SubtitleSettings) -> Int, unit: String = "", update: (Int) -> Unit) {
            val value = selected(Preferences.settings.value)
            val title = label("$name  $value$unit")
            parent.addView(title)
            parent.addView(Slider(this).apply {
                valueFrom = low.toFloat(); valueTo = high.toFloat(); stepSize = 1f
                isTickVisible = false
                this.value = value.coerceIn(low, high).toFloat(); contentDescription = name
                controls += {
                    val v = selected(it).coerceIn(low, high)
                    title.text = "$name  $v$unit"
                    this.value = v.toFloat()
                }
                setLabelFormatter { "${it.toInt()}$unit" }
                addOnChangeListener { _, number, fromUser ->
                    title.text = "$name  ${number.toInt()}$unit"
                    if (fromUser) update(number.toInt())
                }
            })
        }
        val s = Preferences.settings.value
        val display = section("顯示內容")
        toggle(display, "顯示原文", "保留語音辨識的原始文字", { it.showOriginal }) { v -> change { it.copy(showOriginal = v) } }
        toggle(display, "顯示譯文", "顯示翻譯後的字幕", { it.showTranslated }) { v -> change { it.copy(showTranslated = v) } }
        toggle(display, "顯示延遲", "在字幕下方顯示處理時間", { it.showLatency }) { v -> change { it.copy(showLatency = v) } }
        slider(display, "全螢幕顯示筆數", 1, 100, { it.maxDisplayCount }) { v -> change { it.copy(maxDisplayCount = v) } }
        slider(display, "懸浮顯示筆數", 1, 10, { it.overlayDisplayCount }) { v -> change { it.copy(overlayDisplayCount = v) } }
        val text = section("文字")
        slider(text, "原文字級", 10, 200, { it.fontSize }, " sp") { v -> change { it.copy(fontSize = v) } }
        slider(text, "譯文字級", 10, 200, { it.translatedFontSize }, " sp") { v -> change { it.copy(translatedFontSize = v) } }
        text.addView(label("字重"))
        val normalId = View.generateViewId()
        val boldId = View.generateViewId()
        text.addView(MaterialButtonToggleGroup(this).apply {
            isSingleSelection = true; isSelectionRequired = true
            listOf(normalId to "標準", boldId to "粗體").forEach { (key, title) ->
                addView(MaterialButton(this@SettingsActivity, null, com.google.android.material.R.attr.materialButtonOutlinedStyle).apply {
                    id = key; this.text = title
                }, LinearLayout.LayoutParams(0, -2, 1f))
            }
            check(if (s.bold) boldId else normalId)
            controls += { check(if (it.bold) boldId else normalId) }
            addOnButtonCheckedListener { _, id, checked -> if (checked && !syncing) change { it.copy(bold = id == boldId) } }
        })
        slider(text, "外框粗細", 0, 8, { it.strokeWidth }, " dp") { v -> change { it.copy(strokeWidth = v) } }
        slider(text, "陰影", 0, 12, { it.shadowRadius }, " dp") { v -> change { it.copy(shadowRadius = v) } }
        val colors = section("顏色")
        val textPresets = listOf("#55FFFF", "#FFDD00", "#FFFFFF", "#AAFFAA", "#FF99CC", "#FFAA55", "#AABFFF", "#DD99FF", "#000000")
        val backgroundPresets = listOf("#000000", "#202124", "#0B1E3A", "#0F2A1D", "#24123A", "#FFFFFF")
        fun palette(title: String, presets: List<String>, selected: (SubtitleSettings) -> String, update: (String) -> Unit) {
            colors.addView(label(title))
            val flow = object : ViewGroup(this) {
                private val gap = dp(6)
                override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
                    val maxWidth = MeasureSpec.getSize(widthMeasureSpec).let { if (it > 0) it else resources.displayMetrics.widthPixels }
                    var x = 0; var y = 0; var rowHeight = 0
                    for (i in 0 until childCount) {
                        val child = getChildAt(i)
                        if (child.visibility == GONE) continue
                        measureChild(child, widthMeasureSpec, heightMeasureSpec)
                        val cw = child.measuredWidth; val ch = child.measuredHeight
                        if (x > 0 && x + cw > maxWidth) { x = 0; y += rowHeight + gap; rowHeight = 0 }
                        x += cw + gap; rowHeight = maxOf(rowHeight, ch)
                    }
                    setMeasuredDimension(resolveSize(maxWidth, widthMeasureSpec), resolveSize(y + rowHeight, heightMeasureSpec))
                }
                override fun onLayout(changed: Boolean, l: Int, t: Int, r: Int, b: Int) {
                    val maxWidth = r - l
                    var x = 0; var y = 0; var rowHeight = 0
                    for (i in 0 until childCount) {
                        val child = getChildAt(i)
                        if (child.visibility == GONE) continue
                        val cw = child.measuredWidth; val ch = child.measuredHeight
                        if (x > 0 && x + cw > maxWidth) { x = 0; y += rowHeight + gap; rowHeight = 0 }
                        child.layout(x, y, x + cw, y + ch)
                        x += cw + gap; rowHeight = maxOf(rowHeight, ch)
                    }
                }
            }
            fun makeCell(colorProvider: () -> String): Pair<FrameLayout, () -> Unit> {
                val swatch = View(this)
                val cell = FrameLayout(this).apply {
                    addView(swatch, FrameLayout.LayoutParams(dp(30), dp(30), Gravity.CENTER))
                    isFocusable = true
                    setOnClickListener { update(colorProvider()) }
                }
                val refresh: () -> Unit = {
                    val color = colorProvider()
                    val current = selected(Preferences.settings.value)
                    val isSel = current.equals(color, true)
                    swatch.isSelected = isSel
                    swatch.contentDescription = "$title $color"
                    cell.contentDescription = "$title $color"
                    val fillColor = try { Color.parseColor(color) } catch (_: Exception) { Color.BLACK }
                    swatch.background = if (isSel) {
                        val ring = GradientDrawable().apply {
                            shape = GradientDrawable.OVAL
                            setColor(ContextCompat.getColor(this@SettingsActivity, R.color.surface_card))
                            setStroke(dp(3), ContextCompat.getColor(this@SettingsActivity, R.color.accent))
                        }
                        val fill = GradientDrawable().apply {
                            shape = GradientDrawable.OVAL
                            setColor(fillColor)
                        }
                        LayerDrawable(arrayOf(ring, fill)).apply {
                            val inset = dp(5)
                            setLayerInset(1, inset, inset, inset, inset)
                        }
                    } else GradientDrawable().apply {
                        shape = GradientDrawable.OVAL
                        setColor(fillColor)
                        setStroke(dp(1), Color.GRAY)
                    }
                }
                return cell to refresh
            }
            presets.forEach { preset ->
                val (cell, refresh) = makeCell { preset }
                swatches += refresh; refresh()
                flow.addView(cell, ViewGroup.LayoutParams(dp(38), dp(38)))
            }
            val (extraCell, extraRefresh) = makeCell { selected(Preferences.settings.value) }
            val updateExtra: () -> Unit = {
                val current = selected(Preferences.settings.value)
                val inPresets = presets.any { it.equals(current, true) }
                extraCell.visibility = if (inPresets) View.GONE else View.VISIBLE
                if (!inPresets) extraRefresh()
                flow.requestLayout()
            }
            swatches += updateExtra; updateExtra()
            flow.addView(extraCell, ViewGroup.LayoutParams(dp(38), dp(38)))
            colors.addView(flow, LinearLayout.LayoutParams(-1, -2))
        }
        palette("原文顏色", textPresets, { it.textColor }) { v -> change { it.copy(textColor = v) } }
        palette("譯文顏色", textPresets, { it.translatedColor }) { v -> change { it.copy(translatedColor = v) } }
        palette("背景顏色", backgroundPresets, { it.backgroundColor }) { v -> change { it.copy(backgroundColor = v) } }
        slider(colors, "全螢幕背景不透明度", 0, 100, { it.backgroundOpacity }, "%") { v -> change { it.copy(backgroundOpacity = v) } }
        slider(colors, "懸浮字幕背景不透明度", 0, 100, { it.overlayBackgroundOpacity }, "%") { v -> change { it.copy(overlayBackgroundOpacity = v) } }
        val overlay = section("懸浮字幕")
        slider(overlay, "寬度", 30, 100, { it.overlayWidth }, "%") { v -> change { it.copy(overlayWidth = v) } }
        toggle(overlay, "預設鎖定", "鎖定後可從通知解除，讓觸控穿透字幕", { it.mousePassthrough }) { v -> change { it.copy(mousePassthrough = v) } }
        overlay.addView(MaterialButton(android.view.ContextThemeWrapper(this, R.style.TextButtonTheme)).apply {
            this.text = "重設位置"; setOnClickListener { Preferences.resetPosition() }
        })
        val about = section("關於")
        val version = packageManager.getPackageInfo(packageName, 0).versionName.orEmpty()
        about.addView(label("版本 $version"))
        about.addView(label("主機位址\n${Preferences.server.ifEmpty { "尚未設定" }}"))
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                Preferences.settings.collect { settings ->
                    preview.render(SubtitleState(rows = listOf(mapOf("original" to "みなさんこんすいせい！", "translated" to "大家好，我是彗星！", "total_latency_ms" to 128))), settings)
                    syncing = true
                    try { controls.forEach { it(settings) } } finally { syncing = false }
                    swatches.forEach { it() }
                }
            }
        }
    }
    override fun onStart() { super.onStart(); SubtitleRepository.attachView(); SubtitleRepository.reconnectIfEnabled() }
    override fun onStop() { SubtitleRepository.detachView(isChangingConfigurations); super.onStop() }
}
