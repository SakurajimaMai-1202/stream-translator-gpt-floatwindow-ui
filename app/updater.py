"""Standalone, rollback-capable GUI updater for Stream Translator."""
from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import tempfile
from pathlib import Path
from manual_update import prepare_package

import yaml
from update_runtime_contract import read_update_json, validate_update_schema, validate_update_runtime
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QTextEdit, QVBoxLayout

logger = logging.getLogger(__name__)


ALLOWED = {
    "app-update-build.json", "StreamTranslatorUpdater.exe",
    "PORTABLE_GUIDE_zh-TW.txt", "Stream Translator.exe",
    "UPDATE_NOTES_zh-TW.txt", "_internal", "_js_runtime", "_runtime",
}
UPDATE_MODES = {"app_only", "runtime_replace"}


class Worker(QThread):
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, plan_path: Path, preview: bool = False, recovery_root: Path | None = None):
        super().__init__()
        self.plan_path = plan_path
        self.preview = preview
        self.recovery_root = recovery_root

    def step(self, value: int, message: str) -> None:
        self.progress.emit(value, message)
        self.log.emit(message)

    @staticmethod
    def process_exists(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            # os.kill(pid, 0) is not a harmless existence probe on Windows:
            # CPython maps unsupported signals to TerminateProcess.  Query a
            # limited process handle instead, without requesting termination
            # rights or changing the target process.
            process_query_limited_information = 0x1000
            still_active = 259
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            kernel32.GetExitCodeProcess.restype = ctypes.c_int
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.restype = ctypes.c_int
            handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and exit_code.value == still_active
            finally:
                kernel32.CloseHandle(handle)
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def wait_for_processes(self, pids: list[int], timeout: float = 45.0) -> None:
        pending = {pid for pid in pids if pid > 0}
        deadline = time.monotonic() + timeout
        while pending and time.monotonic() < deadline:
            pending = {pid for pid in pending if self.process_exists(pid)}
            if pending:
                time.sleep(0.25)
        if pending:
            raise RuntimeError(f"主程式或後端未在期限內關閉（PID: {', '.join(map(str, sorted(pending))) }）")
        # Process exit and Windows image-section release are not always
        # observed at exactly the same instant.  Give loaded .pyd/DLL files a
        # short grace period before the first atomic directory rename.
        time.sleep(0.5)

    def wait_for_runtime_processes(self, app_root: Path, timeout: float = 45.0) -> None:
        runtime = app_root / "_runtime"
        deadline = time.monotonic() + timeout
        while True:
            pending = installation_processes(runtime)
            if not pending:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Runtime processes did not exit within {timeout:g}s: {runtime} (PID: {', '.join(map(str, pending))})")
            time.sleep(0.25)

    @staticmethod
    def cleanup_success(app_root: Path, staging: Path) -> None:
        """Remove only updater-owned scratch data after the success commit."""
        root = app_root.resolve() / ".app-update"
        if root.resolve() != root:
            raise RuntimeError("Update cleanup directory points outside the installation")
        staging = staging.resolve()
        candidates = [root / "downloads"]
        if staging.parent == root and staging.name.startswith("staging"):
            candidates.append(staging)
        elif staging.name == "staging" and staging.parent.parent == root and staging.parent.name.startswith("manual-"):
            candidates.append(staging.parent)
        else:
            raise RuntimeError("Invalid update cleanup staging path")
        for path in candidates:
            if path.resolve().parent != root or path.is_symlink():
                raise RuntimeError(f"Unsafe update cleanup path: {path}")
            if path.exists():
                shutil.rmtree(path)

    @staticmethod
    def rename_with_retry(source: Path, destination: Path, timeout: float = 30.0) -> None:
        """Atomically rename an update item without shutil.move's copy fallback."""
        deadline = time.monotonic() + timeout
        while True:
            try:
                os.replace(source, destination)
                return
            except PermissionError as exc:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"檔案仍被其他程序使用，無法移動：{source}") from exc
                time.sleep(0.25)

    @staticmethod
    def remove_with_retry(path: Path, timeout: float = 30.0) -> None:
        deadline = time.monotonic() + timeout
        while path.exists():
            try:
                shutil.rmtree(path) if path.is_dir() else path.unlink()
                return
            except PermissionError as exc:
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"檔案仍被其他程序使用，無法移除：{path}") from exc
                time.sleep(0.25)

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
        plan = read_update_json(plan_path)
        validate_update_schema(plan)
        app_root = Path(plan["app_root"]).resolve()
        staging = Path(plan["staging"]).resolve()
        if plan.get("schema") not in {1, 2} or app_root == Path(app_root.anchor) or app_root / ".app-update" not in staging.parents:
            raise RuntimeError("更新計畫的路徑或格式無效")
        manifest = read_update_json(staging / "app-update-build.json")
        schema = validate_update_schema(manifest)
        if schema == 1 and (staging / "_runtime").exists():
            raise RuntimeError("Legacy update package contains an unsafe partial _runtime; use the Full package")
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
            runtime_info = read_update_json(runtime_manifest)
            if str(runtime_info.get("profile") or "").lower() != str(plan.get("profile") or "").lower():
                raise RuntimeError("替換 Runtime 的 Profile 不相符")
        validate_update_runtime(manifest, runtime if mode == "runtime_replace" else app_root / "_runtime")
        return plan, manifest, app_root, staging, items, mode

    @staticmethod
    def write_journal(app_root: Path, journal: dict) -> None:
        path = app_root / ".app-update" / "apply-journal.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(journal, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)

    @staticmethod
    def pending_journal(app_root: Path) -> dict | None:
        path = app_root / ".app-update" / "apply-journal.json"
        if not path.exists():
            return None
        journal = read_update_json(path)
        return journal if journal.get("status") in {"applying", "rollback_failed"} else None

    @staticmethod
    def reconcile_journal(app_root: Path, journal: dict) -> None:
        pending = journal.get("pending")
        if not pending:
            return
        action, name = pending["action"], pending["name"]
        if name not in ALLOWED:
            raise RuntimeError("回復紀錄包含不允許的項目")
        saved = Path(journal["backup"]) / name
        target = app_root / name
        if action == "move" and saved.exists():
            if name not in journal["moved"]:
                journal["moved"].append(name)
        elif action == "install" and target.exists():
            if name not in journal["installed"]:
                journal["installed"].append(name)
        elif action == "remove" and not target.exists():
            if name in journal["installed"]:
                journal["installed"].remove(name)
        elif action == "restore" and not saved.exists() and target.exists():
            if name in journal["moved"]:
                journal["moved"].remove(name)
        journal.pop("pending", None)
        Worker.write_journal(app_root, journal)

    @staticmethod
    def apply_item(app_root: Path, item: Path, journal: dict) -> None:
        target = app_root / item.name
        if target.exists():
            journal["pending"] = {"action": "move", "name": item.name}
            Worker.write_journal(app_root, journal)
            Worker.rename_with_retry(target, Path(journal["backup"]) / item.name)
            journal["moved"].append(item.name)
            journal.pop("pending")
            Worker.write_journal(app_root, journal)
        journal["pending"] = {"action": "install", "name": item.name}
        Worker.write_journal(app_root, journal)
        Worker.rename_with_retry(item, target)
        journal["installed"].append(item.name)
        journal.pop("pending")
        Worker.write_journal(app_root, journal)

    @staticmethod
    def rollback(app_root: Path, journal: dict) -> list[str]:
        errors = []
        backup = Path(journal["backup"])
        try:
            if not backup.is_dir():
                raise RuntimeError(f"備份目錄不存在；未刪除任何檔案：{backup}")
            if backup.resolve().parent != app_root.resolve().parent or not backup.name.startswith(".stream-translator-backup-"):
                raise RuntimeError(f"備份路徑無效：{backup}")
            if any(name not in ALLOWED for name in journal["installed"] + journal["moved"]):
                raise RuntimeError("回復紀錄包含不允許的項目")
            Worker.reconcile_journal(app_root, journal)
            for action, key in [("remove", "installed"), ("restore", "moved")]:
                for name in reversed(journal[key][:]):
                    target = app_root / name
                    try:
                        if action == "restore" and (target.exists() or not (backup / name).exists()):
                            raise RuntimeError(f"無法回復：備份項目遺失或目標仍存在：{name}")
                        journal["pending"] = {"action": action, "name": name}
                        Worker.write_journal(app_root, journal)
                        if action == "remove":
                            Worker.remove_with_retry(target)
                        else:
                            if target.exists():
                                raise RuntimeError(f"回復目標仍存在：{target}")
                            Worker.rename_with_retry(backup / name, target)
                        journal[key].remove(name)
                        journal.pop("pending", None)
                        Worker.write_journal(app_root, journal)
                    except Exception as exc:
                        errors.append(f"{name}：{exc}")
                        Worker.reconcile_journal(app_root, journal)
        except Exception as exc:
            errors.append(str(exc))
        journal["status"] = "rollback_failed" if errors else "rolled_back"
        journal["errors"] = errors[:]
        try:
            Worker.write_journal(app_root, journal)
        except Exception as exc:
            errors.append(f"無法寫入回復紀錄：{exc}")
        return errors

    def report_failure(self, message: str, app_root: Path, journal: dict | None, errors: list[str]) -> None:
        if errors:
            detail = ("更新失敗；回復未完成\n" + "；".join(errors) +
                      f"\n程式備份：{journal.get('backup', '未建立') if journal else '未建立'}" +
                      f"\n使用者設定備份：{journal.get('user_backup', '未建立') if journal else '未建立'}" +
                      f"\n請關閉主程式，將程式備份中的資料夾與檔案複製回安裝目錄：{app_root}。" +
                      "\n如需還原設定，將使用者設定備份的 config.yaml 與 cookies 資料夾複製回安裝目錄；外部 Cookies 請複製回原設定路徑。")
        elif journal:
            detail = "更新失敗；上一版本已回復並重新啟動"
        else:
            detail = "更新失敗；尚未套用更新"
        self.log.emit(detail)
        self.failed.emit(message + "\n" + detail)

    def recover(self, app_root: Path) -> bool:
        journal = self.pending_journal(app_root)
        if journal is None:
            return False
        self.step(8, "偵測到中斷的更新；正在回復上一版本，暫停新更新")
        errors = []
        try:
            self.wait_for_processes(installation_processes(app_root))
            self.wait_for_runtime_processes(app_root)
            errors = self.rollback(app_root, journal)
            if not errors:
                subprocess.Popen([str(app_root / "Stream Translator.exe")], cwd=app_root)
        except Exception as exc:
            errors.append(str(exc))
        if errors:
            self.report_failure("中斷的更新需要回復", app_root, journal, errors)
        else:
            self.completed.emit("上一版本已回復並重新啟動；請重新準備更新包")
        return True

    def run(self) -> None:
        if self.preview:
            for value, message in [(8, "等待主程式結束"), (18, "備份使用者設定"), (35, "驗證更新套件"), (60, "套用更新"), (82, "啟動健康檢查"), (100, "更新完成")]:
                self.step(value, message)
                time.sleep(0.7)
            self.completed.emit("預覽完成；未修改任何檔案")
            return
        backup = None
        proc = None
        journal = None
        items: list[Path] = []
        app_root = None
        try:
            if self.recovery_root is not None:
                app_root = self.recovery_root.resolve()
                self.recover(app_root)
                return
            raw_plan = read_update_json(self.plan_path)
            app_root = Path(raw_plan["app_root"]).resolve()
            if self.recover(app_root):
                return
            plan, _manifest, app_root, _staging, items, mode = self.validate_plan(self.plan_path)
            self.step(8, "等待 Stream Translator 與後端完全關閉")
            process_ids = [int(plan.get("parent_pid") or 0), int(plan.get("backend_pid") or 0)]
            self.wait_for_processes(process_ids)
            self.wait_for_runtime_processes(app_root)
            self.step(18, "備份 config、術語、ASR 修正與 Cookies")
            user_backup = self.backup_user_settings(app_root, str(plan["version"]))
            self.log.emit(f"使用者設定備份：{user_backup}")
            self.step(30, f"準備 {mode} 回復點")
            backup = app_root.parent / f".stream-translator-backup-{plan['version']}-{int(time.time())}"
            backup.mkdir()
            journal = {"status": "applying", "version": str(plan["version"]), "update_mode": mode,
                       "backup": str(backup), "user_backup": str(user_backup), "moved": [], "installed": [],
                       "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
            self.write_journal(app_root, journal)
            apply_label = "套用程式更新（保留 Runtime）" if mode == "app_only" else "套用程式與 Runtime 更新"
            self.step(52, apply_label)
            for item in items:
                self.apply_item(app_root, item, journal)
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
            journal["status"] = "completed"
            self.write_journal(app_root, journal)
            # Cleanup errors cannot turn a committed update into a rollback.
            try:
                self.cleanup_success(app_root, _staging)
            except Exception as cleanup_exc:
                self.log.emit(f"Update succeeded; temporary files could not be removed: {cleanup_exc}")
            self.step(100, "更新完成，Stream Translator 已重新啟動")
            self.completed.emit(f"已更新至 v{plan['version']}")
        except Exception as exc:
            logger.debug("套用更新失敗，準備回復", exc_info=True)
            self.log.emit(f"更新失敗：{exc}\n正在回復上一版本")
            rollback_errors = []
            try:
                if proc is not None and proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=30)
                if journal:
                    try:
                        self.wait_for_runtime_processes(app_root)
                    except Exception as wait_exc:
                        logger.warning("Runtime wait failed before rollback: %s", wait_exc)
                        self.log.emit(f"Runtime wait failed; attempting rollback anyway: {wait_exc}")
                    rollback_errors = self.rollback(app_root, journal)
            except Exception as rollback_exc:
                rollback_errors.append(str(rollback_exc))
                if journal:
                    journal["status"] = "rollback_failed"
                    journal["errors"] = rollback_errors[:]
                    try:
                        self.write_journal(app_root, journal)
                    except Exception as journal_exc:
                        rollback_errors.append(str(journal_exc))
            if journal and not rollback_errors:
                try:
                    subprocess.Popen([str(app_root / "Stream Translator.exe")], cwd=app_root)
                except Exception as restart:
                    rollback_errors.append(f"上一版本已回復，但重新啟動失敗：{restart}")
            self.report_failure(str(exc), app_root, journal, rollback_errors)


class PrepareWorker(QThread):
    progress = pyqtSignal(int, str)
    ready = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, package, installation):
        super().__init__()
        self.package, self.installation = Path(package), Path(installation)

    def run(self):
        plan = None
        try:
            plan = prepare_package(self.package, self.installation, ALLOWED, self.progress.emit)
            Worker.validate_plan(plan)
            self.ready.emit(str(plan))
        except Exception as exc:
            logger.debug("準備手動更新失敗", exc_info=True)
            if plan is not None:
                work = plan.parent.resolve()
                expected = (self.installation.resolve() / ".app-update").resolve()
                if work.parent == expected and work.name.startswith("manual-"):
                    shutil.rmtree(work)
            self.failed.emit(str(exc))


def installation_processes(root: Path) -> list[int]:
    """Query process image paths without terminating any process."""
    if os.name != "nt":
        return []
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    ids = (wintypes.DWORD * 65536)()
    needed = wintypes.DWORD()
    if not psapi.EnumProcesses(ids, ctypes.sizeof(ids), ctypes.byref(needed)):
        raise RuntimeError("無法確認主程式是否已關閉")
    found = []
    for pid in ids[:needed.value // ctypes.sizeof(wintypes.DWORD)]:
        if pid == os.getpid():
            continue
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            continue
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                if root.resolve() in Path(buffer.value).resolve().parents:
                    found.append(pid)
        finally:
            kernel.CloseHandle(handle)
    return found


class Window(QDialog):
    def __init__(self, plan=None, preview=False, package="", installation=""):
        super().__init__()
        self.setWindowTitle("Stream Translator 更新器")
        self.setMinimumSize(560, 390)
        self.setStyleSheet("QDialog{background:#0b1220;color:#e5e7eb} QLabel#title{font-size:22px;font-weight:700;color:#67e8f9} QLabel#status{font-size:14px;color:#cbd5e1} QProgressBar{height:14px;border:1px solid #334155;border-radius:7px;background:#111827;text-align:center} QProgressBar::chunk{border-radius:6px;background:#0891b2} QTextEdit{background:#070d18;border:1px solid #263449;border-radius:8px;color:#94a3b8;padding:8px} QPushButton{background:#155e75;color:white;border:0;border-radius:7px;padding:9px 18px;font-weight:600} QPushButton:disabled{background:#334155;color:#94a3b8}")
        self.setStyleSheet(self.styleSheet() + " QLabel{color:#cbd5e1} QLineEdit{background:#111827;color:#e5e7eb;border:1px solid #334155;border-radius:6px;padding:8px} QProgressBar{color:#e5e7eb}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(14)
        title = QLabel("Stream Translator 更新器")
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addWidget(QLabel("更新前會備份設定；啟動失敗時會自動回復上一版本。"))
        self.manual = not plan and not preview
        self.plan = None
        self.worker = None
        self.preparer = None
        self.manual_controls = []
        if self.manual:
            hint = QLabel("選取 App Update ZIP 或 .zip.part01；所有分割檔需放在同一資料夾。\n建議將同版本的 SHA256SUMS 清單放在更新包旁。套用前請關閉主程式。")
            hint.setWordWrap(True)
            layout.addWidget(hint)
            self.package_edit = QLineEdit(package)
            self.install_edit = QLineEdit(installation)
            for label, field, directory in [("更新包", self.package_edit, False), ("安裝目錄", self.install_edit, True)]:
                layout.addWidget(QLabel(label))
                selection = QHBoxLayout()
                selection.addWidget(field)
                button = QPushButton("選取")
                button.clicked.connect(lambda _=False, f=field, d=directory: self.select_path(f, d))
                selection.addWidget(button)
                layout.addLayout(selection)
                self.manual_controls.extend([field, button])
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
        if self.manual:
            self.start_btn = QPushButton("驗證更新包")
            self.start_btn.clicked.connect(self.prepare_or_apply)
            row.addWidget(self.start_btn)
        self.close_btn = QPushButton("關閉")
        self.close_btn.setEnabled(self.manual)
        self.close_btn.clicked.connect(self.accept)
        row.addWidget(self.close_btn)
        layout.addLayout(row)
        if plan or preview:
            self.start_worker(plan, preview)
        elif installation:
            self.start_recovery(Path(installation))

    def select_path(self, field, directory):
        if directory:
            path = QFileDialog.getExistingDirectory(self, "選取安裝目錄", field.text())
        else:
            path, _ = QFileDialog.getOpenFileName(self, "選取更新包", field.text(), "更新包 (*.zip *.zip.part01)")
        if path:
            field.setText(path)

    def start_recovery(self, root):
        try:
            pending = Worker.pending_journal(root)
        except Exception:
            pending = True  # Let the worker report an unreadable journal; block new updates.
        if not pending:
            return False
        self.start_btn.setEnabled(False)
        self.close_btn.setEnabled(False)
        for control in self.manual_controls:
            control.setEnabled(False)
        self.start_worker(recovery_root=root)
        return True

    def prepare_or_apply(self):
        if self.install_edit.text().strip() and self.start_recovery(Path(self.install_edit.text().strip())):
            return
        if self.plan:
            root = Path(read_update_json(Path(self.plan))["app_root"])
            try:
                running = installation_processes(root)
                if running:
                    raise RuntimeError("請先關閉主程式與後端，再按套用更新（PID：" + ", ".join(map(str, running)) + "）")
            except Exception as exc:
                logger.debug("更新前程序檢查失敗", exc_info=True)
                QMessageBox.warning(self, "尚未套用", str(exc))
                return
            self.start_btn.setEnabled(False)
            self.close_btn.setEnabled(False)
            self.start_worker(self.plan)
            return
        if not self.package_edit.text().strip() or not self.install_edit.text().strip():
            QMessageBox.warning(self, "請選取檔案與目錄", "請選取更新包及安裝目錄")
            return
        self.start_btn.setEnabled(False)
        self.close_btn.setEnabled(False)
        for control in self.manual_controls:
            control.setEnabled(False)
        self.preparer = PrepareWorker(self.package_edit.text().strip(), self.install_edit.text().strip())
        self.preparer.progress.connect(self.on_prepare_progress)
        self.preparer.ready.connect(self.prepared)
        self.preparer.failed.connect(self.prepare_failed)
        self.preparer.start()

    def on_prepare_progress(self, value, message):
        if self.status.text() != message:
            self.details.append(message)
        self.on_progress(value, message)

    def prepared(self, plan):
        self.plan = plan
        info = read_update_json(Path(plan))
        self.status.setText(f"可更新至 v{info['version']}（{info['profile']}）")
        self.details.append("更新目錄：" + info["app_root"])
        self.start_btn.setText("套用更新")
        self.start_btn.setEnabled(True)
        self.close_btn.setEnabled(True)

    def prepare_failed(self, message):
        self.status.setText("更新包驗證失敗；尚未套用")
        self.details.append(message)
        self.start_btn.setEnabled(True)
        self.close_btn.setEnabled(True)
        for control in self.manual_controls:
            control.setEnabled(True)
        QMessageBox.critical(self, "更新包驗證失敗", message)

    def start_worker(self, plan=None, preview=False, recovery_root=None):
        self.worker = Worker(Path(plan) if plan else Path(), preview, recovery_root)
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
        self.status.setText(message)
        self.status.setWordWrap(True)
        self.close_btn.setEnabled(True)
        QMessageBox.critical(self, "更新失敗", message)

    def closeEvent(self, event):
        event.accept() if self.close_btn.isEnabled() else event.ignore()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--health-check", action="store_true")
    parser.add_argument("--package", default="", help="Local App Update ZIP or .zip.part01")
    parser.add_argument("--install-dir", default="", help="Existing installation directory")
    parser.add_argument("--local-session", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.health_check:
        return 0
    if not args.plan and not args.preview and getattr(sys, "frozen", False) and not args.local_session:
        # Keep the running updater outside the installation it will replace.
        destination = Path(tempfile.mkdtemp(prefix="StreamTranslatorManualUpdater-")) / "StreamTranslatorUpdater.exe"
        shutil.copy2(sys.executable, destination)
        subprocess.Popen([str(destination), "--local-session", "--package", args.package,
                          "--install-dir", args.install_dir or str(Path(sys.executable).parent)])
        return 0
    preview = args.preview
    app = QApplication(sys.argv)
    app.setApplicationName("Stream Translator Updater")
    icon = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / "app_icon.ico"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
    window = Window(args.plan, preview, args.package, args.install_dir)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
