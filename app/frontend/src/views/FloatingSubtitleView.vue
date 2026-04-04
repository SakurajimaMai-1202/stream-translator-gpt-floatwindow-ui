<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useTranslationStore } from '../stores/translation';

const store = useTranslationStore();

// 基本顯示設定
const fontSize = ref(24);
const fontWeight = ref(700);
const opacity = ref(100);
const showOriginal = ref(true);
const showTranslated = ref(true);
const showTimestamp = ref(false);
const position = ref<'top' | 'bottom'>('bottom');
const autoScroll = ref(true);
const maxDisplayCount = ref(5);

// 顏色設定
const textColor = ref('#FFFFFF');
const translatedColor = ref('#FFDD00'); // 更亮一點的黃色
const timestampColor = ref('#888888'); // 時間碼顏色(灰色)
const backgroundColor = ref('#000000');
const backgroundOpacity = ref(50);

// 初始化旗標：防止 watch 在設定載入完成前覆蓋正確值
const isInitializing = ref(true);

// 字幕歷史
const subtitleHistory = ref<Array<{
  id: number;
  timestamp_id: string; // 來自後端的原始時間碼範圍字串
  original: string;
  translated: string;
  timestamp: Date;
}>>([]); 

// 滾動容器引用
const scrollContainer = ref<HTMLElement | null>(null);
const isUserScrolling = ref(false);
let scrollTimeout: number | null = null;

// 計算樣式
const containerStyle = computed(() => {
  const bgColor = `rgba(${hexToRgb(backgroundColor.value)}, ${backgroundOpacity.value / 100})`;
  return {
    fontSize: `${fontSize.value}px`,
    fontWeight: fontWeight.value,
    backgroundColor: bgColor
  };
});

function hexToRgb(hex: string): string {
  if (!hex || typeof hex !== 'string') return '0, 0, 0';
  const cleaned = hex.startsWith('#') ? hex : `#${hex}`;
  const result = /^#([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(cleaned);
  if (result) {
    return `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`;
  }
  console.warn(`[hexToRgb] 無效的顏色值: '${hex}'，使用黑色替代`);
  return '0, 0, 0';
}

// 共用的字幕新增或更新邏輯
function addOrUpdateSubtitle(newSub: any, source: string = 'Store') {
  if (!newSub || (!newSub.original && !newSub.translated)) return;
  
  console.log(`[${source}] 收到新字幕:`, newSub);
  const ts = newSub.backend_timestamp;
  let existingIndex = -1;
  
  // 若後端有提供時間戳，則以此尋找是否已存在該筆字幕
  if (ts) {
    existingIndex = subtitleHistory.value.findIndex(sub => sub.timestamp_id === ts);
  }
  
  if (existingIndex !== -1) {
    // 找到了，直接更新該筆字幕的內容
    subtitleHistory.value[existingIndex].original = newSub.original || '';
    subtitleHistory.value[existingIndex].translated = newSub.translated || '';
    subtitleHistory.value[existingIndex].timestamp = new Date(); // 更新最後收到時間
  } else {
    // 沒找到，新增一筆
    subtitleHistory.value.push({
      id: Date.now() + Math.random(), // 確保 key 唯一
      timestamp_id: ts || '',
      original: newSub.original || '',
      translated: newSub.translated || '',
      timestamp: new Date()
    });
  }
  
  // 限制歷史數量
  while (subtitleHistory.value.length > 50) {
    subtitleHistory.value.shift();
  }
  
  // 自動捲動到底部
  if (autoScroll.value && !isUserScrolling.value) {
    scrollToBottom();
  }
}

// 注意：FloatingSubtitleView 改為只使用 BroadcastChannel 接收字幕
// 不再監聽 store.latestSubtitle 避免與 BroadcastChannel 重複觸發兩次
// (Store 更新字幕後會廣播，FloatingView 只需從 BroadcastChannel 接收)

// 使用 BroadcastChannel 接收字幕
let subtitleChannel: BroadcastChannel | null = null;
// 使用 BroadcastChannel 接收設定變更
let settingsChannel: BroadcastChannel | null = null;

function initSubtitleChannel() {
  try {
    subtitleChannel = new BroadcastChannel('subtitle-updates');
    subtitleChannel.onmessage = (event) => {
      addOrUpdateSubtitle(event.data, 'BroadcastChannel');
    };
    console.log('字幕 BroadcastChannel 已初始化');
  } catch (error) {
    console.error('字幕 BroadcastChannel 初始化失敗:', error);
  }
}

function initSettingsChannel() {
  try {
    settingsChannel = new BroadcastChannel('subtitle-settings');
    settingsChannel.onmessage = (event) => {
      const settings = event.data;
      if (settings) {
        console.log('從設定視窗收到更新:', settings);
        applySettings(settings);
      }
    };
    console.log('設定 BroadcastChannel 已初始化');
  } catch (error) {
    console.error('設定 BroadcastChannel 初始化失敗:', error);
  }
}

function applySettings(settings: any) {
  fontSize.value = settings.fontSize ?? fontSize.value;
  fontWeight.value = settings.fontWeight ?? fontWeight.value;
  opacity.value = settings.opacity ?? opacity.value;
  showOriginal.value = settings.showOriginal ?? showOriginal.value;
  showTranslated.value = settings.showTranslated ?? showTranslated.value;
  showTimestamp.value = settings.showTimestamp ?? showTimestamp.value;
  position.value = settings.position ?? position.value;
  autoScroll.value = settings.autoScroll ?? autoScroll.value;
  maxDisplayCount.value = settings.maxDisplayCount ?? maxDisplayCount.value;
  textColor.value = settings.textColor ?? textColor.value;
  translatedColor.value = settings.translatedColor ?? translatedColor.value;
  timestampColor.value = settings.timestampColor ?? timestampColor.value;
  backgroundColor.value = settings.backgroundColor ?? backgroundColor.value;
  backgroundOpacity.value = settings.backgroundOpacity ?? backgroundOpacity.value;
  console.log('設定已即時更新，原文顏色:', textColor.value, '翻譯顏色:', translatedColor.value, '時間碼顏色:', timestampColor.value);
}

// 滾動到底部
function scrollToBottom() {
  if (scrollContainer.value) {
    setTimeout(() => {
      if (scrollContainer.value) {
        scrollContainer.value.scrollTop = scrollContainer.value.scrollHeight;
      }
    }, 50);
  }
}

// 檢查是否在底部
function isAtBottom(): boolean {
  if (!scrollContainer.value) return true;
  const threshold = 50; // 50px 容差
  const { scrollTop, scrollHeight, clientHeight } = scrollContainer.value;
  return scrollHeight - scrollTop - clientHeight < threshold;
}

// 處理用戶滾動
function handleScroll() {
  if (!scrollContainer.value) return;
  
  // 清除之前的計時器
  if (scrollTimeout !== null) {
    clearTimeout(scrollTimeout);
  }
  
  // 檢查是否在底部
  if (isAtBottom()) {
    // 在底部，重新啟用自動滾動
    isUserScrolling.value = false;
  } else {
    // 不在底部，表示用戶正在查看歷史
    isUserScrolling.value = true;
  }
  
  // 設定計時器，2秒後如果還在底部則確認不是用戶滾動
  scrollTimeout = window.setTimeout(() => {
    if (isAtBottom()) {
      isUserScrolling.value = false;
    }
  }, 2000);
}

// 顯示的字幕
const displaySubtitles = computed(() => {
  return subtitleHistory.value.slice(-maxDisplayCount.value);
});

// 格式化時間戳
function formatTimestamp(date: Date): string {
  return date.toLocaleTimeString('zh-TW', { hour12: false, hour: '2-digit', minute: '2-digit' });
}

// 儲存設定到 localStorage
async function saveSettings() {
  const settings = {
    fontSize: fontSize.value,
    fontWeight: fontWeight.value,
    opacity: opacity.value,
    showOriginal: showOriginal.value,
    showTranslated: showTranslated.value,
    showTimestamp: showTimestamp.value,
    position: position.value,
    autoScroll: autoScroll.value,
    maxDisplayCount: maxDisplayCount.value,
    textColor: textColor.value,
    translatedColor: translatedColor.value,
    timestampColor: timestampColor.value,
    backgroundColor: backgroundColor.value,
    backgroundOpacity: backgroundOpacity.value
  };
  localStorage.setItem('subtitleSettings', JSON.stringify(settings));
  try {
    await fetch('/api/config/subtitle_settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings)
    });
  } catch (e) {
    console.error('儲存字幕設定到後端失敗:', e);
  }
  console.log('💾 已儲存字幕設定');
}

async function loadSettingsFromBackend() {
  try {
    const response = await fetch('/api/config');
    const data = await response.json();
    const config = data?.data ?? data;
    const settings = config?.subtitle_settings;
    if (!settings) return false;

    applySettings(settings);
    return true;
  } catch (e) {
    console.error('讀取字幕設定失敗:', e);
    return false;
  }
}

onMounted(async () => {
  console.log('FloatingSubtitleView mounted');
  console.log('Store:', store);
  console.log('Latest subtitle:', store.latestSubtitle);
  
  // 標記初始化開始（阻止 watch 觸發 saveSettings）
  isInitializing.value = true;
  
  // 優先載入設定（在初始化其他功能之前）
  const loaded = await loadSettingsFromBackend();
  if (!loaded) {
    const saved = localStorage.getItem('subtitleSettings');
    if (saved) {
      try {
        const settings = JSON.parse(saved);
        fontSize.value = settings.fontSize ?? fontSize.value;
        fontWeight.value = settings.fontWeight ?? fontWeight.value;
        opacity.value = settings.opacity ?? opacity.value;
        showOriginal.value = settings.showOriginal ?? showOriginal.value;
        showTranslated.value = settings.showTranslated ?? showTranslated.value;
        showTimestamp.value = settings.showTimestamp ?? showTimestamp.value;
        position.value = settings.position ?? position.value;
        autoScroll.value = settings.autoScroll ?? autoScroll.value;
        maxDisplayCount.value = settings.maxDisplayCount ?? maxDisplayCount.value;
        textColor.value = settings.textColor ?? textColor.value;
        translatedColor.value = settings.translatedColor ?? translatedColor.value;
        timestampColor.value = settings.timestampColor ?? timestampColor.value;
        backgroundColor.value = settings.backgroundColor ?? backgroundColor.value;
        backgroundOpacity.value = settings.backgroundOpacity ?? backgroundOpacity.value;
        console.log('✅ 成功載入字幕設定:', {
          fontSize: fontSize.value,
          textColor: textColor.value,
          translatedColor: translatedColor.value,
          backgroundColor: backgroundColor.value,
          backgroundOpacity: backgroundOpacity.value
        });
      } catch (e) {
        console.error('❌ 載入字幕設定失敗:', e);
      }
    } else {
      console.log('ℹ️ 未找到儲存的字幕設定，使用預設值');
    }
  }
  
  // 初始化完成，解除 watch 封鎖
  isInitializing.value = false;
  
  // 初始化 BroadcastChannel
  initSubtitleChannel();
  initSettingsChannel();

  // 監聯 storage 事件作為備用
  window.addEventListener('storage', handleStorageChange);
  
  if (window.qt && window.qt.webChannelTransport) {
    new window.QWebChannel(window.qt.webChannelTransport, (channel: any) => {
      window.bridge = channel.objects.bridge;
      console.log('WebChannel 已連接');
    });
  }
});

onUnmounted(() => {
  // 移除事件監聽器
  window.removeEventListener('storage', handleStorageChange);
  // 關閉 BroadcastChannel
  if (subtitleChannel) {
    subtitleChannel.close();
  }
  if (settingsChannel) {
    settingsChannel.close();
  }
});

// 處理 storage 變更事件（備用方案）
function handleStorageChange(e: StorageEvent) {
  if (e.key === 'subtitleSettings' && e.newValue) {
    try {
      const settings = JSON.parse(e.newValue);
      applySettings(settings);
      console.log('從 StorageEvent 更新設定');
    } catch (e) {
      console.error('即時更新設定失敗:', e);
    }
  }
}

// 自動儲存設定（初始化完成後才觸發）
watch([fontSize, fontWeight, opacity, showOriginal, showTranslated, showTimestamp, position, autoScroll, maxDisplayCount, textColor, translatedColor, timestampColor, backgroundColor, backgroundOpacity], () => {
  if (!isInitializing.value) {
    saveSettings();
  }
});

const showSettings = ref(false);
const activeSettingsTab = ref<'display' | 'color'>('display');

// 清除歷史
function clearHistory() {
  subtitleHistory.value = [];
}

// WebChannel 橋接（如果可用）
declare global {
  interface Window {
    qt?: {
      webChannelTransport?: any;
    };
    QWebChannel?: any;
    bridge?: {
      requestOpenSettings: () => void;
      requestCloseWindow?: () => void;
    };
  }
}

function openSettings() {
  // 如果在 Qt 環境中，使用橋接
  if (window.bridge && window.bridge.requestOpenSettings) {
    window.bridge.requestOpenSettings();
  } else {
    // 否則顯示內嵌面板（開發模式）
    showSettings.value = !showSettings.value;
  }
}

function closeSubtitleWindow() {
  if (window.bridge && window.bridge.requestCloseWindow) {
    window.bridge.requestCloseWindow();
  } else {
    window.close();
  }
}

async function stopTranslation() {
  try {
    // 先獲取所有活動任務
    const response = await fetch('/api/translation/status');
    const data = await response.json();
    
    if (data.tasks && data.tasks.length > 0) {
      // 停止所有活動任務
      await Promise.all(
        data.tasks.map((task: any) =>
          fetch(`/api/translation/stop/${task.task_id}`, { method: 'DELETE' })
        )
      );
      console.log('✅ 所有翻譯任務已停止');
    } else {
      console.log('ℹ️ 沒有活動的翻譯任務');
    }
  } catch (error) {
    console.error('❌ 停止翻譯失敗:', error);
  }
}

// NOTE: 第二個 onMounted 已移除（WebChannel 初始化已在第一個 onMounted 中完成）
</script>

<template>
  <div class="relative w-full h-full overflow-hidden bg-transparent group">
    <!-- Subtitle Display -->
    <div
      ref="scrollContainer"
      @scroll="handleScroll"
      :style="containerStyle"
      :class="[
        'absolute left-0 right-0 top-0 bottom-0 px-4 py-2 transition-all duration-300 flex flex-col rounded-lg overflow-y-auto',
        position === 'top' ? 'justify-start' : 'justify-end'
      ]"
    >
      <div v-if="displaySubtitles.length > 0" class="space-y-3" :class="autoScroll ? 'scroll-smooth' : ''">
        <div v-for="sub in displaySubtitles" :key="sub.id" class="text-left leading-relaxed">
          <!-- 時間戳 -->
          <div v-if="showTimestamp" class="text-xs opacity-70 font-mono mb-1" :style="{ color: timestampColor }">
            {{ formatTimestamp(sub.timestamp) }}
          </div>
          
          <!-- 原文 -->
          <div
            v-if="showOriginal && sub.original"
            class="flex items-start gap-1.5"
          >
            <!-- 原文色塊指示器 -->
            <span
              class="flex-shrink-0 w-1 rounded-full mt-1 self-stretch"
              :style="{ backgroundColor: textColor, transition: 'background-color 0.3s ease' }"
            ></span>
            <span
              class="tracking-wide drop-shadow-lg"
              :style="{ 
                color: textColor,
                fontWeight: fontWeight,
                textShadow: '2px 2px 4px rgba(0,0,0,0.9)',
                transition: 'color 0.3s ease'
              }"
            >{{ sub.original }}</span>
          </div>
         
          <!-- 翻譯 -->
          <div
            v-if="showTranslated && sub.translated"
            class="flex items-start gap-1.5 mt-1"
          >
            <!-- 翻譯色塊指示器 -->
            <span
              class="flex-shrink-0 w-1 rounded-full mt-1 self-stretch"
              :style="{ backgroundColor: translatedColor, transition: 'background-color 0.3s ease' }"
            ></span>
            <span
              class="tracking-wide drop-shadow-lg"
              :style="{ 
                color: translatedColor, 
                fontWeight: fontWeight, 
                textShadow: '2px 2px 4px rgba(0,0,0,0.9)',
                transition: 'color 0.3s ease'
              }"
            >{{ sub.translated }}</span>
          </div>
        </div>
      </div>
      <!-- 調試資訊 -->
      <div v-else class="text-white/50 text-sm text-center py-4">
        <p>等待字幕...</p>
        <p class="text-xs mt-2">Store subtitles: {{ store.subtitles.length }}</p>
        <p class="text-xs">History: {{ subtitleHistory.length }}</p>
        <p class="text-xs mt-2">原文顏色: {{ textColor }}</p>
        <p class="text-xs">翻譯顏色: {{ translatedColor }}</p>
      </div>
    </div>

    <!-- Resize visual cue (Bottom Right) -->
    <div class="absolute bottom-1 right-1 w-4 h-4 opacity-0 group-hover:opacity-50 transition-opacity pointer-events-none">
      <svg viewBox="0 0 24 24" fill="white">
        <path d="M22 22H20V20H22V22ZM22 18H18V22H20V20H22V18ZM18 18H16V22H18V18Z" />
      </svg>
    </div>

    <!-- 垂直按鈕列（預設可見，避免首次開啟 hover 未觸發導致消失） -->
    <div class="absolute top-2 right-2 flex flex-col gap-2 opacity-75 hover:opacity-100 transition-opacity z-50">
      <!-- Settings Toggle Button -->
      <button
        @click="openSettings"
        class="bg-black/40 hover:bg-black/80 text-white p-2 rounded-full transition-all shadow-lg backdrop-blur-sm transform scale-90 hover:scale-100"
        title="設定"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
      </button>

      <!-- Stop Translation Button -->
      <button
        @click="stopTranslation"
        class="bg-black/40 hover:bg-red-600/80 text-white p-2 rounded-full transition-all shadow-lg backdrop-blur-sm transform scale-90 hover:scale-100"
        title="停止翻譯"
      >
        <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>
      </button>

      <!-- Clear History Button -->
      <button
        v-if="subtitleHistory.length > 0"
        @click="clearHistory"
        class="bg-black/40 hover:bg-yellow-600/80 text-white p-2 rounded-full transition-all shadow-lg backdrop-blur-sm transform scale-90 hover:scale-100"
        title="清除歷史"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
      </button>

      <!-- Close Button -->
      <button
        @click="closeSubtitleWindow"
        class="bg-black/40 hover:bg-red-600/80 text-white p-2 rounded-full transition-all shadow-lg backdrop-blur-sm transform scale-90 hover:scale-100"
        title="關閉字幕視窗"
      >
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
      </button>
    </div>

    <!-- Settings Panel -->
    <div
      v-show="showSettings"
      class="absolute top-12 right-4 bg-gray-900/95 backdrop-blur-xl rounded-2xl shadow-2xl p-6 w-80 max-h-[calc(100vh-80px)] overflow-y-auto z-40 border border-white/20"
    >
      <div class="flex justify-between items-center mb-4">
        <h3 class="text-xl font-bold text-white">字幕設定</h3>
        <button
          @click="showSettings = false"
          class="text-white/60 hover:text-white font-bold text-2xl"
        >
          ✕
        </button>
      </div>

      <!-- 分頁標籤 -->
      <div class="flex border-b border-white/20 mb-4">
        <button
          @click="activeSettingsTab = 'display'"
          :class="['flex-1 py-2 text-sm font-semibold transition', activeSettingsTab === 'display' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-white/60 hover:text-white']"
        >顯示</button>
        <button
          @click="activeSettingsTab = 'color'"
          :class="['flex-1 py-2 text-sm font-semibold transition', activeSettingsTab === 'color' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-white/60 hover:text-white']"
        >顏色</button>
      </div>

      <!-- 顯示設定 -->
      <div v-show="activeSettingsTab === 'display'" class="space-y-4">
        <!-- 字體大小 -->
        <div>
          <label class="block text-white/70 text-sm mb-1">字體大小: {{ fontSize }}px</label>
          <input v-model.number="fontSize" type="range" min="16" max="80" class="w-full accent-blue-500" />
        </div>

        <!-- 字體粗細 -->
        <div>
          <label class="block text-white/70 text-sm mb-1">字體粗細: {{ fontWeight }}</label>
          <input v-model.number="fontWeight" type="range" min="300" max="900" step="100" class="w-full accent-blue-500" />
        </div>

        <!-- 位置 -->
        <div>
          <label class="block text-white/70 text-sm mb-2">位置</label>
          <div class="flex gap-2">
            <button
              @click="position = 'top'"
              :class="['flex-1 py-2 rounded-lg font-semibold transition', position === 'top' ? 'bg-blue-600 text-white' : 'bg-white/10 text-white hover:bg-white/20']"
            >頂部</button>
            <button
              @click="position = 'bottom'"
              :class="['flex-1 py-2 rounded-lg font-semibold transition', position === 'bottom' ? 'bg-blue-600 text-white' : 'bg-white/10 text-white hover:bg-white/20']"
            >底部</button>
          </div>
        </div>

        <!-- 顯示數量 -->
        <div>
          <label class="block text-white/70 text-sm mb-1">顯示字幕數量: {{ maxDisplayCount }}</label>
          <input v-model.number="maxDisplayCount" type="range" min="1" max="100" class="w-full accent-blue-500" />
        </div>

        <!-- 顯示選項 -->
        <div class="space-y-2 pt-2">
          <label class="flex items-center gap-2 cursor-pointer">
            <input v-model="showOriginal" type="checkbox" class="w-4 h-4 accent-blue-500" />
            <span class="text-white text-sm">顯示原文</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer">
            <input v-model="showTranslated" type="checkbox" class="w-4 h-4 accent-blue-500" />
            <span class="text-white text-sm">顯示翻譯</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer">
            <input v-model="showTimestamp" type="checkbox" class="w-4 h-4 accent-blue-500" />
            <span class="text-white text-sm">顯示時間戳</span>
          </label>
          <label class="flex items-center gap-2 cursor-pointer">
            <input v-model="autoScroll" type="checkbox" class="w-4 h-4 accent-blue-500" />
            <span class="text-white text-sm">自動捲動</span>
          </label>
        </div>
      </div>

      <!-- 顏色設定 -->
      <div v-show="activeSettingsTab === 'color'" class="space-y-4">
        <div class="grid grid-cols-2 gap-4">
          <div>
            <label class="block text-white/70 text-sm mb-1">原文顏色</label>
            <input v-model="textColor" type="color" class="w-full h-10 rounded cursor-pointer bg-transparent" />
          </div>
          <div>
            <label class="block text-white/70 text-sm mb-1">翻譯顏色</label>
            <input v-model="translatedColor" type="color" class="w-full h-10 rounded cursor-pointer bg-transparent" />
          </div>
          <div>
            <label class="block text-white/70 text-sm mb-1">時間碼顏色</label>
            <input v-model="timestampColor" type="color" class="w-full h-10 rounded cursor-pointer bg-transparent" />
          </div>
        </div>
        
        <div>
          <label class="block text-white/70 text-sm mb-1">背景顏色</label>
          <input v-model="backgroundColor" type="color" class="w-full h-10 rounded cursor-pointer bg-transparent" />
        </div>

        <div>
          <label class="block text-white/70 text-sm mb-1">背景透明度: {{ backgroundOpacity }}%</label>
          <input v-model.number="backgroundOpacity" type="range" min="0" max="100" class="w-full accent-blue-500" />
        </div>

        <!-- 預覽 -->
        <div class="pt-4 border-t border-white/10">
          <p class="text-white/70 text-sm mb-2">預覽</p>
          <div
            :style="{
              fontSize: Math.min(fontSize * 0.5, 20) + 'px',
              fontWeight: fontWeight,
              backgroundColor: `rgba(${hexToRgb(backgroundColor)}, ${backgroundOpacity / 100})`
            }"
            class="p-3 rounded-lg text-center"
          >
            <div v-if="showOriginal" :style="{ color: textColor }">こんにちは</div>
            <div v-if="showTranslated" :style="{ color: translatedColor }" class="font-bold">你好</div>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
/* 確保視窗可以透明背景 */
body {
  background: transparent !important;
}

/* 強制啟用 backdrop-filter 支援 */
.backdrop-blur-support {
  isolation: isolate;
}

/* 為不支援 backdrop-filter 的環境提供替代方案 */
@supports not (backdrop-filter: blur(10px)) {
  .backdrop-blur-support::before {
    content: '';
    position: absolute;
    inset: 0;
    background: inherit;
    filter: blur(10px);
    z-index: -1;
  }
}
</style>
