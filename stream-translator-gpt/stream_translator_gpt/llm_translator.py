import os
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
)
from .translation_glossary_auditor import TranslationGlossaryAuditor

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


class GeminiProvider(TranslationProvider):
    name = "gemini"

    def translate(self, client: "LLMClient", task: TranslationTask) -> None:
        client._translate_by_gemini(task)


_PROVIDER_TYPES = {
    "openai": OpenAIProvider,
    "openai_compatible": OpenAICompatibleProvider,
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
                 glossary_audit_enabled: bool = False) -> None:
        if llm_type not in (self.LLM_TYPE.GPT, self.LLM_TYPE.GEMINI):
            raise ValueError(f'Unknow LLM type: {llm_type}')
        print(f'{INFO}Using {model} API as translation engine.')
        self.llm_type = llm_type
        self.model = model
        self.prompt = prompt
        self.history_size = history_size
        self.proxy = proxy
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
        self.max_output_tokens = max(16, int(max_output_tokens or 128))
        self.history_pairs = deque(maxlen=max(0, history_size))
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

    def _prepare_prompt(self, task: TranslationTask):
        previous_original, previous_translation = self._history_snapshot()
        request = TranslationRequest(
            segment_id=task.segment_id,
            source_text=task.transcript or "",
            previous_original=previous_original,
            previous_translation=previous_translation,
            glossary=self.glossary,
        )
        return self.prompt_strategy.prepare(request)

    def _append_history_message(self, source_text: str, assistant_content: str):
        if not self.history_size or not source_text or not assistant_content:
            return
        with self._history_lock:
            self.history_pairs.append((source_text, assistant_content))

    def _translate_by_gpt(self, translation_task: TranslationTask):
        # https://platform.openai.com/docs/api-reference/chat/create?lang=python
        from openai import OpenAI
        import httpx

        ApiKeyPool.use_openai_api()
        api_key = os.environ.get("OPENAI_API_KEY")
        client_key = api_key or ""
        with self._openai_clients_lock:
            client = self._openai_clients.get(client_key)
            if client is None:
                client = OpenAI(
                    api_key=api_key,
                    http_client=httpx.Client(proxy=self.proxy),
                )
                self._openai_clients[client_key] = client
        prepared = self._prepare_prompt(translation_task)
        messages = []
        if prepared.system_instruction:
            messages.append({'role': 'system', 'content': prepared.system_instruction})
        messages.append({'role': 'user', 'content': prepared.user_content})

        try:
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

            translation_task.translation = parse_translation_output(
                completion.choices[0].message.content,
                prepared.output_format,
            )
            usage = getattr(completion, "usage", None)
            if usage is not None:
                translation_task.translation_prompt_tokens = getattr(usage, "prompt_tokens", None)
                translation_task.translation_completion_tokens = getattr(usage, "completion_tokens", None)
            
            # 調試：顯示翻譯結果
            print(f'[DEBUG] GPT 響應: {translation_task.translation[:100] if translation_task.translation else "空"}', flush=True)
            
        except Exception as e:
            translation_task.translation_failed = True
            translation_task.translation_error = str(e)
            print(f'[ERROR] GPT 翻譯錯誤: {e}', flush=True)
            return
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
            translation_task.translation = parse_translation_output(response.text, prepared.output_format)
        except Exception as e:
            translation_task.translation_failed = True
            translation_task.translation_error = str(e)
            print(e)
            return
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
            )
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
        translation_task.translation_failed = False
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
                and task._translation_attempts < 2
                and not _is_task_timeout(task, self.timeout)
            ):
                self._trigger(task)
                print(f'Translation failed: {task.transcript}')

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
                        not self.retry_if_translation_fails
                        or self.processing_queue[0]._translation_attempts >= 2
                    )
                )):
            task = self.processing_queue.popleft()
            if _is_task_timeout(task, self.timeout) and task._translation_inflight:
                # The Python thread cannot be force-cancelled. Keep counting it
                # against concurrency until its provider call really returns;
                # otherwise repeated timeouts can create unbounded requests.
                self._timed_out_inflight.add(task)
            if not task.translation:
                if _is_task_timeout(task, self.timeout):
                    self._mark_timeout_latency(task)
                    print(f'Translation timeout: {task.transcript}')
                else:
                    print(f'Translation failed: {task.transcript}')
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
        translation_task.translation_failed = False
        translation_task.llm_latency_ms = None
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
                            print(f'Translation timeout: {current_task.transcript}')
                        else:
                            print(f'Translation failed: {current_task.transcript}')
                            if self.retry_if_translation_fails:
                                self._trigger(current_task)
                                time.sleep(1)
                                continue
                    output_queue.put(current_task)
                    current_task = None

            if current_task is None and not input_queue.empty():
                current_task = input_queue.get()
                if current_task is None:
                    output_queue.put(None)
                    break
                self._trigger(current_task)
            time.sleep(0.1)
