<script setup lang="ts">
import { ref, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';

const router = useRouter();
const route = useRoute();
const appVersion = import.meta.env.VITE_APP_VERSION || '1.3.11';
const isMobileMenuOpen = ref(false);

// Define navigation items
const primaryNavigation = [
  { path: '/', name: '即時轉譯', icon: '🎙️', id: 'home' },
  { path: '/subtitle-style', name: '字幕外觀', icon: '🎨', id: 'subtitle-style' },
  { path: '/guide', name: '使用教學', icon: '📖', id: 'guide' }
];

type SettingsNavItem = { id: string; name: string; icon: string; path?: string };
const settingsGroups: Array<{ groupName: string; items: SettingsNavItem[] }> = [
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
      { id: 'model_management', name: 'ASR模型管理', icon: '📦' }
    ]
  },
  {
    groupName: '翻譯與術語',
    items: [
      { id: 'translation', name: '翻譯選項', icon: '🌐' },
      { id: 'llama', name: 'Llama 執行設定', icon: '🦙' },
      { id: 'llm-models', path: '/llm-models', name: 'LLM 模型管理', icon: '🧠' },
      { id: 'terminology', name: '術語表', icon: '📖' }
    ]
  }
];

// Check active status
function isTabActive(tabId: string) {
  if (tabId === 'llm-models') return route.path === '/llm-models';
  if (route.path === '/settings') {
    return (route.query.tab || 'general') === tabId;
  }
  return false;
}

function navigateTo(path: string, tabId?: string) {
  isMobileMenuOpen.value = false;
  if (tabId) {
    if (route.path === '/settings' && route.query.tab === tabId) return;
    router.replace({ path: '/settings', query: { tab: tabId } });
  } else {
    if (route.path === path) return;
    router.push(path);
  }
}

watch(() => route.fullPath, () => {
  isMobileMenuOpen.value = false;
});
</script>

<template>
  <div class="flex h-screen w-screen flex-col overflow-hidden bg-slate-950 text-white font-sans md:flex-row">
    <!-- Mobile Header -->
    <header class="relative z-40 flex h-14 flex-shrink-0 items-center justify-between border-b border-white/10 bg-slate-950/95 px-4 backdrop-blur md:hidden">
      <div class="flex min-w-0 items-center gap-2.5">
        <span class="text-xl">🎙️</span>
        <div class="min-w-0">
          <h1 class="truncate text-[11px] font-bold uppercase tracking-[0.16em] text-white">Stream Translator</h1>
          <p class="mt-0.5 text-[9px] font-semibold tracking-wider text-indigo-300/60">即時字幕翻譯系統</p>
        </div>
      </div>
      <button
        type="button"
        class="flex h-10 w-10 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-lg text-white transition active:scale-95 active:bg-white/10"
        :aria-expanded="isMobileMenuOpen"
        aria-label="開啟導覽選單"
        @click="isMobileMenuOpen = true"
      >
        ☰
      </button>
    </header>

    <Transition name="drawer-fade">
      <button
        v-if="isMobileMenuOpen"
        type="button"
        class="fixed inset-0 z-40 bg-black/65 backdrop-blur-[2px] md:hidden"
        aria-label="關閉導覽選單"
        @click="isMobileMenuOpen = false"
      ></button>
    </Transition>

    <!-- Left Sidebar -->
    <aside
      :class="[
        'fixed inset-y-0 right-0 z-50 flex w-[min(19rem,86vw)] flex-shrink-0 flex-col justify-between border-l border-white/10 bg-slate-950/98 shadow-2xl transition-transform duration-200 md:static md:z-auto md:w-60 md:translate-x-0 md:border-l-0 md:border-r md:bg-slate-950/95 md:shadow-none',
        isMobileMenuOpen ? 'translate-x-0' : 'translate-x-full'
      ]"
    >
      <div>
        <!-- App Header / Logo -->
        <div class="p-5 border-b border-white/5 flex items-center gap-3">
          <span class="text-2xl">🎙️</span>
          <div>
            <h1 class="text-xs font-bold text-white tracking-widest uppercase">Stream Translator</h1>
            <p class="text-[9px] text-indigo-300/60 font-semibold tracking-wider mt-0.5">即時字幕翻譯系統</p>
          </div>
          <button
            type="button"
            class="ml-auto flex h-9 w-9 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-white/70 md:hidden"
            aria-label="關閉導覽選單"
            @click="isMobileMenuOpen = false"
          >
            ✕
          </button>
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
                @click="tab.path ? navigateTo(tab.path) : navigateTo('/settings', tab.id)"
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
        <span>v{{ appVersion }}</span>
      </div>
    </aside>

    <!-- Right Content Panel -->
    <main class="app-scroll-surface relative min-h-0 min-w-0 flex-1 overflow-y-auto bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950/40">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-scroll-surface {
  background-color: rgb(2 6 23);
  overscroll-behavior: contain;
  isolation: isolate;
}
</style>

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

.drawer-fade-enter-active,
.drawer-fade-leave-active {
  transition: opacity 0.2s ease;
}

.drawer-fade-enter-from,
.drawer-fade-leave-to {
  opacity: 0;
}
</style>
