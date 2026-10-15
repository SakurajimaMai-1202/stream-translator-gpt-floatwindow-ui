import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from backend.core import model_identity


def _serve(routes):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = routes.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            payload = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture(autouse=True)
def _clear_cache():
    model_identity._cache.clear()
    yield
    model_identity._cache.clear()


def test_aliased_llama_server_reveals_index_family_from_gguf_path():
    server = _serve({
        "/props": {"model_path": "F:\\models\\Index-Translate-9B-Q4_K_M.gguf", "model_alias": "localllm"},
        "/v1/models": {"data": [{"id": "localllm"}]},
    })
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        names = model_identity.served_model_names(base_url)
        assert names[0] == "Index-Translate-9B-Q4_K_M.gguf"
        assert "localllm" in names
        family, matched = model_identity.detect_served_family(base_url, "", "openai_compatible")
        assert (family, matched) == ("index_translate", "Index-Translate-9B-Q4_K_M.gguf")
    finally:
        server.shutdown()


def test_generic_model_and_unreachable_server_report_no_family():
    server = _serve({"/v1/models": {"data": [{"id": "gemma-3-12b-it"}]}})
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        assert model_identity.detect_served_family(base_url, "", "openai_compatible") == ("", "")
    finally:
        server.shutdown()
    assert model_identity.served_model_names("http://127.0.0.1:9") == []


def test_custom_localllm_alias_runs_as_index_family(tmp_path):
    from backend.core.config_manager import ConfigManager

    server = _serve({"/props": {"model_path": "/models/Index-Translate-9B-Q4_K_M.gguf", "model_alias": "localllm"}})
    try:
        manager = ConfigManager(tmp_path / "settings.yaml")
        config = manager.get_config()
        config["translation"].update({
            "backend": "custom:localllm", "translation_model_family": "auto",
            "custom_models": [{"name": "localllm", "base_url": f"http://127.0.0.1:{server.server_port}",
                               "api_key": "114514", "model_name": "localllm"}],
        })
        args = manager.to_main_args(config)
        assert args["gpt_model"] == "localllm"
        assert args["translation_model_family"] == "index_translate"
    finally:
        server.shutdown()


def test_llama_backend_probes_llama_server_port_not_gpt_base_url(tmp_path):
    from backend.core.config_manager import ConfigManager

    server = _serve({"/props": {"model_path": r"F:\llm\models\Index-Translate-9B.i1-IQ4_XS.gguf"}})
    try:
        manager = ConfigManager(tmp_path / "settings.yaml")
        config = manager.get_config()
        config["translation"].update({"backend": "llama", "translation_model_family": "auto",
                                      "gpt_model": "localllm", "gpt_base_url": "http://127.0.0.1:9"})
        config["llama"].update({"host": "127.0.0.1", "port": server.server_port, "model_path": ""})
        assert manager.to_main_args(config)["translation_model_family"] == "index_translate"
    finally:
        server.shutdown()


def test_llama_backend_falls_back_to_selected_model_when_server_is_down(tmp_path):
    from backend.core.config_manager import ConfigManager

    manager = ConfigManager(tmp_path / "settings.yaml")
    config = manager.get_config()
    config["translation"].update({"backend": "llama", "translation_model_family": "auto", "gpt_model": "localllm"})
    config["llama"].update({"host": "127.0.0.1", "port": 9, "model_path": r"F:\llm\models\Hy-MT2-7B.i1-Q6_K.gguf"})
    assert manager.to_main_args(config)["translation_model_family"] == "hy_mt2"


def test_fresh_probe_sees_model_switch_on_same_address():
    routes = {"/props": {"model_path": "Hy-MT2-7B.i1-Q6_K.gguf"}}
    server = _serve(routes)
    try:
        base_url = f"http://127.0.0.1:{server.server_port}"
        assert model_identity.detect_served_family(base_url, "", "openai_compatible")[0] == "hy_mt2"
        routes["/props"] = {"model_path": "Index-Translate-9B.i1-IQ4_XS.gguf"}
        assert model_identity.served_model_names(base_url, use_cache=False) == ["Index-Translate-9B.i1-IQ4_XS.gguf"]
        assert model_identity.detect_served_family(base_url, "", "openai_compatible")[0] == "index_translate"
    finally:
        server.shutdown()
