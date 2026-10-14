import { onMounted, onUnmounted } from 'vue';
import { getClientId } from '../services/api';
import { acquireSyncEventSource, releaseSyncEventSource } from './sharedSyncSource';

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

  const listeners: Array<[string, EventListener]> = [];
  const listen = (name: string, handler: EventListener) => {
    listeners.push([name, handler]);
    eventSource?.addEventListener(name, handler);
  };
  const forward = (handler: UseAppSyncEventsOptions[keyof UseAppSyncEventsOptions]) =>
    ((event: MessageEvent) => {
      void invokeIfExternal(handler, JSON.parse(event.data));
    }) as EventListener;

  onMounted(() => {
    eventSource = acquireSyncEventSource();

    listen('config.updated', forward(options.onConfigUpdated));
    listen('config.reset', forward(options.onConfigReset));
    listen('config.imported', forward(options.onConfigImported));
    listen('translation.started', forward(options.onTranslationStarted));
    listen('translation.stopped', forward(options.onTranslationStopped));
    listen('error', ((error: Event) => {
      console.warn('[AppSync] 事件同步連線中斷:', error);
    }) as EventListener);
  });

  onUnmounted(() => {
    if (eventSource) {
      // The connection is shared; detach only this component's handlers.
      for (const [name, handler] of listeners) eventSource.removeEventListener(name, handler);
      listeners.length = 0;
      eventSource = null;
      releaseSyncEventSource();
    }
  });
}
