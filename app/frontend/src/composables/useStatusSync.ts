import { onMounted, onUnmounted } from 'vue';
import { acquireSyncEventSource, releaseSyncEventSource } from './sharedSyncSource';

export function createStatusSync<T>(event: string, fetchStatus: () => Promise<T>, apply: (payload: T) => void | Promise<void>, interval = 1000) {
  let source: EventSource | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let revision = 0;
  const stopPolling = () => { if (timer !== null) clearInterval(timer); timer = null; };
  const refetch = async () => {
    const before = revision;
    try {
      const payload = await fetchStatus();
      if (source && before === revision) await apply(payload);
    } catch (error) { console.warn('[StatusSync]', error); }
  };
  const onMessage = (message: MessageEvent) => {
    try {
      const payload = JSON.parse(message.data) as T;
      revision++;
      void Promise.resolve(apply(payload)).catch(error => console.warn('[StatusSync]', error));
    } catch (error) { console.warn('[StatusSync]', error); }
  };
  const onOpen = () => { stopPolling(); void refetch(); };
  const onError = () => { if (timer === null) timer = setInterval(() => void refetch(), interval); };
  const start = () => {
    if (source) return;
    source = acquireSyncEventSource();
    source.addEventListener(event, onMessage as EventListener);
    source.addEventListener('open', onOpen);
    source.addEventListener('error', onError);
    // A shared connection may already be broken; poll until it reopens.
    if (source.readyState === 2) onError();
    void refetch();
  };
  const stop = () => {
    revision++;
    if (source) {
      source.removeEventListener(event, onMessage as EventListener);
      source.removeEventListener('open', onOpen);
      source.removeEventListener('error', onError);
      source = null;
      releaseSyncEventSource();
    }
    stopPolling();
  };
  return { start, stop, refetch };
}

export function useStatusSync<T>(event: string, fetchStatus: () => Promise<T>, apply: (payload: T) => void | Promise<void>) {
  const sync = createStatusSync(event, fetchStatus, apply);
  onMounted(sync.start);
  onUnmounted(sync.stop);
  return sync;
}
