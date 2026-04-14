"""
PyQt6 + WebView 整合層
管理 FastAPI 後端與 QWebEngineView 的生命週期
"""

import sys
import subprocess
import socket
import time
import logging
import re
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QProcess, QTimer, pyqtSignal, QObject

logger = logging.getLogger(__name__)


def _classify_process_log_level(line: str, default_level: int) -> int:
    """根據子程序輸出內容判斷較合理的 log 等級。"""
    normalized = line.strip().lower()
    if not normalized:
        return logging.DEBUG

    if any(keyword in normalized for keyword in ("traceback", "critical", "exception", "error", "fatal")):
        return logging.ERROR
    if any(keyword in normalized for keyword in ("warning", "warn")):
        return logging.WARNING
    if any(keyword in normalized for keyword in ("watchfiles", "statreload", "detected file change", "reloader")):
        return logging.DEBUG
    if re.search(r"\bdebug\b", normalized):
        return logging.DEBUG

    return default_level


def _log_subprocess_output(prefix: str, line: str, default_level: int):
    level = _classify_process_log_level(line, default_level)
    logger.log(level, f"[{prefix}] {line}")

class BackendProcess(QObject):
    """FastAPI 後端程序管理器"""
    
    started = pyqtSignal()
    stopped = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, backend_dir: Path, port: int = 8000):
        super().__init__()
        self.backend_dir = backend_dir
        self.port = port
        self.process = None
        self._start_attempts = 0
        self._max_attempts = 3
        
    def start(self):
        """啟動後端程序"""
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            logger.warning("後端已在執行中")
            return
        
        # 檢查端口是否被佔用
        if self._is_port_in_use(self.port):
            logger.warning(f"Port {self.port} 已被佔用，嘗試連接現有服務...")
            if self._check_backend_health():
                self.started.emit()
                return
            else:
                self.error.emit(f"Port {self.port} 被其他程式佔用")
                return
        
        # 啟動新的後端程序
        self.process = QProcess()
        
        # 檢查是否為 PyInstaller 打包環境 (frozen)
        if getattr(sys, 'frozen', False):
            # 打包模式：使用當前執行檔本身來啟動後端
            self.process.setProgram(sys.executable)
            # 傳遞端口參數
            self.process.setArguments(["--backend", "--port", str(self.port)])
            logger.info(f"啟動後端 (Frozen): {sys.executable} --backend --port {self.port}")
        else:
            # 開發模式：使用 uvicorn 模組並從專案根目錄啟動
            self.process.setWorkingDirectory(str(self.backend_dir.parent))
            self.process.setProgram(sys.executable)
            self.process.setArguments([
                "-m", "uvicorn",
                "backend.main:app",
                "--host", "0.0.0.0",
                "--port", str(self.port),
                "--reload",
                "--no-access-log"
            ])
            logger.info(f"啟動後端 (Dev): {sys.executable} -m uvicorn backend.main:app --host 0.0.0.0 --port {self.port} --reload")

        if getattr(sys, 'frozen', False):
            self.process.setWorkingDirectory(str(self.backend_dir))
        
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)
        
        self.process.start()
        
        # 等待後端啟動
        QTimer.singleShot(2000, self._check_startup)
        
    def stop(self):
        """停止後端程序"""
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            logger.info("停止後端程序...")
            self.process.terminate()
            if not self.process.waitForFinished(5000):
                logger.warning("正常終止失敗，強制結束...")
                self.process.kill()
                self.process.waitForFinished(2000)
            self.stopped.emit()
        
        # 確保程序對象被正確清理
        if self.process:
            self.process.deleteLater()
            self.process = None
        
    def _check_startup(self):
        """檢查後端是否成功啟動"""
        if self._check_backend_health():
            logger.info("後端啟動成功")
            self.started.emit()
        else:
            self._start_attempts += 1
            if self._start_attempts < self._max_attempts:
                logger.warning(f"後端啟動檢查失敗，重試 {self._start_attempts}/{self._max_attempts}")
                QTimer.singleShot(2000, self._check_startup)
            else:
                error_msg = "後端啟動失敗，請檢查日誌"
                logger.error(error_msg)
                self.error.emit(error_msg)
    
    def _check_backend_health(self) -> bool:
        """檢查後端健康狀態"""
        try:
            import urllib.request
            response = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/health", timeout=2)
            return response.status == 200
        except Exception as e:
            logger.debug(f"後端健康檢查失敗: {e}")
            return False
    
    def _is_port_in_use(self, port: int) -> bool:
        """檢查端口是否被佔用"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('127.0.0.1', port)) == 0
    
    def _on_stdout(self):
        """處理標準輸出"""
        if self.process:
            data = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
            for line in data.strip().split('\n'):
                if line:
                    _log_subprocess_output("Backend", line, logging.INFO)
    
    def _on_stderr(self):
        """處理錯誤輸出"""
        if self.process:
            data = self.process.readAllStandardError().data().decode('utf-8', errors='ignore')
            for line in data.strip().split('\n'):
                if line:
                    _log_subprocess_output("Backend", line, logging.WARNING)
    
    def _on_finished(self, exit_code, exit_status):
        """程序結束處理"""
        logger.info(f"後端程序結束 (Exit Code: {exit_code}, Status: {exit_status})")
        self.stopped.emit()


class FrontendServer(QObject):
    """Vite 開發伺服器管理器（僅開發模式）"""
    
    started = pyqtSignal(int)  # 發送實際使用的 Port
    stopped = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, frontend_dir: Path, port: int = 5173):
        super().__init__()
        self.frontend_dir = frontend_dir
        self.port = port
        self.actual_port = port  # 實際使用的端口
        self.process = None
        
    def start(self):
        """啟動 Vite 開發伺服器"""
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            logger.warning("前端開發伺服器已在執行中")
            return
        
        # 檢查是否為開發模式
        if not (self.frontend_dir / "node_modules").exists():
            error_msg = "node_modules 不存在，請先執行 npm install"
            logger.error(error_msg)
            self.error.emit(error_msg)
            return
        
        self.process = QProcess()
        self.process.setWorkingDirectory(str(self.frontend_dir))
        
        # Windows 使用 npm.cmd
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        self.process.setProgram(npm_cmd)
        self.process.setArguments(["run", "dev"])
        
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        
        logger.info(f"啟動前端開發伺服器: {npm_cmd} run dev")
        self.process.start()
        
        # 較短的初次檢查時間，並增加重試次數
        QTimer.singleShot(4000, self._check_startup)
        
    def stop(self):
        """停止前端開發伺服器"""
        if self.process and self.process.state() == QProcess.ProcessState.Running:
            logger.info("停止前端開發伺服器...")
            
            # Windows 需要特殊處理 npm 進程
            if sys.platform == "win32":
                try:
                    import subprocess
                    # 使用 taskkill 強制結束整個進程樹
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.processId())], 
                                 capture_output=True, timeout=3)
                except Exception as e:
                    logger.warning(f"taskkill 失敗: {e}")
            
            self.process.terminate()
            if not self.process.waitForFinished(5000):
                self.process.kill()
                self.process.waitForFinished(2000)
            self.stopped.emit()
        
        # 確保程序對象被正確清理
        if self.process:
            self.process.deleteLater()
            self.process = None
    
    def _check_startup(self, attempt: int = 0):
        """檢查前端是否成功啟動"""
        max_attempts = 15  # 最多重試 15 次 (約 30 秒)
        
        # 嘗試原始端口和備用端口
        for port in range(self.port, self.port + 10):
            try:
                import urllib.request
                response = urllib.request.urlopen(f"http://localhost:{port}", timeout=1)
                if response.status == 200:
                    self.actual_port = port
                    logger.info(f"前端開發伺服器啟動成功（Port: {port}）")
                    self.started.emit(port)
                    return
            except Exception:
                continue
        
        # 重試
        if attempt < max_attempts:
            logger.debug(f"前端啟動檢查 {attempt + 1}/{max_attempts}，等待中...")
            QTimer.singleShot(2000, lambda: self._check_startup(attempt + 1))
        else:
            error_msg = "前端開發伺服器啟動超時，請檢查 node_modules 是否已安裝"
            logger.error(error_msg)
            self.error.emit(error_msg)
    
    def _on_stdout(self):
        """處理標準輸出"""
        if self.process:
            data = self.process.readAllStandardOutput().data().decode('utf-8', errors='ignore')
            for line in data.strip().split('\n'):
                if line:
                    _log_subprocess_output("Frontend", line, logging.INFO)
    
    def _on_stderr(self):
        """處理錯誤輸出"""
        if self.process:
            data = self.process.readAllStandardError().data().decode('utf-8', errors='ignore')
            for line in data.strip().split('\n'):
                if line:
                    # Vite 的啟動訊息通常在 stderr
                    if any(keyword in line.lower() for keyword in ['ready', 'local', 'network', 'vite']):
                        _log_subprocess_output("Frontend", line, logging.INFO)
                    else:
                        _log_subprocess_output("Frontend", line, logging.DEBUG)
