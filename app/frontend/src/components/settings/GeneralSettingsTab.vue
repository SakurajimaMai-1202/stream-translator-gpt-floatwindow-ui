<script setup lang="ts">
import { computed } from 'vue';
import UiSelect, { type UiSelectOption } from '../UiSelect.vue';
import { useSettingsContext } from '../../composables/settings/settingsContext';

const { localConfig, sharingLanAddresses, copiedSharingUrl, appUpdateStatus, appUpdateBusy, checkAppUpdate, downloadAppUpdate, cancelAppUpdate, applyAppUpdate, testingGpt, testingGemini, testConnection } = useSettingsContext();

const sharingHost = computed(() => {
  const browserHost = window.location.hostname;
  if (browserHost && !['localhost', '127.0.0.1', '::1'].includes(browserHost)) return browserHost;
  return sharingLanAddresses.value[0] || '127.0.0.1';
});
const sharingBaseUrl = computed(() => `http://${sharingHost.value}:${localConfig.value.server.public_port || 8765}`);
const desktopSharingUrl = computed(() => `${sharingBaseUrl.value}/desktop`);
const mobileSharingUrl = computed(() => `${sharingBaseUrl.value}/mobile`);

async function copySharingUrl(url: string) {
  try {
    await navigator.clipboard.writeText(url);
  } catch {
    const input = document.createElement('textarea');
    input.value = url;
    input.style.position = 'fixed';
    input.style.left = '-9999px';
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    input.remove();
  }
  copiedSharingUrl.value = url;
  window.setTimeout(() => {
    if (copiedSharingUrl.value === url) copiedSharingUrl.value = '';
  }, 1800);
}

const logLevelOptions: UiSelectOption[] = [
  { value: 'DEBUG', label: 'DEBUG' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
];
</script>

<template>
          <div class="settings-paint-section apple-settings">
            <header class="apple-page-header"><h2>一般設定</h2><p>管理程式啟動、更新與執行環境。</p></header>

            <div class="rounded-xl border border-blue-500/25 bg-blue-500/10 p-5 space-y-4">
              <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                <div>
                  <h3 class="text-lg font-semibold text-blue-200">程式更新</h3>
                  <p class="text-sm text-white/55 mt-1">
                    目前 {{ appUpdateStatus?.current_version || '—' }} · {{ appUpdateStatus?.profile?.toUpperCase() || '開發版' }}
                    <template v-if="appUpdateStatus?.latest_version"> → 最新 {{ appUpdateStatus.latest_version }}</template>
                  </p>
                </div>
                <div class="flex flex-wrap gap-2">
                  <button v-if="!appUpdateStatus?.ready_to_apply" @click="checkAppUpdate" :disabled="appUpdateBusy"
                    class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 font-semibold">
                    {{ appUpdateStatus?.status === 'checking' ? '檢查中…' : '檢查更新' }}
                  </button>
                  <button v-if="appUpdateStatus?.available && !appUpdateStatus?.ready_to_apply" @click="downloadAppUpdate" :disabled="appUpdateBusy"
                    class="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 font-semibold">
                    下載並準備更新
                  </button>
                  <button v-if="appUpdateBusy" @click="cancelAppUpdate"
                    class="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 font-semibold">取消</button>
                  <button v-if="appUpdateStatus?.ready_to_apply" @click="applyAppUpdate"
                    class="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 font-semibold">重新啟動並套用</button>
                </div>
              </div>
              <div v-if="appUpdateBusy" class="space-y-2">
                <div class="h-2 rounded-full bg-white/10 overflow-hidden"><div class="h-full bg-cyan-400" :style="{ width: `${Math.max(2, (appUpdateStatus?.progress || 0) * 100)}%` }"></div></div>
                <p class="text-xs text-white/55">{{ appUpdateStatus?.message }} · {{ Math.round((appUpdateStatus?.progress || 0) * 100) }}%</p>
              </div>
              <p v-if="appUpdateStatus?.status === 'up_to_date'" class="text-sm text-emerald-300">目前已是最新版。</p>
              <p v-if="appUpdateStatus?.status === 'full_install_required'" class="text-sm text-yellow-200">
                此版本無法直接從 UI 升級，請下載相同 Profile 的 Full 完整包。
              </p>
              <p v-if="appUpdateStatus?.status === 'unsupported'" class="text-sm text-yellow-200">開發模式不提供自動更新；正式 CPU／CUDA／ROCm 包才會啟用。</p>
              <p v-if="appUpdateStatus?.status === 'cancelled'" class="text-sm text-white/55">下載已取消，下次會從暫存進度繼續。</p>
              <p v-if="appUpdateStatus?.error" class="text-sm text-red-300 break-words">{{ appUpdateStatus.error }}</p>
              <details v-if="appUpdateStatus?.available && appUpdateStatus?.release_notes" class="rounded-lg bg-black/15 p-3">
                <summary class="cursor-pointer text-sm font-semibold text-blue-200">查看更新說明</summary>
                <pre class="mt-3 whitespace-pre-wrap break-words text-xs leading-6 text-white/60 font-sans">{{ appUpdateStatus.release_notes }}</pre>
              </details>
              <p class="text-xs text-white/40">只會安裝相同 Profile 的 App Update；套用前會備份 config、術語、ASR 修正與 Cookies，模型、輸出與日誌不會被覆蓋。</p>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div v-if="false">
                <label class="block text-white/70 font-semibold mb-2">OpenAI API Key</label>
                <div class="flex gap-2">
                  <input disabled value="" type="password" placeholder="sk-..."
                    class="flex-1 px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                  <button @click="testConnection('gpt')" :disabled="testingGpt" 
                    class="bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 font-semibold px-4 rounded-lg transition text-xs whitespace-nowrap flex items-center justify-center gap-1.5 min-w-[95px]">
                    <span v-if="testingGpt" class="inline-block w-3 h-3 border-2 border-blue-300 border-t-transparent rounded-full animate-spin"></span>
                    <span>⚡ 測試連線</span>
                  </button>
                </div>
                <p class="text-white/40 text-sm mt-1">用於 GPT 翻譯</p>
              </div>

              <div v-if="false">
                <label class="block text-white/70 font-semibold mb-2">Google API Key (Gemini)</label>
                <div class="flex gap-2">
                  <input disabled value="" type="password" placeholder="AIza..."
                    class="flex-1 px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                  <button @click="testConnection('gemini')" :disabled="testingGemini" 
                    class="bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 font-semibold px-4 rounded-lg transition text-xs whitespace-nowrap flex items-center justify-center gap-1.5 min-w-[95px]">
                    <span v-if="testingGemini" class="inline-block w-3 h-3 border-2 border-blue-300 border-t-transparent rounded-full animate-spin"></span>
                    <span>⚡ 測試連線</span>
                  </button>
                </div>
                <p class="text-white/40 text-sm mt-1">用於 Gemini 翻譯</p>
              </div>

              <div>
                <label class="block text-white/70 font-semibold mb-2">日誌等級</label>
                <UiSelect v-model="localConfig.general.log_level" :options="logLevelOptions" />
              </div>

              <div class="md:col-span-2 rounded-xl p-5 border border-white/10 bg-gradient-to-br from-emerald-500/10 via-white/5 to-blue-500/10 space-y-5">
                <label class="flex items-start justify-between gap-5 cursor-pointer">
                  <div>
                    <div class="flex items-center gap-2">
                      <span class="text-white font-semibold">即時字幕分享</span>
                      <span :class="['px-2 py-0.5 rounded-full text-xs border', localConfig.server.enable_subtitle_sharing ? 'text-emerald-300 bg-emerald-500/10 border-emerald-500/25' : 'text-white/45 bg-white/5 border-white/10']">
                        {{ localConfig.server.enable_subtitle_sharing ? '已啟用' : '已關閉' }}
                      </span>
                    </div>
                    <p class="text-white/55 text-sm mt-2 leading-6">讓同一個區域網路中的手機、平板或另一台電腦，透過瀏覽器觀看目前的即時原文與翻譯字幕。</p>
                  </div>
                  <input v-model="localConfig.server.enable_subtitle_sharing" type="checkbox" class="w-5 h-5 accent-emerald-500 mt-1 shrink-0" />
                </label>

                <div v-if="localConfig.server.enable_subtitle_sharing" class="space-y-3">
                  <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
                    <div class="rounded-lg border border-white/10 bg-black/15 p-4">
                      <div class="text-white/80 font-semibold text-sm">桌面版字幕</div>
                      <p class="text-white/40 text-xs mt-1">適合電腦、投影幕與直播監看畫面。</p>
                      <div class="flex items-center gap-2 mt-3">
                        <code class="min-w-0 flex-1 truncate text-xs text-cyan-300 bg-black/20 rounded px-3 py-2">{{ desktopSharingUrl }}</code>
                        <button type="button" @click="copySharingUrl(desktopSharingUrl)" class="px-3 py-2 rounded-lg bg-blue-600/25 hover:bg-blue-600/40 text-blue-200 text-xs border border-blue-500/25">
                          {{ copiedSharingUrl === desktopSharingUrl ? '已複製' : '複製' }}
                        </button>
                      </div>
                    </div>
                    <div class="rounded-lg border border-white/10 bg-black/15 p-4">
                      <div class="text-white/80 font-semibold text-sm">行動版字幕</div>
                      <p class="text-white/40 text-xs mt-1">適合手機與平板，版面會依螢幕自動調整。</p>
                      <div class="flex items-center gap-2 mt-3">
                        <code class="min-w-0 flex-1 truncate text-xs text-cyan-300 bg-black/20 rounded px-3 py-2">{{ mobileSharingUrl }}</code>
                        <button type="button" @click="copySharingUrl(mobileSharingUrl)" class="px-3 py-2 rounded-lg bg-blue-600/25 hover:bg-blue-600/40 text-blue-200 text-xs border border-blue-500/25">
                          {{ copiedSharingUrl === mobileSharingUrl ? '已複製' : '複製' }}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div class="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-xs text-white/55 leading-5">
                    <span class="text-amber-300 font-semibold">使用方式：</span>
                    分享裝置需與本機位於同一個 Wi-Fi／區域網路。若無法開啟，請允許 Windows 防火牆存取連接埠 {{ localConfig.server.public_port || 8765 }}。此功能沒有登入驗證，請勿直接暴露至公網；關閉後，分享頁與公開字幕 API 都會停止存取。
                  </div>
                </div>

                <p v-else class="text-white/40 text-sm">分享頁面與公開字幕 API 已停用，區域網路中的其他裝置無法讀取字幕。</p>
              </div>
            </div>
          </div>
</template>

<style scoped src="./settings-shared.css"></style>
