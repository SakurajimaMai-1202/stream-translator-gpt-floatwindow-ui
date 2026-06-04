"""
UI2 主程式
PyQt6 + WebView + FastAPI 整合啟動器
"""

import sys
import logging
import socket
import threading
from pathlib import Path
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QIcon

from backend.core.logging_setup import configure_logging
from services import BackendProcess, FrontendServer
from windows import HomeWindow, SettingsWindow, FloatingSubtitleWindow

# 設定日誌
# 由 UI 啟動器統一在每次開啟時清掉 app/backend/translator stderr 舊檔，避免 log 無限累積。
LOG_FILE = configure_logging("app", reset_log_names=["backend", "translator_stderr"])
logger = logging.getLogger(__name__)


def resolve_app_icon() -> QIcon:
    """解析可用的應用圖示，支援開發與打包模式。"""
    candidates = []

    if getattr(sys, 'frozen', False):
        exe_path = Path(sys.executable)
        candidates.extend([
            exe_path,  # 直接使用嵌入在 exe 的圖示
            exe_path.parent / "app_icon.ico",
            Path(getattr(sys, '_MEIPASS', exe_path.parent)) / "app_icon.ico",
        ])
    else:
        candidates.append(Path(__file__).parent / "app_icon.ico")

    for candidate in candidates:
        try:
            if not candidate.exists():
                continue
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return icon
        except Exception:
            continue

    return QIcon()


class UI2Application:
    """UI2 應用程式管理器"""
    
    def __init__(self, dev_mode: bool = True):
        self.dev_mode = dev_mode
        # 設定 OpenGL 上下文共享，解決 WebView 閃爍問題
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
        # 針對某些環境的 GPU 加速優化
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseDesktopOpenGL)
        
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("Stream Translator")

        # 設定應用程式圖標（支援打包模式）
        app_icon = resolve_app_icon()
        if not app_icon.isNull():
            self.app.setWindowIcon(app_icon)
        
        # 路徑設定
        self.base_dir = Path(__file__).parent
        self.backend_dir = self.base_dir / "backend"
        self.frontend_dir = self.base_dir / "frontend"
        
        # 服務管理
        # 排除已知被翻譯 API 使用的端口（如 8080），從設定讀取
        reserved_ports = self._get_reserved_ports()
        self.backend_port = self._pick_backend_port(8010, reserved=reserved_ports)
        logger.info(f"使用後端端口: {self.backend_port}")
        self.backend = BackendProcess(self.backend_dir, port=self.backend_port)
        self.frontend = None
        self.frontend_port = 5173  # 預設值，實際會在啟動時更新
        
        # 視窗
        self.home_window = None
        self.settings_window = None
        self.subtitle_window = None
        
        # 連接信號
        self.backend.started.connect(self._on_backend_started)
        self.backend.error.connect(self._on_backend_error)
        
        # 開發模式需要 Vite 開發伺服器
        if self.dev_mode:
            self.frontend = FrontendServer(self.frontend_dir, port=5173)
            self.frontend.started.connect(self._on_frontend_started)
            self.frontend.error.connect(self._on_frontend_error)
    
    def run(self):
        """啟動應用程式"""
        logger.info("=" * 60)
        logger.info("Stream Translator 啟動中...")
        logger.info(f"開發模式: {self.dev_mode}")
        logger.info(f"App log 檔案: {LOG_FILE}")
        logger.info("=" * 60)
        
        # 啟動後端
        logger.info("啟動 FastAPI 後端...")
        self.backend.start()
        
        # 開發模式啟動前端開發伺服器
        if self.dev_mode:
            logger.info("啟動 Vite 開發伺服器...")
            QTimer.singleShot(2000, lambda: self.frontend.start())
        else:
            # 生產模式等待後端就緒再顯示視窗
            pass
        
        # 執行應用程式
        return self.app.exec()
    
    def _on_backend_started(self):
        """後端啟動成功"""
        logger.info("✅ FastAPI 後端已就緒")
        
        # 如果不是開發模式，直接顯示主視窗
        if not self.dev_mode:
            self._show_main_window()
    
    def _on_backend_error(self, error_msg: str):
        """後端啟動失敗"""
        logger.error(f"❌ 後端啟動失敗: {error_msg}")
        QMessageBox.critical(None, "啟動失敗", f"後端服務啟動失敗：\n{error_msg}")
        self.app.quit()
    
    def _on_frontend_started(self, port: int):
        """前端開發伺服器啟動成功"""
        self.frontend_port = port
        logger.info(f"✅ Vite 開發伺服器已就緒（Port: {port}）")
        self._show_main_window()
    
    def _on_frontend_error(self, error_msg: str):
        """前端啟動失敗"""
        logger.error(f"❌ 前端啟動失敗: {error_msg}")
        QMessageBox.critical(None, "啟動失敗", f"前端開發伺服器啟動失敗：\n{error_msg}")
        self.app.quit()
    
    def _show_main_window(self):
        """顯示主視窗"""
        if self.dev_mode:
            base_url = f"http://localhost:{self.frontend_port}"
        else:
            base_url = f"http://127.0.0.1:{self.backend_port}"

        self.base_url = base_url
        
        logger.info(f"建立主視窗 (Base URL: {base_url})")
        self.home_window = HomeWindow(base_url, on_open_subtitle=self.open_subtitle_window)
        
        # 連接視窗關閉信號到 cleanup
        self.home_window.destroyed.connect(self.cleanup)
        
        self.home_window.show()
        
        logger.info("建立浮動字幕視窗")
        self.open_subtitle_window()
        
        logger.info("=" * 60)
        logger.info("✅ UI2 應用程式啟動完成")
        logger.info("=" * 60)
    
    def cleanup(self):
        """清理資源"""
        logger.info("清理資源...")
        
        # 停止 llama server
        try:
            import requests
            response = requests.post(
                f"http://127.0.0.1:{self.backend_port}/api/llama/server/stop",
                timeout=2
            )
            if response.status_code == 200:
                logger.info("✅ Llama server 已停止")
            else:
                logger.warning(f"停止 Llama server 回應: {response.status_code}")
        except requests.exceptions.ConnectionError:
            logger.debug("Llama server 未執行或後端已關閉")
        except Exception as e:
            logger.warning(f"停止 Llama server 失敗: {e}")
        
        # 停止 backend 和 frontend
        if self.backend:
            self.backend.stop()
        if self.frontend:
            self.frontend.stop()

    def open_subtitle_window(self):
        """開啟（或重新開啟）字幕視窗"""
        # 如果視窗存在且可見，只需提升到前面
        if self.subtitle_window is not None and self.subtitle_window.isVisible():
            logger.info("字幕視窗已存在，提升到前面")
            self.subtitle_window.raise_()
            self.subtitle_window.activateWindow()
            return
        
        # 清除舊引用（如果存在）
        if self.subtitle_window is not None:
            logger.info("關閉舊的字幕視窗")
            try:
                self.subtitle_window.close()
            except:
                pass
            self.subtitle_window = None
        
        # 建立新視窗
        logger.info("建立新的字幕視窗")
        # 傳遞 config_manager 給字幕視窗
        from backend.core.config_manager import ConfigManager
        config_manager = ConfigManager()
        self.subtitle_window = FloatingSubtitleWindow(self.base_url, config_manager)
        self.subtitle_window.destroyed.connect(lambda: setattr(self, 'subtitle_window', None))
        self.subtitle_window.show()
        self.subtitle_window.raise_()
        self.subtitle_window.activateWindow()

    def _get_reserved_ports(self) -> set:
        """從設定檔讀取已被其他服務占用的端口，以避免衝突"""
        reserved = {8080}  # 預設排除常見的本地 API 服務端口
        try:
            import yaml
            config_path = self.base_dir / "config.yaml"
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    cfg = yaml.safe_load(f) or {}
                translation = cfg.get('translation', {})
                # 解析自訂模型的 base_url
                for model in translation.get('custom_models', []):
                    url = model.get('base_url', '')
                    self._extract_port(url, reserved)
                # 解析 gpt_base_url
                self._extract_port(translation.get('gpt_base_url', ''), reserved)
                # 解析 llama server_url
                llama = translation.get('llama', {})
                self._extract_port(llama.get('server_url', ''), reserved)
        except Exception as e:
            logger.warning(f"讀取設定檔端口時發生錯誤: {e}")
        logger.info(f"保留端口（不使用）: {reserved}")
        return reserved

    def _extract_port(self, url: str, port_set: set):
        """從 URL 字串中解析端口號並加入集合"""
        if not url:
            return
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.port:
                port_set.add(parsed.port)
        except Exception:
            pass

    def _pick_backend_port(self, preferred: int, reserved: set = None) -> int:
        """從首選端口開始依序尋找可用端口，跳過已保留端口"""
        if reserved is None:
            reserved = set()
        # 依序嘗試 preferred ~ preferred+98
        for port in range(preferred, preferred + 99):
            if port in reserved:
                logger.debug(f"端口 {port} 在保留清單中，跳過")
                continue
            if not self._is_port_in_use(port):
                return port
        # 極少數情況下全部被佔用，回傳首選（讓系統報錯）
        logger.error("找不到可用端口，回傳首選端口")
        return preferred

    def _is_port_in_use(self, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0


def main():
    """主入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Stream Translator")
    parser.add_argument(
        '--prod',
        action='store_true',
        help='生產模式（使用構建後的前端）'
    )
    parser.add_argument(
        '--backend',
        action='store_true',
        help='啟動後端服務（內部使用）'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=8010,
        help='後端埠號（內部使用）'
    )
    args = parser.parse_args()

    if args.backend:
        run_backend_directly(args.port)
        return
    
    try:
        is_frozen = getattr(sys, 'frozen', False)
        dev_mode = (not args.prod) and (not is_frozen)
        app = UI2Application(dev_mode=dev_mode)
        exit_code = app.run()
        app.cleanup()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("收到中斷信號，正在關閉...")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"應用程式發生錯誤: {e}")
        sys.exit(1)


def run_backend_directly(port: int):
    """在打包模式下直接啟動後端"""
    import uvicorn
    from backend.main import app
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
