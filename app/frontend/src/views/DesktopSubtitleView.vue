<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue';

// ─── 狀態 ───────────────────────────────────────────────
const subtitles = ref<Array<{ id: number; original: string; translated: string; timestamp_id?: string }>>([]);
const status = ref<'connecting' | 'connected' | 'waiting' | 'error'>('connecting');
const statusText = ref('連線中...');
const showPanel = ref(false);

// ─── 設定 ───────────────────────────────────────────────
const fontSize = ref(Number(localStorage.getItem('dfw_fontSize') || 32));
const showOriginal = ref(localStorage.getItem('dfw_showOriginal') !== 'false');
const showTranslated = ref(localStorage.getItem('dfw_showTranslated') !== 'false');
const maxItems = ref(Number(localStorage.getItem('dfw_maxItems') || 100));
const layout = ref<'bottom' | 'top' | 'side'>(
  (localStorage.getItem('dfw_layout') as any) || 'bottom'
);
const bgOpacity = ref(Number(localStorage.getItem('dfw_bgOpacity') ?? 70));
const theme = ref<'auto' | 'dark' | 'light'>((localStorage.getItem('dfw_theme') as any) || 'auto');

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

// ─── SSE 連線 ────────────────────────────────────────────
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

function addOrUpdateSubtitle(data: { timestamp?: string; original: string; translated: string }) {
  if (!data.original && !data.translated) return;

  const ts = data.timestamp || '';
  if (ts) {
    const idx = subtitles.value.findIndex(s => s.timestamp_id === ts);
    if (idx !== -1) {
      subtitles.value[idx].original = data.original || '';
      subtitles.value[idx].translated = data.translated || '';
      // 更新不新增，不需要捲動
      return;
    }
  }

  subtitles.value.push({
    id: Date.now() + Math.random(),
    original: data.original || '',
    translated: data.translated || '',
    ...(ts ? { timestamp_id: ts } : {})
  });

  // 超出歷史記錄上限時移除最舊的
  if (subtitles.value.length > maxItems.value) subtitles.value.shift();

  // 只有使用者在底部才自動捲動
  if (isAutoScroll.value) {
    scrollToBottom();
  }
}

// ─── 設定儲存 ────────────────────────────────────────────
function saveSettings() {
  localStorage.setItem('dfw_fontSize', String(fontSize.value));
  localStorage.setItem('dfw_showOriginal', String(showOriginal.value));
  localStorage.setItem('dfw_showTranslated', String(showTranslated.value));
  localStorage.setItem('dfw_maxItems', String(maxItems.value));
  localStorage.setItem('dfw_layout', layout.value);
  localStorage.setItem('dfw_bgOpacity', String(bgOpacity.value));
  localStorage.setItem('dfw_theme', theme.value);
}

// ─── 生命週期 ────────────────────────────────────────────
onMounted(() => { connect(); });
onUnmounted(() => {
  sse?.close();
  if (reconnectTimer) clearTimeout(reconnectTimer);
});

function clearHistory() {
  subtitles.value = [];
}
</script>

<template>
  <div class="desktop-root" :class="[`layout-${layout}`, theme !== 'auto' && `theme-${theme}`]">

    <!-- 頂部控制欄 -->
    <header class="top-bar">
      <div class="brand">
        <span class="brand-icon">◈</span>
        <span class="brand-name">字幕顯示</span>
      </div>

      <!-- 狀態指示 -->
      <div class="status-indicator" :class="status">
        <span class="dot"></span>
        <span class="label">{{ statusText }}</span>
      </div>

      <div class="toolbar">
        <button class="icon-btn" @click="clearHistory" title="清除">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
            <path d="M10 11v6M14 11v6"/><path d="M9 6V4h6v2"/>
          </svg>
        </button>
        <button class="icon-btn" @click="showPanel = !showPanel" title="設定">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
      </div>
    </header>

    <!-- 設定面板 (側滑) -->
    <Transition name="panel-slide">
      <aside v-if="showPanel" class="settings-aside">
        <div class="aside-title">
          <span>設定</span>
          <button class="close-btn" @click="showPanel = false">✕</button>
        </div>

        <div class="setting-group">
          <label>字體大小：{{ fontSize }}px</label>
          <input type="range" min="16" max="96" v-model.number="fontSize" @input="saveSettings" />
        </div>

        <div class="setting-group">
          <label>歷史記錄數量：{{ maxItems }}</label>
          <input type="range" min="10" max="200" v-model.number="maxItems" @input="saveSettings" />
        </div>

        <div class="setting-group">
          <label>背景透明度：{{ bgOpacity }}%</label>
          <input type="range" min="0" max="100" v-model.number="bgOpacity" @input="saveSettings" />
        </div>

        <div class="setting-group">
          <label>版面配置</label>
          <div class="layout-btns">
            <button :class="['layout-btn', layout === 'bottom' && 'active']"
              @click="layout = 'bottom'; saveSettings()">下方靠齊</button>
            <button :class="['layout-btn', layout === 'top' && 'active']"
              @click="layout = 'top'; saveSettings()">上方靠齊</button>
          </div>
        </div>

        <div class="setting-group">
          <label>外觀主題</label>
          <div class="layout-btns">
            <button :class="['layout-btn', theme === 'auto' && 'active']"
              @click="theme = 'auto'; saveSettings()">自動</button>
            <button :class="['layout-btn', theme === 'dark' && 'active']"
              @click="theme = 'dark'; saveSettings()">深色</button>
            <button :class="['layout-btn', theme === 'light' && 'active']"
              @click="theme = 'light'; saveSettings()">淺色</button>
          </div>
        </div>

        <div class="setting-group">
          <label class="toggle-row">
            <input type="checkbox" v-model="showOriginal" @change="saveSettings" />
            顯示原文
          </label>
          <label class="toggle-row">
            <input type="checkbox" v-model="showTranslated" @change="saveSettings" />
            顯示翻譯
          </label>
        </div>
      </aside>
    </Transition>

    <!-- 字幕顯示區（固定高度，可捲動） -->
    <main
      ref="scrollContainer"
      class="subtitle-area"
      :class="{ 'layout-top-mode': layout === 'top' }"
      :style="{ '--bg-opacity': bgOpacity / 100 }"
      @scroll.passive="handleScroll"
    >
      <!-- 空狀態 -->
      <div v-if="subtitles.length === 0" class="empty-state">
        <div class="pulse-ring"></div>
        <p>{{ statusText }}</p>
      </div>

      <template v-else>
        <!-- spacer：字幕少時靠底部顯示 -->
        <div class="spacer"></div>

        <TransitionGroup name="sub-fade" tag="div" class="subtitle-list">
          <div
            v-for="(sub, idx) in subtitles"
            :key="sub.id"
            class="subtitle-card"
            :class="{ latest: idx === subtitles.length - 1 }"
          >
            <div v-if="showOriginal && sub.original"
              class="sub-line original"
              :style="{ fontSize: fontSize + 'px' }">
              {{ sub.original }}
            </div>
            <div v-if="showTranslated && sub.translated"
              class="sub-line translated"
              :style="{ fontSize: fontSize + 'px' }">
              {{ sub.translated }}
            </div>
          </div>
        </TransitionGroup>
      </template>
    </main>

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

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ─── 深色模式（預設）CSS 變數 ─── */
.desktop-root {
  --bg:                  #080c10;
  --text:                #fff;
  --bar-bg:              rgba(255,255,255,0.04);
  --bar-border:          rgba(255,255,255,0.07);
  --brand-icon:          #818cf8;
  --brand-name:          rgba(255,255,255,0.7);
  --status-label:        rgba(255,255,255,0.45);
  --icon-btn-bg:         rgba(255,255,255,0.07);
  --icon-btn-border:     rgba(255,255,255,0.1);
  --icon-btn-color:      rgba(255,255,255,0.5);
  --icon-btn-hover-bg:   rgba(255,255,255,0.14);
  --aside-bg:            rgba(12,16,24,0.97);
  --aside-border:        rgba(255,255,255,0.1);
  --close-btn:           rgba(255,255,255,0.4);
  --setting-label:       rgba(255,255,255,0.6);
  --toggle-label:        rgba(255,255,255,0.75);
  --layout-btn-bg:       rgba(255,255,255,0.05);
  --layout-btn-border:   rgba(255,255,255,0.15);
  --layout-btn-color:    rgba(255,255,255,0.6);
  --layout-btn-hover-bg: rgba(255,255,255,0.1);
  --card-rgb:            255, 255, 255;
  --card-latest-rgb:     129, 140, 248;
  --card-border:         rgba(129,140,248,0.4);
  --card-border-latest:  #818cf8;
  --original-color:      #e5e7eb;
  --translated-color:    #fde68a;
  --sub-shadow:          0 1px 6px rgba(0,0,0,0.9);
  --empty-color:         rgba(255,255,255,0.2);
  --pulse-ring:          rgba(129,140,248,0.3);
  --pulse-top:           #818cf8;
  --scrollbar-thumb:     rgba(255,255,255,0.15);
  --scrollbar-aside:     rgba(255,255,255,0.1);
  --jump-bg:             #4f46e5;
  --jump-hover-bg:       #6366f1;
}

/* ─── 淺色模式覆蓋 ─── */
@media (prefers-color-scheme: light) {
  .desktop-root:not(.theme-dark) {
    --bg:                  #f1f5f9;
    --text:                #1e293b;
    --bar-bg:              rgba(0,0,0,0.03);
    --bar-border:          rgba(0,0,0,0.08);
    --brand-icon:          #4f46e5;
    --brand-name:          rgba(0,0,0,0.6);
    --status-label:        rgba(0,0,0,0.45);
    --icon-btn-bg:         rgba(0,0,0,0.06);
    --icon-btn-border:     rgba(0,0,0,0.1);
    --icon-btn-color:      rgba(0,0,0,0.5);
    --icon-btn-hover-bg:   rgba(0,0,0,0.1);
    --aside-bg:            rgba(248,250,252,0.98);
    --aside-border:        rgba(0,0,0,0.1);
    --close-btn:           rgba(0,0,0,0.4);
    --setting-label:       rgba(0,0,0,0.55);
    --toggle-label:        rgba(0,0,0,0.7);
    --layout-btn-bg:       rgba(0,0,0,0.04);
    --layout-btn-border:   rgba(0,0,0,0.12);
    --layout-btn-color:    rgba(0,0,0,0.55);
    --layout-btn-hover-bg: rgba(0,0,0,0.08);
    --card-rgb:            0, 0, 0;
    --card-latest-rgb:     79, 70, 229;
    --card-border:         rgba(79,70,229,0.35);
    --card-border-latest:  #4f46e5;
    --original-color:      #374151;
    --translated-color:    #b45309;
    --sub-shadow:          0 1px 3px rgba(0,0,0,0.1);
    --empty-color:         rgba(0,0,0,0.25);
    --pulse-ring:          rgba(79,70,229,0.3);
    --pulse-top:           #4f46e5;
    --scrollbar-thumb:     rgba(0,0,0,0.15);
    --scrollbar-aside:     rgba(0,0,0,0.1);
    --jump-bg:             #4f46e5;
    --jump-hover-bg:       #6366f1;
  }
}

/* ─── 強制淺色（手動選擇）─── */
.desktop-root.theme-light {
  --bg:                  #f1f5f9;
  --text:                #1e293b;
  --bar-bg:              rgba(0,0,0,0.03);
  --bar-border:          rgba(0,0,0,0.08);
  --brand-icon:          #4f46e5;
  --brand-name:          rgba(0,0,0,0.6);
  --status-label:        rgba(0,0,0,0.45);
  --icon-btn-bg:         rgba(0,0,0,0.06);
  --icon-btn-border:     rgba(0,0,0,0.1);
  --icon-btn-color:      rgba(0,0,0,0.5);
  --icon-btn-hover-bg:   rgba(0,0,0,0.1);
  --aside-bg:            rgba(248,250,252,0.98);
  --aside-border:        rgba(0,0,0,0.1);
  --close-btn:           rgba(0,0,0,0.4);
  --setting-label:       rgba(0,0,0,0.55);
  --toggle-label:        rgba(0,0,0,0.7);
  --layout-btn-bg:       rgba(0,0,0,0.04);
  --layout-btn-border:   rgba(0,0,0,0.12);
  --layout-btn-color:    rgba(0,0,0,0.55);
  --layout-btn-hover-bg: rgba(0,0,0,0.08);
  --card-rgb:            0, 0, 0;
  --card-latest-rgb:     79, 70, 229;
  --card-border:         rgba(79,70,229,0.35);
  --card-border-latest:  #4f46e5;
  --original-color:      #374151;
  --translated-color:    #b45309;
  --sub-shadow:          0 1px 3px rgba(0,0,0,0.1);
  --empty-color:         rgba(0,0,0,0.25);
  --pulse-ring:          rgba(79,70,229,0.3);
  --pulse-top:           #4f46e5;
  --scrollbar-thumb:     rgba(0,0,0,0.15);
  --scrollbar-aside:     rgba(0,0,0,0.1);
  --jump-bg:             #4f46e5;
  --jump-hover-bg:       #6366f1;
}

.desktop-root {
  font-family: 'Noto Sans TC', 'PingFang TC', 'Microsoft JhengHei', sans-serif;
  background: var(--bg);
  height: 100dvh;          /* 固定在視窗高度，不讓頁面本身滾動 */
  display: grid;
  grid-template-rows: 48px 1fr;
  grid-template-columns: 1fr;
  color: var(--text);
  overflow: hidden;        /* 頁面本身不可捲動 */
  position: relative;
}

/* ─── 控制欄 ─── */
.top-bar {
  grid-row: 1;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 0 20px;
  background: var(--bar-bg);
  border-bottom: 1px solid var(--bar-border);
  z-index: 10;
  flex-shrink: 0;
}

.brand { display: flex; align-items: center; gap: 8px; }
.brand-icon { font-size: 18px; color: var(--brand-icon); }
.brand-name { font-size: 14px; font-weight: 600; color: var(--brand-name); }

.status-indicator {
  display: flex;
  align-items: center;
  gap: 7px;
  flex: 1;
}
.status-indicator .dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: #555;
  transition: background 0.3s;
  flex-shrink: 0;
}
.status-indicator.connected .dot { background: #22c55e; box-shadow: 0 0 8px #22c55e; }
.status-indicator.waiting .dot  { background: #f59e0b; animation: pulse 1.4s infinite; }
.status-indicator.error .dot    { background: #ef4444; }
.status-indicator .label { font-size: 12px; color: var(--status-label); }

@keyframes pulse { 0%,100% { opacity:1 } 50% { opacity:0.3 } }

.toolbar { display: flex; gap: 8px; margin-left: auto; }
.icon-btn {
  background: var(--icon-btn-bg);
  border: 1px solid var(--icon-btn-border);
  color: var(--icon-btn-color);
  width: 32px; height: 32px;
  border-radius: 8px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}
.icon-btn svg { width: 15px; height: 15px; }
.icon-btn:hover { background: var(--icon-btn-hover-bg); color: var(--text); }

/* ─── 設定面板 ─── */
.settings-aside {
  position: fixed;
  top: 48px; right: 0; bottom: 0;
  width: 300px;
  background: var(--aside-bg);
  backdrop-filter: blur(16px);
  border-left: 1px solid var(--aside-border);
  z-index: 50;
  padding: 24px 20px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  overflow-y: auto;
}

.aside-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 17px;
  font-weight: 700;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--aside-border);
}
.close-btn {
  background: none; border: none;
  color: var(--close-btn);
  font-size: 18px; cursor: pointer; padding: 4px 8px;
  transition: color 0.2s;
}
.close-btn:hover { color: var(--text); }

.setting-group {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.setting-group label {
  font-size: 13px;
  color: var(--setting-label);
}
.setting-group input[type=range] {
  width: 100%;
  accent-color: #818cf8;
}
.toggle-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: var(--toggle-label);
  cursor: pointer;
  margin-bottom: 4px;
}
.toggle-row input { width: 18px; height: 18px; accent-color: #818cf8; }

.layout-btns { display: flex; gap: 8px; }
.layout-btn {
  flex: 1;
  padding: 8px;
  border: 1px solid var(--layout-btn-border);
  border-radius: 8px;
  background: var(--layout-btn-bg);
  color: var(--layout-btn-color);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.layout-btn.active { background: #4f46e5; border-color: #4f46e5; color: #fff; }
.layout-btn:hover:not(.active) { background: var(--layout-btn-hover-bg); }

/* ─── 字幕區（固定高度，可捲動，聊天室模式）─── */
.subtitle-area {
  grid-row: 2;
  overflow-y: auto;          /* 容器內部可捲動 */
  padding: 24px 40px 50px;
  display: flex;
  flex-direction: column;    /* spacer + list 由上到下 */
  scroll-behavior: auto;     /* 程式捲動用 instant，按鈕用 smooth */
}

/* spacer：字幕少時撐開空間，讓字幕靠底部 */
.spacer { flex: 1; min-height: 0; }

/* layout-top 時字幕靠頂部，不需要 spacer 效果 */
.layout-top-mode .spacer { display: none; }

.subtitle-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 空狀態 */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  flex: 1;                   /* 撐滿整個容器使其垂直置中 */
  color: var(--empty-color);
  font-size: 15px;
}

.pulse-ring {
  width: 48px; height: 48px;
  border: 3px solid var(--pulse-ring);
  border-top-color: var(--pulse-top);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ─── 字幕卡片 ─── */
.subtitle-card {
  padding: 14px 20px;
  background: rgba(var(--card-rgb), calc(var(--bg-opacity, 0.7) * 0.06));
  border-radius: 14px;
  border-left: 4px solid var(--card-border);
  transition: border-color 0.3s;
}

.subtitle-card.latest {
  border-left-color: var(--card-border-latest);
  background: rgba(var(--card-latest-rgb), calc(var(--bg-opacity, 0.7) * 0.08));
}

.sub-line {
  line-height: 1.55;
  word-break: break-word;
}

.sub-line.original {
  color: var(--original-color);
  font-weight: 400;
  text-shadow: var(--sub-shadow);
}

.sub-line.translated {
  color: var(--translated-color);
  font-weight: 700;
  margin-top: 6px;
  text-shadow: var(--sub-shadow);
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
.sub-fade-enter-active { transition: opacity 0.3s ease, transform 0.3s ease; }
.sub-fade-enter-from { opacity: 0; transform: translateY(12px); }

.panel-slide-enter-active,
.panel-slide-leave-active { transition: transform 0.3s ease, opacity 0.3s ease; }
.panel-slide-enter-from,
.panel-slide-leave-to { transform: translateX(100%); opacity: 0; }

.jump-fade-enter-active,
.jump-fade-leave-active { transition: opacity 0.25s ease, transform 0.25s ease; }
.jump-fade-enter-from,
.jump-fade-leave-to { opacity: 0; transform: translateX(-50%) translateY(8px); }

/* ─── 捲動條美化 ─── */
.subtitle-area::-webkit-scrollbar { width: 5px; }
.subtitle-area::-webkit-scrollbar-track { background: transparent; }
.subtitle-area::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: 99px;
}
.settings-aside::-webkit-scrollbar { width: 4px; }
.settings-aside::-webkit-scrollbar-thumb {
  background: var(--scrollbar-aside); border-radius: 99px;
}
</style>
