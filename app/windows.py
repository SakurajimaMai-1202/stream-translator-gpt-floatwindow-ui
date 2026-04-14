"""
PyQt6 視窗管理器
提供三個主要視窗：Home, Settings, FloatingSubtitle
"""

import sys
from pathlib import Path
from PyQt6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QApplication
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings, QWebEngineScript
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, QUrl, QTimer, QPoint, QRect, QEvent, QObject, pyqtSlot, pyqtSignal
from PyQt6.QtGui import QIcon, QCursor, QMouseEvent, QWheelEvent, QKeyEvent
import logging

logger = logging.getLogger(__name__)


class SubtitleBridge(QObject):
    """JavaScript 與 Python 之間的橋接"""
    
    openSettings = pyqtSignal()
    closeRequested = pyqtSignal()
    
    @pyqtSlot()
    def requestOpenSettings(self):
        """從 JavaScript 呼叫以打開設定視窗"""
        logger.info("收到打開設定視窗請求")
        self.openSettings.emit()

    @pyqtSlot()
    def requestCloseWindow(self):
        """從 JavaScript 呼叫以關閉字幕視窗"""
        logger.info("收到關閉字幕視窗請求")
        self.closeRequested.emit()


class HomeBridge(QObject):
    """主頁橋接：開啟字幕視窗、複製到剪貼簿"""

    openSubtitleWindowRequested = pyqtSignal()

    @pyqtSlot()
    def openSubtitleWindow(self):
        """從 JavaScript 呼叫以開啟字幕視窗"""
        logger.info("收到開啟字幕視窗請求")
        self.openSubtitleWindowRequested.emit()

    @pyqtSlot(str, result=bool)
    def copyToClipboard(self, text: str) -> bool:
        """從 JavaScript 呼叫以將文字複製到系統剪貼簿"""
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            logger.info(f"已複製到剪貼簿: {text[:80]}")
            return True
        except Exception as e:
            logger.error(f"複製到剪貼簿失敗: {e}")
            return False


class WebViewWindow(QMainWindow):
    """通用 WebView 視窗基類"""
    
    def __init__(self, title: str, url: str, width: int = 1200, height: int = 800):
        super().__init__()
        self.setWindowTitle(title)
        app = QApplication.instance()
        if app is not None:
            icon = app.windowIcon()
            if not icon.isNull():
                self.setWindowIcon(icon)
        self.resize(width, height)
        
        # 設定視窗背景色為深色，避免載入或重新繪製時的白屏閃爍
        self.setStyleSheet("background-color: #0f172a;")
        
        # 建立 WebView
        self.web_view = QWebEngineView()
        self.web_view.setPage(CustomWebPage(self.web_view))
        self.web_view.setZoomFactor(1.0)
        # 設定 WebView 背景也為深色 (會被頁面 CSS 覆蓋，但防止空頁面閃爍)
        self.web_view.setStyleSheet("background-color: #0f172a;")
        
        # 設定
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

        # 在 Qt 層鎖定縮放，避免原生下拉/彈窗層的 Ctrl+Wheel 造成畫面持續放大
        self.web_view.installEventFilter(self)
        if self.web_view.focusProxy():
            self.web_view.focusProxy().installEventFilter(self)

        # 保險機制：定時校正 zoomFactor，覆蓋原生層可能漏攔截的縮放改動
        self._zoom_guard_timer = QTimer(self)
        self._zoom_guard_timer.setInterval(250)
        self._zoom_guard_timer.timeout.connect(self._enforce_zoom_factor)
        self._zoom_guard_timer.start()
        
        self.setCentralWidget(self.web_view)
        
        # 延遲載入 URL（確保服務已啟動）
        self._target_url = url
        QTimer.singleShot(500, self._load_url)
        
    def _load_url(self):
        """載入 URL"""
        logger.info(f"載入 URL: {self._target_url}")
        self.web_view.setUrl(QUrl(self._target_url))
        self._enforce_zoom_factor()

    def _should_block_zoom_key(self, event: QKeyEvent) -> bool:
        """判斷是否為縮放快捷鍵 (Ctrl/Meta + +/-/=0)"""
        if not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier)):
            return False

        key = event.key()
        return key in (
            Qt.Key.Key_Plus,
            Qt.Key.Key_Minus,
            Qt.Key.Key_Equal,
            Qt.Key.Key_0,
        )

    def _enforce_zoom_factor(self):
        """強制保持縮放倍率為 1，避免原生下拉/彈窗層改動頁面縮放"""
        current = self.web_view.zoomFactor()
        if abs(current - 1.0) > 1e-6:
            logger.warning(f"偵測到 zoomFactor={current:.3f}，已重設為 1.0")
            self.web_view.setZoomFactor(1.0)

    def eventFilter(self, obj, event):
        """攔截 WebEngine 原生縮放事件（DOM 層攔截不到的情境）"""
        # Ctrl + 滾輪縮放
        if event.type() == QEvent.Type.Wheel and isinstance(event, QWheelEvent):
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                self._enforce_zoom_factor()
                return True

        # Ctrl + +/-/= / 0
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if self._should_block_zoom_key(event):
                self._enforce_zoom_factor()
                return True

        return super().eventFilter(obj, event)


class CustomWebPage(QWebEnginePage):
    """自訂 WebPage 用於處理控制台訊息"""
    
    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        """捕獲 JavaScript 控制台訊息"""
        log_levels = {
            QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel: logger.info,
            QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel: logger.warning,
            QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel: logger.error
        }
        log_func = log_levels.get(level, logger.debug)
        log_func(f"[WebView Console] {message} (Line: {lineNumber})")


class HomeWindow(WebViewWindow):
    """主視窗（首頁）"""

    def __init__(self, base_url: str = "http://localhost:5173", on_open_subtitle=None):
        super().__init__(
            title="Stream Translator",
            url=f"{base_url}/",
            width=1000,
            height=700
        )

        self._on_open_subtitle = on_open_subtitle

        # 設定 WebChannel 以便與 JavaScript 通訊
        self.channel = QWebChannel()
        self.bridge = HomeBridge()
        self.channel.registerObject("pyqt", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        if callable(self._on_open_subtitle):
            self.bridge.openSubtitleWindowRequested.connect(self._handle_open_subtitle)

        self._inject_home_webchannel_scripts()

    def _handle_open_subtitle(self):
        if callable(self._on_open_subtitle):
            self._on_open_subtitle()

    def _inject_home_webchannel_scripts(self):
        """注入 WebChannel 腳本，建立 window.pyqt"""
        qwebchannel_script = QWebEngineScript()
        qwebchannel_script.setSourceUrl(QUrl("qrc:///qtwebchannel/qwebchannel.js"))
        qwebchannel_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        qwebchannel_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        qwebchannel_script.setRunsOnSubFrames(False)
        self.web_view.page().scripts().insert(qwebchannel_script)

        init_script = QWebEngineScript()
        init_script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        init_script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        init_script.setRunsOnSubFrames(False)
        init_script.setSourceCode(
            """
            (function () {
              if (window.qt && window.qt.webChannelTransport) {
                new QWebChannel(window.qt.webChannelTransport, function (channel) {
                  window.pyqt = channel.objects.pyqt;
                });
              }
            })();
            """
        )
        self.web_view.page().scripts().insert(init_script)


class SettingsWindow(WebViewWindow):
    """設定視窗"""
    
    def __init__(self, base_url: str = "http://localhost:5173"):
        super().__init__(
            title="設定",
            url=f"{base_url}/settings",
            width=1200,
            height=800
        )


class SubtitleSettingsWindow(QMainWindow):
    """字幕設定彈窗（獨立視窗）"""
    
    def __init__(self, base_url: str = "http://localhost:5173"):
        super().__init__()
        self.setWindowTitle("字幕設定")
        app = QApplication.instance()
        if app is not None:
            icon = app.windowIcon()
            if not icon.isNull():
                self.setWindowIcon(icon)
        self.resize(450, 650)
        
        # 設定視窗屬性：置頂、工具視窗
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        
        self.setStyleSheet("background-color: #0f172a;")
        
        # 建立 WebView
        self.web_view = QWebEngineView()
        self.web_view.setPage(CustomWebPage(self.web_view))
        self.web_view.setStyleSheet("background-color: #0f172a;")
        
        # 設定
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        
        self.setCentralWidget(self.web_view)
        
        # 延遲載入 URL
        self._target_url = f"{base_url}/subtitle-settings"
        QTimer.singleShot(500, self._load_url)
    
    def _load_url(self):
        """載入 URL"""
        logger.info(f"載入字幕設定 URL: {self._target_url}")
        self.web_view.setUrl(QUrl(self._target_url))


class FloatingSubtitleWindow(WebViewWindow):
    """浮動字幕視窗"""
    
    def __init__(self, base_url: str = "http://localhost:5173", config_manager=None):
        # 不呼叫 super().__init__ 以自定義佈局
        QMainWindow.__init__(self)
        
        self.config_manager = config_manager
        self.setWindowTitle("字幕")
        app = QApplication.instance()
        if app is not None:
            icon = app.windowIcon()
            if not icon.isNull():
                self.setWindowIcon(icon)
        
        # 從配置載入位置和大小
        if config_manager:
            ui_config = config_manager.get_config().get('ui', {})
            windows_config = ui_config.get('windows', {})
            subtitle_config = windows_config.get('floating_subtitle', {})
            
            width = subtitle_config.get('width', 800)
            height = subtitle_config.get('height', 200)
            x = subtitle_config.get('x', 100)
            y = subtitle_config.get('y', 100)
            
            self.resize(width, height)
            self.move(x, y)
        else:
            self.resize(800, 200)
        
        self.setMinimumSize(200, 100)
        self.setMouseTracking(True)
        
        # 設定為無邊框、置頂視窗
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool  # 工具視窗，不出現在工作列
        )
        
        # 設定背景透明
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background:transparent;")
        
        # 建立容器與佈局
        self.container = QWidget()
        self.container.setStyleSheet("background:transparent;")
        self.layout = QVBoxLayout(self.container)
        self.layout.setContentsMargins(0, 0, 0, 0) # 移除邊距，WebView 填滿
        
        # 建立 WebView
        self.web_view = QWebEngineView()
        self.web_view.setPage(CustomWebPage(self.web_view))
        self.web_view.setZoomFactor(1.0)
        self.web_view.setStyleSheet("background:transparent;")
        self.web_view.page().setBackgroundColor(Qt.GlobalColor.transparent)
        
        # 設定 WebChannel 以便與 JavaScript 通訊
        self.channel = QWebChannel()
        self.bridge = SubtitleBridge()
        self.channel.registerObject("bridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)
        
        # 連接橋接信號
        self.bridge.openSettings.connect(self._open_settings_window)
        self.bridge.closeRequested.connect(self._handle_close_requested)
        
        # 設定視窗引用
        self.settings_window = None
        self.base_url = base_url
        
        # 安裝事件過濾器以處理 WebView 上的滑鼠事件
        self.web_view.installEventFilter(self)
        # 嘗試在 focusProxy 上安裝過濾器（這通常是接收輸入的實際 Widget）
        if self.web_view.focusProxy():
            self.web_view.focusProxy().installEventFilter(self)
            
        # 設定 WebView 權限
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        
        self.layout.addWidget(self.web_view)
        self.setCentralWidget(self.container)
        
        # 延遲載入 URL
        self._target_url = f"{base_url}/subtitle"
        QTimer.singleShot(500, self._load_url)
        
        # 延遲安裝事件過濾器，確保子元件已建立
        QTimer.singleShot(1000, self._install_event_filter)
        
        # 移動與縮放狀態
        self._drag_pos = None
        self._resize_edge = None
        self._margin = 10

    def _install_event_filter(self):
        """遞迴安裝事件過濾器到所有子元件"""
        def install_recursive(widget):
            widget.installEventFilter(self)
            for child in widget.children():
                if isinstance(child, QWidget):
                    install_recursive(child)
        
        install_recursive(self.web_view)
        logger.info("已安裝事件過濾器到 WebView 及其子元件")
    
    def _open_settings_window(self):
        """打開設定視窗"""
        if self.settings_window is None:
            self.settings_window = SubtitleSettingsWindow(self.base_url)
            # 當視窗關閉時清除引用
            self.settings_window.destroyed.connect(lambda: setattr(self, 'settings_window', None))
        
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def _handle_close_requested(self):
        """處理字幕視窗關閉請求"""
        # 儲存視窗位置和大小
        self._save_window_geometry()
        if self.settings_window is not None:
            self.settings_window.close()
        self.hide()

    def eventFilter(self, obj, event):
        """處理 WebView 的滑鼠事件"""
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease):
            # 確保 event 是滑鼠事件
            if not isinstance(event, QMouseEvent):
                return super().eventFilter(obj, event)

            global_pos = event.globalPosition().toPoint()
            local_pos = self.mapFromGlobal(global_pos)
            
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    edge = self._check_edge(local_pos)
                    if edge:
                        self._resize_edge = edge
                        return True  # 攔截縮放操作
                    else:
                        self._drag_pos = global_pos - self.frameGeometry().topLeft()
                        # 不攔截拖曳的 Press，讓 WebView 處理按鈕點擊
            
            elif event.type() == QEvent.Type.MouseMove:
                # 處理縮放
                if self._resize_edge:
                    self._handle_resize(global_pos)
                    return True
                
                # 處理拖曳
                if self._drag_pos:
                    # 只有移動超過一定距離才視為拖曳，避免誤觸
                    start_pos = self.frameGeometry().topLeft() + self._drag_pos
                    if (global_pos - start_pos).manhattanLength() > 5 or self.cursor().shape() == Qt.CursorShape.ArrowCursor: 
                         self.move(global_pos - self._drag_pos)
                         return True
                    
                # 更新游標
                self._update_cursor(self._check_edge(local_pos))
                
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if self._resize_edge or self._drag_pos:
                    self._resize_edge = None
                    self._drag_pos = None
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                    # 儲存視窗位置和大小
                    self._save_window_geometry()
                    # 不攔截，確保釋放事件傳遞給 WebView
                        
        return super().eventFilter(obj, event)

    def _load_url(self):
        """載入 URL"""
        logger.info(f"載入 URL: {self._target_url}")
        self.web_view.setUrl(QUrl(self._target_url))
        self.web_view.setZoomFactor(1.0)

        # 首次顯示後微幅重繪，避免透明無框視窗首幀元素未完全更新
        QTimer.singleShot(900, self._trigger_initial_repaint)

    def _trigger_initial_repaint(self):
        """觸發一次首幀重繪，提升首次顯示穩定性"""
        size = self.size()
        self.resize(size.width() + 1, size.height() + 1)

        def restore():
            self.resize(size)
            self.web_view.update()
            self.web_view.repaint()
            self.web_view.page().runJavaScript("window.dispatchEvent(new Event('resize'));")

        QTimer.singleShot(120, restore)
        
    def _check_edge(self, pos: QPoint):
        """檢查滑鼠是否在邊緣"""
        r = self.rect()
        x, y, w, h = pos.x(), pos.y(), r.width(), r.height()
        edge = 0
        
        if x < self._margin: edge |= 1  # Left
        if x > w - self._margin: edge |= 2  # Right
        if y < self._margin: edge |= 4  # Top
        if y > h - self._margin: edge |= 8  # Bottom
        
        return edge

    def _update_cursor(self, edge):
        """更新游標樣式"""
        cursors = {
            0: Qt.CursorShape.ArrowCursor,
            1: Qt.CursorShape.SizeHorCursor,
            2: Qt.CursorShape.SizeHorCursor,
            4: Qt.CursorShape.SizeVerCursor,
            8: Qt.CursorShape.SizeVerCursor,
            5: Qt.CursorShape.SizeFDiagCursor,
            6: Qt.CursorShape.SizeBDiagCursor,
            9: Qt.CursorShape.SizeBDiagCursor,
            10: Qt.CursorShape.SizeFDiagCursor
        }
        # 只有當游標真正改變時才設定，避免閃爍
        current_cursor = self.cursor().shape()
        target_cursor = cursors.get(edge, Qt.CursorShape.ArrowCursor)
        if current_cursor != target_cursor:
            self.setCursor(target_cursor)

    def _handle_resize(self, global_pos: QPoint):
        """處理視窗縮放邏輯"""
        rect = self.geometry()
        
        if self._resize_edge & 1: # Left
            rect.setLeft(global_pos.x())
        if self._resize_edge & 2: # Right
            rect.setRight(global_pos.x())
        if self._resize_edge & 4: # Top
            rect.setTop(global_pos.y())
        if self._resize_edge & 8: # Bottom
            rect.setBottom(global_pos.y())
        
        # 確保不小於最小值
        if rect.width() >= self.minimumWidth() and rect.height() >= self.minimumHeight():
            self.setGeometry(rect)

    def mousePressEvent(self, event):
        # 備用，如果事件沒有被過濾器攔截（例如點擊到非 WebView 區域，雖然這裡沒有）
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
         super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
         super().mouseReleaseEvent(event)
    
    def _save_window_geometry(self):
        """儲存視窗位置和大小到配置"""
        if not self.config_manager:
            return
        
        try:
            geometry = self.geometry()
            window_config = {
                'x': geometry.x(),
                'y': geometry.y(),
                'width': geometry.width(),
                'height': geometry.height(),
                'visible': self.isVisible()
            }
            
            # 獲取當前配置
            config = self.config_manager.get_config()
            if 'ui' not in config:
                config['ui'] = {}
            if 'windows' not in config['ui']:
                config['ui']['windows'] = {}
            
            # 更新字幕視窗配置
            config['ui']['windows']['floating_subtitle'] = window_config
            
            # 儲存配置
            self.config_manager.save()
            logger.debug(f"已儲存字幕視窗配置: {window_config}")
        except Exception as e:
            logger.error(f"儲存字幕視窗配置失敗: {e}")
