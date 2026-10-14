import { syncApi } from '../services/api';

// One /sync/events connection per page, shared by every listener. Browsers
// (and QtWebEngine) allow only six connections per host, so each consumer
// opening its own EventSource would starve ordinary API requests.
let source: EventSource | null = null;
let users = 0;

export function acquireSyncEventSource(): EventSource {
  if (!source) source = syncApi.createEventSource();
  users++;
  return source;
}

export function releaseSyncEventSource(): void {
  users = Math.max(0, users - 1);
  if (users === 0 && source) {
    source.close();
    source = null;
  }
}
