"""WebView 渲染模式：決定 Qt WebEngine 的 Chromium 旗標。

必須在建立 QApplication 前套用；此模組不得匯入 Qt 或產生副作用，
以便單元測試直接驗證旗標組合。

模式：
- ``software``（Windows 預設）：完整軟體渲染。Qt WebEngine 的軟體合成實測
  約每秒 15 幀，捲動與下拉選單較不流暢，但不會破圖。
- ``gpu-safe``：保留 GPU 合成，由 CPU 光柵化網頁內容並停用 zero-copy，
  可達 60 幀。實測 Qt WebEngine 6.9–6.11 的 GPU 合成路徑在內容變化或
  視窗縮放後仍會漏畫或整片變黑（Chrome 本身不會），因此不再作為預設。
- ``gpu``：完整 GPU 渲染。
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


logger = logging.getLogger(__name__)

WEBVIEW_RENDER_MODES = ("gpu-safe", "gpu", "software")


def append_chromium_flags(*flags: str) -> str:
    """將 Chromium 啟動旗標合併且去重，保留外部傳入旗標的順序。"""
    existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").split()
    merged = list(existing)
    for flag in flags:
        if flag and flag not in merged:
            merged.append(flag)
    value = " ".join(merged)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = value
    return value


def read_configured_render_mode(config_path: Path) -> str:
    """讀取 config.yaml 的 ``ui.webview_rendering``；無效或缺少時回傳空字串。"""
    try:
        import yaml

        if not config_path.exists():
            return ""
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        ui_config = config.get("ui") or {}
        value = str(ui_config.get("webview_rendering") or "").strip().lower()
    except Exception as exc:
        logger.warning(f"讀取 WebView 渲染設定失敗，使用預設值: {exc}")
        return ""
    if value and value not in WEBVIEW_RENDER_MODES:
        logger.warning(f"未知的 ui.webview_rendering: {value}，使用預設值")
        return ""
    return value


def resolve_render_mode(args, configured: str, platform: str = sys.platform) -> str:
    """命令列參數優先於 config.yaml，方便使用者以捷徑臨時切換。"""
    if args.disable_gpu:
        return "software"
    if args.enable_webview_gpu or args.enable_webview_direct_composition:
        return "gpu"
    if configured:
        return configured
    return "software" if platform == "win32" else "gpu"


def apply_render_mode(mode: str, args, platform: str = sys.platform) -> bool:
    """套用旗標；回傳 True 表示 Qt 端也須使用軟體 OpenGL。"""
    if mode == "software":
        append_chromium_flags("--disable-gpu", "--disable-gpu-compositing")
        os.environ.setdefault("QT_OPENGL", "software")
        logger.info("WebView 渲染模式: software（已停用 GPU 合成）")
        return True

    if platform == "win32":
        # Qt 的置頂／半透明多視窗可能讓 Chromium 誤判 WebView 已被
        # Windows 遮蔽，暫停繪製後再恢復時便出現整塊灰底閃爍。
        # 預設停用 DirectComposition；僅在明確指定啟用參數時
        # 使用此路徑。停用參數優先，方便相容性測試。
        append_chromium_flags("--disable-features=CalculateNativeWinOcclusion")
        if args.disable_webview_direct_composition or not args.enable_webview_direct_composition:
            append_chromium_flags(
                "--disable-direct-composition",
                "--disable-direct-composition-video-overlays",
            )
    if mode == "gpu-safe":
        append_chromium_flags("--disable-gpu-rasterization", "--disable-zero-copy")
    logger.info(f"WebView 渲染模式: {mode}（旗標: {os.environ.get('QTWEBENGINE_CHROMIUM_FLAGS', '')}）")
    return False
