<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router';

const router = useRouter();
const route = useRoute();

// Define navigation items
const primaryNavigation = [
  { path: '/', name: '即時轉譯', icon: '🎙️', id: 'home' },
  { path: '/subtitle-style', name: '字幕外觀', icon: '🎨', id: 'subtitle-style' }
];

const settingsGroups = [
  {
    groupName: '系統與輸入',
    items: [
      { id: 'general', name: '一般設定', icon: '⚙️' },
      { id: 'input', name: '輸入選項', icon: '📥' },
      { id: 'output', name: '輸出與通知', icon: '📤' }
    ]
  },
  {
    groupName: '語音辨識與切片',
    items: [
      { id: 'audio_vad', name: '音訊切片/VAD', icon: '🔊' },
      { id: 'transcription', name: '轉錄選項', icon: '🎤' },
      { id: 'model_management', name: '模型管理', icon: '📦' }
    ]
  },
  {
    groupName: '翻譯與術語',
    items: [
      { id: 'translation', name: '翻譯選項', icon: '🌐' },
      { id: 'llama', name: 'Llama 設定', icon: '🦙' },
      { id: 'terminology', name: '術語表', icon: '📖' }
    ]
  }
];

// Check active status
function isTabActive(tabId: string) {
  if (route.path === '/settings') {
    return route.query.tab === tabId;
  }
  return false;
}

function navigateTo(path: string, tabId?: string) {
  if (tabId) {
    router.push({ path: '/settings', query: { tab: tabId } });
  } else {
    router.push(path);
  }
}
</script>

<template>
  <div class="flex h-screen w-screen overflow-hidden bg-slate-950 text-white font-sans">
    <!-- Left Sidebar -->
    <aside class="w-60 bg-slate-950/80 border-r border-white/10 flex-shrink-0 flex flex-col justify-between backdrop-blur-xl">
      <div>
        <!-- App Header / Logo -->
        <div class="p-5 border-b border-white/5 flex items-center gap-3">
          <span class="text-2xl">🎙️</span>
          <div>
            <h1 class="text-xs font-bold text-white tracking-widest uppercase">Stream Translator</h1>
            <p class="text-[9px] text-indigo-300/60 font-semibold tracking-wider mt-0.5">即時字幕翻譯系統</p>
          </div>
        </div>

        <!-- Navigation Links -->
        <div class="py-4 px-3 space-y-5 overflow-y-auto max-h-[calc(100vh-120px)] custom-scrollbar">
          <!-- Core Control Section -->
          <div>
            <div class="text-white/30 text-[9px] font-bold tracking-wider mb-2 px-2 uppercase">核心功能</div>
            <div class="space-y-0.5">
              <button
                v-for="item in primaryNavigation"
                :key="item.id"
                @click="navigateTo(item.path)"
                :class="[
                  'w-full flex items-center py-2 px-2.5 font-semibold text-left transition-all duration-200 rounded-lg text-xs',
                  route.path === item.path
                    ? 'bg-gradient-to-r from-blue-600/30 to-indigo-600/30 text-white border-l-4 border-blue-500 font-bold shadow-md shadow-blue-500/5'
                    : 'text-white/60 hover:bg-white/5 hover:text-white'
                ]"
              >
                <span class="mr-2 text-sm">{{ item.icon }}</span>
                {{ item.name }}
              </button>
            </div>
          </div>

          <!-- Settings Groups -->
          <div v-for="group in settingsGroups" :key="group.groupName">
            <div class="text-white/30 text-[9px] font-bold tracking-wider mb-2 px-2 uppercase">{{ group.groupName }}</div>
            <div class="space-y-0.5">
              <button
                v-for="tab in group.items"
                :key="tab.id"
                @click="navigateTo('/settings', tab.id)"
                :class="[
                  'w-full flex items-center py-2 px-2.5 font-semibold text-left transition-all duration-200 rounded-lg text-xs',
                  isTabActive(tab.id)
                    ? 'bg-gradient-to-r from-blue-600/30 to-indigo-600/30 text-white border-l-4 border-blue-500 font-bold shadow-md shadow-blue-500/5'
                    : 'text-white/60 hover:bg-white/5 hover:text-white'
                ]"
              >
                <span class="mr-2 text-sm">{{ tab.icon }}</span>
                {{ tab.name }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Sidebar Footer -->
      <div class="p-4 border-t border-white/5 bg-black/10 flex items-center text-[10px] text-white/30">
        <span>v1.2.0</span>
      </div>
    </aside>

    <!-- Right Content Panel -->
    <main class="flex-1 overflow-y-auto bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950/40 relative">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.08);
  border-radius: 9999px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
