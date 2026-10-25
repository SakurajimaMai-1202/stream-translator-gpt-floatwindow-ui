package com.streamtranslator.subtitle

import android.content.Context
import android.content.SharedPreferences
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

data class SubtitleSettings(
    val fontSize: Int = 20,
    val maxDisplayCount: Int = 5,
    val showOriginal: Boolean = true,
    val showTranslated: Boolean = true,
    val showLatency: Boolean = false,
    val textColor: String = "#55FFFF",
    val translatedColor: String = "#FFDD00",
    val backgroundOpacity: Int = 100,
    val overlayBackgroundOpacity: Int = 0,
    val mousePassthrough: Boolean = false,
    val translatedFontSize: Int = 24,
    val overlayDisplayCount: Int = 2,
    val bold: Boolean = true,
    val strokeWidth: Int = 3,
    val shadowRadius: Int = 4,
    val backgroundColor: String = "#000000",
    val overlayWidth: Int = 92,
    val positionRevision: Int = 0
)

object Preferences {
    private lateinit var prefs: SharedPreferences
    private var boundContext: Context? = null
    private val mutableSettings = MutableStateFlow(SubtitleSettings())
    val settings = mutableSettings.asStateFlow()
    fun initialize(context: Context) {
        // Re-bind when the application context changes (a new process, or a new Robolectric test app).
        if (!::prefs.isInitialized || boundContext !== context.applicationContext) {
            boundContext = context.applicationContext
            prefs = context.applicationContext.getSharedPreferences("subtitle", Context.MODE_PRIVATE)
        }
        if (prefs.contains("backgroundOpacity") && !prefs.contains("overlayBackgroundOpacity")) {
            prefs.edit()
                .putInt("fullscreenBackgroundOpacity", prefs.getInt("backgroundOpacity", 100).coerceIn(0, 100))
                .putInt("overlayBackgroundOpacity", 0)
                .remove("backgroundOpacity")
                .apply()
        }
        mutableSettings.value = SubtitleSettings(
            prefs.getInt("fontSize", 20).coerceIn(10, 200),
            prefs.getInt("maxDisplayCount", 5).coerceIn(1, 100),
            prefs.getBoolean("showOriginal", true), prefs.getBoolean("showTranslated", true),
            prefs.getBoolean("showLatency", false), prefs.getString("textColor", "#55FFFF")!!,
            prefs.getString("translatedColor", "#FFDD00")!!,
            prefs.getInt("fullscreenBackgroundOpacity", 100).coerceIn(0, 100),
            prefs.getInt("overlayBackgroundOpacity", 0).coerceIn(0, 100),
            prefs.getBoolean("mousePassthrough", false),
            prefs.getInt("translatedFontSize", 24).coerceIn(10, 200),
            prefs.getInt("overlayDisplayCount", 2).coerceIn(1, 10),
            prefs.getBoolean("bold", true), prefs.getInt("strokeWidth", 3).coerceIn(0, 8),
            prefs.getInt("shadowRadius", 4).coerceIn(0, 12),
            prefs.getString("backgroundColor", "#000000")!!,
            prefs.getInt("overlayWidth", 92).coerceIn(30, 100),
            mutableSettings.value.positionRevision
        )
    }
    var server: String
        get() = prefs.getString("server_url", "").orEmpty()
        set(value) { prefs.edit().putString("server_url", value).apply() }
    var autoConnect: Boolean
        get() = prefs.getBoolean("auto_connect", false)
        set(value) { prefs.edit().putBoolean("auto_connect", value).apply() }
    private fun positionKey(axis: String, landscape: Boolean) = "overlay${axis}_${if (landscape) "landscape" else "portrait"}"
    fun overlayX(landscape: Boolean) = prefs.getInt(positionKey("X", landscape), Int.MIN_VALUE)
    fun overlayY(landscape: Boolean) = prefs.getInt(positionKey("Y", landscape), Int.MIN_VALUE)
    fun savePosition(landscape: Boolean, x: Int, y: Int, horizontal: Boolean) {
        prefs.edit().apply {
            if (horizontal) putInt(positionKey("X", landscape), x)
            putInt(positionKey("Y", landscape), y)
        }.apply()
    }
    fun resetPosition() {
        prefs.edit().apply {
            for (landscape in listOf(false, true)) {
                remove(positionKey("X", landscape)); remove(positionKey("Y", landscape))
            }
            remove("overlayX"); remove("overlayY")
        }.apply()
        update(settings.value.copy(positionRevision = settings.value.positionRevision + 1))
    }
    fun update(value: SubtitleSettings, persist: Boolean = true) {
        mutableSettings.value = value
        if (!persist) return
        prefs.edit().putInt("fontSize", value.fontSize).putInt("maxDisplayCount", value.maxDisplayCount)
            .putBoolean("showOriginal", value.showOriginal).putBoolean("showTranslated", value.showTranslated)
            .putBoolean("showLatency", value.showLatency).putString("textColor", value.textColor)
            .putString("translatedColor", value.translatedColor)
            .putInt("fullscreenBackgroundOpacity", value.backgroundOpacity)
            .putInt("overlayBackgroundOpacity", value.overlayBackgroundOpacity)
            .remove("backgroundOpacity")
            .putBoolean("mousePassthrough", value.mousePassthrough)
            .putInt("translatedFontSize", value.translatedFontSize).putInt("overlayDisplayCount", value.overlayDisplayCount)
            .putBoolean("bold", value.bold).putInt("strokeWidth", value.strokeWidth).putInt("shadowRadius", value.shadowRadius)
            .putString("backgroundColor", value.backgroundColor).putInt("overlayWidth", value.overlayWidth).apply()
    }
}
