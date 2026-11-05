import logging
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[2]
if str(APP_DIR) not in sys.path:
    sys.path.append(str(APP_DIR))

from backend.core import logging_setup


def test_console_reconfigures_locale_pipe_to_utf8(monkeypatch, tmp_path):
    import io
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    reset_files = logging_setup._RESETTED_LOG_FILES.copy()
    exception_hook = sys.excepthook
    named_state = {name: (logger.handlers[:], logger.level, logger.propagate)
                   for name, logger in logging.Logger.manager.loggerDict.items()
                   if isinstance(logger, logging.Logger)}
    warning_hook = __import__("warnings").showwarning
    logging_warning_hook = logging._warnings_showwarning
    stream = io.TextIOWrapper(io.BytesIO(), encoding="cp950")
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="cp950")
    monkeypatch.setenv("STREAM_TRANSLATOR_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(sys, "stderr", stream)
    monkeypatch.setattr(sys, "stdout", stdout)
    root.handlers = []  # configure_logging must not close the test runner's handlers.
    try:
        logging_setup.configure_logging("backend", console=True)
        root.warning("繁體中文翻譯")
        _flush_root_handlers()
        assert "繁體中文翻譯".encode("utf-8") in stream.buffer.getvalue()
        assert stream.encoding == stdout.encoding == "utf-8"
    finally:
        logging_setup._close_handlers(root)
        root.handlers = handlers
        root.setLevel(level)
        logging_setup._RESETTED_LOG_FILES.clear()
        logging_setup._RESETTED_LOG_FILES.update(reset_files)
        sys.excepthook = exception_hook
        __import__("warnings").showwarning = warning_hook
        logging._warnings_showwarning = logging_warning_hook
        for name, logger in logging.Logger.manager.loggerDict.items():
            if isinstance(logger, logging.Logger):
                logger.handlers, logger.level, logger.propagate = named_state.get(name, ([], logging.NOTSET, True))


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


def test_backend_relay_levels_and_frontend_unchanged(caplog):
    # Exercise the relay functions without requiring a Qt GUI installation.
    import ast
    import re
    source = ast.parse((APP_DIR / 'services.py').read_text(encoding='utf-8'))
    functions = [node for node in source.body if isinstance(node, ast.FunctionDef)
                 and node.name in {'_classify_process_log_level', '_log_subprocess_output'}]
    relay_logger = logging.getLogger('test.services.relay')
    namespace = {'logging': logging, 're': re, 'logger': relay_logger}
    exec(compile(ast.Module(body=functions, type_ignores=[]), 'services.py', 'exec'), namespace)
    relay = namespace['_log_subprocess_output']
    cases = [
        ('Backend', '2026-11-05 12:34:56,789 [INFO] backend: error count 0', logging.INFO, logging.DEBUG),
        ('Backend', '[DEBUG] warning details', logging.WARNING, logging.WARNING),
        ('Backend', '[INFO] Error initializing CUDA', logging.INFO, logging.ERROR),
        ('Backend', '2026-11-05 12:34:56,789 [INFO] Error initializing CUDA', logging.INFO, logging.DEBUG),
        ('Backend', 'message contains [INFO] Error initializing CUDA', logging.INFO, logging.ERROR),
        ('Backend', '  INFO: server ready', logging.WARNING, logging.DEBUG),
        ('Backend', '[WARNING] slow', logging.INFO, logging.WARNING),
        ('Backend', '[ERROR] failed', logging.INFO, logging.ERROR),
        ('Backend', '2026-11-05 12:34:56,789 [CRITICAL] failed', logging.INFO, logging.CRITICAL),
        ('Backend', 'INFO: server ready', logging.WARNING, logging.DEBUG),
        ('Backend', 'Traceback (most recent call last):', logging.INFO, logging.ERROR),
        ('Backend', 'startup crash text', logging.INFO, logging.WARNING),
        ('Frontend', 'INFO ready', logging.WARNING, logging.INFO),
        ('Frontend', 'warning: slow', logging.INFO, logging.WARNING),
        ('Frontend', 'plain text', logging.INFO, logging.INFO),
    ]
    with caplog.at_level(logging.DEBUG, logger=relay_logger.name):
        for prefix, line, default, expected in cases:
            relay(prefix, line, default)
            assert caplog.records[-1].levelno == expected
