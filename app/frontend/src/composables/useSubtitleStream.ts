import { ref } from 'vue';
import { updateLine, trimLines, type SubtitleLine } from './subtitleStreamLogic';
export interface SubtitleStreamOptions {
  transport: 'sse' | 'broadcast';
  maxItems: () => number;
  queueLatency: boolean;
  trimAll?: boolean;
  trimBeforeTyping?: boolean;
  scrollOnReplacement?: boolean;
  scrollDuringTyping?: boolean;
  shouldScroll: () => boolean;
  scrollToBottom: () => void;
}
export function useSubtitleStream(options: SubtitleStreamOptions) {
  const subtitles = ref<SubtitleLine[]>([]);
  const status = ref<'connecting' | 'connected' | 'waiting' | 'error'>('connecting');
  const statusText = ref('連線中...');
  const scrollToBottom = options.scrollToBottom;
  const typingTimers = new Map<number, ReturnType<typeof setInterval>>();
  const typingItemIds = ref<number[]>([]);
  const TYPING_SPEED_MS = 18;
  const MAX_TYPING_DURATION_MS = 1800;

  function stopTyping(itemId: number) {
    const timer = typingTimers.get(itemId);
    if (timer) clearInterval(timer);
    typingTimers.delete(itemId);
    const index = typingItemIds.value.indexOf(itemId);
    if (index !== -1) typingItemIds.value.splice(index, 1);
  }

  function clearAllTypingTimers() {
    typingTimers.forEach(timer => clearInterval(timer));
    typingTimers.clear();
    typingItemIds.value = [];
  }

  function reconcileRenderedText(rendered: string, target: string): string {
    const renderedChars = Array.from(rendered);
    const targetChars = Array.from(target);
    let commonLength = 0;
    while (commonLength < renderedChars.length
      && commonLength < targetChars.length
      && renderedChars[commonLength] === targetChars[commonLength]) commonLength += 1;
    return targetChars.slice(0, commonLength).join('');
  }

  function hasPendingText(rendered: string, target: string): boolean {
    return Array.from(rendered).length < Array.from(target).length;
  }

  function startTyping(itemId: number) {
    const item = subtitles.value.find(sub => sub.id === itemId);
    if (!item) return;
    stopTyping(itemId);
    item.displayOriginal = reconcileRenderedText(item.displayOriginal, item.original);
    item.displayTranslated = reconcileRenderedText(item.displayTranslated, item.translated);
    const remaining = (Array.from(item.original).length - Array.from(item.displayOriginal).length)
      + (Array.from(item.translated).length - Array.from(item.displayTranslated).length);
    if (remaining <= 0) return;
    typingItemIds.value.push(itemId);
    const speed = Math.max(1, Math.min(TYPING_SPEED_MS, Math.floor(MAX_TYPING_DURATION_MS / remaining)));
    let ticks = 0;
    const timer = setInterval(() => {
      const target = subtitles.value.find(sub => sub.id === itemId);
      if (!target) { stopTyping(itemId); return; }
      let changed = false;
      const originalChars = Array.from(target.original);
      const translatedChars = Array.from(target.translated);
      const originalLength = Array.from(target.displayOriginal).length;
      const translatedLength = Array.from(target.displayTranslated).length;
      if (originalLength < originalChars.length) {
        target.displayOriginal = originalChars.slice(0, originalLength + 1).join('');
        changed = true;
      }
      if (translatedLength < translatedChars.length) {
        target.displayTranslated = translatedChars.slice(0, translatedLength + 1).join('');
        changed = true;
      }
      if (!changed) { stopTyping(itemId); return; }
      ticks += 1;
      if (ticks % 4 === 0 && options.scrollDuringTyping && options.shouldScroll()) scrollToBottom();
    }, speed);
    typingTimers.set(itemId, timer);
  }
  let sse: EventSource | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function getApiBase(): string {
    return `${location.protocol}//${location.host}`;
  }

  async function getActiveTaskId(): Promise<string | null> {
    try {
      const res = await fetch(`${getApiBase()}/api/translation/active-task`);
      const data = await res.json();
      return data.success ? data.task_id : null;
    } catch {
      return null;
    }
  }

  async function connect() {
    if (options.transport === 'broadcast') { initSubtitleChannel(); return; }
    status.value = 'connecting';
    statusText.value = '取得任務中...';

    const taskId = await getActiveTaskId();
    if (!taskId) {
      status.value = 'waiting';
      statusText.value = '等待翻譯任務啟動...';
      reconnectTimer = setTimeout(connect, 5000);
      return;
    }

    status.value = 'connected';
    statusText.value = '已連線';

    const url = `${getApiBase()}/api/translation/stream/${taskId}`;
    sse = new EventSource(url);

    sse.addEventListener('subtitle', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        addOrUpdateSubtitle(data);
      } catch {}
    });

    sse.addEventListener('status', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data);
        if (data.status === 'completed' || data.status === 'error') {
          statusText.value = '任務已結束，重新連線中...';
          status.value = 'waiting';
          sse?.close();
          reconnectTimer = setTimeout(connect, 3000);
        }
      } catch {}
    });

    sse.onerror = () => {
      status.value = 'error';
      statusText.value = '連線中斷，重連中...';
      sse?.close();
      reconnectTimer = setTimeout(connect, 3000);
    };
  }


  function addOrUpdateSubtitle(data: any) {
    const broadcast = options.transport === 'broadcast';
    if (broadcast && data && (data.original || data.translated)) console.log(`[BroadcastChannel] 收到新字幕:`, data);

    const result = updateLine(subtitles.value, data, broadcast, options.queueLatency);
    if (!result) return;
    const trim = () => trimLines(subtitles.value, options.maxItems(), !!options.trimAll, stopTyping);
    if (!result.replaced && options.trimBeforeTyping) trim();
    startTyping(result.item.id);
    if (result.replaced && !options.scrollOnReplacement) return;
    if (!options.trimBeforeTyping) trim();
    if (options.shouldScroll()) scrollToBottom();
  }
  let subtitleChannel: BroadcastChannel | null = null;
  function initSubtitleChannel() {
    try {
      subtitleChannel = new BroadcastChannel('subtitle-updates');
      subtitleChannel.onmessage = (event) => {
        addOrUpdateSubtitle(event.data);
      };
      console.log('字幕 BroadcastChannel 已初始化');
    } catch (error) {
      console.error('字幕 BroadcastChannel 初始化失敗:', error);
    }
  }


  function dispose() {
    sse?.close();
    if (reconnectTimer) clearTimeout(reconnectTimer);
    subtitleChannel?.close();
    clearAllTypingTimers();
  }
  return { subtitles, status, statusText, typingItemIds, hasPendingText, connect, dispose, clearAllTypingTimers };
}
