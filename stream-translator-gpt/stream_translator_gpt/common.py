import os
import re
import threading
import itertools
import time
import uuid
import io
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from urllib.parse import urlparse

import numpy as np

SAMPLE_RATE = 16000
SAMPLES_PER_FRAME = 512  # Requested by silero-vad >= v5
FRAME_DURATION = SAMPLES_PER_FRAME / SAMPLE_RATE

RED = '\033[91m'
YELLOW = '\033[93m'
GREEN = "\033[32m"
BOLD = '\033[1m'
ENDC = '\033[0m'

INFO = f'{GREEN}[INFO]{ENDC} '
WARNING = f'{YELLOW}[WARNING]{ENDC} '
ERROR = f'{RED}[ERROR]{ENDC} '


def configure_utf8_stdio() -> None:
    """Keep Windows worker-thread output from crashing on non-CP950 text."""
    if os.name != "nt":
        return
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONUNBUFFERED"] = "1"
    import sys
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        try:
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
            continue
        except (AttributeError, OSError, ValueError):
            pass
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            try:
                setattr(
                    sys,
                    stream_name,
                    io.TextIOWrapper(buffer, encoding="utf-8", errors="replace", line_buffering=True),
                )
            except (OSError, ValueError):
                pass


def _elapsed_ms(start: float | None, end: float | None) -> float | None:
    if start is None or end is None or end < start:
        return None
    return (end - start) * 1000


@dataclass
class LatencyTrace:
    """Monotonic timestamps carried with one subtitle through the pipeline."""

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    merged_trace_ids: list[str] = field(default_factory=list)
    audio_duration_ms: float | None = None
    capture_started_at: float | None = None
    first_speech_at: float | None = None
    last_speech_at: float | None = None
    slice_emitted_at: float | None = None
    asr_queued_at: float | None = None
    asr_started_at: float | None = None
    asr_finished_at: float | None = None
    asr_queue_accumulated_ms: float | None = None
    asr_inference_accumulated_ms: float | None = None
    assembler_received_at: float | None = None
    assembler_emitted_at: float | None = None
    translation_queued_at: float | None = None
    translation_started_at: float | None = None
    translation_finished_at: float | None = None
    subtitle_delivered_at: float | None = None

    def merge(self, other: "LatencyTrace") -> None:
        self.merged_trace_ids.extend([other.trace_id, *other.merged_trace_ids])
        if other.audio_duration_ms is not None:
            self.audio_duration_ms = (self.audio_duration_ms or 0.0) + other.audio_duration_ms
        for accumulator in ("asr_queue_accumulated_ms", "asr_inference_accumulated_ms"):
            incoming = getattr(other, accumulator)
            if incoming is not None:
                setattr(self, accumulator, (getattr(self, accumulator) or 0.0) + incoming)
        for name in ("first_speech_at", "capture_started_at", "asr_queued_at", "asr_started_at"):
            current = getattr(self, name)
            incoming = getattr(other, name)
            if incoming is not None and (current is None or incoming < current):
                setattr(self, name, incoming)
        for name in ("last_speech_at", "slice_emitted_at", "asr_finished_at", "assembler_received_at"):
            current = getattr(self, name)
            incoming = getattr(other, name)
            if incoming is not None and (current is None or incoming > current):
                setattr(self, name, incoming)

    def metrics(self) -> dict[str, float | str | list[str] | None]:
        audio_duration_ms = self.audio_duration_ms
        asr_inference_ms = self.asr_inference_accumulated_ms
        if asr_inference_ms is None:
            asr_inference_ms = _elapsed_ms(self.asr_started_at, self.asr_finished_at)
        asr_queue_ms = self.asr_queue_accumulated_ms
        if asr_queue_ms is None:
            asr_queue_ms = _elapsed_ms(self.asr_queued_at, self.asr_started_at)
        metrics = {
            "trace_id": self.trace_id,
            "merged_trace_ids": list(self.merged_trace_ids),
            "capture_wait_ms": _elapsed_ms(self.capture_started_at, self.slice_emitted_at),
            "speech_to_slice_ms": _elapsed_ms(self.last_speech_at, self.slice_emitted_at),
            "audio_duration_ms": audio_duration_ms,
            "asr_queue_ms": asr_queue_ms,
            "asr_inference_ms": asr_inference_ms,
            "asr_realtime_factor": (
                asr_inference_ms / audio_duration_ms
                if asr_inference_ms is not None and audio_duration_ms and audio_duration_ms > 0
                else None
            ),
            "assembler_wait_ms": _elapsed_ms(self.assembler_received_at, self.assembler_emitted_at),
            "translation_queue_ms": _elapsed_ms(self.translation_queued_at, self.translation_started_at),
            "translation_inference_ms": _elapsed_ms(self.translation_started_at, self.translation_finished_at),
            "delivery_ms": _elapsed_ms(self.translation_finished_at, self.subtitle_delivered_at),
            "end_to_end_ms": _elapsed_ms(self.last_speech_at, self.subtitle_delivered_at),
        }
        return metrics


class TranslationTask:
    _segment_counter = itertools.count(1)
    _segment_counter_lock = threading.Lock()

    def __init__(self, audio: np.array, time_range: tuple[float, float], latency_trace: LatencyTrace | None = None):
        with self._segment_counter_lock:
            self.segment_id = next(self._segment_counter)
        self.audio = audio
        self.latency_trace = latency_trace or LatencyTrace()
        self.raw_transcript = None
        self.transcript = None
        self.translation = None
        self.time_range = time_range
        self.start_time = None
        self.translation_failed = False
        self.asr_latency_ms = None
        self.llm_latency_ms = None
        self._llm_latency_started_at = None
        self.created_at_monotonic = time.perf_counter()
        self.translation_queued_at = None
        self.translation_queue_latency_ms = None
        self.total_latency_ms = None
        self.translation_provider = None
        self.translation_model = None
        self.translation_error = None
        self.translation_result = None
        self.translation_prompt_tokens = None
        self.translation_completion_tokens = None
        self._translation_attempts = 0
        self._translation_inflight = False


class LoopWorkerBase(ABC):

    @abstractmethod
    def loop(self):
        pass


def start_daemon_thread(func, *args, **kwargs):
    thread = threading.Thread(target=func, args=args, kwargs=kwargs)
    thread.daemon = True
    thread.start()
    return thread


def sec2str(second: float):
    dt = datetime.fromtimestamp(second, tz=timezone.utc)
    result = dt.strftime('%H:%M:%S')
    result += ',' + f'{int(second * 1000 % 1000):03d}'
    return result


class ApiKeyPool():

    @classmethod
    def init(cls, openai_api_key, google_api_key):
        cls.openai_api_key_list = [key.strip() for key in openai_api_key.split(',')] if openai_api_key else None
        cls.openai_api_key_index = 0
        cls.use_openai_api()
        cls.google_api_key_list = [key.strip() for key in google_api_key.split(',')] if google_api_key else None
        cls.google_api_key_index = 0
        cls.use_google_api()

    @classmethod
    def use_openai_api(cls):
        if not cls.openai_api_key_list:
            return
        os.environ['OPENAI_API_KEY'] = cls.openai_api_key_list[cls.openai_api_key_index]
        cls.openai_api_key_index = (cls.openai_api_key_index + 1) % len(cls.openai_api_key_list)

    @classmethod
    def use_google_api(cls):
        if not cls.google_api_key_list:
            return
        os.environ['GOOGLE_API_KEY'] = cls.google_api_key_list[cls.google_api_key_index]
        cls.google_api_key_index = (cls.google_api_key_index + 1) % len(cls.google_api_key_list)


class ClientPool:

    @classmethod
    def init(cls, openai_api_key, google_api_key, proxy=None, google_base_url=None):
        ApiKeyPool.init(openai_api_key=openai_api_key, google_api_key=google_api_key)
        cls._openai_clients = []
        cls._openai_index = 0
        if openai_api_key:
            try:
                from openai import OpenAI
                import httpx
                for key in openai_api_key.split(','):
                    key = key.strip()
                    client = OpenAI(api_key=key, http_client=httpx.Client(proxy=proxy, verify=False))
                    cls._openai_clients.append(client)
            except Exception as e:
                import sys
                print(f"[ERROR] Failed to initialize OpenAI ClientPool: {e}", file=sys.stderr, flush=True)

        cls._google_clients = []
        cls._google_index = 0
        if google_api_key:
            try:
                from google import genai
                http_options = {'client_args': {'verify': False}}
                if proxy:
                    http_options['client_args']['proxy'] = proxy
                if google_base_url:
                    http_options['base_url'] = google_base_url
                for key in google_api_key.split(','):
                    key = key.strip()
                    client = genai.Client(api_key=key, http_options=http_options)
                    cls._google_clients.append(client)
            except Exception as e:
                import sys
                print(f"[ERROR] Failed to initialize Google ClientPool: {e}", file=sys.stderr, flush=True)

    @classmethod
    def get_openai_client(cls):
        if not cls._openai_clients:
            return None
        client = cls._openai_clients[cls._openai_index]
        cls._openai_index = (cls._openai_index + 1) % len(cls._openai_clients)
        return client

    @classmethod
    def get_google_client(cls):
        if not cls._google_clients:
            return None
        client = cls._google_clients[cls._google_index]
        cls._google_index = (cls._google_index + 1) % len(cls._google_clients)
        return client


def is_url(address):
    parsed_url = urlparse(address)

    if parsed_url.scheme and parsed_url.scheme != 'file':
        if parsed_url.netloc or (parsed_url.scheme in ['mailto', 'tel', 'data']):
            return True

    if parsed_url.scheme == 'file':
        return False

    if parsed_url.netloc:
        return True

    if os.name == 'nt':
        if re.match(r'^[a-zA-Z]:[\\/]', address):
            return False
        if address.startswith('\\\\') or address.startswith('//'):
            return False
        if '\\' in address and '/' not in address:
            return False

    if address.startswith('/') or address.startswith('./') or address.startswith('../'):
        return False

    if '/' in address or (os.name == 'nt' and '\\' in address):
        if not parsed_url.scheme and not parsed_url.netloc:
            return False

    return False
