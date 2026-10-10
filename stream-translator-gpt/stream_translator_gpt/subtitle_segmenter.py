from __future__ import annotations

import queue
import re
import sys
import time
import unicodedata

from .common import LoopWorkerBase, TranslationTask, sec2str


_SENTENCE_END_RE = re.compile(r"[。！？!?…．.][」』”’）)\]]?$")
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
_JAPANESE_RE = re.compile(r'[\u3040-\u30ff]')
_DEPENDENT_JAPANESE_TAIL_RE = re.compile(r'(なんて|だって|って|[がをにへ])$')


def is_punctuation_only(text: str) -> bool:
    text = str(text or "").strip()
    return bool(text) and all(unicodedata.category(char)[0] in {"P", "Z"} for char in text)


def remove_text_overlap(previous: str, current: str, minimum_chars: int = 4) -> str:
    previous = str(previous or "").strip()
    current = str(current or "").strip()
    if not previous or not current:
        return current

    maximum = min(len(previous), len(current), 80)
    for size in range(maximum, minimum_chars - 1, -1):
        if previous[-size:].casefold() != current[:size].casefold():
            continue
        overlap = current[:size]
        if _CJK_RE.search(overlap) or size >= 8:
            return current[size:].lstrip()
    return current


def _join_text(left: str, right: str) -> str:
    left = str(left or "").rstrip()
    right = str(right or "").lstrip()
    if not left:
        return right
    if not right:
        return left
    if _CJK_RE.search(left[-1]) or _CJK_RE.search(right[0]):
        return left + right
    separator = " " if left[-1].isalnum() and right[0].isalnum() else ""
    return left + separator + right


class SubtitleSegmenter(LoopWorkerBase):
    def __init__(
        self,
        deduplicate_overlap: bool = True,
        assembler_enabled: bool = True,
        assembler_wait_ms: int = 400,
        assembler_max_duration: float = 6.0,
        assembler_gap_threshold: float = 0.8,
        print_result: bool = False,
        output_timestamps: bool = False,
    ):
        self.deduplicate_overlap = bool(deduplicate_overlap)
        self.assembler_enabled = bool(assembler_enabled)
        self.assembler_wait_seconds = max(0.0, int(assembler_wait_ms)) / 1000
        self.assembler_max_duration = max(0.1, float(assembler_max_duration))
        self.assembler_gap_threshold = max(0.0, float(assembler_gap_threshold))
        self.previous_transcript = ""
        self.print_result = bool(print_result)
        self.output_timestamps = bool(output_timestamps)
        print(f'[Assembler] policy=bounded-v2 enabled={self.assembler_enabled} '
              f'wait_ms={self.assembler_wait_seconds * 1000:g} '
              f'max_span_s={self.assembler_max_duration:g} gap_s={self.assembler_gap_threshold:g}', file=sys.stderr, flush=True)

    @staticmethod
    def _is_complete(task: TranslationTask) -> bool:
        text = str(task.transcript or "").strip()
        if getattr(task, 'audio_boundary', None) == 'max_length':
            return False
        tail = re.sub(r'[。！？!?…．.」』”’）)\]]+$', '', text)
        if _JAPANESE_RE.search(tail) and _DEPENDENT_JAPANESE_TAIL_RE.search(tail):
            return False
        return bool(_SENTENCE_END_RE.search(text))

    def _prepare(self, task: TranslationTask) -> TranslationTask | None:
        if task.latency_trace.assembler_received_at is None:
            task.latency_trace.assembler_received_at = time.perf_counter()
        transcript = str(task.transcript or "").strip()
        if self.deduplicate_overlap:
            transcript = remove_text_overlap(self.previous_transcript, transcript)
        if not transcript or is_punctuation_only(transcript):
            return None
        self.previous_transcript = _join_text(self.previous_transcript, transcript)[-500:]
        task.transcript = transcript
        print(f'[Assembler] received trace={task.latency_trace.trace_id} '
              f'at={task.latency_trace.assembler_received_at:.6f} '
              f'range={task.time_range[0]:.3f}:{task.time_range[1]:.3f} '
              f'boundary={getattr(task, "audio_boundary", None)} '
              f'complete={self._is_complete(task)}', file=sys.stderr, flush=True)
        return task

    @staticmethod
    def _merge(first: TranslationTask, second: TranslationTask) -> TranslationTask:
        left = first.transcript
        tail = re.sub(r'[。！？!?…．.」』”’）)\]]+$', '', str(left or '').strip())
        if _JAPANESE_RE.search(tail) and _DEPENDENT_JAPANESE_TAIL_RE.search(tail):
            left = tail
        first.transcript = _join_text(left, second.transcript)
        first.raw_transcript = _join_text(first.raw_transcript, second.raw_transcript)
        first.time_range = (first.time_range[0], second.time_range[1])
        if first.asr_latency_ms is not None and second.asr_latency_ms is not None:
            first.asr_latency_ms += second.asr_latency_ms
        received_at = first.latency_trace.assembler_received_at
        first.latency_trace.merge(second.latency_trace)
        # The deadline belongs to the first fragment, including after a merge.
        first.latency_trace.assembler_received_at = received_at
        first.audio_boundary = getattr(second, 'audio_boundary', None)
        return first

    def _can_merge(self, first: TranslationTask, second: TranslationTask) -> bool:
        duration = second.time_range[1] - first.time_range[0]
        gap = max(0.0, second.time_range[0] - first.time_range[1])
        return (
            not self._is_complete(first)
            and duration <= self.assembler_max_duration
            and gap <= self.assembler_gap_threshold
        )

    def _emit(self, task: TranslationTask, output_queue: queue.SimpleQueue[TranslationTask], reason: str = 'complete') -> None:
        task.latency_trace.assembler_emitted_at = time.perf_counter()
        waited = (task.latency_trace.assembler_emitted_at - task.latency_trace.assembler_received_at) * 1000
        print(f'[Assembler] trace={task.latency_trace.trace_id} '
              f'at={task.latency_trace.assembler_emitted_at:.6f} '
              f'range={task.time_range[0]:.3f}:{task.time_range[1]:.3f} '
              f'boundary={getattr(task, "audio_boundary", None)} reason={reason} '
              f'merged={len(task.latency_trace.merged_trace_ids)} wait_ms={waited:.1f}', file=sys.stderr, flush=True)
        if task.translation_queued_at is None:
            task.translation_queued_at = task.latency_trace.assembler_emitted_at
        task.latency_trace.translation_queued_at = task.translation_queued_at
        if self.print_result:
            if self.output_timestamps:
                timestamp = f'{sec2str(task.time_range[0])} --> {sec2str(task.time_range[1])}'
                print(f'{timestamp} {task.transcript}', flush=True)
            else:
                print(task.transcript, flush=True)
        output_queue.put(task)

    def loop(
        self,
        input_queue: queue.SimpleQueue[TranslationTask],
        output_queue: queue.SimpleQueue[TranslationTask],
    ):
        pending = None
        input_complete = False
        while not input_complete:
            if pending is None:
                task = input_queue.get()
                if task is None:
                    output_queue.put(None)
                    break
                pending = self._prepare(task)
                if pending is None:
                    continue

            if not self.assembler_enabled or self._is_complete(pending):
                self._emit(pending, output_queue, 'complete' if self.assembler_enabled else 'disabled')
                pending = None
                continue

            # Future audio extends the span; at the cap there is no merge budget.
            if pending.time_range[1] - pending.time_range[0] >= self.assembler_max_duration:
                self._emit(pending, output_queue, 'max_span')
                pending = None
                continue

            remaining = max(0.0, self.assembler_wait_seconds -
                            (time.perf_counter() - pending.latency_trace.assembler_received_at))
            wait_started = time.perf_counter()
            try:
                task = input_queue.get(timeout=remaining)
            except queue.Empty:
                self._emit(pending, output_queue, 'timeout')
                pending = None
                continue

            if task is None:
                input_complete = True
                self._emit(pending, output_queue, 'end_of_stream')
                output_queue.put(None)
                break

            task = self._prepare(task)
            if task is None:
                elapsed = time.perf_counter() - wait_started
                if elapsed >= self.assembler_wait_seconds:
                    self._emit(pending, output_queue, 'timeout')
                    pending = None
                continue

            if self._can_merge(pending, task):
                pending = self._merge(pending, task)
            else:
                reason = ('max_span' if task.time_range[1] - pending.time_range[0] > self.assembler_max_duration
                          else 'gap')
                self._emit(pending, output_queue, reason)
                pending = task
