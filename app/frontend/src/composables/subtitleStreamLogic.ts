import type { LatencyWindowSnapshot, SubtitleLatencyTrace } from '../services/api';
export type SubtitleLine = {
  id: number;
  original: string;
  translated: string;
  displayOriginal: string;
  displayTranslated: string;
  timestamp: Date;
  timestamp_id?: string;
  asr_latency_ms?: number | null;
  llm_latency_ms?: number | null;
  translation_retry_ms?: number | null;
  translation_retry_count?: number;
  translation_status?: 'failed' | 'timeout' | null;
  translation_queue_latency_ms?: number | null;
  total_latency_ms?: number | null;
  latency_trace?: SubtitleLatencyTrace;
  latency_window?: LatencyWindowSnapshot;
};


// Timestamp identity, rather than partial/final flags, controls replacement.
export function updateLine(lines: SubtitleLine[], data: any, broadcast: boolean, queue: boolean) {
  if (broadcast && !data) return;
  if (!data.original && !data.translated) return;
  const ts = broadcast ? data.backend_timestamp : data.timestamp || '';
  const existing = ts ? lines.find(line => line.timestamp_id === ts) : undefined;
  const fields = {
    original: data.original || '', translated: data.translated || '',
    asr_latency_ms: data.asr_latency_ms ?? null, llm_latency_ms: data.llm_latency_ms ?? null,
    translation_retry_ms: data.translation_retry_ms ?? null,
    translation_retry_count: data.translation_retry_count ?? 0,
    translation_status: data.translation_status ?? null,
    total_latency_ms: data.total_latency_ms ?? null,
    latency_trace: data.latency_trace, latency_window: data.latency_window,
    ...(queue ? { translation_queue_latency_ms: data.translation_queue_latency_ms ?? null } : {}),
    ...(broadcast ? { timestamp: new Date() } : {}),
  };
  if (existing) { Object.assign(existing, fields); return { item: existing, replaced: true }; }
  const item = {
    id: Date.now() + Math.random(), displayOriginal: '', displayTranslated: '', ...fields,
    ...(broadcast ? { timestamp_id: ts || '' } : ts ? { timestamp_id: ts } : {}),
  } as SubtitleLine;
  lines.push(item);
  return { item, replaced: false };
}
export function trimLines(lines: SubtitleLine[], limit: number, all: boolean, remove: (id: number) => void) {
  while (lines.length > limit) {
    const item = lines.shift();
    if (item) remove(item.id);
    if (!all) break;
  }
}
