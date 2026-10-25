package com.streamtranslator.subtitle

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.view.inputmethod.EditorInfo
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.card.MaterialCardView
import com.google.android.material.chip.Chip
import android.graphics.drawable.GradientDrawable
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputLayout
import com.google.android.material.textfield.TextInputEditText
import android.view.View
import android.view.WindowManager
import android.widget.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {
    private lateinit var address: EditText
    private lateinit var controls: LinearLayout
    private var hidden = false
    private var pendingOverlay = false
    private val notificationPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) {
        requestOverlayPermission()
    }
    private val overlayPermission = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        if (pendingOverlay && Settings.canDrawOverlays(this)) startOverlay()
        pendingOverlay = false
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Preferences.initialize(this)
        hidden = savedInstanceState?.getBoolean("hidden") ?: false
        pendingOverlay = savedInstanceState?.getBoolean("pendingOverlay") ?: false
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(ContextCompat.getColor(this@MainActivity, R.color.surface))
        }
        WindowCompat.setDecorFitsSystemWindows(window, false)
        ViewCompat.setOnApplyWindowInsetsListener(root) { view, insets ->
            val padding = insets.getInsets(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout() or WindowInsetsCompat.Type.ime())
            val safe = insets.getInsetsIgnoringVisibility(WindowInsetsCompat.Type.systemBars() or WindowInsetsCompat.Type.displayCutout())
            view.setPadding(maxOf(padding.left, safe.left), if (hidden) padding.top else maxOf(padding.top, safe.top),
                maxOf(padding.right, safe.right), maxOf(padding.bottom, safe.bottom))
            insets
        }
        controls = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val gutter = resources.getDimensionPixelSize(R.dimen.screen_gutter)
            setPadding(gutter, dp(12), gutter, dp(12))
        }
        address = TextInputEditText(this).apply {
            id = View.generateViewId()
            setSingleLine(true)
            imeOptions = EditorInfo.IME_ACTION_GO
            setOnEditorActionListener { _, action, _ ->
                if (action == EditorInfo.IME_ACTION_GO) { connect(); true } else false
            }
            inputType = android.text.InputType.TYPE_CLASS_TEXT or android.text.InputType.TYPE_TEXT_VARIATION_URI
            setTextColor(Color.WHITE)
            setHintTextColor(Color.LTGRAY)
            setHint(R.string.server_hint)
            setText(savedInstanceState?.getString("address") ?: Preferences.server)
        }
        val addressBox = TextInputLayout(this).apply {
            boxBackgroundMode = TextInputLayout.BOX_BACKGROUND_OUTLINE
            hint = getString(R.string.server_hint)
            addView(address, LinearLayout.LayoutParams(-1, -2))
        }
        val toggle = MaterialButton(this).apply {
            setText(R.string.connect)
            setOnClickListener {
                if (SubtitleRepository.state.value.running) {
                    stopService(Intent(this@MainActivity, OverlayService::class.java))
                    Preferences.autoConnect = false
                    SubtitleRepository.disconnect()
                } else connect()
            }
        }
        controls.addView(MaterialToolbar(this).apply {
            setTitle(R.string.main_title)
            menu.add(R.string.settings).apply {
                setIcon(R.drawable.ic_settings); setShowAsAction(android.view.MenuItem.SHOW_AS_ACTION_ALWAYS)
            }
            setOnMenuItemClickListener { startActivity(Intent(this@MainActivity, SettingsActivity::class.java)); true }
        })
        val connectionBody = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(dp(16), dp(12), dp(16), dp(12))
            addView(addressBox, LinearLayout.LayoutParams(-1, -2))
            addView(toggle, LinearLayout.LayoutParams(-1, -2))
        }
        val status = Chip(this).apply { isClickable = false; isCheckable = false }
        connectionBody.addView(status)
        controls.addView(MaterialCardView(this).apply {
            radius = resources.getDimension(R.dimen.card_radius); addView(connectionBody)
        }, LinearLayout.LayoutParams(-1, -2))
        val overlayButton = MaterialButton(this).apply {
            setText(R.string.overlay)
            setOnClickListener {
                if (SubtitleRepository.overlayActive) stopService(Intent(this@MainActivity, OverlayService::class.java))
                else beginOverlay()
            }
        }
        controls.addView(overlayButton, LinearLayout.LayoutParams(-1, -2).apply { topMargin = dp(12) })
        // Controls remain reachable on compact landscape displays and with a keyboard.
        val controlsScroll = object : ScrollView(this) {
            override fun onMeasure(widthMeasureSpec: Int, heightMeasureSpec: Int) {
                val limit = (resources.displayMetrics.heightPixels * 0.6f).toInt()
                super.onMeasure(widthMeasureSpec, View.MeasureSpec.makeMeasureSpec(
                    minOf(View.MeasureSpec.getSize(heightMeasureSpec), limit), View.MeasureSpec.AT_MOST))
            }
        }.apply { addView(controls) }
        root.addView(controlsScroll, LinearLayout.LayoutParams(-1, -2))
        val subtitles = SubtitleView(this, overlay = false)
        val overlayNote = TextView(this).apply {
            setText(R.string.overlay_active_note)
            setTextAppearance(com.google.android.material.R.style.TextAppearance_Material3_BodyLarge)
            setTextColor(ContextCompat.getColor(this@MainActivity, R.color.on_surface))
            gravity = Gravity.CENTER
            visibility = View.GONE
            setOnClickListener { hidden = !hidden; applyImmersive(controlsScroll) }
        }
        val subtitleArea = FrameLayout(this).apply {
            addView(subtitles, FrameLayout.LayoutParams(-1, -1))
            addView(overlayNote, FrameLayout.LayoutParams(-1, -1, Gravity.CENTER))
        }
        root.addView(subtitleArea, LinearLayout.LayoutParams(-1, 0, 1f))
        subtitles.onTap = { hidden = !hidden; applyImmersive(controlsScroll) }
        setContentView(root)
        applyImmersive(controlsScroll)
        ViewCompat.requestApplyInsets(root)
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                combine(SubtitleRepository.state, Preferences.settings, SubtitleRepository.overlay) { state, settings, overlay -> Triple(state, settings, overlay) }
                    .collect { (state, settings, overlay) ->
                        toggle.setText(if (state.running) R.string.disconnect else R.string.connect)
                        overlayButton.setText(if (overlay) R.string.close_overlay else R.string.overlay)
                        status.setText(if (state.status == ConnectionStatus.CONNECTED) {
                            if (state.ready) R.string.connected_ready else R.string.connected_waiting
                        } else state.status.textResource())
                        status.chipIcon = GradientDrawable().apply {
                            shape = GradientDrawable.OVAL
                            setColor(ContextCompat.getColor(this@MainActivity, when (state.status) {
                                ConnectionStatus.CONNECTED -> R.color.state_connected
                                ConnectionStatus.CONNECTING, ConnectionStatus.RECONNECTING, ConnectionStatus.WAITING -> R.color.state_waiting
                                else -> R.color.state_stopped
                            }))
                            setSize(dp(10), dp(10))
                        }
                        status.isChipIconVisible = true
                        status.chipIconTint = null
                        status.chipIconSize = dp(10).toFloat()
                        subtitles.visibility = if (overlay) View.GONE else View.VISIBLE
                        overlayNote.visibility = if (overlay) View.VISIBLE else View.GONE
                        subtitles.render(state, settings)
                        if (state.running) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                        else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    }
            }
        }
    }
    private fun applyImmersive(container: View) {
        container.visibility = if (hidden) View.GONE else View.VISIBLE
        WindowInsetsControllerCompat(window, window.decorView).apply {
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            if (hidden) hide(WindowInsetsCompat.Type.systemBars()) else show(WindowInsetsCompat.Type.systemBars())
        }
    }
    private fun connect(): Boolean {
        val base = try { normalizeServerUrl(address.text.toString()) } catch (_: IllegalArgumentException) {
            address.error = getString(R.string.invalid_server); return false
        }
        Preferences.autoConnect = base.isNotEmpty()
        Preferences.server = base
        address.setText(base)
        SubtitleRepository.connect(base)
        if (base.isEmpty()) { address.error = getString(R.string.unconfigured); return false }
        return true
    }
    private fun beginOverlay() {
        if (!connect()) return
        pendingOverlay = true
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        } else requestOverlayPermission()
    }
    private fun requestOverlayPermission() {
        if (Settings.canDrawOverlays(this)) { startOverlay(); pendingOverlay = false }
        else {
            Toast.makeText(this, R.string.overlay_permission, Toast.LENGTH_LONG).show()
            overlayPermission.launch(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
        }
    }
    private fun startOverlay() {
        // Reconnect if Android stopped the visible-only owner while permission settings were open.
        SubtitleRepository.connect(Preferences.server)
        ContextCompat.startForegroundService(this, Intent(this, OverlayService::class.java).setAction(OverlayService.ACTION_START))
    }
    override fun onStart() { super.onStart(); SubtitleRepository.attachView(); SubtitleRepository.reconnectIfEnabled() }
    override fun onStop() { SubtitleRepository.detachView(isChangingConfigurations); super.onStop() }
    override fun onSaveInstanceState(outState: Bundle) {
        outState.putBoolean("hidden", hidden)
        outState.putBoolean("pendingOverlay", pendingOverlay)
        outState.putString("address", address.text.toString())
        super.onSaveInstanceState(outState)
    }
}
