from __future__ import annotations

import queue
import re
import time

from .common import LoopWorkerBase, TranslationTask


_SENTENCE_END_RE = re.compile(r"[。！？!?…．.][」』”’）)\]]?$")
_CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


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
    ):
        self.deduplicate_overlap = bool(deduplicate_overlap)
        self.assembler_enabled = bool(assembler_enabled)
        self.assembler_wait_seconds = max(0.0, int(assembler_wait_ms)) / 1000
        self.assembler_max_duration = max(0.1, float(assembler_max_duration))
        self.assembler_gap_threshold = max(0.0, float(assembler_gap_threshold))
        self.previous_transcript = ""

    @staticmethod
    def _is_complete(task: TranslationTask) -> bool:
        return bool(_SENTENCE_END_RE.search(str(task.transcript or "").strip()))

    def _prepare(self, task: TranslationTask) -> TranslationTask | None:
        transcript = str(task.transcript or "").strip()
        if self.deduplicate_overlap:
            transcript = remove_text_overlap(self.previous_transcript, transcript)
        if not transcript:
            return None
        self.previous_transcript = _join_text(self.previous_transcript, transcript)[-500:]
        task.transcript = transcript
        return task

    @staticmethod
    def _merge(first: TranslationTask, second: TranslationTask) -> TranslationTask:
        first.transcript = _join_text(first.transcript, second.transcript)
        first.raw_transcript = _join_text(first.raw_transcript, second.raw_transcript)
        first.time_range = (first.time_range[0], second.time_range[1])
        if first.asr_latency_ms is not None and second.asr_latency_ms is not None:
            first.asr_latency_ms += second.asr_latency_ms
        return first

    def _can_merge(self, first: TranslationTask, second: TranslationTask) -> bool:
        duration = second.time_range[1] - first.time_range[0]
        gap = max(0.0, second.time_range[0] - first.time_range[1])
        return (
            not self._is_complete(first)
            and duration <= self.assembler_max_duration
            and gap <= self.assembler_gap_threshold
        )

    @staticmethod
    def _emit(task: TranslationTask, output_queue: queue.SimpleQueue[TranslationTask]) -> None:
        if task.translation_queued_at is None:
            task.translation_queued_at = time.perf_counter()
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
                self._emit(pending, output_queue)
                pending = None
                continue

            wait_started = time.perf_counter()
            try:
                task = input_queue.get(timeout=self.assembler_wait_seconds)
            except queue.Empty:
                self._emit(pending, output_queue)
                pending = None
                continue

            if task is None:
                input_complete = True
                self._emit(pending, output_queue)
                output_queue.put(None)
                break

            task = self._prepare(task)
            if task is None:
                elapsed = time.perf_counter() - wait_started
                if elapsed >= self.assembler_wait_seconds:
                    self._emit(pending, output_queue)
                    pending = None
                continue

            if self._can_merge(pending, task):
                pending = self._merge(pending, task)
            else:
                self._emit(pending, output_queue)
                pending = task
