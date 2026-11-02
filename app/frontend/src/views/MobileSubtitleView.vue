<script setup lang="ts">
import { useSubtitleStream } from '../composables/useSubtitleStream';
import type { SubtitleLine } from '../composables/subtitleStreamLogic';
import { ref, onMounted, onUnmounted, nextTick } from 'vue';
import AppIcon from '../components/AppIcon.vue';

// ─── 類型 ───────────────────────────────────────────────
type SubtitleItem = SubtitleLine;

const fontSize = ref(Number(localStorage.getItem('mfw_fontSize') || 28));
const showOriginal = ref(localStorage.getItem('mfw_showOriginal') !== 'false');
const showTranslated = ref(localStorage.getItem('mfw_showTranslated') !== 'false');
const showLatency = ref(localStorage.getItem('mfw_showLatency') !== 'false');
const showPanel = ref(false);
const maxItems = ref(Number(localStorage.getItem('mfw_maxItems') || 100));
const theme = ref<'auto' | 'dark' | 'light'>((localStorage.getItem('mfw_theme') as any) || 'auto');

// ─── 捲動控制 ───────────────────────────────────────────
const scrollContainer = ref<HTMLElement | null>(null);
const isAutoScroll = ref(true);
const SCROLL_THRESHOLD = 80; // px，距離底部多少以內視為「在底部」

function handleScroll() {
  const el = scrollContainer.value;
  if (!el) return;
  const distFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
  isAutoScroll.value = distFromBottom < SCROLL_THRESHOLD;
}

function scrollToBottom(smooth = false) {
  nextTick(() => {
    // requestAnimationFrame 確保瀏覽器完成 layout reflow 後再讀 scrollHeight
    requestAnimationFrame(() => {
      const el = scrollContainer.value;
      if (!el) return;
      if (smooth) {
        el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' });
      } else {
        el.scrollTop = el.scrollHeight;
      }
      isAutoScroll.value = true;
    });
  });
}

// ─── 打字動畫 ───────────────────────────────────────────
// 使用 Map 存 timer（非響應式，只用於清理）
const { subtitles, status, statusText, typingItemIds, hasPendingText, connect, dispose, clearAllTypingTimers } = useSubtitleStream({
  transport: 'sse', maxItems: () => maxItems.value,
  queueLatency: false, trimBeforeTyping: true, scrollDuringTyping: false,
  shouldScroll: () => isAutoScroll.value, scrollToBottom,
});

let wakeLock: WakeLockSentinel | null = null;

async function requestWakeLock() {
  try {
    if ('wakeLock' in navigator) {
      wakeLock = await (navigator as any).wakeLock.request('screen');
      // 當 OS 自動釋放鎖定（例如切換 app）時重置 ref
      wakeLock?.addEventListener('release', () => {
        wakeLock = null;
      });
    }
  } catch {}
}

// 頁面重新可見時（從背景回來、息屏後亮屏），重新請求 wake lock
async function handleVisibilityChange() {
  if (document.visibilityState === 'visible' && !wakeLock) {
    await requestWakeLock();
  }
}

// ─── 設定儲存 ────────────────────────────────────────────
function saveSettings() {
  localStorage.setItem('mfw_fontSize', String(fontSize.value));
  localStorage.setItem('mfw_showOriginal', String(showOriginal.value));
  localStorage.setItem('mfw_showTranslated', String(showTranslated.value));
  localStorage.setItem('mfw_showLatency', String(showLatency.value));
  localStorage.setItem('mfw_maxItems', String(maxItems.value));
  localStorage.setItem('mfw_theme', theme.value);
}

function formatLatency(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return '';
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${Math.round(value)}ms`;
}

function latencyLabel(sub: SubtitleItem): string {
  const parts: string[] = [];
  if (sub.asr_latency_ms != null) parts.push(`ASR ${formatLatency(sub.asr_latency_ms)}`);
  if (sub.llm_latency_ms != null) parts.push(`翻譯 ${formatLatency(sub.llm_latency_ms)}${(sub.translation_retry_ms ?? 0) > 0 ? `（含重翻 ${formatLatency(sub.translation_retry_ms)}）` : ''}`);
  if (sub.total_latency_ms != null) parts.push(`總計 ${formatLatency(sub.total_latency_ms)}`);
  return parts.join(' · ');
}

// ─── 生命週期 ────────────────────────────────────────────
onMounted(async () => {
  document.addEventListener('visibilitychange', handleVisibilityChange);
  await requestWakeLock();
  connect();
});

onUnmounted(() => {
  document.removeEventListener('visibilitychange', handleVisibilityChange);
  dispose();
  wakeLock?.release();
  clearAllTypingTimers();
});
</script>

<template>
  <div class="mobile-root" :class="theme !== 'auto' && `theme-${theme}`">
    <!-- 狀態欄 -->
    <div class="status-bar" :class="status">
      <span class="status-dot"></span>
      <span class="status-text">{{ statusText }}</span>
      <button class="settings-btn" @click="showPanel = !showPanel" title="設定" aria-label="設定"><AppIcon name="general" /></button>
    </div>

    <!-- 設定面板 -->
    <Transition name="slide">
      <div v-if="showPanel" class="settings-panel">
        <div class="panel-title">字幕設定</div>

        <label class="setting-row">
          <span>字體大小：{{ fontSize }}px</span>
          <input type="range" min="16" max="72" v-model.number="fontSize" @change="saveSettings" />
        </label>

        <label class="setting-row">
          <span>歷史記錄數量：{{ maxItems }}</span>
          <input type="range" min="10" max="200" v-model.number="maxItems" @change="saveSettings" />
        </label>

        <label class="setting-toggle">
          <input type="checkbox" v-model="showOriginal" @change="saveSettings" />
          <span>顯示原文</span>
        </label>

        <label class="setting-toggle">
          <input type="checkbox" v-model="showTranslated" @change="saveSettings" />
          <span>顯示翻譯</span>
        </label>

        <label class="setting-toggle">
          <input type="checkbox" v-model="showLatency" @change="saveSettings" />
          <span>顯示 ASR／翻譯處理時間</span>
        </label>

        <div class="theme-group">
          <span class="theme-label">外觀主題</span>
          <div class="theme-btns">
            <button :class="['theme-btn', theme === 'auto' && 'active']"
              @click="theme = 'auto'; saveSettings()">自動</button>
            <button :class="['theme-btn', theme === 'dark' && 'active']"
              @click="theme = 'dark'; saveSettings()">深色</button>
            <button :class="['theme-btn', theme === 'light' && 'active']"
              @click="theme = 'light'; saveSettings()">淺色</button>
          </div>
        </div>

        <button class="panel-close" @click="showPanel = false">關閉</button>
      </div>
    </Transition>

    <!-- 字幕顯示區（固定高度，可捲動，聊天室模式） -->
    <div
      ref="scrollContainer"
      class="subtitle-area"
      @scroll.passive="handleScroll"
    >
      <!-- 空狀態 -->
      <div v-if="subtitles.length === 0" class="empty-hint">
        <div class="spinner"></div>
        <p>{{ statusText }}</p>
      </div>

      <template v-else>
        <!-- spacer：字幕少時撐開空間，讓字幕靠底部 -->
        <div class="spacer"></div>

        <div
          v-for="(sub, idx) in subtitles"
          :key="sub.id"
          class="subtitle-item"
          :class="{ latest: idx === subtitles.length - 1 }"
        >
          <!-- 原文：正在打字時顯示游標（原文未打完） -->
          <div
            v-if="showOriginal && sub.original"
            class="sub-original"
            :style="{ fontSize: fontSize + 'px' }"
          >{{ sub.displayOriginal }}<span
              v-if="typingItemIds.includes(sub.id) && hasPendingText(sub.displayOriginal, sub.original)"
              class="typing-cursor"
            >|</span></div>
          <!-- 翻譯：正在打字時顯示游標（原文已完成，翻譯未打完） -->
          <div
            v-if="showTranslated && sub.translated"
            class="sub-translated"
            :style="{ fontSize: fontSize + 'px' }"
          >{{ sub.displayTranslated }}<span
              v-if="typingItemIds.includes(sub.id) && hasPendingText(sub.displayTranslated, sub.translated)"
              class="typing-cursor"
            >|</span></div>
          <div
            v-if="showTranslated && !sub.translated && sub.translation_status"
            class="sub-translated translation-status"
            :style="{ fontSize: fontSize + 'px' }">
            {{ sub.translation_status === 'timeout' ? '翻譯逾時' : '翻譯失敗' }}
          </div>
          <div
            v-if="showLatency && latencyLabel(sub)"
            class="latency-line"
          >{{ latencyLabel(sub) }}</div>
        </div>
      </template>
    </div>

    <!-- 跳至底部按鈕（使用者往上滾動時顯示） -->
    <Transition name="jump-fade">
      <button v-if="!isAutoScroll" class="jump-btn" @click="scrollToBottom(true)">
        ↓ 最新訊息
      </button>
    </Transition>
  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;700;900&display=swap');

* { box-sizing: border-box; margin: 0; padding: 0; }

/* ─── 深色模式（預設）CSS 變數 ─── */
.mobile-root {
  --bg:                 #0a0a0a;
  --text:               #fff;
  --bar-bg:             rgba(255,255,255,0.05);
  --bar-border:         rgba(255,255,255,0.08);
  --status-text:        rgba(255,255,255,0.6);
  --settings-btn:       rgba(255,255,255,0.5);
  --panel-bg:           rgba(0,0,0,0.92);
  --panel-title:        #fff;
  --panel-title-border: rgba(255,255,255,0.15);
  --panel-text:         rgba(255,255,255,0.75);
  --toggle-text:        rgba(255,255,255,0.85);
  --card-bg:            rgba(255,255,255,0.04);
  --card-bg-latest:     rgba(99,102,241,0.07);
  --card-border:        rgba(99,102,241,0.4);
  --card-border-latest: #6366f1;
  --original-color:     #e5e7eb;
  --translated-color:   #fbbf24;
  --sub-shadow:         0 1px 4px rgba(0,0,0,0.8);
  --empty-color:        rgba(255,255,255,0.3);
  --spinner-track:      rgba(255,255,255,0.1);
  --spinner-top:        #6366f1;
  --jump-bg:            #4f46e5;
  --jump-hover-bg:      #6366f1;
  --scrollbar-thumb:    rgba(255,255,255,0.15);
}

/* ─── 淺色模式覆蓋 ─── */
@media (prefers-color-scheme: light) {
  .mobile-root:not(.theme-dark) {
    --bg:                 #f1f5f9;
    --text:               #1e293b;
    --bar-bg:             rgba(0,0,0,0.03);
    --bar-border:         rgba(0,0,0,0.08);
    --status-text:        rgba(0,0,0,0.55);
    --settings-btn:       rgba(0,0,0,0.45);
    --panel-bg:           rgba(248,250,252,0.97);
    --panel-title:        #1e293b;
    --panel-title-border: rgba(0,0,0,0.1);
    --panel-text:         rgba(0,0,0,0.65);
    --toggle-text:        rgba(0,0,0,0.75);
    --card-bg:            rgba(0,0,0,0.04);
    --card-bg-latest:     rgba(99,102,241,0.07);
    --card-border:        rgba(99,102,241,0.35);
    --card-border-latest: #6366f1;
    --original-color:     #374151;
    --translated-color:   #b45309;
    --sub-shadow:         0 1px 3px rgba(0,0,0,0.1);
    --empty-color:        rgba(0,0,0,0.3);
    --spinner-track:      rgba(0,0,0,0.1);
    --spinner-top:        #6366f1;
    --jump-bg:            #4f46e5;
    --jump-hover-bg:      #6366f1;
    --scrollbar-thumb:    rgba(0,0,0,0.15);
  }
}

/* ─── 強制淺色（手動選擇）─── */
.mobile-root.theme-light {
  --bg:                 #f1f5f9;
  --text:               #1e293b;
  --bar-bg:             rgba(0,0,0,0.03);
  --bar-border:         rgba(0,0,0,0.08);
  --status-text:        rgba(0,0,0,0.55);
  --settings-btn:       rgba(0,0,0,0.45);
  --panel-bg:           rgba(248,250,252,0.97);
  --panel-title:        #1e293b;
  --panel-title-border: rgba(0,0,0,0.1);
  --panel-text:         rgba(0,0,0,0.65);
  --toggle-text:        rgba(0,0,0,0.75);
  --card-bg:            rgba(0,0,0,0.04);
  --card-bg-latest:     rgba(99,102,241,0.07);
  --card-border:        rgba(99,102,241,0.35);
  --card-border-latest: #6366f1;
  --original-color:     #374151;
  --translated-color:   #b45309;
  --sub-shadow:         0 1px 3px rgba(0,0,0,0.1);
  --empty-color:        rgba(0,0,0,0.3);
  --spinner-track:      rgba(0,0,0,0.1);
  --spinner-top:        #6366f1;
  --jump-bg:            #4f46e5;
  --jump-hover-bg:      #6366f1;
  --scrollbar-thumb:    rgba(0,0,0,0.15);
}

.mobile-root {
  font-family: 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif;
  background: var(--bg);
  height: 100dvh;          /* 固定在視窗高度，不讓頁面本身滾動 */
  display: flex;
  flex-direction: column;
  color: var(--text);
  overflow: hidden;        /* 頁面本身不可捲動 */
  position: relative;
}

/* ─── 狀態欄 ─── */
.status-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: var(--bar-bg);
  border-bottom: 1px solid var(--bar-border);
  min-height: 42px;
  flex-shrink: 0;
}

.status-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #888;
  flex-shrink: 0;
  transition: background 0.3s;
}
.status-bar.connected .status-dot { background: #22c55e; box-shadow: 0 0 6px #22c55e; }
.status-bar.waiting .status-dot   { background: #f59e0b; animation: pulse 1.5s infinite; }
.status-bar.error .status-dot     { background: #ef4444; }

@keyframes pulse {
  0%, 100% { opacity: 1; } 50% { opacity: 0.3; }
}

.status-text {
  font-size: 13px;
  color: var(--status-text);
  flex: 1;
}

.settings-btn {
  background: none;
  border: none;
  color: var(--settings-btn);
  font-size: 20px;
  cursor: pointer;
  padding: 4px 8px;
  line-height: 1;
  transition: color 0.2s;
}
.settings-btn:hover { color: var(--text); }
.settings-btn .app-icon { width: 22px; height: 22px; }

/* ─── 設定面板 ─── */
.settings-panel {
  position: fixed;
  inset: 0;
  background: var(--panel-bg);
  backdrop-filter: blur(12px);
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 40px 24px 24px;
}

.panel-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--panel-title);
  border-bottom: 1px solid var(--panel-title-border);
  padding-bottom: 14px;
}

.setting-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
  font-size: 15px;
  color: var(--panel-text);
}
.setting-row input[type=range] {
  width: 100%;
  accent-color: #6366f1;
  height: 6px;
}

.setting-toggle {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 16px;
  color: var(--toggle-text);
  cursor: pointer;
}
.setting-toggle input { width: 20px; height: 20px; accent-color: #6366f1; }

.panel-close {
  margin-top: auto;
  background: #6366f1;
  color: #fff;
  border: none;
  border-radius: 12px;
  padding: 14px;
  font-size: 17px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.2s;
}
.panel-close:hover { background: #4f46e5; }

/* ─── 字幕區（固定高度，可捲動，聊天室模式）─── */
.subtitle-area {
  flex: 1;
  overflow-y: auto;          /* 容器內部可捲動 */
  padding: 20px 16px 50px;
  display: flex;
  flex-direction: column;    /* spacer + items 由上到下 */
  scroll-behavior: auto;     /* 程式捲動用 instant，按鈕用 smooth */
}

/* spacer：字幕少時撐開空間，讓字幕靠底部 */
.spacer { flex: 1; min-height: 0; }

.empty-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  flex: 1;
  color: var(--empty-color);
  font-size: 15px;
}

.spinner {
  width: 36px; height: 36px;
  border: 3px solid var(--spinner-track);
  border-top-color: var(--spinner-top);
  border-radius: 50%;
  animation: spin 0.9s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.subtitle-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 14px;
  background: var(--card-bg);
  border-radius: 12px;
  border-left: 3px solid var(--card-border);
  animation: fadeIn 0.25s ease;
  margin-bottom: 12px;
  transition: border-color 0.3s;
}
.subtitle-item.latest {
  border-left-color: var(--card-border-latest);
  background: var(--card-bg-latest);
}
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }

.sub-original {
  color: var(--original-color);
  font-weight: 400;
  line-height: 1.5;
  text-shadow: var(--sub-shadow);
  word-break: break-word;
}

.sub-translated {
  color: var(--translated-color);
  font-weight: 700;
  line-height: 1.5;
  text-shadow: var(--sub-shadow);
  word-break: break-word;
  margin-top: 4px;
}

.translation-status {
  opacity: 0.6;
  font-style: italic;
  font-weight: 400;
}

.latency-line {
  margin-top: 4px;
  color: #7dd3fc;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.4;
  opacity: 0.85;
}

/* ─── 打字游標 ─── */
.typing-cursor {
  display: inline-block;
  margin-left: 1px;
  font-weight: 300;
  opacity: 1;
  animation: cursorBlink 0.7s ease-in-out infinite;
}
@keyframes cursorBlink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}

/* ─── 跳至底部按鈕 ─── */
.jump-btn {
  position: fixed;
  bottom: 28px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--jump-bg);
  color: #fff;
  border: none;
  border-radius: 99px;
  padding: 9px 22px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  z-index: 30;
  box-shadow: 0 4px 20px rgba(0,0,0,0.5);
  transition: background 0.2s, transform 0.2s;
  white-space: nowrap;
}
.jump-btn:hover {
  background: var(--jump-hover-bg);
  transform: translateX(-50%) translateY(-2px);
}

/* ─── 動畫 ─── */
.slide-enter-active, .slide-leave-active { transition: opacity 0.25s, transform 0.25s; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: scale(0.97); }

.jump-fade-enter-active,
.jump-fade-leave-active { transition: opacity 0.25s ease, transform 0.25s ease; }
.jump-fade-enter-from,
.jump-fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(8px); }

/* ─── 捲動條美化 ─── */
.subtitle-area::-webkit-scrollbar { width: 4px; }
.subtitle-area::-webkit-scrollbar-track { background: transparent; }
.subtitle-area::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: 99px;
}

/* ─── 主題選擇器 ─── */
.theme-group { display: flex; flex-direction: column; gap: 10px; }
.theme-label { font-size: 15px; color: var(--panel-text); }
.theme-btns { display: flex; gap: 8px; }
.theme-btn {
  flex: 1;
  padding: 10px 8px;
  border: 1px solid var(--card-border);
  border-radius: 10px;
  background: var(--card-bg);
  color: var(--panel-text);
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
}
.theme-btn.active { background: #6366f1; border-color: #6366f1; color: #fff; }
.theme-btn:hover:not(.active) { background: var(--card-bg-latest); }

/* Control chrome follows the app; subtitle presentation keeps its own theme. */
.status-bar, .settings-panel { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft JhengHei", sans-serif; }
.settings-btn, .theme-btn, .panel-close { min-width: 2.75rem; min-height: 2.75rem; border-radius: .65rem; touch-action: manipulation; }
.panel-title { font-weight: 650; letter-spacing: -.025em; }
:is(.settings-btn,.theme-btn,.panel-close):focus-visible { outline: 2px solid var(--fw-primary, #7297f5); outline-offset: 3px; }
:is(.settings-btn,.theme-btn,.panel-close):active { transform: scale(.97); }
@media (prefers-reduced-motion: reduce) { .status-dot, .spinner { animation: none !important; } .settings-btn,.theme-btn,.panel-close { transition: none; transform: none; } }
@media (prefers-reduced-transparency: reduce) { .settings-panel { backdrop-filter: none; background: var(--bg); } }

</style>
