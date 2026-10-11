import asyncio
from threading import Event, get_ident

from starlette.requests import Request

from backend.api import config as config_api


def test_full_config_disk_save_leaves_event_loop_responsive(monkeypatch):
    async def scenario():
        loop = asyncio.get_running_loop()
        loop_thread = get_ident()
        save_started = asyncio.Event()
        release_save = Event()
        saved_updates = []
        published_events = []
        updated_config = {"translation": {"backend": "gpt"}, "general": {"language": "zh-TW"}}

        class SlowManager:
            def update_config(self, updates):
                # Fail immediately if persistence regresses onto the event loop;
                # do not deadlock the loop waiting for its own release signal.
                assert get_ident() != loop_thread
                saved_updates.append(updates)
                loop.call_soon_threadsafe(save_started.set)
                assert release_save.wait(5), "test did not release the disk writer"
                return updated_config

        async def publish(event_type, payload):
            published_events.append((event_type, payload))

        monkeypatch.setattr(config_api, "get_config_manager", lambda: SlowManager())
        monkeypatch.setattr(config_api, "publish_app_event", publish)
        custom_models = [{"id": "test-model"}]
        incoming = {"translation": {"backend": "gpt"}, "custom_models": custom_models}
        request = Request({"type": "http", "headers": [(b"x-client-id", b"desktop-test")]})
        pending = asyncio.create_task(config_api.update_full_config(incoming, request))
        try:
            await asyncio.wait_for(save_started.wait(), timeout=2)
            # This coroutine can advance while disk persistence is still gated.
            await asyncio.sleep(0)
            assert not pending.done()
            assert published_events == []
        finally:
            release_save.set()
            result = await asyncio.wait_for(pending, timeout=5)

        assert result == {"success": True, "data": updated_config}
        assert saved_updates == [{"translation": {"backend": "gpt", "custom_models": custom_models}}]
        assert incoming == {"translation": {"backend": "gpt"}, "custom_models": custom_models}
        assert published_events == [("config.updated", {
            "section": "*",
            "config": updated_config,
            "source_client_id": "desktop-test",
        })]

    asyncio.run(scenario())
