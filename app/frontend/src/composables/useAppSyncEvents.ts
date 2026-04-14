import { onMounted, onUnmounted } from 'vue';
import { getClientId, syncApi } from '../services/api';

export interface SyncEventPayload {
  source_client_id?: string;
  [key: string]: any;
}

interface UseAppSyncEventsOptions {
  onConfigUpdated?: (payload: SyncEventPayload) => void | Promise<void>;
  onConfigReset?: (payload: SyncEventPayload) => void | Promise<void>;
  onConfigImported?: (payload: SyncEventPayload) => void | Promise<void>;
  onTranslationStarted?: (payload: SyncEventPayload) => void | Promise<void>;
  onTranslationStopped?: (payload: SyncEventPayload) => void | Promise<void>;
}

export function useAppSyncEvents(options: UseAppSyncEventsOptions) {
  let eventSource: EventSource | null = null;
  const clientId = getClientId();

  const invokeIfExternal = async (
    handler: ((payload: SyncEventPayload) => void | Promise<void>) | undefined,
    payload: SyncEventPayload
  ) => {
    if (!handler) return;
    if (payload?.source_client_id && payload.source_client_id === clientId) return;
    await handler(payload);
  };

  onMounted(() => {
    eventSource = syncApi.createEventSource();

    eventSource.addEventListener('config.updated', (event: MessageEvent) => {
      void invokeIfExternal(options.onConfigUpdated, JSON.parse(event.data));
    });

    eventSource.addEventListener('config.reset', (event: MessageEvent) => {
      void invokeIfExternal(options.onConfigReset, JSON.parse(event.data));
    });

    eventSource.addEventListener('config.imported', (event: MessageEvent) => {
      void invokeIfExternal(options.onConfigImported, JSON.parse(event.data));
    });

    eventSource.addEventListener('translation.started', (event: MessageEvent) => {
      void invokeIfExternal(options.onTranslationStarted, JSON.parse(event.data));
    });

    eventSource.addEventListener('translation.stopped', (event: MessageEvent) => {
      void invokeIfExternal(options.onTranslationStopped, JSON.parse(event.data));
    });

    eventSource.onerror = (error) => {
      console.warn('[AppSync] 事件同步連線中斷:', error);
    };
  });

  onUnmounted(() => {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
  });
}
