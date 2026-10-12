import logging
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
if str(APP_DIR) not in sys.path:
    sys.path.append(str(APP_DIR))

from backend.core import logging_setup


def _flush_root_handlers():
    for handler in logging.getLogger().handlers:
        handler.flush()


def _reset_root_logger_state():
    logging_setup._close_handlers(logging.getLogger())
    logging_setup._RESETTED_LOG_FILES.clear()


def test_configure_logging_clears_existing_log_and_backups(monkeypatch, tmp_path):
    monkeypatch.setattr(logging_setup, "resolve_log_dir", lambda: tmp_path)
    _reset_root_logger_state()

    current_log = tmp_path / "backend.log"
    backup_log = tmp_path / "backend.log.1"
    current_log.write_text("old backend log\n", encoding="utf-8")
    backup_log.write_text("old backup\n", encoding="utf-8")

    log_file = logging_setup.configure_logging("backend", console=False)
    logging.getLogger("test.logging").info("fresh backend log")
    _flush_root_handlers()

    assert log_file == current_log
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "fresh backend log" in content
    assert "old backend log" not in content
    assert not backup_log.exists()

    _reset_root_logger_state()


def test_configure_logging_clears_extra_log_files(monkeypatch, tmp_path):
    monkeypatch.setattr(logging_setup, "resolve_log_dir", lambda: tmp_path)
    _reset_root_logger_state()

    stderr_log = tmp_path / "translator_stderr.log"
    stderr_backup = tmp_path / "translator_stderr.log.1"
    stderr_log.write_text("old stderr\n", encoding="utf-8")
    stderr_backup.write_text("old stderr backup\n", encoding="utf-8")

    logging_setup.configure_logging(
        "backend",
        console=False,
        reset_log_names=["translator_stderr"],
    )

    with open(stderr_log, "a", encoding="utf-8") as handle:
        handle.write("new stderr\n")

    assert stderr_log.read_text(encoding="utf-8") == "new stderr\n"
    assert not stderr_backup.exists()

    _reset_root_logger_state()
