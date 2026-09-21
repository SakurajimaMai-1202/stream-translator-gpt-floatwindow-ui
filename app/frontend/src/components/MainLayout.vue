<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useInterfaceModeStore } from '../stores/interfaceMode';
import { useRouter, useRoute } from 'vue-router';
import BrandIcon from './BrandIcon.vue';
import AppIcon from './AppIcon.vue';
import UiSelect from './UiSelect.vue';

const router = useRouter();
const route = useRoute();
const interfaceMode = useInterfaceModeStore();
onMounted(() => { void interfaceMode.load(); });
watch(() => interfaceMode.mode, (mode) => {
  if (mode === 'simple' && (
    route.path === '/llm-models' || route.path === '/translation-models' ||
    (route.path === '/settings' && !['general', 'translation'].includes(String(route.query.tab || 'general')))
  )) void router.replace('/');
});
const visibleSettingsGroups = computed(() => interfaceMode.isSimple
  ? [{ groupName: '常用設定', items: [{ id: 'general', name: '一般設定' }] }]
  : settingsGroups);
const appVersion = import.meta.env.VITE_APP_VERSION || '1.4.8';
const isMobileMenuOpen = ref(false);

// Define navigation items
const primaryNavigation = [
  { path: '/', name: '即時轉譯', id: 'home' },
  { path: '/subtitle-style', name: '字幕外觀', id: 'subtitle-style' },
  { path: '/guide', name: '使用教學', id: 'guide' }
];

type SettingsNavItem = { id: string; name: string; path?: string };
const settingsGroups: Array<{ groupName: string; items: SettingsNavItem[] }> = [
  {
    groupName: '系統與輸入',
    items: [
      { id: 'general', name: '一般設定' },
      { id: 'input', name: '輸入選項' },
      { id: 'output', name: '輸出與通知' }
    ]
  },
  {
    groupName: '語音辨識與切片',
    items: [
      { id: 'audio_vad', name: '音訊切片/VAD' },
      { id: 'transcription', name: '轉錄選項' },
      { id: 'model_management', name: 'ASR模型管理' }
    ]
  },
  {
    groupName: '翻譯與術語',
    items: [
      { id: 'translation', name: '翻譯選項' },
      { id: 'llama', name: 'Llama 執行設定' },
      { id: 'llm-models', path: '/llm-models', name: 'LLM 模型管理' },
      { id: 'translation-models', path: '/translation-models', name: '推薦翻譯模型' },
      { id: 'terminology', name: '術語表' }
    ]
  }
];

// Check active status
function isTabActive(tabId: string) {
  if (tabId === 'llm-models') return route.path === '/llm-models';
  if (tabId === 'translation-models') return route.path === '/translation-models';
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
  <div v-if="!interfaceMode.loaded || !interfaceMode.mode || interfaceMode.pendingMode" class="flex min-h-screen items-center justify-center bg-slate-950 p-6 text-white">
    <section class="w-full max-w-2xl space-y-6" aria-labelledby="interface-mode-title">
      <template v-if="interfaceMode.onboardingStep === 'mode'">
      <h1 id="interface-mode-title" class="text-2xl font-bold">第一次使用，選擇操作方式</h1>
      <p class="text-sm text-slate-300">簡單模式會自動準備語音辨識與翻譯；選擇會記住，之後可在側欄切換。</p>
      <div v-if="interfaceMode.loaded" class="grid gap-4 sm:grid-cols-2">
        <button :disabled="interfaceMode.busy" class="rounded-2xl border border-indigo-400 bg-indigo-500/15 p-6 text-left disabled:opacity-50" @click="interfaceMode.select('simple')">
          <span class="block text-lg font-bold">簡單模式 · 推薦</span>
          <span class="mt-3 block text-sm text-slate-300">選擇音訊來源與語言，開始翻譯。保留日常操作與字幕控制。</span>
        </button>
        <button :disabled="interfaceMode.busy" class="rounded-2xl border border-slate-600 bg-slate-900 p-6 text-left disabled:opacity-50" @click="interfaceMode.select('advanced')">
          <span class="block text-lg font-bold">進階模式</span>
          <span class="mt-3 block text-sm text-slate-300">完整設定、辨識引擎、模型管理、音訊切片、執行日誌與分享。</span>
        </button>
      </div>
      </template>
      <template v-else-if="interfaceMode.onboardingStep === 'translation'">
        <div>
          <p class="text-xs font-bold uppercase tracking-widest text-indigo-300">簡單模式設定</p>
          <h1 id="interface-mode-title" class="mt-2 text-2xl font-bold">你想用哪種方式翻譯？</h1>
          <p class="mt-2 text-sm text-slate-300">選好後，程式會自動完成其餘設定。</p>
        </div>
        <div v-if="interfaceMode.hardware?.selected_gpu" class="rounded-xl border border-white/10 bg-white/5 p-4 text-sm">
          偵測到 {{ interfaceMode.hardware.selected_gpu.name }} · {{ interfaceMode.hardware.vram_gb }} GB VRAM
          <span class="ml-2 rounded-full bg-indigo-400/15 px-2 py-1 text-xs text-indigo-200">{{ interfaceMode.hardware.vram_tier_label }}</span>
        </div>
        <div class="grid gap-4 sm:grid-cols-2">
          <button :disabled="interfaceMode.busy || !interfaceMode.hardware?.simple_setup.supported" class="rounded-2xl border border-emerald-400/40 bg-emerald-500/10 p-5 text-left disabled:opacity-45" @click="interfaceMode.configureLocal()">
            <span class="block text-lg font-bold">使用這台電腦翻譯</span>
            <span class="mt-2 block text-sm text-slate-300">自動下載 llama.cpp 與適合顯存的 Hy-MT2 模型。</span>
            <span class="mt-3 block text-xs text-emerald-200">{{ interfaceMode.hardware?.simple_setup.reason }}</span>
          </button>
          <div class="rounded-2xl border border-indigo-400/40 bg-indigo-500/10 p-5">
            <span class="block text-lg font-bold">使用 Gemini 雲端翻譯</span>
            <span class="mt-2 block text-sm text-slate-300">不下載翻譯模型，需要網路與 Google API Key。</span>
            <a href="https://aistudio.google.com/api-keys" target="_blank" rel="noopener noreferrer" class="mt-3 inline-block text-sm font-semibold text-indigo-300 underline">前往 Google AI Studio 取得 API Key ↗</a>
            <input v-model="interfaceMode.googleApiKey" type="password" autocomplete="off" placeholder="貼上 API Key" class="mt-3 w-full rounded-lg border border-white/20 bg-slate-950 px-3 py-2 text-sm text-white" />
            <button :disabled="interfaceMode.busy || !interfaceMode.googleApiKey.trim()" class="mt-3 w-full rounded-lg bg-indigo-500 px-4 py-2 text-sm font-bold disabled:opacity-45" @click="interfaceMode.configureCloud()">測試並繼續</button>
            <p class="mt-2 text-xs text-white/45">預設模型：gemini-2.5-flash-lite</p>
          </div>
        </div>
        <button class="text-sm text-slate-300 underline" @click="interfaceMode.backToModeChoice()">返回選擇介面</button>
      </template>
      <template v-else>
        <h1 id="interface-mode-title" class="text-2xl font-bold">正在自動準備</h1>
        <p class="text-sm text-slate-300">{{ interfaceMode.setupMessage }}</p>
        <div v-if="interfaceMode.runtimeInstallStatus" class="space-y-2 rounded-xl border border-white/10 p-4">
          <div class="flex items-center justify-between gap-4 text-sm">
            <p>翻譯引擎 · {{ interfaceMode.runtimeInstallStatus.message }}</p>
            <span class="shrink-0 tabular-nums text-slate-300">{{ Math.round(Math.min(1, Math.max(0, interfaceMode.runtimeInstallStatus.progress || 0)) * 100) }}%</span>
          </div>
          <progress
            class="w-full"
            :value="interfaceMode.runtimeInstallStatus.progress"
            :max="1"
            :aria-label="`翻譯引擎安裝進度 ${Math.round(Math.min(1, Math.max(0, interfaceMode.runtimeInstallStatus.progress || 0)) * 100)}%`"
          />
        </div>
        <div v-if="interfaceMode.localModelInstallStatus" class="space-y-2 rounded-xl border border-white/10 p-4">
          <p class="text-sm">翻譯模型 · {{ interfaceMode.localModelInstallStatus.message }}</p>
          <progress class="w-full" :value="interfaceMode.localModelInstallStatus.progress" :max="1" />
          <p class="text-xs text-slate-400">{{ Math.round(interfaceMode.localModelInstallStatus.progress * 100) }}%</p>
        </div>
      </template>
      <p v-if="interfaceMode.busy" role="status">{{ interfaceMode.setupMessage || (interfaceMode.loaded ? '正在儲存選擇…' : '正在讀取設定…') }}</p>
      <div v-if="interfaceMode.sidecarStatus" class="space-y-2" aria-label="CPU 語音辨識環境安裝進度">
        <progress class="w-full" :value="interfaceMode.sidecarStatus.progress" :max="1" />
        <p class="text-sm text-slate-300">{{ Math.round(interfaceMode.sidecarStatus.progress * 100) }}% · {{ interfaceMode.sidecarStatus.message }}</p>
      </div>
      <p v-if="interfaceMode.error" role="alert" class="text-red-300">{{ interfaceMode.error }}</p>
      <div v-if="interfaceMode.preparingModels" class="space-y-3" aria-label="ASR 模型準備進度">
        <div v-for="model in interfaceMode.modelProgress" :key="model.id" class="rounded-xl border border-white/15 p-3">
          <p class="text-sm">{{ model.label }} · {{ Math.round(model.progress * 100) }}%</p>
          <progress class="w-full" :value="model.progress" :max="1" />
          <p class="text-xs text-slate-300">{{ model.message }}</p>
        </div>
      </div>
      <button v-if="interfaceMode.pendingMode && !interfaceMode.busy && interfaceMode.error && interfaceMode.onboardingStep === 'translation'" class="rounded-lg border px-4 py-2" @click="interfaceMode.translationChoice === 'local' ? interfaceMode.configureLocal() : interfaceMode.translationChoice === 'cloud' ? interfaceMode.configureCloud() : undefined">重試準備環境</button>
      <button v-if="!interfaceMode.loaded && !interfaceMode.busy" class="rounded-lg border px-4 py-2" @click="interfaceMode.load()">重新讀取</button>
    </section>
  </div>
  <div v-else class="commercial-shell flex h-screen w-screen flex-col overflow-hidden bg-slate-950 text-white font-sans md:flex-row">
    <!-- Mobile Header -->
    <header class="commercial-mobile-header relative z-40 flex h-14 flex-shrink-0 items-center justify-between border-b border-white/10 bg-slate-950/95 px-4 backdrop-blur md:hidden">
      <div class="flex min-w-0 items-center gap-2.5">
        <BrandIcon />
        <div class="min-w-0">
          <h1 class="truncate text-[11px] font-bold uppercase tracking-[0.16em] text-white">Stream Translator</h1>
          <p class="mt-0.5 text-[11px] font-semibold tracking-wide text-indigo-300/60">即時字幕翻譯系統</p>
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
        'commercial-sidebar',
        'fixed inset-y-0 right-0 z-50 flex w-[min(19rem,86vw)] flex-shrink-0 flex-col justify-between border-l border-white/10 bg-slate-950/98 shadow-2xl transition-transform duration-200 md:static md:z-auto md:w-60 md:translate-x-0 md:border-l-0 md:border-r md:bg-slate-950/95 md:shadow-none',
        isMobileMenuOpen ? 'translate-x-0' : 'translate-x-full'
      ]"
    >
      <div class="flex min-h-0 flex-1 flex-col">
        <!-- App Header / Logo -->
        <div class="commercial-brand shrink-0 p-5 border-b border-white/5 flex items-center gap-3">
          <BrandIcon />
          <div>
            <h1 class="text-xs font-bold text-white tracking-widest uppercase">Stream Translator</h1>
            <p class="mt-0.5 text-[11px] font-semibold tracking-wide text-indigo-300/60">即時字幕翻譯系統</p>
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
        <div class="commercial-navigation min-h-0 flex-1 py-4 px-3 space-y-5 overflow-y-auto custom-scrollbar">
          <!-- Core Control Section -->
          <div>
            <div class="mb-2 px-2 text-[11px] font-bold uppercase tracking-wider text-white/30">核心功能</div>
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
                <AppIcon :name="item.id" />
                {{ item.name }}
              </button>
            </div>
          </div>

          <!-- Settings Groups -->
          <div v-for="group in visibleSettingsGroups" :key="group.groupName">
            <div class="mb-2 px-2 text-[11px] font-bold uppercase tracking-wider text-white/30">{{ group.groupName }}</div>
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
                <AppIcon :name="tab.id" />
                {{ tab.name }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Sidebar Footer -->
      <div class="shrink-0 p-4 border-t border-white/5 bg-black/10 space-y-2 text-xs text-white/60">
        <label for="interface-mode" class="block">介面模式</label>
        <UiSelect id="interface-mode" :model-value="interfaceMode.mode" :disabled="interfaceMode.busy"
          :options="[{ value: 'simple', label: '簡單模式' }, { value: 'advanced', label: '進階模式' }]"
          button-class="w-full rounded-lg border border-white/20 bg-slate-900 p-2 text-white"
          @update:model-value="interfaceMode.select($event as 'simple' | 'advanced')" />
        <p v-if="interfaceMode.error" role="alert" class="text-red-300">{{ interfaceMode.error }}</p>
        <div class="pt-2">v{{ appVersion }}</div>
      </div>
    </aside>

    <!-- Right Content Panel -->
    <main class="commercial-main app-scroll-surface relative min-h-0 min-w-0 flex-1 overflow-y-auto bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950/40">
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
