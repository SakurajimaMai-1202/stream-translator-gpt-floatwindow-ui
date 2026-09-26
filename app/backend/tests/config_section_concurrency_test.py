import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event

import pytest
from starlette.requests import Request

from backend.api import config as config_api
from backend.core.config_manager import ConfigManager


@pytest.mark.parametrize("existing_lock_byte", [False, True])
def test_terminology_save_waits_for_another_writer(tmp_path, monkeypatch, existing_lock_byte):
    path = tmp_path / "config.yaml"
    holder = ConfigManager(path)
    writer = ConfigManager(path)
    if existing_lock_byte:
        path.with_suffix(".yaml.lock").write_bytes(b"0")
    monkeypatch.setattr(config_api, "_config_manager_instance", writer)
    started = Event()
    terminology = {
        "use_terminology_glossary": True,
        "glossary_list": [{"original": "すいちゃん", "translated": "星街"}],
    }

    def save():
        started.set()
        return asyncio.run(config_api.update_section(
            "terminology", terminology,
            Request({"type": "http", "headers": []}),
        ))

    with ThreadPoolExecutor(max_workers=1) as pool:
        with holder._config_lock():
            pending = pool.submit(save)
            assert started.wait(5)
            # A contending writer must wait, not fail while reading a locked byte.
            with pytest.raises(TimeoutError):
                pending.result(timeout=0.2)
            current = holder._read_current_config()
            current["general"]["log_level"] = "DEBUG"
            holder._save(current)
        result = pending.result(timeout=10)

    assert result["success"] is True
    assert result["data"]["glossary_list"] == terminology["glossary_list"]
    reloaded = ConfigManager(path).get_config()
    assert reloaded["terminology"]["use_terminology_glossary"] is True
    assert reloaded["terminology"]["glossary_list"] == terminology["glossary_list"]
    assert reloaded["general"]["log_level"] == "DEBUG"
