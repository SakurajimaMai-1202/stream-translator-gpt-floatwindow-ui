import axios from 'axios';
import { useTranslationStore } from '../../stores/translation';
import { validateAudioSlicing } from './audioSlicingValidation';

const pending = new Map<string, { snapshot: any; failures: number }>();
let timer: ReturnType<typeof setTimeout> | null = null;
let running: Promise<void> | null = null;
let paused = 0;

function schedule() {
  if (timer || running || paused || !pending.size) return;
  timer = setTimeout(() => {
    timer = null;
    const request = retry().finally(() => {
      if (running === request) running = null;
      schedule();
    });
    running = request;
  }, 3000);
}

async function send(section: string, entry: { snapshot: any; failures: number }) {
  const store = useTranslationStore();
  try {
    await store.saveConfigSection(section, entry.snapshot);
    if (pending.get(section) === entry) pending.delete(section);
  } catch (error: any) {
    if (pending.get(section) !== entry) return;
    try {
      const health = await axios.get('/api/health', { timeout: 3000 });
      if (health.data?.status !== 'ok' || pending.get(section) !== entry) return;
      if (++entry.failures >= 3) {
        pending.delete(section);
        store.errorMessage = `儲存 ${section} 設定失敗: ${error.message}`;
      }
    } catch { /* Offline attempts do not count toward the limit. */ }
  }
}

async function retry() {
  try {
    const health = await axios.get('/api/health', { timeout: 3000 });
    if (health.data?.status !== 'ok') return;
    for (const [section, entry] of pending) {
      if (paused) break;
      await send(section, entry);
    }
  } catch { /* Wait until the backend is reachable. */ }
}

export function queuePendingSave(section: string, snapshot: any, failures = 0, immediate = false, wait?: Promise<void>) {
  if (section === 'audio_slicing_vad' && validateAudioSlicing(snapshot)) return;
  const entry = { snapshot: JSON.parse(JSON.stringify(snapshot)), failures };
  pending.set(section, entry);
  if (immediate && !paused) {
    if (timer) clearTimeout(timer);
    timer = null;
    const previous = running;
    const request: Promise<void> = Promise.resolve(previous).then(async () => {
      await wait?.catch(() => undefined);
      if (!paused && pending.get(section) === entry) await send(section, entry);
    }).finally(() => {
      if (running === request) running = null;
      schedule();
    });
    running = request;
  }
  schedule();
}

export async function takePendingSaves() {
  paused++;
  if (timer) clearTimeout(timer);
  timer = null;
  try {
    await running;
    const entries = new Map(pending);
    pending.clear();
    return entries;
  } finally {
    paused--;
    schedule();
  }
}
