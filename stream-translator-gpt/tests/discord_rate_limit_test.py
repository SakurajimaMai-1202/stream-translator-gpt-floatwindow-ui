from unittest.mock import Mock
import queue

from stream_translator_gpt.result_exporter import (
    DISCORD_MAX_RATE_LIMIT_RETRIES,
    ResultExporter,
    _discord_retry_after,
)


def _response(status_code, *, headers=None, payload=None, text=""):
    response = Mock()
    response.status_code = status_code
    response.headers = headers or {}
    response.text = text
    if payload is None:
        response.json.side_effect = ValueError
    else:
        response.json.return_value = payload
    return response


def _exporter():
    return ResultExporter(
        cqhttp_url=None,
        cqhttp_token=None,
        discord_webhook_url=None,
        telegram_token=None,
        telegram_chat_id=None,
        output_file_path=None,
        proxy=None,
        output_whisper_result=True,
        output_timestamps=False,
    )


def test_retry_delay_uses_longest_discord_rate_limit_hint():
    response = _response(
        429,
        headers={"Retry-After": "0.25", "X-RateLimit-Reset-After": "0.4"},
        payload={"retry_after": 0.3},
    )

    assert _discord_retry_after(response) == 0.4


def test_discord_retries_same_payload_after_429(monkeypatch):
    responses = [
        _response(429, payload={"retry_after": 0.422}),
        _response(204),
    ]
    post = Mock(side_effect=responses)
    sleep = Mock()
    monkeypatch.setattr("stream_translator_gpt.result_exporter.requests.post", post)
    monkeypatch.setattr("stream_translator_gpt.result_exporter.time.sleep", sleep)

    assert _exporter()._post_discord_chunk("https://discord.test/webhook", "message")
    assert post.call_count == 2
    assert post.call_args_list[0].kwargs["json"] == {"content": "message"}
    assert post.call_args_list[1].kwargs["json"] == {"content": "message"}
    sleep.assert_called_once_with(0.422)


def test_discord_waits_when_bucket_is_exhausted(monkeypatch):
    response = _response(
        204,
        headers={
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset-After": "0.75",
        },
    )
    sleep = Mock()
    monkeypatch.setattr(
        "stream_translator_gpt.result_exporter.requests.post",
        Mock(return_value=response),
    )
    monkeypatch.setattr("stream_translator_gpt.result_exporter.time.sleep", sleep)

    assert _exporter()._post_discord_chunk("https://discord.test/webhook", "message")
    sleep.assert_called_once_with(0.75)


def test_discord_does_not_retry_non_rate_limit_client_error(monkeypatch):
    post = Mock(return_value=_response(400, text="bad request"))
    sleep = Mock()
    monkeypatch.setattr("stream_translator_gpt.result_exporter.requests.post", post)
    monkeypatch.setattr("stream_translator_gpt.result_exporter.time.sleep", sleep)

    assert not _exporter()._post_discord_chunk("https://discord.test/webhook", "message")
    post.assert_called_once()
    sleep.assert_not_called()


def test_discord_rate_limit_retry_is_bounded(monkeypatch):
    response = _response(429, headers={"Retry-After": "0"})
    post = Mock(return_value=response)
    monkeypatch.setattr("stream_translator_gpt.result_exporter.requests.post", post)
    monkeypatch.setattr("stream_translator_gpt.result_exporter.time.sleep", Mock())

    assert not _exporter()._post_discord_chunk("https://discord.test/webhook", "message")
    assert post.call_count == DISCORD_MAX_RATE_LIMIT_RETRIES + 1


def test_discord_worker_drains_single_queue_in_fifo_order(monkeypatch):
    exporter = _exporter()
    exporter.discord_queue = queue.SimpleQueue()
    exporter.discord_queue.put("first")
    exporter.discord_queue.put("second")
    exporter.discord_queue.put(None)
    send = Mock(return_value=True)
    monkeypatch.setattr(exporter, "_post_discord_chunk", send)

    exporter._send_message_to_discord("https://discord.test/webhook")

    assert [call.args[1] for call in send.call_args_list] == ["first", "second"]
