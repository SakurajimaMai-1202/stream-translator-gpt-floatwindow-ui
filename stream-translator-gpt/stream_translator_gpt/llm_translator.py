import os
import sys
import queue
import threading
import time

from collections import deque
from datetime import datetime, timedelta, timezone

from .common import TranslationTask, LoopWorkerBase, ApiKeyPool, INFO
from .translation_policy import (
    TranslationRequest,
    TranslationResult,
    create_prompt_strategy,
    get_capabilities,
    parse_translation_output,
    resolve_model_family,
    resolve_output_format,
    validate_translation,
    _matching_glossary,
)
from .translation_glossary_auditor import TranslationGlossaryAuditor
from .qwen3_asr_postprocess import normalize_chinese_script, _TRADITIONAL_CHINESE, strip_unknown_token

class TranslationOutputConversionError(RuntimeError):
    code = "translation_script_conversion_failed"


def normalize_translation_output(text: str, target_language: str | None) -> str:
    text = strip_unknown_token(text)
    language = str(target_language or "").strip().lower().replace("_", "-")
    if language in _TRADITIONAL_CHINESE:
        try:
            return normalize_chinese_script(text, language)
        except Exception as exc:
            if "opencc" in str(exc).lower() and any(
                    word in str(exc).lower() for word in ("requires", "no module", "unavailable")):
                raise TranslationOutputConversionError(
                    "OpenCC unavailable: Traditional Chinese translation requires OpenCC (opencc-python-reimplemented); "
                    "the translation runtime is missing this dependency."
                ) from exc
            raise TranslationOutputConversionError("Traditional Chinese translation script conversion failed.") from exc
    return text


def _is_task_timeout(task: TranslationTask, timeout: float) -> bool:
    if timeout == 0.0:
        return False
    return datetime.now(timezone.utc) - task.start_time > timedelta(seconds=timeout)


class TranslationProvider:
    name = "unknown"

    def translate(self, client: "LLMClient", task: TranslationTask) -> None:
        raise NotImplementedError


class OpenAIProvider(TranslationProvider):
    name = "openai"

    def translate(self, client: "LLMClient", task: TranslationTask) -> None:
        client._translate_by_gpt(task)


class OpenAICompatibleProvider(OpenAIProvider):
    name = "openai_compatible"


class LMStudioProvider(OpenAICompatibleProvider):
    """LM Studio's OpenAI-compatible chat completions transport."""
    name = "lm_studio"


class LlamaCppProvider(OpenAICompatibleProvider):
    """llama-server's OpenAI-compatible chat completions transport."""
    name = "llama_cpp"


class GeminiProvider(TranslationProvider):
    name = "gemini"

    def translate(self, client: "LLMClient", task: TranslationTask) -> None:
        client._translate_by_gemini(task)


_PROVIDER_TYPES = {
    "openai": OpenAIProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "lm_studio": LMStudioProvider,
    "llama_cpp": LlamaCppProvider,
    "gemini": GeminiProvider,
}


class LLMClient():

    class LLM_TYPE:
        GPT = 'GPT'
        GEMINI = 'Gemini'

    def __init__(self,
                 llm_type: str,
                 model: str,
                 prompt: str,
                 history_size: int,
                 proxy: str,
                 use_json_result: bool,
                 gemini_base_url: str = None,
                 glossary: dict = None,
                 model_family: str = "auto",
                 output_format: str = "auto",
                 max_output_tokens: int = 128,
                 provider: str | None = None,
                 glossary_audit_enabled: bool = False,
                 hy_mt2_optimizer_enabled: bool = False,
                 hy_mt2_context_window: int = 3,
                 hy_mt2_max_context_chars: int = 1000,
                 hy_mt2_max_terms: int = 10,
                 hy_mt2_style: bool = True,
                 hy_mt2_style_text: str = "",
                 hy_mt2_preferences: str = "",
                 hy_mt2_debug: bool = False,
                 hy_mt2_aliases: str | None = None,
                 hy_mt2_glossary_folder: str | None = None,
                 replay_response_hook=None,
                 translation_target_language: str | None = None,
                 index_translate_optimizer_enabled: bool = False,
                 index_translate_context_window: int = 3,
                 index_translate_max_context_chars: int = 1000,
                 index_translate_max_terms: int = 10,
                 index_translate_style: bool = True,
                 index_translate_style_text: str = "",
                 index_translate_preferences: str = "",
                 index_translate_debug: bool = False,
                 index_translate_aliases: str | None = None,
                 index_translate_glossary_folder: str | None = None,
                 api_key: str | None = None,
                 base_url: str | None = None,
                 request_timeout: float = 30.0) -> None:
        if llm_type not in (self.LLM_TYPE.GPT, self.LLM_TYPE.GEMINI):
            raise ValueError(f'Unknow LLM type: {llm_type}')
        print(f'{INFO}Using {model} API as translation engine.')
        self.api_key = api_key
        self.base_url = base_url
        self.request_timeout = max(1.0, float(request_timeout))
        self.llm_type = llm_type
        self.model = model
        self.prompt = prompt
        self.translation_target_language = translation_target_language
        if translation_target_language is None:
            # Legacy CLI callers express the target only through the prompt.
            import re
            if re.search(r"繁[體体]中文|traditional\s+chinese|zh[-_]hant|zh[-_]tw", prompt, re.IGNORECASE):
                self.translation_target_language = "Traditional Chinese"
        self.history_size = history_size
        self.proxy = str(proxy).strip() if proxy and str(proxy).strip() else None
        self.gemini_base_url = gemini_base_url
        self.glossary = glossary or {}
        self.glossary_auditor = TranslationGlossaryAuditor(
            self.glossary,
            enabled=glossary_audit_enabled,
        )
        provider = provider or (
            "gemini" if llm_type == self.LLM_TYPE.GEMINI else (
                "openai_compatible" if os.environ.get("OPENAI_BASE_URL") else "openai"
            )
        )
        self.provider = provider
        self.provider_adapter = _PROVIDER_TYPES.get(provider, OpenAIProvider)()
        self.model_family = resolve_model_family(model_family, model, provider)
        self.capabilities = get_capabilities(self.model_family)
        requested_format = "json" if use_json_result and output_format == "auto" else output_format
        self.output_format = resolve_output_format(requested_format, self.capabilities)
        self.prompt_strategy = create_prompt_strategy(self.model_family, prompt, self.output_format)
        self.hy_mt2_context = None
        self.hy_mt2_debug = bool(hy_mt2_debug and hy_mt2_optimizer_enabled and self.model_family == "hy_mt2")
        # Opt-in replay observer. Normal runtime never stores raw model content.
        self.replay_response_hook = replay_response_hook
        if hy_mt2_optimizer_enabled and self.model_family == "hy_mt2":
            from .hy_mt2_context import SourceContext
            self.hy_mt2_context = SourceContext(max(0, min(5, int(hy_mt2_context_window))))
            if hy_mt2_glossary_folder:
                from .hy_mt2_glossary import load_glossary_folder
                self.glossary = dict(self.glossary)
                for source, target in load_glossary_folder(hy_mt2_glossary_folder).items():
                    self.glossary.setdefault(source, target)
            if hy_mt2_aliases:
                import json
                try:
                    aliases = json.loads(hy_mt2_aliases)
                    if isinstance(aliases, dict):
                        self.glossary = dict(self.glossary)
                        for alias, target in aliases.items():
                            if isinstance(alias, str) and isinstance(target, str) and alias and target:
                                self.glossary.setdefault(alias, target)
                except (TypeError, ValueError):
                    pass
            from .hy_mt2_optimizer import OptimizerSettings
            self.prompt_strategy.optimizer_settings = OptimizerSettings(
                context_window=max(0, min(5, int(hy_mt2_context_window))),
                max_context_chars=max(0, min(4000, int(hy_mt2_max_context_chars))),
                max_terms=max(0, min(30, int(hy_mt2_max_terms))),
                style=bool(hy_mt2_style),
                style_text=str(hy_mt2_style_text or ""),
                preferences=str(hy_mt2_preferences or ""),
            )
        self.family_optimizer_enabled = bool(
            (self.model_family == "hy_mt2" and hy_mt2_optimizer_enabled)
            or (self.model_family == "index_translate" and index_translate_optimizer_enabled))
        if self.model_family == "index_translate" and index_translate_optimizer_enabled:
            from .hy_mt2_context import SourceContext
            from .hy_mt2_optimizer import OptimizerSettings
            self.hy_mt2_context = SourceContext(max(0, min(5, int(index_translate_context_window))))
            self.prompt_strategy.optimizer_settings = OptimizerSettings(
                max(0, min(5, int(index_translate_context_window))),
                max(0, min(4000, int(index_translate_max_context_chars))),
                max(0, min(30, int(index_translate_max_terms))), bool(index_translate_style),
                str(index_translate_style_text or ""), str(index_translate_preferences or ""))
            self.hy_mt2_debug = bool(index_translate_debug)
            self.glossary = dict(self.glossary)
            if index_translate_glossary_folder:
                from .hy_mt2_glossary import load_glossary_folder
                for source, target in load_glossary_folder(index_translate_glossary_folder).items():
                    self.glossary.setdefault(source, target)
            if index_translate_aliases:
                import json
                aliases = json.loads(index_translate_aliases)
                if not isinstance(aliases, dict):
                    raise ValueError("index_translate_aliases must be a JSON object")
                for alias, target in aliases.items():
                    if isinstance(alias, str) and isinstance(target, str) and alias and target:
                        self.glossary.setdefault(alias, target)
        self._preview_glossary_folder = (index_translate_glossary_folder if self.model_family == "index_translate"
                                         else hy_mt2_glossary_folder if self.model_family == "hy_mt2" else None)
        self._preview_aliases = (index_translate_aliases if self.model_family == "index_translate"
                                else hy_mt2_aliases if self.model_family == "hy_mt2" else None)
        self._context_generation = 0
        self.max_output_tokens = max(16, int(max_output_tokens or 128))
        self.history_pairs = deque(maxlen=max(3 if self.family_optimizer_enabled else 0, history_size))
        self._history_lock = threading.Lock()
        self._openai_clients = {}
        self._openai_clients_lock = threading.Lock()
        print(
            f"{INFO}Translation policy: provider={provider}, family={self.model_family}, "
            f"format={self.output_format}, max_tokens={self.max_output_tokens}"
        )

    def _history_snapshot(self) -> tuple[str, str]:
        if not self.history_size:
            return "", ""
        with self._history_lock:
            if not self.history_pairs:
                return "", ""
            return self.history_pairs[-1]

    def reset_context(self):
        with self._history_lock:
            self._context_generation += 1
            self.history_pairs.clear()
            if self.hy_mt2_context is not None:
                self.hy_mt2_context.clear()

    def prepare_translation_request(self, source_text, segment_id=0, previous_sources=(),
                                    candidates=None, preserve_elements=(), repair=False):
        source_text = strip_unknown_token(source_text)
        previous_sources = tuple(strip_unknown_token(source) for source in previous_sources)
        from dataclasses import replace
        import re
        if self.family_optimizer_enabled and not preserve_elements:
            preserve_elements = tuple(dict.fromkeys(re.findall(r"https?://[^\s<>]+|(?<!\w)@[A-Za-z0-9_]+", source_text)))
        settings = getattr(self.prompt_strategy, "optimizer_settings", None)
        glossary = self.glossary
        if self.family_optimizer_enabled:
            glossary = _matching_glossary(source_text, glossary, settings.max_terms)
        request = TranslationRequest(
            segment_id=segment_id, source_text=source_text,
            previous_sources=tuple(previous_sources), glossary=glossary,
            target_language=self.translation_target_language or "Traditional Chinese",
            candidates=candidates, preserve_elements=tuple(preserve_elements),
            repair=repair, session_id=self._context_generation)
        strategy = self.prompt_strategy
        if repair and settings is not None and self.model_family == "hy_mt2":
            strategy = create_prompt_strategy(self.model_family, self.prompt, self.output_format)
            strategy.optimizer_settings = replace(settings, context_window=0, style=False,
                                                  style_text="", preferences="")
        return request, strategy.prepare(request)

    def _prepare_prompt(self, task: TranslationTask):
        previous_original, previous_translation = self._history_snapshot()
        if self.hy_mt2_context is not None:
            previous_sources = self.hy_mt2_context.snapshot()
        else:
            with self._history_lock:
                previous_sources = tuple(source for source, _ in self.history_pairs)
        request, prepared = self.prepare_translation_request(
            task.transcript or "", task.segment_id, previous_sources,
            getattr(task, "translation_candidates", None),
            getattr(task, "translation_preserve_elements", ()),
            getattr(task, "_family_repair", False))
        if not self.family_optimizer_enabled and self.model_family != "index_translate":
            from dataclasses import replace
            request = replace(request, previous_original=previous_original,
                              previous_translation=previous_translation)
            prepared = self.prompt_strategy.prepare(request)
        task._family_request = request
        if self.hy_mt2_debug:
            print(f'[DEBUG] [FAMILY OPTIMIZER] PROMPT={prepared.user_content!r}', file=sys.stderr, flush=True)
        return prepared

    def close(self):
        """Close this client's cached transports after its owner has finished."""
        with self._openai_clients_lock:
            clients = tuple(self._openai_clients.values())
            self._openai_clients.clear()
        for client in clients:
            client.close()

    def translate_preview(self, text: str, context=None, diagnostic_glossary=None):
        import numpy as np
        import re
        from dataclasses import replace
        context = context or []
        history = tuple((str(item.get("source", "")), str(item.get("target", "")))
                        for item in context)
        for source, target in history:
            if target:
                self._append_history_message(source, target)
            elif source:
                # Explicit preview context can contain sources without an existing
                # translation. Preserve that distinction for echo validation.
                if self.hy_mt2_context is not None:
                    self.hy_mt2_context.append(source)
                if self.history_size or self.family_optimizer_enabled:
                    with self._history_lock:
                        self.history_pairs.append((source, ""))
        task = TranslationTask(np.zeros(0, dtype=np.float32), (0, 0))
        task.transcript = text
        task._translation_attempts = 1
        task.start_time = datetime.now(timezone.utc)
        task._translation_timeout = self.request_timeout
        task._preview_deadline = time.perf_counter() + self.request_timeout
        attempts = []
        old_hook = self.replay_response_hook
        self.replay_response_hook = lambda task, event: attempts.append(event)
        preview_started = time.perf_counter()
        try:
            self.translate(task)
            if (task.translation_failed and getattr(task, "_family_repair", False)
                    and time.perf_counter() < task._preview_deadline
                    and not _is_task_timeout(task, task._translation_timeout)):
                task._translation_attempts = 2
                task.translation_failed = False
                task.translation_error = None
                task.translation_validation_rejected = False
                task.translation_validation_reasons = ()
                self.translate(task)
        finally:
            self.replay_response_hook = old_hook
        if time.perf_counter() >= task._preview_deadline:
            task.translation = ""
            task.translation_failed = True
            task.translation_error = "preview_deadline_expired"
            task.translation_validation_reasons = ("preview_deadline_expired",)
        request = getattr(task, "_family_request", None)
        if request is None:
            request, _ = self.prepare_translation_request(text)
        settings = getattr(self.prompt_strategy, "optimizer_settings", None)
        glossary = dict(self.glossary if diagnostic_glossary is None else diagnostic_glossary)
        if self._preview_glossary_folder:
            from .hy_mt2_glossary import load_glossary_folder
            for source, target in load_glossary_folder(self._preview_glossary_folder).items():
                glossary.setdefault(source, target)
        if self._preview_aliases:
            import json
            for source, target in json.loads(self._preview_aliases).items():
                glossary.setdefault(source, target)
        terms = _matching_glossary(text, glossary, settings.max_terms if settings else 10)
        diagnostic_request = replace(request, glossary=terms,
            preserve_elements=tuple(dict.fromkeys(re.findall(r"https?://[^\s<>]+|(?<!\w)@[A-Za-z0-9_]+", text))))
        reasons = getattr(task, "translation_validation_reasons", ())
        if not self.family_optimizer_enabled and task.translation_error != "preview_deadline_expired":
            diagnostic_reasons = tuple(issue.code for issue in validate_translation(diagnostic_request, task.translation, history))
            reasons = tuple(dict.fromkeys(tuple(reasons) + diagnostic_reasons))
        if task.translation_failed and not reasons:
            reasons = ("translation_request_failed",)
        if not (task.translation or "").strip() and "empty_output" not in reasons:
            reasons = tuple(reasons) + ("empty_output",)
        return {"translation": task.translation or "", "glossary_hits": terms,
                "validation": [{"code": code, "severity": "error"} for code in reasons],
                "validation_enforced": self.family_optimizer_enabled, "attempts": attempts,
                "retry_count": task._translation_attempts - 1,
                "latency_ms": (time.perf_counter() - preview_started) * 1000,
                "error": task.translation_error}

    def _append_history_message(self, source_text: str, assistant_content: str):
        if self.hy_mt2_context is not None and source_text and assistant_content:
            self.hy_mt2_context.append(source_text)
        if (not self.history_size and not self.family_optimizer_enabled) or not source_text or not assistant_content:
            return
        with self._history_lock:
            self.history_pairs.append((source_text, assistant_content))

    def _record_translation_failure(self, task, exc):
        task.translation = ""
        task.translation_failed = True
        task.translation_error = str(exc)
        code = (exc.code if isinstance(exc, TranslationOutputConversionError)
                else "translation_request_failed")
        task.translation_validation_reasons = (code, "empty_output")
        if isinstance(exc, TranslationOutputConversionError):
            # Retrying inference cannot repair a missing local dependency.
            task.translation_validation_rejected = True
            task._family_repair = False

    def _validate_hy_mt2_output(self, task: TranslationTask) -> str | None:
        if not self.family_optimizer_enabled:
            return None
        request = getattr(task, "_family_request", None)
        if request is None:
            request, _ = self.prepare_translation_request(task.transcript or "", task.segment_id)
            task._family_request = request
        if request.session_id != self._context_generation or getattr(task, "_translation_expired", False) or (task.start_time is not None and _is_task_timeout(task, getattr(task, "_translation_timeout", 0))):
            reasons = ("stale_result",)
        else:
            with self._history_lock:
                history = tuple(self.history_pairs)
            reasons = tuple(issue.code for issue in validate_translation(request, task.translation, history))
        task.translation_validation_reasons = reasons
        if not reasons:
            task.translation_error = None
            task.translation_validation_rejected = False
            task.translation_failed = False
            task._family_repair = False
            return None
        task.translation = ""
        task.translation_failed = True
        task._family_repair = reasons != ("stale_result",)
        task.translation_validation_rejected = (getattr(task, "_translation_attempts", 0) != 1
                                                or reasons == ("stale_result",))
        task.translation_error = reasons[0]
        return reasons[0]

    def _translate_by_gpt(self, translation_task: TranslationTask):
        # https://platform.openai.com/docs/api-reference/chat/create?lang=python
        from openai import OpenAI
        import httpx

        if self.api_key is None:
            ApiKeyPool.use_openai_api()
        api_key = self.api_key if self.api_key is not None else os.environ.get("OPENAI_API_KEY")
        client_key = api_key or ""
        with self._openai_clients_lock:
            client = self._openai_clients.get(client_key)
            if client is None:
                client = OpenAI(
                    api_key=api_key,
                    max_retries=0,
                    base_url=self.base_url,
                    timeout=self.request_timeout,
                    http_client=httpx.Client(proxy=self.proxy),
                )
                self._openai_clients[client_key] = client
        prepared = self._prepare_prompt(translation_task)
        messages = []
        if prepared.system_instruction:
            messages.append({'role': 'system', 'content': prepared.system_instruction})
        messages.append({'role': 'user', 'content': prepared.user_content})

        try:
            deadline = getattr(translation_task, "_preview_deadline", None)
            if deadline is not None:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    raise TimeoutError("preview_deadline_expired")
                client = client.with_options(timeout=remaining, max_retries=0)
            is_official_openai = self.provider == "openai"
            is_reasoning_model = str(self.model).lower().startswith(("o1", "o3", "o4", "gpt-5"))
            if is_official_openai and is_reasoning_model:
                completion = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    reasoning_effort='minimal',
                    max_completion_tokens=self.max_output_tokens,
                )
            else:
                create_params = {
                    'model': self.model,
                    'messages': messages,
                    'temperature': prepared.temperature,
                    'top_p': prepared.top_p,
                }
                if is_official_openai:
                    create_params["max_completion_tokens"] = self.max_output_tokens
                    if prepared.output_format == "json":
                        create_params['response_format'] = {"type": "json_object"}
                    else:
                        create_params['stop'] = ['\n']
                else:
                    create_params["max_tokens"] = self.max_output_tokens
                    if self.model_family == "hy_mt2":
                        create_params["extra_body"] = {
                            "top_k": prepared.top_k,
                            "repeat_penalty": prepared.repetition_penalty,
                        }
                
                completion = client.chat.completions.create(**create_params)

            raw_content = completion.choices[0].message.content
            finish_reason = getattr(completion.choices[0], 'finish_reason', None)
            usage = getattr(completion, 'usage', None)
            message = completion.choices[0].message
            dump_message = getattr(message, 'model_dump', None)
            message_fields = tuple(dump_message(exclude_none=True).keys()) if callable(dump_message) else ('content',)
            # Some local server parsers classify this translation-only family's
            # answer as reasoning. Scope compatibility to completed Index replies.
            content_field = 'content'
            if (self.model_family == 'index_translate' and self.provider != 'openai'
                    and not str(raw_content or '').strip() and finish_reason == 'stop'
                    and not getattr(message, 'tool_calls', None)
                    and not getattr(message, 'function_call', None)
                    and not getattr(message, 'refusal', None)):
                alternate = getattr(completion.choices[0].message, 'reasoning_content', None)
                if isinstance(alternate, str) and alternate.strip():
                    import re
                    if not re.search(r'<think>|</think>|【源文】|(?:^|\n)\s*(?:思考过程|推理过程|Let me think)', alternate, re.IGNORECASE):
                        raw_content = alternate
                        content_field = 'reasoning_content_compat'
            parsed_translation = parse_translation_output(
                raw_content,
                prepared.output_format,
            )
            translation_task.translation = normalize_translation_output(
                parsed_translation, self.translation_target_language,
            )
            validation_reason = self._validate_hy_mt2_output(translation_task)
            if self.hy_mt2_debug:
                print(f'[DEBUG] [FAMILY OPTIMIZER] RAW_OUTPUT={raw_content!r} VALIDATION={validation_reason!r}',
                      file=sys.stderr, flush=True)
                print(f'[DEBUG] [FAMILY OPTIMIZER] FINISH_REASON={finish_reason!r} '
                      f'PROMPT_TOKENS={getattr(usage, "prompt_tokens", None)} '
                      f'COMPLETION_TOKENS={getattr(usage, "completion_tokens", None)} MESSAGE_FIELDS={message_fields!r}',
                      file=sys.stderr, flush=True)
                if content_field != 'content':
                    print('[DEBUG] [FAMILY OPTIMIZER] CONTENT_FIELD=reasoning_content_compat', file=sys.stderr, flush=True)
            if self.replay_response_hook is not None:
                try:
                    self.replay_response_hook(translation_task, {
                        "request_id": getattr(completion, "id", None),
                        "provider": self.provider,
                        "model": self.model,
                        "raw_model_response": raw_content,
                        "finish_reason": finish_reason,
                        "content_field": content_field,
                        "completion_tokens": getattr(usage, 'completion_tokens', None),
                        "message_fields": message_fields,
                        "reasoning_content": getattr(completion.choices[0].message, 'reasoning_content', None),
                        "parsed_translation": parsed_translation,
                        "parsing_failure_reason": None if parsed_translation else "empty_parsed_translation",
                        "output_validation_reason": validation_reason,
                        "latency_ms": (time.perf_counter() - translation_task._llm_latency_started_at) * 1000,
                    })
                except Exception:
                    pass  # Replay storage must never change translation outcome.
            usage = getattr(completion, "usage", None)
            if usage is not None:
                translation_task.translation_prompt_tokens = getattr(usage, "prompt_tokens", None)
                translation_task.translation_completion_tokens = getattr(usage, "completion_tokens", None)
            
            # 調試：顯示翻譯結果
            if self.model_family not in {"hy_mt2", "index_translate"} or self.hy_mt2_debug:
                print(f'[DEBUG] GPT 響應: {translation_task.translation[:100] if translation_task.translation else "空"}', flush=True)
            
        except Exception as e:
            self._record_translation_failure(translation_task, e)
            if self.replay_response_hook is not None:
                try:
                    self.replay_response_hook(translation_task, {
                        "request_id": getattr(locals().get("completion"), "id", None),
                        "provider": self.provider, "model": self.model,
                        "raw_model_response": locals().get("raw_content"),
                        "parsed_translation": locals().get("parsed_translation"),
                        "output_validation_reason": getattr(e, "code", "translation_request_failed"),
                        "parsing_failure_reason": type(e).__name__ if "raw_content" in locals() else None,
                        "request_failure_reason": type(e).__name__ if "raw_content" not in locals() else None,
                        "request_failure_status": getattr(e, "status_code", None),
                        "latency_ms": (time.perf_counter() - translation_task._llm_latency_started_at) * 1000,
                    })
                except Exception:
                    pass
            print(f'[ERROR] GPT 翻譯錯誤: {e}', flush=True)
            return
        if not getattr(translation_task, "_translation_expired", False):
            self._append_history_message(translation_task.transcript, translation_task.translation)

    def _translate_by_gemini(self, translation_task: TranslationTask):
        # https://ai.google.dev/tutorials/python_quickstart
        from google import genai
        from google.genai import types

        ApiKeyPool.use_google_api()

        http_options = {}
        if self.proxy:
            http_options['client_args'] = {'proxy': self.proxy}

        if self.gemini_base_url:
            http_options['base_url'] = self.gemini_base_url

        client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"), http_options=http_options)

        prepared = self._prepare_prompt(translation_task)
        messages = [{'role': 'user', 'parts': [{'text': prepared.user_content}]}]

        config = types.GenerateContentConfig(
            candidate_count=1,
            temperature=prepared.temperature,
            top_p=prepared.top_p,
            max_output_tokens=self.max_output_tokens,
            stop_sequences=None if prepared.output_format == "json" else ['\n'],
            system_instruction=prepared.system_instruction,
            thinking_config=types.ThinkingConfig(include_thoughts=False),
            response_mime_type='application/json' if prepared.output_format == "json" else 'text/plain',
            safety_settings=[
                types.SafetySetting(category='HARM_CATEGORY_HARASSMENT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_HATE_SPEECH', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_SEXUALLY_EXPLICIT', threshold='BLOCK_NONE'),
                types.SafetySetting(category='HARM_CATEGORY_DANGEROUS_CONTENT', threshold='BLOCK_NONE')
            ])

        try:
            response = client.models.generate_content(model=self.model, contents=messages, config=config)
            translation_task.translation = normalize_translation_output(
                parse_translation_output(response.text, prepared.output_format),
                self.translation_target_language,
            )
            self._validate_hy_mt2_output(translation_task)
        except Exception as e:
            self._record_translation_failure(translation_task, e)
            print(e)
            return
        if not getattr(translation_task, "_translation_expired", False):
            self._append_history_message(translation_task.transcript, translation_task.translation)

    def translate(self, translation_task: TranslationTask):
        llm_started_at = time.perf_counter()
        translation_task.latency_trace.translation_started_at = llm_started_at
        translation_task._llm_latency_started_at = llm_started_at
        translation_task.translation_provider = self.provider
        translation_task.translation_model = self.model
        if translation_task.translation_queued_at is not None:
            translation_task.translation_queue_latency_ms = (
                llm_started_at - translation_task.translation_queued_at
            ) * 1000
        try:
            self.provider_adapter.translate(self, translation_task)
            if translation_task.translation:
                translation_task.translation = normalize_translation_output(
                    translation_task.translation, self.translation_target_language,
                )
        except Exception as exc:
            self._record_translation_failure(translation_task, exc)
            print(f'[ERROR] Translation pipeline: {exc}', flush=True)
        finally:
            translation_task.latency_trace.translation_finished_at = time.perf_counter()
            translation_task.llm_latency_ms = (translation_task.latency_trace.translation_finished_at - llm_started_at) * 1000
            translation_task.total_latency_ms = (
                time.perf_counter() - translation_task.created_at_monotonic
            ) * 1000
            translation_task.translation_result = TranslationResult(
                segment_id=translation_task.segment_id,
                translation=translation_task.translation or "",
                provider=self.provider,
                model=self.model,
                queue_latency_ms=translation_task.translation_queue_latency_ms,
                generation_latency_ms=translation_task.llm_latency_ms,
                prompt_tokens=translation_task.translation_prompt_tokens,
                completion_tokens=translation_task.translation_completion_tokens,
                error=translation_task.translation_error,
                validation_reasons=getattr(translation_task, "translation_validation_reasons", ()),
                matched_terms=getattr(getattr(translation_task, "_family_request", None), "glossary", {}),
                retry_count=max(0, translation_task._translation_attempts - 1),
            )
            if self.hy_mt2_debug:
                print(f'[DEBUG] [FAMILY OPTIMIZER] OUTPUT={translation_task.translation!r}', file=sys.stderr, flush=True)
            if translation_task.translation:
                try:
                    self.glossary_auditor.audit(translation_task)
                except Exception as audit_error:
                    print(f'[WARNING] Translation glossary audit failed: {audit_error}', flush=True)
            translation_task._translation_inflight = False


class ParallelTranslator(LoopWorkerBase):
    def __init__(
        self,
        llm_client: LLMClient,
        timeout: int,
        retry_if_translation_fails: bool,
        max_concurrency: int = 2,
    ):
        self.llm_client = llm_client
        self.timeout = timeout
        self.retry_if_translation_fails = retry_if_translation_fails
        self.max_concurrency = max(1, int(max_concurrency))
        self.processing_queue = deque()
        self._scheduler_events = queue.Queue()
        self._timed_out_inflight = set()

    def _trigger(self, translation_task: TranslationTask):
        if translation_task._translation_inflight:
            return
        if not translation_task.start_time:
            translation_task.start_time = datetime.now(timezone.utc)
        if translation_task.translation_queued_at is None:
            translation_task.translation_queued_at = time.perf_counter()
        if translation_task.latency_trace.translation_queued_at is None:
            translation_task.latency_trace.translation_queued_at = translation_task.translation_queued_at
        translation_task._translation_timeout = getattr(self, "timeout", 0)
        translation_task.translation_failed = False
        translation_task.translation_error = None
        translation_task.llm_latency_ms = None
        translation_task._translation_attempts += 1
        translation_task._translation_inflight = True
        thread = threading.Thread(target=self._translate_and_notify, args=(translation_task,))
        thread.daemon = True
        thread.start()

    def _translate_and_notify(self, translation_task: TranslationTask):
        try:
            self.llm_client.translate(translation_task)
        finally:
            self._scheduler_events.put(("completed", translation_task))

    def _retrigger_failed_tasks(self):
        for task in self.processing_queue:
            if (
                task.translation_failed
                and not task._translation_inflight
                and not task.translation_validation_rejected
                and task._translation_attempts < 2
                and not _is_task_timeout(task, self.timeout)
            ):
                self._trigger(task)
                print(f'[DEBUG] Translation retry scheduled: {task.transcript}', file=sys.stderr, flush=True)

    def _mark_timeout_latency(self, task: TranslationTask):
        if task.llm_latency_ms is None and task._llm_latency_started_at is not None:
            task.llm_latency_ms = (time.perf_counter() - task._llm_latency_started_at) * 1000

    def _get_results(self):
        results = []
        while self.processing_queue and (
                (self.processing_queue[0].translation and self.processing_queue[0].llm_latency_ms is not None) or
                _is_task_timeout(self.processing_queue[0], self.timeout) or
                (
                    self.processing_queue[0].translation_failed
                    and self.processing_queue[0].llm_latency_ms is not None
                    and (
                        self.processing_queue[0].translation_validation_rejected
                        or
                        not self.retry_if_translation_fails
                        or self.processing_queue[0]._translation_attempts >= 2
                    )
                )):
            task = self.processing_queue.popleft()
            if _is_task_timeout(task, self.timeout):
                task._translation_expired = True
            if _is_task_timeout(task, self.timeout) and task._translation_inflight:
                # The Python thread cannot be force-cancelled. Keep counting it
                # against concurrency until its provider call really returns;
                # otherwise repeated timeouts can create unbounded requests.
                self._timed_out_inflight.add(task)
            if not task.translation:
                if _is_task_timeout(task, self.timeout):
                    self._mark_timeout_latency(task)
                    print(f'[WARNING] Translation timeout: {task.transcript}', file=sys.stderr, flush=True)
                else:
                    print(f'[WARNING] Translation failed: {task.transcript}', file=sys.stderr, flush=True)
            results.append(task)
        return results

    def loop(self, input_queue: queue.SimpleQueue[TranslationTask], output_queue: queue.SimpleQueue[TranslationTask]):
        pending_input = deque()
        input_complete = False

        def forward_input():
            while True:
                task = input_queue.get()
                self._scheduler_events.put(("input", task))
                if task is None:
                    return

        input_thread = threading.Thread(target=forward_input, daemon=True)
        input_thread.start()

        while True:
            # Retire completed work before checking capacity.  Doing this after
            # the scheduling block leaves processing_queue artificially full;
            # with max_concurrency=1 the next pending subtitle then sleeps until
            # an unrelated future input event wakes the scheduler.
            finished_tasks = self._get_results()
            for task in finished_tasks:
                output_queue.put(task)
            if self.retry_if_translation_fails:
                self._retrigger_failed_tasks()

            active_count = (
                sum(task._translation_inflight for task in self.processing_queue)
                + len(self._timed_out_inflight)
            )
            while (
                pending_input
                and len(self.processing_queue) < self.max_concurrency
                and active_count < self.max_concurrency
            ):
                task = pending_input.popleft()
                self.processing_queue.append(task)
                self._trigger(task)
                active_count += 1

            if input_complete and not pending_input and not self.processing_queue:
                output_queue.put(None)
                break

            wait_timeout = None
            if self.timeout != 0.0 and self.processing_queue:
                remaining = [
                    self.timeout - (datetime.now(timezone.utc) - task.start_time).total_seconds()
                    for task in self.processing_queue
                    if task.start_time is not None
                ]
                if remaining:
                    wait_timeout = max(0.0, min(remaining))
            try:
                event, task = self._scheduler_events.get(timeout=wait_timeout)
            except queue.Empty:
                continue
            if event == "input":
                if task is None:
                    input_complete = True
                else:
                    pending_input.append(task)
            elif event == "completed":
                self._timed_out_inflight.discard(task)


class SerialTranslator(LoopWorkerBase):

    def __init__(self, llm_client: LLMClient, timeout: int, retry_if_translation_fails: bool):
        self.llm_client = llm_client
        self.timeout = timeout
        self.retry_if_translation_fails = retry_if_translation_fails

    def _trigger(self, translation_task: TranslationTask):
        if not translation_task.start_time:
            translation_task.start_time = datetime.now(timezone.utc)
        if translation_task.translation_queued_at is None:
            translation_task.translation_queued_at = time.perf_counter()
        if translation_task.latency_trace.translation_queued_at is None:
            translation_task.latency_trace.translation_queued_at = translation_task.translation_queued_at
        translation_task._translation_timeout = getattr(self, "timeout", 0)
        translation_task.translation_failed = False
        translation_task.translation_error = None
        translation_task.llm_latency_ms = None
        translation_task._translation_attempts += 1
        thread = threading.Thread(target=self.llm_client.translate, args=(translation_task,))
        thread.daemon = True
        thread.start()

    def loop(self, input_queue: queue.SimpleQueue[TranslationTask], output_queue: queue.SimpleQueue[TranslationTask]):
        current_task = None
        while True:
            if current_task:
                if ((current_task.translation and current_task.llm_latency_ms is not None) or
                        (current_task.translation_failed and current_task.llm_latency_ms is not None) or
                        _is_task_timeout(current_task, self.timeout)):
                    if not current_task.translation:
                        if _is_task_timeout(current_task, self.timeout):
                            if current_task.llm_latency_ms is None and current_task._llm_latency_started_at is not None:
                                current_task.llm_latency_ms = (time.perf_counter() - current_task._llm_latency_started_at) * 1000
                            print(f'[WARNING] Translation timeout: {current_task.transcript}', file=sys.stderr, flush=True)
                        else:
                            print(f'[WARNING] Translation failed: {current_task.transcript}', file=sys.stderr, flush=True)
                            if (self.retry_if_translation_fails and not current_task.translation_validation_rejected
                                    and current_task._translation_attempts < 2):
                                self._trigger(current_task)
                                time.sleep(1)
                                continue
                    if _is_task_timeout(current_task, self.timeout):
                        current_task._translation_expired = True
                    output_queue.put(current_task)
                    current_task = None

            if current_task is None and not input_queue.empty():
                current_task = input_queue.get()
                if current_task is None:
                    output_queue.put(None)
                    break
                self._trigger(current_task)
            time.sleep(0.1)
