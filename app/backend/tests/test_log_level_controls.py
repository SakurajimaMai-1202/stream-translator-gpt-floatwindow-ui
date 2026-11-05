"""Focused logging checks runnable with unittest, without Qt or the engine stack."""
import ast
import importlib.util
import io
import json
import logging
import math
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3]


def extract(relative, names, namespace, class_name=None):
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    body = tree.body
    if class_name:
        body = next(node.body for node in body if isinstance(node, ast.ClassDef) and node.name == class_name)
    nodes = [node for node in body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), relative, "exec"), namespace)
    return namespace


class LogLevelControlsTest(unittest.TestCase):
    def translator(self):
        return extract("app/backend/core/translator.py",
                       {"_SubtitleSummary", "_engine_stderr_level", "_write_engine_stderr"},
                       dict(logging=logging, logger=Mock(), math=math, threading=threading, time=time))

    def test_console_hosts(self):
        levels = SimpleNamespace(InfoMessageLevel=0, WarningMessageLevel=1, ErrorMessageLevel=2)
        for path, cls, method in [("app/windows.py", "CustomWebPage", "javaScriptConsoleMessage"),
                                  ("app/webview2_host.py", "WebView2Host", "_console")]:
            # Locate the owning class without importing native GUI dependencies.
            tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
            cls = next(n.name for n in tree.body if isinstance(n, ast.ClassDef)
                       and any(isinstance(m, ast.FunctionDef) and m.name == method for m in n.body))
            log = Mock()
            ns = extract(path, {method}, dict(logger=log, json=json, ui_perf=Mock(),
                         QWebEnginePage=SimpleNamespace(JavaScriptConsoleMessageLevel=levels)), cls)
            for value, expected in [("log", "debug"), ("info", "debug"), ("warning", "warning"),
                                    ("error", "error"), ("unknown", "debug")]:
                log.reset_mock()
                if method == "_console":
                    ns[method](None, None, SimpleNamespace(ParameterObjectAsJson=json.dumps({"type": value})))
                else:
                    ns[method](None, {"info": 0, "warning": 1, "error": 2}.get(value, 99), "text", 1, "")
                getattr(log, expected).assert_called_once()

    def test_stderr_live_gate(self):
        ns = self.translator()
        root = logging.getLogger()
        old = root.level
        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "stderr.log"
                root.setLevel(logging.INFO)
                ns["_write_engine_stderr"](path, "[DEBUG] hidden", "[DEBUG] hidden")
                self.assertFalse(path.exists())
                for line in ["[INFO] start", "[WARNING] warning", "[ERROR] failed", "Traceback:"]:
                    ns["_write_engine_stderr"](path, line, line)
                root.setLevel(logging.DEBUG)
                ns["_write_engine_stderr"](path, "[DEBUG] secret", "[DEBUG] redacted")
                root.setLevel(logging.INFO)
                ns["_write_engine_stderr"](path, "[DEBUG] hidden again", "hidden again")
                content = path.read_text(encoding="utf-8")
                self.assertIn("redacted", content)
                self.assertIn("Traceback:", content)
                self.assertNotIn("hidden", content)
        finally:
            root.setLevel(old)

    def test_summary_windows_and_final(self):
        ns = self.translator()
        now = [0.0]
        summary = ns["_SubtitleSummary"]("task-1", clock=lambda: now[0])
        summary.add({"total_latency_ms": 100, "asr_latency_ms": 10})
        now[0] = 59
        summary.add({"total_latency_ms": 200, "llm_latency_ms": 20,
                     "translation_queue_latency_ms": 5})
        ns["logger"].info.assert_not_called()
        now[0] = 60
        summary.add({})
        message = ns["logger"].info.call_args.args[1]
        self.assertIn("subtitles=2 total_ms p50=150.0 p95=195.0", message)
        self.assertIn("asr_ms p95=10.0 llm_ms p95=20.0 queue_ms p95=5.0", message)
        summary.finish()
        self.assertIn("final: subtitles=1 task_total=3", ns["logger"].info.call_args.args[1])
        summary.finish()
        self.assertEqual(ns["logger"].info.call_count, 2)
        empty = ns["_SubtitleSummary"]("empty", clock=lambda: now[0])
        now[0] = 180
        empty.add({})  # No empty periodic summary.
        self.assertEqual(ns["logger"].info.call_count, 2)
        empty.finish()
        zero = ns["_SubtitleSummary"]("zero")
        zero.finish()
        self.assertIn("final: subtitles=0 task_total=0", ns["logger"].info.call_args.args[1])

    def test_summary_counts_resent_subtitle_once(self):
        ns = self.translator()
        summary = ns["_SubtitleSummary"]("task-2")
        summary.add({"segment_id": 7, "original": "a"})
        summary.add({"segment_id": 7, "translated": "b", "total_latency_ms": 300})
        summary.add({"segment_id": 7, "translated": "b", "total_latency_ms": 900})
        summary.finish()
        message = ns["logger"].info.call_args.args[1]
        self.assertIn("final: subtitles=1 total_ms p50=300.0 p95=300.0", message)
        self.assertIn("task_total=1", message)

    def test_apply_levels_and_preserve_handlers(self):
        # Load the real module with only its settings dependency substituted.
        import sys
        spec = importlib.util.spec_from_file_location("logging_setup_under_test", ROOT / "app/backend/core/logging_setup.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"backend.config": SimpleNamespace(settings=SimpleNamespace())}):
            spec.loader.exec_module(module)
        root = logging.getLogger()
        old_handlers, old_level = root.handlers[:], root.level
        names = ("uvicorn", "uvicorn.error", "fastapi", "starlette", "py.warnings",
                 "uvicorn.access", "watchfiles", "asyncio", "httpx", "urllib3")
        old_named = {name: (logging.getLogger(name).level, logging.getLogger(name).handlers[:],
                            logging.getLogger(name).propagate) for name in names}
        root.handlers = []
        try:
            with tempfile.TemporaryDirectory() as directory, patch.object(module, "_install_exception_hook"), patch.object(logging, "captureWarnings"), patch.object(sys, "stdout", io.StringIO()), patch.object(sys, "stderr", io.StringIO()):
                config = Path(directory) / "config.yaml"
                with patch.object(module, "resolve_log_dir", return_value=Path(directory)):
                    config.write_text("general: {log_level: INFO}", encoding="utf-8")
                    module.configure_logging("test", config)
                    handlers = root.handlers[:]
                    for level in ("DEBUG", "INFO", "ERROR"):
                        config.write_text("general: {log_level: " + level + "}", encoding="utf-8")
                        module.apply_configured_log_level(config)
                        self.assertEqual(root.level, getattr(logging, level))
                        self.assertEqual(root.handlers, handlers)
                        self.assertTrue(all(h.level == root.level for h in handlers))
                        self.assertEqual(logging.getLogger("uvicorn.error").level, root.level)
                        self.assertEqual(logging.getLogger("uvicorn.access").level,
                                         logging.DEBUG if level == "DEBUG" else logging.WARNING)
                    module._close_handlers(root)
        finally:
            root.handlers = old_handlers
            root.setLevel(old_level)
            for name, (level, handlers, propagate) in old_named.items():
                target = logging.getLogger(name)
                target.setLevel(level)
                target.handlers, target.propagate = handlers, propagate

    def test_config_save_applies_only_after_success(self):
        manager = Mock(config_path=Path("config.yaml"))
        apply = Mock()
        ns = extract("app/backend/api/config.py", {"_write_config"},
                     dict(get_config_manager=lambda: manager, apply_configured_log_level=apply))
        for method in ("update_config", "replace_config", "reset_to_defaults"):
            ns["_write_config"](method, None if method == "reset_to_defaults" else {})
            apply.assert_called_with(manager.config_path)
        apply.reset_mock()
        manager.update_config.side_effect = ValueError("save failed")
        with self.assertRaises(ValueError):
            ns["_write_config"]("update_config", {})
        apply.assert_not_called()

    def test_gui_mtime_poll(self):
        config = Mock()
        config.stat.return_value.st_mtime_ns = 1
        apply = Mock()
        ns = extract("app/main.py", {"_refresh_log_level"},
                     dict(settings=SimpleNamespace(CONFIG_FILE=config),
                          apply_configured_log_level=apply, logger=Mock()), "UI2Application")
        instance = SimpleNamespace(_log_config_mtime=None)
        poll = ns["_refresh_log_level"]
        poll(instance)
        poll(instance)
        self.assertEqual(apply.call_count, 1)
        config.stat.return_value.st_mtime_ns = 2
        poll(instance)
        self.assertEqual(apply.call_count, 2)
        config.stat.side_effect = OSError("busy")
        poll(instance)
        self.assertEqual(instance._log_config_mtime, 2)

    def test_request_log_opt_in(self):
        path = ROOT / "stream-translator-gpt/stream_translator_gpt/request_log.py"
        spec = importlib.util.spec_from_file_location("request_log_under_test", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"STREAM_TRANSLATOR_LOG_DIR": directory}):
                target = Path(directory) / "translation_requests.jsonl"
                for value in (None, "0", "true"):
                    if value is None:
                        os.environ.pop("STREAM_TRANSLATOR_REQUEST_LOG", None)
                    else:
                        os.environ["STREAM_TRANSLATOR_REQUEST_LOG"] = value
                    module._write({"value": "hidden"})
                self.assertFalse(target.exists())
                os.environ["STREAM_TRANSLATOR_REQUEST_LOG"] = "1"
                module._write({"value": "visible"})
                os.environ["STREAM_TRANSLATOR_REQUEST_LOG"] = "0"
                module._write({"value": "hidden"})
                self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"value": "visible"})
                for handler in module._logger.handlers:
                    handler.close()
        finally:
            for handler in module._logger.handlers:
                handler.close()


if __name__ == "__main__":
    unittest.main()
