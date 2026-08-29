"""Standalone, rollback-capable GUI updater for Stream Translator."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressBar, QPushButton, QTextEdit, QVBoxLayout

ALLOWED = {
    "app-update-build.json", "StreamTranslatorUpdater.exe", "diagnose_runtime.ps1",
    "PORTABLE_GUIDE_zh-TW.txt", "smoke_sensevoice_asr.ps1", "Stream Translator.exe",
    "UPDATE_NOTES_zh-TW.txt", "_internal", "_js_runtime", "_runtime",
}
UPDATE_MODES = {"app_only", "runtime_replace"}


class Worker(QThread):
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, plan_path: Path, preview: bool = False):
        super().__init__()
        self.plan_path = plan_path
        self.preview = preview

    def step(self, value: int, message: str) -> None:
        self.progress.emit(value, message)
        self.log.emit(message)

    @staticmethod
    def prune_user_backups(backup_parent: Path, keep: int = 5) -> None:
        parent = backup_parent.resolve()
        if keep < 1 or not parent.is_dir():
            return
        candidates = []
        for path in backup_parent.iterdir():
            if not path.name.startswith("before-") or not path.is_dir():
                continue
            if path.is_symlink():
                raise RuntimeError(f"備份目錄不可為符號連結：{path.name}")
            resolved = path.resolve()
            if resolved.parent != parent:
                raise RuntimeError(f"備份路徑超出允許範圍：{path.name}")
            candidates.append(resolved)
        candidates.sort(key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
        for old in candidates[keep:]:
            shutil.rmtree(old)

    @staticmethod
    def backup_user_settings(app_root: Path, version: str) -> Path:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup_root = app_root / ".app-update" / "user-backups" / f"before-{version}-{stamp}"
        if backup_root.exists():
            raise RuntimeError("同名的更新前備份已存在")
        backup_root.mkdir(parents=True)
        config_path = app_root / "config.yaml"
        if not config_path.is_file():
            raise RuntimeError("找不到 config.yaml，已停止更新")
        shutil.copy2(config_path, backup_root / "config.yaml")
        try:
            config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            raise RuntimeError(f"config.yaml 無法解析，已停止更新：{exc}") from exc
        terminology = (config.get("terminology") or {}).get("glossary_list") or []
        corrections = (config.get("transcription") or {}).get("asr_correction_rules") or []
        (backup_root / "custom-glossary.json").write_text(json.dumps(terminology, ensure_ascii=False, indent=2), encoding="utf-8")
        (backup_root / "asr-correction-rules.json").write_text(json.dumps(corrections, ensure_ascii=False, indent=2), encoding="utf-8")
        cookie_backup = backup_root / "cookies"
        cookie_backup.mkdir()
        local_cookie_dir = app_root / "cookies"
        if local_cookie_dir.is_dir():
            for source in local_cookie_dir.glob("*.txt"):
                if source.is_file():
                    shutil.copy2(source, cookie_backup / source.name)
        input_config = config.get("input") or {}
        configured = [str(input_config.get("cookies") or "").strip()]
        by_site = input_config.get("cookies_by_site") or {}
        if isinstance(by_site, dict):
            configured.extend(str(value or "").strip() for value in by_site.values())
        seen = set()
        for index, value in enumerate(path for path in configured if path):
            source = Path(os.path.expandvars(os.path.expanduser(value)))
            if not source.is_absolute():
                source = app_root / source
            try:
                resolved = source.resolve()
            except OSError:
                continue
            if not resolved.is_file() or resolved in seen:
                continue
            seen.add(resolved)
            destination = cookie_backup / resolved.name
            if destination.exists():
                destination = cookie_backup / f"configured-{index + 1}-{resolved.name}"
            shutil.copy2(resolved, destination)
        manifest = {
            "schema": 1, "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "before_version": str(version),
            "files": [str(path.relative_to(backup_root)) for path in backup_root.rglob("*") if path.is_file()],
        }
        (backup_root / "backup-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        Worker.prune_user_backups(backup_root.parent, keep=5)
        return backup_root

    @staticmethod
    def validate_plan(plan_path: Path) -> tuple[dict, dict, Path, Path, list[Path], str]:
        plan = json.loads(plan_path.read_text(encoding="utf-8-sig"))
        app_root = Path(plan["app_root"]).resolve()
        staging = Path(plan["staging"]).resolve()
        if plan.get("schema") not in {1, 2} or app_root == Path(app_root.anchor) or app_root / ".app-update" not in staging.parents:
            raise RuntimeError("更新計畫的路徑或格式無效")
        manifest = json.loads((staging / "app-update-build.json").read_text(encoding="utf-8"))
        if manifest.get("profile") != plan.get("profile") or str(manifest.get("version")) != str(plan.get("version")):
            raise RuntimeError("更新套件的 Profile 或版本不相符")
        items = list(staging.iterdir())
        if not items or any(item.name not in ALLOWED for item in items):
            raise RuntimeError("更新套件包含未允許的檔案")
        mode = str(manifest.get("update_mode") or plan.get("update_mode") or ("runtime_replace" if (staging / "_runtime").exists() else "app_only"))
        if mode not in UPDATE_MODES or (plan.get("update_mode") and plan["update_mode"] != mode):
            raise RuntimeError("更新模式不相符")
        runtime = staging / "_runtime"
        if mode == "app_only" and runtime.exists():
            raise RuntimeError("app_only 更新不可包含 _runtime")
        if mode == "runtime_replace":
            runtime_python = runtime / "python.exe"
            runtime_manifest = runtime / "runtime-version.json"
            if not runtime_python.is_file() or not runtime_manifest.is_file():
                raise RuntimeError("runtime_replace 套件缺少完整 Runtime")
            runtime_info = json.loads(runtime_manifest.read_text(encoding="utf-8"))
            if str(runtime_info.get("profile") or "").lower() != str(plan.get("profile") or "").lower():
                raise RuntimeError("替換 Runtime 的 Profile 不相符")
        return plan, manifest, app_root, staging, items, mode

    def run(self) -> None:
        if self.preview:
            for value, message in [(8, "等待主程式結束"), (18, "備份使用者設定"), (35, "驗證更新套件"), (60, "套用更新"), (82, "啟動健康檢查"), (100, "更新完成")]:
                self.step(value, message)
                time.sleep(0.7)
            self.completed.emit("預覽完成；未修改任何檔案")
            return
        backup = None
        moved: list[str] = []
        items: list[Path] = []
        app_root = None
        try:
            plan, _manifest, app_root, _staging, items, mode = self.validate_plan(self.plan_path)
            self.step(8, "等待 Stream Translator 關閉")
            deadline = time.time() + 45
            while time.time() < deadline:
                try:
                    os.kill(int(plan["parent_pid"]), 0)
                    time.sleep(0.25)
                except OSError:
                    break
            else:
                raise RuntimeError("主程式未在期限內關閉")
            self.step(18, "備份 config、術語、ASR 修正與 Cookies")
            user_backup = self.backup_user_settings(app_root, str(plan["version"]))
            self.log.emit(f"使用者設定備份：{user_backup}")
            self.step(30, f"準備 {mode} 回復點")
            backup = app_root.parent / f".stream-translator-backup-{plan['version']}-{int(time.time())}"
            backup.mkdir()
            self.step(52, "套用程式與 Runtime 更新")
            for item in items:
                target = app_root / item.name
                if target.exists():
                    shutil.move(str(target), str(backup / item.name))
                    moved.append(item.name)
                shutil.move(str(item), str(target))
            self.step(72, "驗證新版 GUI 與 DLL")
            exe = app_root / plan["executable"]
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            try:
                preflight = subprocess.run(
                    [str(exe), "--update-health-check"],
                    cwd=app_root,
                    creationflags=creationflags,
                    timeout=30,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError("新版 GUI/DLL 健康檢查逾時") from exc
            except OSError as exc:
                raise RuntimeError(f"無法啟動新版 GUI/DLL 健康檢查：{exc}") from exc
            if preflight.returncode != 0:
                raise RuntimeError(f"新版 GUI/DLL 健康檢查失敗，退出碼 {preflight.returncode}")

            self.step(82, "啟動新版並確認程序狀態")
            proc = subprocess.Popen([str(exe)], cwd=app_root, creationflags=creationflags)
            time.sleep(12)
            if proc.poll() is not None:
                raise RuntimeError(f"新版程式啟動失敗，退出碼 {proc.returncode}")
            result = {"status": "completed", "version": str(plan["version"]), "update_mode": mode, "backup": str(backup), "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")}
            (app_root / ".app-update" / "update-result.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            self.step(100, "更新完成，Stream Translator 已重新啟動")
            self.completed.emit(f"已更新至 v{plan['version']}")
        except Exception as exc:
            self.log.emit(f"更新失敗：{exc}\n正在回復上一版本")
            try:
                if app_root and backup:
                    for item in items:
                        target = app_root / item.name
                        if target.exists():
                            shutil.rmtree(target) if target.is_dir() else target.unlink()
                    for name in moved:
                        saved = backup / name
                        if saved.exists():
                            shutil.move(str(saved), str(app_root / name))
                    old = app_root / "Stream Translator.exe"
                    if old.exists():
                        subprocess.Popen([str(old)], cwd=app_root)
            except Exception as rollback:
                self.log.emit(f"回復失敗：{rollback}")
            self.failed.emit(str(exc))


class Window(QDialog):
    def __init__(self, plan=None, preview=False):
        super().__init__()
        self.setWindowTitle("Stream Translator 更新器")
        self.setMinimumSize(560, 390)
        self.setStyleSheet("QDialog{background:#0b1220;color:#e5e7eb} QLabel#title{font-size:22px;font-weight:700;color:#67e8f9} QLabel#status{font-size:14px;color:#cbd5e1} QProgressBar{height:14px;border:1px solid #334155;border-radius:7px;background:#111827;text-align:center} QProgressBar::chunk{border-radius:6px;background:#0891b2} QTextEdit{background:#070d18;border:1px solid #263449;border-radius:8px;color:#94a3b8;padding:8px} QPushButton{background:#155e75;color:white;border:0;border-radius:7px;padding:9px 18px;font-weight:600} QPushButton:disabled{background:#334155;color:#94a3b8}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(14)
        title = QLabel("Stream Translator 更新器")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addWidget(QLabel("更新前會備份設定；啟動失敗時會自動回復上一版本。"))
        self.status = QLabel("準備更新")
        self.status.setObjectName("status")
        layout.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        layout.addWidget(self.bar)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("更新進度會顯示在這裡")
        layout.addWidget(self.details, 1)
        row = QHBoxLayout()
        row.addStretch()
        self.close_btn = QPushButton("關閉")
        self.close_btn.setEnabled(False)
        self.close_btn.clicked.connect(self.accept)
        row.addWidget(self.close_btn)
        layout.addLayout(row)
        self.worker = Worker(Path(plan) if plan else Path(), preview)
        self.worker.progress.connect(self.on_progress)
        self.worker.log.connect(self.details.append)
        self.worker.completed.connect(self.done_ok)
        self.worker.failed.connect(self.done_fail)
        self.worker.start()

    def on_progress(self, value, message):
        self.bar.setValue(value)
        self.status.setText(message)

    def done_ok(self, message):
        self.status.setText(message)
        self.close_btn.setEnabled(True)

    def done_fail(self, message):
        self.status.setText("更新失敗；已嘗試回復上一版本")
        self.close_btn.setEnabled(True)
        QMessageBox.critical(self, "更新失敗", message)

    def closeEvent(self, event):
        event.accept() if self.close_btn.isEnabled() else event.ignore()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan")
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    preview = args.preview or not args.plan
    app = QApplication(sys.argv)
    app.setApplicationName("Stream Translator Updater")
    icon = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "app_icon.ico"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = Window(args.plan, preview)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
