from stream_translator_gpt.translation_policy import (
    TranslationRequest, create_prompt_strategy, validate_translation, resolve_model_family,
)
from stream_translator_gpt.hy_mt2_optimizer import OptimizerSettings


def test_index_official_and_quantized_detection():
    for model in ("IndexTeam/Index-Translate-2B", "Index-Translate-9B-Q4_K_M.gguf"):
        assert resolve_model_family("auto", model, "llama_cpp") == "index_translate"
    assert resolve_model_family("index", "my-model", "lm_studio") == "index_translate"
    assert resolve_model_family("auto", "index-reader", "llama_cpp") == "generic_chat"


def test_index_background_has_separate_boundaries():
    strategy = create_prompt_strategy("index_translate", "translate", "text")
    strategy.optimizer_settings = OptimizerSettings()
    prompt = strategy.prepare(TranslationRequest(1, "人と人", previous_sources=(
        "新しい私を形づくる", "誰かが見つけてくれたから", "私の後ろに道が出来た"))).user_content
    assert prompt.index("【背景参考结束】") < prompt.index("【源文】")
    assert "【源文】\n人と人\n【源文结束】" in prompt


def test_exact_japanese_copy_detection_respects_exemptions():
    request = TranslationRequest(1, "人と人")
    assert "untranslated_source" in [i.code for i in validate_translation(request, "人と人")]
    assert validate_translation(request, "人與人") == ()
    assert validate_translation(TranslationRequest(1, "人"), "人") == ()
    assert validate_translation(TranslationRequest(1, "すいちゃん", preserve_elements=("すいちゃん",)), "すいちゃん") == ()
    assert validate_translation(TranslationRequest(1, "すいちゃん", glossary={"すいちゃん": "すいちゃん"}), "すいちゃん") == ()
    assert validate_translation(TranslationRequest(1, "人と人", target_language="Japanese"), "人と人") == ()


def test_japanese_rewrite_and_short_multiline_context_echo():
    request = TranslationRequest(1, 'もしかして初配信もう初配信かもこれ')
    issues = validate_translation(request, 'もしかして、初配信はもう初配信だったのかもね、これ。')
    assert 'target_language_mismatch' in [issue.code for issue in issues]
    request = TranslationRequest(1, 'パソコンが')
    history = (('壊れました', '壞掉啦！'), ('こちらは新しいパソコンです', '這是新的電腦'))
    assert 'context_echo_rejected' in [issue.code for issue in validate_translation(request, '電腦壞了\n這是新的電腦', history)]
    assert validate_translation(request, '電腦啊……', history) == ()
    assert validate_translation(TranslationRequest(1, 'すいちゃん', preserve_elements=('すいちゃん',)), 'すいちゃん') == ()


def test_contextual_multiline_echo_without_exact_history_match():
    request = TranslationRequest(1, 'すいちゃんがPCの掃除なんかどこどこを拭いたら壊れるかわかんないんだから。',
        previous_sources=('P.C.の掃除全然してなかったんだ。', 'うん。', 'してない。'))
    output = 'Sui醬根本沒清過電腦啊！\n嗯。\n就是沒清。'
    assert 'unexpected_multiline_output' in [issue.code for issue in validate_translation(request, output)]
    assert validate_translation(request, 'Sui醬不知道清電腦時擦哪些地方會弄壞啊。') == ()


def test_sparse_common_japanese_word_in_chinese():
    request = TranslationRequest(1, 'まさか妄想で見るというのか買ってくれてるはず')
    output = 'まさか是用妄想來看的嗎？應該有人買下來的吧！'
    assert 'target_language_mismatch' in [issue.code for issue in validate_translation(request, output)]
    assert validate_translation(request, '難道是靠想像看的嗎？應該有買吧！') == ()
    assert validate_translation(TranslationRequest(1, 'まさか', preserve_elements=('まさか',)), 'まさか') == ()
    assert validate_translation(TranslationRequest(1, 'まさか', glossary={'まさか': 'まさか'}), 'まさか') == ()


def test_latest_sparse_filler_and_broken_romanization():
    assert 'target_language_mismatch' in [i.code for i in validate_translation(
        TranslationRequest(1, 'うん、まあそういうね。'), '嗯，まあ就是那樣啦。')]
    request = TranslationRequest(1, '美味しくなれ、モエモエバウ！')
    assert 'target_language_mismatch' in [i.code for i in validate_translation(request, '變得美味吧，Moemoebaウ！')]
    assert validate_translation(request, '變得好吃吧，萌萌汪！') == ()
    assert validate_translation(TranslationRequest(1, 'Moemoebaウ', preserve_elements=('Moemoebaウ',)), 'Moemoebaウ') == ()
    assert validate_translation(TranslationRequest(1, 'Windows。'), 'Windows。') == ()


def test_index_basic_and_optimized_constraints():
    strategy = create_prompt_strategy("index_translate", "translate", "json")
    request = TranslationRequest(1, "マリーとタイ", glossary={"マリー": "瑪麗", "無關": "錯誤"},
                                 candidates={"タイ": "鯛魚"}, previous_sources=("前文",))
    basic = strategy.prepare(request)
    assert basic.system_instruction is None and basic.output_format == "text"
    assert "瑪麗" not in basic.user_content and basic.temperature == 0
    strategy.optimizer_settings = OptimizerSettings()
    optimized = strategy.prepare(request).user_content
    assert "【硬性要求】" in optimized and "マリー→瑪麗" in optimized
    assert "不确定" in optimized and "錯誤" not in optimized
    assert "前文" in optimized


def test_validation_only_matched_terms_and_exact_preservation():
    request = TranslationRequest(1, "マリー @abc @xyz", glossary={"マリー": "瑪麗", "無關": "錯誤"},
                                 preserve_elements=("@abc", "@xyz"))
    assert validate_translation(request, "瑪麗 @abc @xyz") == ()
    assert [i.code for i in validate_translation(request, "瑪麗 @xyz @abc")] == ["preserve_element_order"]
    assert [i.code for i in validate_translation(request, "瑪麗 @abc")] == ["preserve_element_changed"]


def _preview_client(**kwargs):
    from stream_translator_gpt.llm_translator import LLMClient
    return LLMClient(llm_type="GPT", model="Index-Translate-2B", prompt="translate",
                     history_size=3, proxy=None, use_json_result=False,
                     provider="llama_cpp", **kwargs)


def test_preview_repair_success_clears_failure():
    client = _preview_client(index_translate_optimizer_enabled=True, glossary={"マリー": "瑪麗"})
    class Provider:
        count = 0
        def translate(self, client, task):
            self.count += 1
            client._prepare_prompt(task)
            task.translation = "wrong" if self.count == 1 else "瑪麗"
            client._validate_hy_mt2_output(task)
    client.provider_adapter = Provider()
    result = client.translate_preview("マリー")
    assert result["translation"] == "瑪麗" and result["error"] is None
    assert result["validation"] == [] and result["retry_count"] == 1


def test_japanese_copy_repaired_without_background():
    client = _preview_client(index_translate_optimizer_enabled=True)
    prompts = []
    class Provider:
        def translate(self, client, task):
            prompts.append(client._prepare_prompt(task).user_content)
            task.translation = "人と人" if len(prompts) == 1 else "人與人"
            client._validate_hy_mt2_output(task)
    client.provider_adapter = Provider()
    result = client.translate_preview("人と人", [{'source': '私の後ろに道が出来た'}])
    assert result['translation'] == '人與人' and result['retry_count'] == 1
    assert '【背景参考】' in prompts[0] and '【背景参考】' not in prompts[1]


def test_preview_baseline_diagnostic_does_not_enforce():
    client = _preview_client()
    class Provider:
        def translate(self, client, task):
            client._prepare_prompt(task)
            task.translation = "wrong"
    client.provider_adapter = Provider()
    result = client.translate_preview("マリー", diagnostic_glossary={"マリー": "瑪麗"})
    assert result["translation"] == "wrong" and result["retry_count"] == 0
    assert result["glossary_hits"] == {"マリー": "瑪麗"}
    assert result["validation"][0]["code"] == "fixed_term_missing"
    assert not result["validation_enforced"]


def test_preview_no_repair_after_total_deadline_and_close():
    import time
    client = _preview_client(index_translate_optimizer_enabled=True)
    class Provider:
        count = 0
        def translate(self, client, task):
            self.count += 1
            client._prepare_prompt(task)
            task.start_time = task.start_time.replace(year=2020)
            task.translation = ""
            client._validate_hy_mt2_output(task)
    client.provider_adapter = Provider()
    result = client.translate_preview("テスト")
    assert result["retry_count"] == 0 and result["error"] == "stale_result"
    class Transport:
        closed = False
        def close(self):
            self.closed = True
    transport = Transport()
    client._openai_clients["test"] = transport
    client.close()
    assert transport.closed and not client._openai_clients


def test_source_only_ui_context_reaches_optimized_prompt():
    client = _preview_client(index_translate_optimizer_enabled=True)
    prompts = []
    class Provider:
        def translate(self, client, task):
            prompts.append(client._prepare_prompt(task).user_content)
            task.translation = "你好"
            client._validate_hy_mt2_output(task)
    client.provider_adapter = Provider()
    client.translate_preview("こんにちは", [{"source": "昨日は雨でした", "target": ""}])
    assert "昨日は雨でした" in prompts[0]
    assert client.hy_mt2_context.snapshot() == ("昨日は雨でした",)
    assert client.history_pairs[0] == ("昨日は雨でした", "")


def test_hy_basic_preview_preserves_live_glossary_and_history_prompt():
    from stream_translator_gpt.llm_translator import LLMClient
    from stream_translator_gpt.common import TranslationTask
    import numpy as np
    kwargs = dict(llm_type="GPT", model="hy-mt2", prompt="翻譯", history_size=3,
                  proxy=None, use_json_result=False, provider="llama_cpp", glossary={"マリー": "瑪麗"})
    live, preview = LLMClient(**kwargs), LLMClient(**kwargs)
    live._append_history_message("昨日は雨でした", "昨天下雨")
    task = TranslationTask(np.zeros(0), (0, 0))
    task.transcript = "マリー"
    expected = live._prepare_prompt(task).user_content
    prompts = []
    class Provider:
        def translate(self, client, task):
            prompts.append(client._prepare_prompt(task).user_content)
            task.translation = "瑪麗"
    preview.provider_adapter = Provider()
    preview.translate_preview("マリー", [{"source": "昨日は雨でした", "target": ""}])
    assert prompts == [expected]


def test_preview_attempt_transport_error_does_not_expose_exception_body():
    from types import SimpleNamespace
    client = _preview_client(api_key="test-key")
    class TransportError(Exception):
        status_code = 503
    def fail(**kwargs):
        raise TransportError("server echoed secret test-key")
    class Transport:
        chat = SimpleNamespace(completions=SimpleNamespace(create=fail))
        def with_options(self, **kwargs):
            return self
    client._openai_clients["test-key"] = Transport()
    result = client.translate_preview("こんにちは")
    attempt = result["attempts"][0]
    assert attempt["request_failure_reason"] == "TransportError"
    assert attempt["request_failure_status"] == 503
    assert "test-key" not in str(result["attempts"])


def test_empty_config_proxy_uses_real_httpx_transport(monkeypatch):
    import httpx
    from stream_translator_gpt.llm_translator import LLMClient
    real_client = httpx.Client
    def response(request):
        return httpx.Response(200, json={"id": "preview", "object": "chat.completion",
            "created": 0, "model": "Index-Translate-2B",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "你好"},
                         "finish_reason": "stop"}]})
    class FixtureClient(real_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(response), **kwargs)
    monkeypatch.setattr(httpx, "Client", FixtureClient)
    client = LLMClient(llm_type="GPT", model="Index-Translate-2B", prompt="翻譯",
        history_size=0, proxy="", use_json_result=False, provider="llama_cpp",
        api_key="fixture", base_url="http://127.0.0.1:8080/v1")
    try:
        assert client.proxy is None
        result = client.translate_preview("こんにちは")
        assert result["translation"] == "你好" and result["error"] is None
    finally:
        client.close()


def test_index_local_reasoning_field_compatibility_is_scoped(monkeypatch):
    import httpx
    from stream_translator_gpt.llm_translator import LLMClient
    real_client = httpx.Client
    def response(request):
        return httpx.Response(200, json={'id': 'fixture', 'object': 'chat.completion', 'created': 0,
            'model': 'fixture', 'choices': [{'index': 0, 'finish_reason': 'stop',
            'message': {'role': 'assistant', 'content': '', 'reasoning_content': '我们希望实现创新。'}}]})
    class FixtureClient(real_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(response), **kwargs)
    monkeypatch.setattr(httpx, 'Client', FixtureClient)
    for model, expected in [('Index-Translate-9B', '我們希望實現創新。'), ('other-chat', '')]:
        client = LLMClient('GPT', model, '翻譯', 0, None, False, provider='openai_compatible',
            api_key='fixture', base_url='http://127.0.0.1:8080/v1', translation_target_language='Traditional Chinese')
        try:
            result = client.translate_preview('We want innovation.')
            assert result['translation'] == expected
        finally:
            client.close()


def test_missing_opencc_after_successful_http_never_reports_validation_pass(monkeypatch):
    import httpx
    import stream_translator_gpt.llm_translator as module
    real_client = httpx.Client
    def response(request):
        return httpx.Response(200, json={"id": "fixture", "object": "chat.completion",
            "created": 0, "model": "Index-Translate-2B", "choices": [{"index": 0,
            "message": {"role": "assistant", "content": "你好"}, "finish_reason": "stop"}]})
    class FixtureClient(real_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(response), **kwargs)
    def missing_opencc(*args):
        raise RuntimeError("Traditional/Simplified Chinese Qwen3-ASR output requires OpenCC. Install opencc-python-reimplemented.")
    monkeypatch.setattr(httpx, "Client", FixtureClient)
    monkeypatch.setattr(module, "normalize_chinese_script", missing_opencc)
    for enabled in (False, True):
        client = _preview_client(api_key="fixture", base_url="http://127.0.0.1:8080/v1",
                                 translation_target_language="Traditional Chinese",
                                 index_translate_optimizer_enabled=enabled)
        try:
            result = client.translate_preview("こんにちは")
            assert result["translation"] == "" and result["retry_count"] == 0
            assert "translation requires OpenCC" in result["error"]
            assert "Qwen3-ASR" not in result["error"]
            assert "translation_script_conversion_failed" in [i["code"] for i in result["validation"]]
            assert "empty_output" in [i["code"] for i in result["validation"]]
            assert result["attempts"][0]["raw_model_response"] == "你好"
        finally:
            client.close()
