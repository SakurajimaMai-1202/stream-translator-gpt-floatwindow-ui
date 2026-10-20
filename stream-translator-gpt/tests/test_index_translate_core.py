from stream_translator_gpt.translation_policy import (
    TranslationRequest, create_prompt_strategy, validate_translation, resolve_model_family,
)
from stream_translator_gpt.hy_mt2_optimizer import OptimizerSettings
import pytest


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


@pytest.mark.parametrize('source, output', [
    ('みたいなやっている方が。', '像這樣做會比較好。'),
    ('痩せたねっていうのはどうですか？異性の。', '被說變瘦了這件事呢？是異性說的。'),
    ('デリカシーがないと思う。', '我覺得你這樣好沒分寸啊。'),
    ('ありがとうございます。', '謝謝你喔！'),
    ('FUWAMOCOもすっごく良くて', 'FUWAMOCO也非常出色'),
    ('ホロクルの写真集届いた！！！', 'ホロクル的照片集終於到了！！！'),
])
def test_residual_kana_good_live_outputs(source, output):
    assert validate_translation(TranslationRequest(1, source), output) == ()


def test_residual_kana_sparse_and_exempt_spans():
    source = 'なんか普通に喜ぶだから。'
    output = '普通に開心的話完全沒問題啊。'
    assert [i.code for i in validate_translation(TranslationRequest(1, source), output)] == ['residual_kana']
    assert validate_translation(TranslationRequest(1, source, target_language='Japanese'), output) == ()
    for kwargs in ({'glossary': {'すいちゃん': 'すいちゃん'}},
                   {'preserve_elements': ('すいちゃん',)}):
        assert validate_translation(TranslationRequest(1, 'すいちゃんありがとう', **kwargs), '謝謝すいちゃん') == ()


@pytest.mark.parametrize('family', ['index_translate', 'hy_mt2'])
def test_kana_repair_hint_only_when_requested(family):
    from dataclasses import replace
    strategy = create_prompt_strategy(family, 'translate', 'text')
    strategy.optimizer_settings = OptimizerSettings()
    request = TranslationRequest(1, 'source', repair=True, residual_kana=('に', 'のんでり'))
    hint = '上次译文残留日文「に」「のんでり」，请全部翻成目标语言，不要保留日文假名。'
    content = strategy.prepare(request).user_content
    assert content.count(hint) == 1
    # A hint after the source would be translated along with it.
    assert content.index(hint) < content.rindex('source')
    assert '上次译文' not in strategy.prepare(replace(request, repair=False)).user_content
    assert '上次译文' not in strategy.prepare(replace(request, residual_kana=())).user_content


@pytest.mark.parametrize('family', ['index_translate', 'hy_mt2'])
@pytest.mark.parametrize('preview', [False, True])
@pytest.mark.parametrize('source, outputs, expected, fallback', [
    ('のんでりだと思う。', ('我覺得是「のんでり」。', '我猜是「のんでり」。'), '我猜是「のんでり」。', True),
    ('のんでりだと思う。', ('我覺得這個人應該是「のんでり」才對吧。', '我猜這個人應該是「のんでり」才對吧。'), '我猜這個人應該是「Nonderi」才對吧。', True),
    ('のんでりだと思う。', ('これは日本語です。', 'それは日本語です。'), 'それは日本語です。', True),
    ('のんでりだと思う。', ('我觉得是「に」。', '我猜是「のんでり」。'), '我覺得是。', True),
    ('のんでりだと思う。', ('我覺得是「のんでり」。', '【源文】我猜是這樣。'), '', False),
    ('のんでりだと思う。', ('【源文】我覺得是這樣。', '我猜是「のんでり」。'), '我猜是「のんでり」。', True),
    ('なんか普通に喜ぶだから。', ('普通に開心的話完全沒問題啊。', '普通開心的話完全沒問題啊。'), '普通開心的話完全沒問題啊。', False),
])
def test_kana_repair_http_live_and_preview(monkeypatch, tmp_path, capsys, family, preview, source, outputs, expected, fallback):
    import json
    import queue
    import httpx
    import numpy as np
    from stream_translator_gpt.common import TranslationTask
    from stream_translator_gpt.llm_translator import ParallelTranslator
    real_client = httpx.Client
    prompts = []
    def response(request):
        prompts.append(json.loads(request.content)['messages'][-1]['content'])
        return httpx.Response(200, json={'id': 'fixture', 'object': 'chat.completion', 'created': 0,
            'model': 'fixture', 'choices': [{'index': 0, 'finish_reason': 'stop',
            'message': {'role': 'assistant', 'content': outputs[len(prompts) - 1]}}]})
    class FixtureClient(real_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(response), **kwargs)
    monkeypatch.setattr(httpx, 'Client', FixtureClient)
    client = _preview_client(model_family=family, api_key='fixture', base_url='http://127.0.0.1:8080/v1',
        translation_target_language='Traditional Chinese', index_translate_optimizer_enabled=True,
        hy_mt2_optimizer_enabled=True)
    try:
        if preview:
            result = client.translate_preview(source)
            assert result['translation'] == expected
            assert result['translation_kana_fallback'] is fallback
            assert result['retry_count'] == 1
        else:
            task = TranslationTask(np.zeros(0), (0, 1))
            task.transcript = source
            incoming, outgoing = queue.SimpleQueue(), queue.SimpleQueue()
            incoming.put(task)
            incoming.put(None)
            ParallelTranslator(client, 10, True, 1).loop(incoming, outgoing)
            assert outgoing.get() is task and outgoing.get() is None
            assert task.translation == expected
            assert task.translation_failed is (not bool(expected))
            assert task.translation_kana_fallback is fallback
            assert task.translation_result.translation_kana_fallback is fallback
            assert task.translation_result.translation == expected
            if fallback:
                assert set(task.translation_validation_reasons).intersection({'residual_kana', 'target_language_mismatch'})
                from stream_translator_gpt.result_exporter import ResultExporter
                exporter = ResultExporter(cqhttp_url=None, cqhttp_token=None, discord_webhook_url=None,
                    telegram_token=None, telegram_chat_id=None, output_file_path=str(tmp_path / 'captions.srt'),
                    proxy=None, output_whisper_result=False, output_timestamps=False, require_translation=True)
                export_queue = queue.SimpleQueue()
                export_queue.put(task)
                export_queue.put(None)
                capsys.readouterr()
                exporter.loop(export_queue)
                assert expected in capsys.readouterr().out
                assert expected in (tmp_path / 'captions.srt').read_text(encoding='utf-8')
        assert len(prompts) == 2
        assert '上次译文' not in prompts[0]
        if '【源文】' not in outputs[0]:
            assert '上次译文残留日文' in prompts[1]
            from stream_translator_gpt.translation_policy import residual_kana_runs
            for run in residual_kana_runs(TranslationRequest(1, source), outputs[0]):
                assert f'「{run}」' in prompts[1]
        else:
            assert '上次译文' not in prompts[1]
        assert list(client.history_pairs) == ([(source, expected)] if expected else [])
        assert client.hy_mt2_context.snapshot() == ((source,) if expected else ())
    finally:
        client.close()


@pytest.mark.parametrize('failure', ['transport', 'empty', 'copy', 'stale'])
def test_kana_fallback_blocked_by_other_attempt_failure(failure):
    import numpy as np
    from stream_translator_gpt.common import TranslationTask
    client = _preview_client(index_translate_optimizer_enabled=True)
    task = TranslationTask(np.zeros(0), (0, 1))
    task.transcript = 'のんでりだと思う。'
    task._translation_attempts = 1
    client._prepare_prompt(task)
    if failure == 'transport':
        client._record_translation_failure(task, TimeoutError('transport timeout'))
    else:
        task.translation = '' if failure == 'empty' else task.transcript
        if failure == 'stale':
            client.reset_context()
        client._validate_hy_mt2_output(task)
    task._translation_attempts = 2
    client._prepare_prompt(task)
    task.translation = '我猜是「のんでり」。'
    client._validate_hy_mt2_output(task)
    if failure == 'stale':
        assert task.translation == '' and task.translation_failed
        assert not task.translation_kana_fallback
    else:
        assert task.translation
        assert task.translation_kana_fallback
        assert not task.translation_failed
    client.close()


@pytest.mark.parametrize('family', ['index_translate', 'hy_mt2'])
def test_multiline_then_kana_fallback(family):
    import re
    from stream_translator_gpt.common import TranslationTask
    client = _preview_client(model_family=family, index_translate_optimizer_enabled=True,
        hy_mt2_optimizer_enabled=True, translation_target_language='Traditional Chinese')
    task = TranslationTask(None, (0, 1))
    task.transcript = 'モちゃんお疲れ、パンスちゃんお疲れさんです。ありがとう見てくれて、パシモンお疲れ、セイちゃんお疲れ。'
    try:
        task._family_request, _ = client.prepare_translation_request(
            task.transcript, task.segment_id, previous_sources=('今日はありがとう。',))
        task._translation_attempts = 1
        task.translation = '今天謝謝你。\n莫醬辛苦了，潘絲醬也辛苦了。'
        client._validate_hy_mt2_output(task)
        assert 'unexpected_multiline_output' in task.translation_validation_reasons
        assert not getattr(task, '_family_kana_candidates', ())
        task._translation_attempts = 2
        task.translation = '莫ちゃん辛苦了，潘絲ちゃん也辛苦了。謝謝大家的觀看，帕西蒙辛苦了，賽伊ちゃん也辛苦了。'
        client._validate_hy_mt2_output(task)
        assert task.translation == '莫醬辛苦了，潘絲醬也辛苦了。謝謝大家的觀看，帕西蒙辛苦了，賽伊醬也辛苦了。'
        assert not re.search(r'[\u3041-\u3096]', task.translation)
        assert task.translation_kana_fallback and not task.translation_failed
        assert 'unexpected_multiline_output' in task.translation_validation_reasons
        assert 'residual_kana' in task.translation_validation_reasons
    finally:
        client.close()


def test_kana_only_final_attempt_without_retry_is_shown():
    import queue
    import numpy as np
    from stream_translator_gpt.common import TranslationTask
    from stream_translator_gpt.llm_translator import ParallelTranslator
    client = _preview_client(index_translate_optimizer_enabled=True)
    class Provider:
        def translate(self, client, task):
            client._prepare_prompt(task)
            task.translation = '普通に開心的話完全沒問題啊。'
            client._validate_hy_mt2_output(task)
    client.provider_adapter = Provider()
    task = TranslationTask(np.zeros(0), (0, 1))
    task.transcript = 'なんか普通に喜ぶだから。'
    incoming, outgoing = queue.SimpleQueue(), queue.SimpleQueue()
    incoming.put(task)
    incoming.put(None)
    ParallelTranslator(client, 10, False, 1).loop(incoming, outgoing)
    assert outgoing.get() is task and outgoing.get() is None
    assert task.translation and task.translation_kana_fallback and not task.translation_failed


@pytest.mark.parametrize('family, raw_content, expected', [
    ('index_translate', '草稿……\n</think>\n\n正式譯文。', '正式譯文。'),
    ('index_translate', '<think>\n\n</think>\n\n正式譯文。', '正式譯文。'),
    ('index_translate', '草稿\n</think>中間草稿\n</think>\n正式譯文。', '正式譯文。'),
    ('index_translate', '草稿\n</think>\n<think>正式譯文。', '正式譯文。'),
    ('index_translate', '草稿\n</think>\n', ''),
    ('generic_chat', '草稿……</think>正式譯文。', '草稿……</think>正式譯文。'),
])
def test_index_content_think_block_cleanup_is_scoped(monkeypatch, capsys, family, raw_content, expected):
    import httpx
    import numpy as np
    from stream_translator_gpt.common import TranslationTask
    from stream_translator_gpt.llm_translator import LLMClient
    real_client = httpx.Client
    requests = []
    events = []
    def response(request):
        requests.append(request)
        return httpx.Response(200, json={'id': 'fixture', 'object': 'chat.completion', 'created': 0,
            'model': 'fixture', 'choices': [{'index': 0, 'finish_reason': 'stop',
            'message': {'role': 'assistant', 'content': raw_content}}]})
    class FixtureClient(real_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(response), **kwargs)
    monkeypatch.setattr(httpx, 'Client', FixtureClient)
    client = LLMClient('GPT', 'fixture', 'translate', 0, None, False,
        model_family=family, provider='openai_compatible', api_key='fixture',
        base_url='http://127.0.0.1:8080/v1', translation_target_language='Traditional Chinese',
        index_translate_optimizer_enabled=True, index_translate_debug=True,
        replay_response_hook=lambda task, event: events.append(event))
    task = TranslationTask(np.zeros(0), (0, 0))
    task.transcript = 'This is the final translation.'
    task._translation_attempts = 1
    try:
        client.translate(task)
        assert task.translation == expected
        assert len(requests) == 1 and len(events) == 1
        assert events[0]['raw_model_response'] == raw_content
        assert events[0]['parsed_translation'] == expected
        debug = capsys.readouterr().err
        if family == 'index_translate':
            assert f'RAW_OUTPUT={raw_content!r}' in debug
            assert 'THINK_BLOCK_STRIPPED=True' in debug
        else:
            assert 'THINK_BLOCK_STRIPPED=True' not in debug
        if family != 'index_translate':
            pass  # Only "not stripped" matters here; validation is the family's own.
        elif expected:
            assert not task.translation_failed
            assert not task.translation_validation_rejected
            assert task.translation_validation_reasons == ()
            assert not getattr(task, '_family_repair', False)
            assert events[0]['output_validation_reason'] is None
            assert task.translation_result.retry_count == 0
        else:
            assert task.translation_failed
            assert 'empty_output' in task.translation_validation_reasons
            assert events[0]['output_validation_reason'] == 'empty_output'
    finally:
        client.close()


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


def test_index_repair_attempt_samples_instead_of_greedy():
    strategy = create_prompt_strategy('index_translate', 'translate', 'text')
    strategy.optimizer_settings = OptimizerSettings()
    assert strategy.prepare(TranslationRequest(1, 'どこかさん。')).temperature == 0
    repair = TranslationRequest(1, 'どこかさん。', repair=True, residual_kana=('どこかさん',))
    assert strategy.prepare(repair).temperature > 0


def test_name_honorifics_become_chinese_but_kana_words_stay():
    from stream_translator_gpt.translation_output import normalize_translation_output
    convert = lambda text, _: text
    assert normalize_translation_output('Shinoさん、ケンちゃん、大輝くん', 'Traditional Chinese', convert) == 'Shino桑、ケン醬、大輝くん'
    # After hiragana it is part of a word or a kana name; leave it for the kana check.
    assert normalize_translation_output('みなさん、どこかさん', 'Traditional Chinese', convert) == 'みなさん、どこかさん'
    assert normalize_translation_output('Shinoさん', 'Japanese', convert) == 'Shinoさん'
    assert validate_translation(TranslationRequest(1, 'しのさんこんにちは'), 'Shinoさん，你好',
        normalize_output=lambda text: normalize_translation_output(text, 'Traditional Chinese', convert)) == ()


def test_residual_kana_fallback_writes_romaji_or_chinese():
    from stream_translator_gpt.translation_policy import localize_residual_kana
    request = TranslationRequest(1, 'source')
    assert localize_residual_kana(request, '好希望ゆるき能回來。ゆるきさん！') == '好希望Yuruki能回來。Yuruki桑！'
    assert localize_residual_kana(request, '「しゃしん」ちょっと') == '「Shashin」Chotto'
    assert localize_residual_kana(request, '嗯，いつも可愛照片的「に」') == '嗯，總是可愛照片的'
    preserved = TranslationRequest(1, 'すいちゃん', glossary={'すいちゃん': 'すいちゃん'})
    assert localize_residual_kana(preserved, '謝謝すいちゃん、ふぶき') == '謝謝すいちゃん、Fubuki'


@pytest.mark.parametrize('text, expected', [
    ('赤ちゃん', '赤ちゃん'), ('皆さん', '皆さん'), ('お父さん', 'お父さん'),
    ('奥さん', '奥さん'), ('本屋さん', '本屋さん'), ('Shinoさんは', 'Shino桑は'),
    ('ミオちゃん', 'ミオ醬'), ('Shinoさんはじめ', 'Shinoさんはじめ'),
])
def test_name_honorific_boundaries(text, expected):
    from stream_translator_gpt.translation_output import localize_name_honorifics
    assert localize_name_honorifics(text) == expected


@pytest.mark.parametrize('text, expected', [
    ('皆さん', '大家'), ('お父さん', '爸爸'), ('お母さん', '媽媽'),
    ('お兄さん', '哥哥'), ('お兄ちゃん', '哥哥'), ('兄ちゃん', '哥哥'),
    ('お姉さん', '姊姊'), ('お姉ちゃん', '姊姊'), ('姉ちゃん', '姊姊'),
    ('赤ちゃん', '寶寶'), ('奥さん', '太太'), ('お疲れ様', '辛苦了'),
    ('お疲れさま', '辛苦了'), ('お疲れ', '辛苦了'),
    ('みなさん', '大家'), ('みんなさん', '大家'), ('おじさん', '大叔'), ('おばさん', '阿姨'),
    ('おじいさん', '爺爺'), ('おじいちゃん', '爺爺'), ('おばあさん', '奶奶'), ('おばあちゃん', '奶奶'),
    ('おにいさん', '哥哥'), ('おにいちゃん', '哥哥'), ('おねえさん', '姊姊'), ('おねえちゃん', '姊姊'),
    ('おかあさん', '媽媽'), ('おとうさん', '爸爸'), ('あかちゃん', '寶寶'),
    ('お茶、ご飯', '茶、飯'), ('さん', '桑'), ('ちゃん', '醬'), ('くん', '君'),
    ('さんは', '桑'), ('みなさんの', '大家的'), ('ゆるきさんは', 'Yuruki桑'), ('ゆきの', 'Yukino'),
])
def test_residual_kana_words_and_phrases(text, expected):
    from stream_translator_gpt.translation_policy import localize_residual_kana
    assert localize_residual_kana(TranslationRequest(1, 'source'), text) == expected


@pytest.mark.parametrize('kwargs', [
    {'preserve_elements': ('お疲れ様', '赤ちゃん')},
    {'glossary': {'x': 'お疲れ様', 'y': '赤ちゃん'}},
])
def test_residual_kana_protected_phrases(kwargs):
    from stream_translator_gpt.translation_policy import localize_residual_kana
    request = TranslationRequest(1, 'source', **kwargs)
    assert localize_residual_kana(request, 'お疲れ様、赤ちゃん、皆さん') == 'お疲れ様、赤ちゃん、大家'


@pytest.mark.parametrize('text, expected', [
    ('いっしょ', 'Issho'), ('まっちゃ', 'Matcha'), ('っじゃ', 'Jja'), ('ゐゑゎ', 'Iewa'), ('あっ', 'A'),
])
def test_romaji_small_and_historic_kana(text, expected):
    from stream_translator_gpt.translation_policy import _romanize_hiragana
    assert _romanize_hiragana(text) == expected


def test_residual_kana_share_excludes_all_protected_elements():
    from stream_translator_gpt.translation_policy import residual_kana_share
    request = TranslationRequest(1, 'source', preserve_elements=('すいちゃん',), glossary={'x': '中文字'})
    assert residual_kana_share(request, 'すいちゃん中文字あ中中中') == 0.25
    assert residual_kana_share(request, 'すいちゃん中文字') == 0


def test_one_kana_stem_is_not_split_into_word_and_particle():
    from stream_translator_gpt.translation_policy import localize_residual_kana
    request = TranslationRequest(1, 'source')
    assert localize_residual_kana(request, '那個もの') == '那個Mono'
    assert localize_residual_kana(request, '是おに嗎') == '是Oni嗎'
    assert localize_residual_kana(request, 'Shino，さんは') == 'Shino，桑'


def test_builtin_nested_terms_only_require_the_longest_match():
    from stream_translator_gpt.translation_policy import _matching_glossary
    glossary = {"ツイート": "推文", "リツイート": "轉推", "塩釜焼き": "鹽釜燒", "鯛の塩釜焼き": "鹽釜烤鯛魚"}
    assert _matching_glossary("リツイートありがとう", glossary) == {"リツイート": "轉推"}
    assert _matching_glossary("鯛の塩釜焼きを作った", glossary) == {"鯛の塩釜焼き": "鹽釜烤鯛魚"}
    assert _matching_glossary("ツイートした", glossary) == {"ツイート": "推文"}
