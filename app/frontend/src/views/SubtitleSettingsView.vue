<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';

// 基本顯示設定
const fontSize = ref(24);
const fontWeight = ref(700);
const showOriginal = ref(true);
const showTranslated = ref(true);
const showTimestamp = ref(false);
const position = ref<'top' | 'bottom'>('bottom');
const autoScroll = ref(true);
const maxDisplayCount = ref(5);

// 顏色設定
const textColor = ref('#FFFFFF');
const translatedColor = ref('#FFDD00');
const timestampColor = ref('#888888'); // 時間碼顏色(灰色)
const backgroundColor = ref('#000000');
const backgroundOpacity = ref(50);

// BroadcastChannel 用於跨視窗通訊
let settingsChannel: BroadcastChannel | null = null;

function buildSettings() {
  return {
    fontSize: fontSize.value,
    fontWeight: fontWeight.value,
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
}

async function saveSettings() {
  const settings = buildSettings();
  localStorage.setItem('subtitleSettings', JSON.stringify(settings));
  
  // 使用 BroadcastChannel 通知其他視窗
  if (settingsChannel) {
    settingsChannel.postMessage(settings);
    console.log('設定已廣播到字幕視窗');
  }

  try {
    await fetch('/api/config/subtitle_settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings)
    });
  } catch (e) {
    console.error('儲存字幕設定到後端失敗:', e);
  }
  
  console.log('設定已儲存');
}

function hexToRgb(hex: string): string {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (result) {
    return `${parseInt(result[1], 16)}, ${parseInt(result[2], 16)}, ${parseInt(result[3], 16)}`;
  }
  return '0, 0, 0';
}

async function loadSettingsFromBackend() {
  try {
    const response = await fetch('/api/config');
    const data = await response.json();
    const config = data?.data ?? data;
    const settings = config?.subtitle_settings;
    if (!settings) return false;

    fontSize.value = settings.fontSize ?? fontSize.value;
    fontWeight.value = settings.fontWeight ?? fontWeight.value;
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
    return true;
  } catch (e) {
    console.error('讀取字幕設定失敗:', e);
    return false;
  }
}

onMounted(async () => {
  // 初始化 BroadcastChannel
  try {
    settingsChannel = new BroadcastChannel('subtitle-settings');
    console.log('SubtitleSettingsView: BroadcastChannel 已初始化');
  } catch (e) {
    console.error('BroadcastChannel 初始化失敗:', e);
  }
  
  const loaded = await loadSettingsFromBackend();
  if (!loaded) {
    const saved = localStorage.getItem('subtitleSettings');
    if (saved) {
      try {
        const settings = JSON.parse(saved);
        fontSize.value = settings.fontSize ?? fontSize.value;
        fontWeight.value = settings.fontWeight ?? fontWeight.value;
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
      } catch (e) {
        console.error('載入字幕設定失敗:', e);
      }
    }
  }
});

onUnmounted(() => {
  if (settingsChannel) {
    settingsChannel.close();
  }
});

watch([fontSize, fontWeight, showOriginal, showTranslated, showTimestamp, position, autoScroll, maxDisplayCount, textColor, translatedColor, timestampColor, backgroundColor, backgroundOpacity], () => {
  saveSettings();
});

const activeTab = ref<'display' | 'color'>('display');
</script>

<template>
  <div class="w-full h-full bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 p-6 overflow-y-auto">
    <div class="max-w-2xl mx-auto">
      <h1 class="text-2xl font-bold text-white mb-6">字幕設定</h1>

      <!-- 分頁標籤 -->
      <div class="flex border-b border-white/20 mb-6">
        <button
          @click="activeTab = 'display'"
          :class="['flex-1 py-3 text-sm font-semibold transition', activeTab === 'display' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-white/60 hover:text-white']"
        >顯示</button>
        <button
          @click="activeTab = 'color'"
          :class="['flex-1 py-3 text-sm font-semibold transition', activeTab === 'color' ? 'text-blue-400 border-b-2 border-blue-400' : 'text-white/60 hover:text-white']"
        >顏色</button>
      </div>

      <!-- 顯示設定 -->
      <div v-show="activeTab === 'display'" class="space-y-6">
        <!-- 字體大小 -->
        <div>
          <label class="block text-white/90 text-sm mb-2 font-medium">字體大小: {{ fontSize }}px</label>
          <input v-model.number="fontSize" type="range" min="16" max="80" class="w-full accent-blue-500 h-2" />
        </div>

        <!-- 字體粗細 -->
        <div>
          <label class="block text-white/90 text-sm mb-2 font-medium">字體粗細: {{ fontWeight }}</label>
          <input v-model.number="fontWeight" type="range" min="300" max="900" step="100" class="w-full accent-blue-500 h-2" />
        </div>

        <!-- 位置 -->
        <div>
          <label class="block text-white/90 text-sm mb-3 font-medium">位置</label>
          <div class="flex gap-3">
            <button
              @click="position = 'top'"
              :class="['flex-1 py-3 rounded-lg font-semibold transition', position === 'top' ? 'bg-blue-600 text-white shadow-lg' : 'bg-white/10 text-white hover:bg-white/20']"
            >頂部</button>
            <button
              @click="position = 'bottom'"
              :class="['flex-1 py-3 rounded-lg font-semibold transition', position === 'bottom' ? 'bg-blue-600 text-white shadow-lg' : 'bg-white/10 text-white hover:bg-white/20']"
            >底部</button>
          </div>
        </div>

        <!-- 顯示數量 -->
        <div>
          <label class="block text-white/90 text-sm mb-2 font-medium">顯示字幕數量: {{ maxDisplayCount }}</label>
          <input v-model.number="maxDisplayCount" type="range" min="1" max="100" class="w-full accent-blue-500 h-2" />
        </div>

        <!-- 顯示選項 -->
        <div class="space-y-3 pt-2">
          <label class="flex items-center gap-3 cursor-pointer group">
            <input v-model="showOriginal" type="checkbox" class="w-5 h-5 accent-blue-500" />
            <span class="text-white text-sm group-hover:text-blue-300 transition">顯示原文</span>
          </label>
          <label class="flex items-center gap-3 cursor-pointer group">
            <input v-model="showTranslated" type="checkbox" class="w-5 h-5 accent-blue-500" />
            <span class="text-white text-sm group-hover:text-blue-300 transition">顯示翻譯</span>
          </label>
          <label class="flex items-center gap-3 cursor-pointer group">
            <input v-model="showTimestamp" type="checkbox" class="w-5 h-5 accent-blue-500" />
            <span class="text-white text-sm group-hover:text-blue-300 transition">顯示時間戳</span>
          </label>
          <label class="flex items-center gap-3 cursor-pointer group">
            <input v-model="autoScroll" type="checkbox" class="w-5 h-5 accent-blue-500" />
            <span class="text-white text-sm group-hover:text-blue-300 transition">自動捲動</span>
          </label>
        </div>
      </div>

      <!-- 顏色設定 -->
      <div v-show="activeTab === 'color'" class="space-y-6">
        <div class="grid grid-cols-2 gap-6">
          <div>
            <label class="block text-white/90 text-sm mb-2 font-medium">原文顏色</label>
            <input v-model="textColor" type="color" class="w-full h-12 rounded-lg cursor-pointer bg-transparent border-2 border-white/20" />
            <p class="text-white/50 text-xs mt-1">{{ textColor }}</p>
          </div>
          <div>
            <label class="block text-white/90 text-sm mb-2 font-medium">翻譯顏色</label>
            <input v-model="translatedColor" type="color" class="w-full h-12 rounded-lg cursor-pointer bg-transparent border-2 border-white/20" />
            <p class="text-white/50 text-xs mt-1">{{ translatedColor }}</p>
          </div>
          <div>
            <label class="block text-white/90 text-sm mb-2 font-medium">時間碼顏色</label>
            <input v-model="timestampColor" type="color" class="w-full h-12 rounded-lg cursor-pointer bg-transparent border-2 border-white/20" />
            <p class="text-white/50 text-xs mt-1">{{ timestampColor }}</p>
          </div>
        </div>
        
        <div>
          <label class="block text-white/90 text-sm mb-2 font-medium">背景顏色</label>
          <input v-model="backgroundColor" type="color" class="w-full h-12 rounded-lg cursor-pointer bg-transparent border-2 border-white/20" />
          <p class="text-white/50 text-xs mt-1">{{ backgroundColor }}</p>
        </div>

        <div>
          <label class="block text-white/90 text-sm mb-2 font-medium">背景透明度: {{ backgroundOpacity }}%</label>
          <input v-model.number="backgroundOpacity" type="range" min="0" max="100" class="w-full accent-blue-500 h-2" />
        </div>

        <!-- 預覽 -->
        <div class="pt-6 border-t border-white/20">
          <p class="text-white/90 text-sm mb-3 font-medium">預覽</p>
          <div
            :style="{
              fontSize: Math.min(fontSize * 0.5, 20) + 'px',
              fontWeight: fontWeight,
              backgroundColor: `rgba(${hexToRgb(backgroundColor)}, ${backgroundOpacity / 100})`
            }"
            class="p-4 rounded-lg text-center"
          >
            <div v-if="showTimestamp" :style="{ color: timestampColor, fontSize: '10px', opacity: 0.7 }" class="mb-1">00:00:10</div>
            <div v-if="showOriginal" :style="{ color: textColor, textShadow: '1px 1px 3px rgba(0,0,0,0.8)' }">こんにちは</div>
            <div v-if="showTranslated" :style="{ color: translatedColor, textShadow: '1px 1px 3px rgba(0,0,0,0.8)' }" class="font-bold mt-1">你好</div>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>
