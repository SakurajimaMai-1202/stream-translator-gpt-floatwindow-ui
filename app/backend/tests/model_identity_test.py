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
        family, matched = model_identity.detect_served_family(base_url, "", "openai_compatible", "localllm")
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


@pytest.mark.parametrize("entries,configured,expected", [
    ([{"id": "Qwen3-8B"}, {"id": "Hy-MT2-7B"}], "qwen3-8b", ""),
    ([{"id": "Qwen3-8B", "aliases": ["Hy-MT2-7B"]}, {"id": "other"}], "Qwen3-8B", ""),
    ([{"id": "Hy-MT2-7B"}], "localllm", "hy_mt2"),
    ([{"id": "Qwen3-8B"}, {"id": "Hy-MT2-7B"}], "hy-mt2-7b", "hy_mt2"),
])
def test_models_list_only_trusts_configured_name_or_single_entry(entries, configured, expected):
    server = _serve({"/v1/models": {"data": entries}})
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        family, _ = model_identity.detect_served_family(url, "", "openai_compatible", configured)
        assert family == expected
    finally:
        server.shutdown()


def test_cached_names_are_scoped_to_configured_model():
    server = _serve({"/v1/models": {"data": [{"id": "Hy-MT2-7B"}, {"id": "Qwen3-8B"}]}})
    try:
        url = f"http://127.0.0.1:{server.server_port}"
        assert model_identity.detect_served_family(url, "", "openai_compatible", "Hy-MT2-7B")[0] == "hy_mt2"
        assert model_identity.detect_served_family(url, "", "openai_compatible", "Qwen3-8B") == ("", "")
    finally:
        server.shutdown()


def test_custom_qwen_does_not_inherit_another_loaded_models_family(tmp_path):
    from backend.core.config_manager import ConfigManager
    from stream_translator_gpt.translation_policy import resolve_model_family

    server = _serve({"/v1/models": {"data": [{"id": "Qwen3-8B"}, {"id": "Hy-MT2-7B"}]}})
    try:
        manager = ConfigManager(tmp_path / "settings.yaml")
        config = manager.get_config()
        config["translation"].update({
            "backend": "custom:studio", "translation_model_family": "auto",
            "custom_models": [{"name": "studio", "model_name": "qwen3-8b",
                               "base_url": f"http://127.0.0.1:{server.server_port}/v1"}],
        })
        args = manager.to_main_args(config)
        assert resolve_model_family(args.get("translation_model_family"), args["gpt_model"],
                                    args["translation_provider"]) != "hy_mt2"
    finally:
        server.shutdown()


@pytest.mark.parametrize("url", ["https://models.example/v1", "http://192.168.1.10:8080/v1"])
@pytest.mark.parametrize("model", ["Qwen3-8B", "Hy-MT2-7B"])
def test_remote_custom_endpoint_never_probes(tmp_path, monkeypatch, url, model):
    from backend.core.config_manager import ConfigManager
    from stream_translator_gpt.translation_policy import resolve_model_family

    monkeypatch.setattr(model_identity.httpx, "Client", lambda *a, **kw: pytest.fail("remote HTTP probe"))
    manager = ConfigManager(tmp_path / "settings.yaml")
    config = manager.get_config()
    config["translation"].update({
        "backend": "custom:remote", "translation_model_family": "auto",
        "custom_models": [{"name": "remote", "base_url": url, "model_name": model}],
    })
    args = manager.to_main_args(config)
    family = resolve_model_family(args.get("translation_model_family"), args["gpt_model"], args["translation_provider"])
    assert (family == "hy_mt2") == (model == "Hy-MT2-7B")


@pytest.mark.parametrize("url,expected", [
    ("http://127.0.0.1:8080/v1", True), ("http://[::1]:8080", True),
    ("http://LOCALHOST:8080", True), ("https://localhost.example/v1", False),
    ("http://127.0.0.1@example.com", False),
])
def test_loopback_probe_host(url, expected):
    assert model_identity.is_loopback_probe(url) is expected


def test_llama_server_bound_to_all_interfaces_is_probed_through_loopback():
    from backend.core.model_identity import family_probe_target, is_loopback_probe

    url, fallback = family_probe_target(
        "llama", {"llama": {"host": "0.0.0.0", "port": 8081, "model_path": r"D:\m\Hy-MT2-7B-Q4_K_M.gguf"}}, {})

    assert url == "http://127.0.0.1:8081"
    assert is_loopback_probe(url)
    assert fallback == "Hy-MT2-7B-Q4_K_M.gguf"
