<script setup lang="ts">
import { computed } from 'vue';
import axios from 'axios';
import UiSelect, { type UiSelectOption } from '../UiSelect.vue';
import { useSettingsContext } from '../../composables/settings/settingsContext';

const {
  localConfig, cookiePlatform, cookieBrowser, cookieBrowserProfile,
  cookieImporting, cookieFileInput, cookieImportResult,
} = useSettingsContext();

const sourceTypeOptions: UiSelectOption[] = [
  { value: 'youtube', label: 'YouTube' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'twitch', label: 'Twitch' },
  { value: 'bilibili', label: 'Bilibili' },
  { value: 'x', label: 'X (Twitter)' },
];
const cookiePlatformOptions: UiSelectOption[] = [
  { value: 'youtube', label: 'YouTube' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'twitter', label: 'X (Twitter)' },
  { value: 'twitch', label: 'Twitch' },
  { value: 'bilibili', label: 'Bilibili' },
];
const cookieBrowserOptions: UiSelectOption[] = [
  { value: 'chrome', label: 'Google Chrome' },
  { value: 'edge', label: 'Microsoft Edge' },
  { value: 'firefox', label: 'Mozilla Firefox' },
  { value: 'brave', label: 'Brave' },
  { value: 'chromium', label: 'Chromium' },
];
const selectedPlatformCookiePath = computed(() =>
  localConfig.value?.input?.cookies_by_site?.[cookiePlatform.value] || ''
);
const selectedBrowserMayLockCookies = computed(() =>
  ['chrome', 'edge', 'brave', 'chromium'].includes(cookieBrowser.value)
);

async function importCookiesFromBrowser() {
  cookieImporting.value = true;
  cookieImportResult.value = null;
  try {
    const response = await axios.post('/api/cookies/import-browser', {
      platform: cookiePlatform.value,
      browser: cookieBrowser.value,
      profile: cookieBrowserProfile.value.trim(),
    });
    const result = response.data?.data;
    if (!localConfig.value.input.cookies_by_site) {
      localConfig.value.input.cookies_by_site = {};
    }
    localConfig.value.input.cookies_by_site[cookiePlatform.value] = result.path;
    cookieImportResult.value = {
      type: 'success',
      message: `${result.platform_label} Cookies 已更新（${result.cookie_count} 筆）`,
    };
  } catch (error: any) {
    cookieImportResult.value = {
      type: 'error',
      message: error.response?.data?.detail || error.message || 'Cookies 更新失敗',
    };
  } finally {
    cookieImporting.value = false;
  }
}

function selectCookieFile() {
  cookieFileInput.value?.click();
}

async function importCookiesFromFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;

  cookieImporting.value = true;
  cookieImportResult.value = null;
  try {
    const formData = new FormData();
    formData.append('platform', cookiePlatform.value);
    formData.append('cookie_file', file);
    const response = await axios.post('/api/cookies/import-file', formData);
    const result = response.data?.data;
    if (!localConfig.value.input.cookies_by_site) {
      localConfig.value.input.cookies_by_site = {};
    }
    localConfig.value.input.cookies_by_site[cookiePlatform.value] = result.path;
    cookieImportResult.value = {
      type: 'success',
      message: `${result.platform_label} Cookies 已匯入（${result.cookie_count} 筆）`,
    };
  } catch (error: any) {
    cookieImportResult.value = {
      type: 'error',
      message: error.response?.data?.detail || error.message || 'cookies.txt 匯入失敗',
    };
  } finally {
    cookieImporting.value = false;
    input.value = '';
  }
}
</script>

<template>
          <div class="settings-paint-section apple-settings">
            <header class="apple-page-header"><h2>輸入選項</h2><p>選擇音訊來源與擷取方式。</p></header>

            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label class="block text-white/70 font-semibold mb-2">來源類型</label>
                <UiSelect v-model="localConfig.input.source_type" :options="sourceTypeOptions" />
              </div>

              <div>
                <label class="block text-white/70 font-semibold mb-2">格式</label>
                <input v-model="localConfig.input.format" type="text" placeholder="ba/wa*"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
              </div>

              <div class="md:col-span-2 border-t border-white/10 pt-5">
                <div class="flex items-center justify-between gap-3 mb-4">
                  <div>
                    <h3 class="text-white font-semibold">網站 Cookies</h3>
                    <p class="text-white/40 text-sm mt-1">從已登入的瀏覽器更新平台專用 Cookies</p>
                  </div>
                  <span
                    v-if="selectedPlatformCookiePath"
                    class="text-xs px-2 py-1 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/25"
                  >
                    已設定
                  </span>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">平台</label>
                    <UiSelect v-model="cookiePlatform" :options="cookiePlatformOptions" />
                  </div>
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">瀏覽器</label>
                    <UiSelect v-model="cookieBrowser" :options="cookieBrowserOptions" />
                    <p v-if="selectedBrowserMayLockCookies" class="text-amber-300/70 text-xs mt-2">
                      Windows 新版 Chromium 可能無法直接解密；可改用 Firefox 或匯入 cookies.txt
                    </p>
                  </div>
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">瀏覽器 Profile</label>
                    <input
                      v-model="cookieBrowserProfile"
                      type="text"
                      placeholder="留空使用預設 Profile"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400"
                    />
                  </div>
                </div>

                <div class="mt-4 flex flex-col md:flex-row md:items-center gap-3">
                  <button
                    type="button"
                    :disabled="cookieImporting"
                    class="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition"
                    @click="importCookiesFromBrowser"
                  >
                    {{ cookieImporting ? '更新中...' : '從瀏覽器更新' }}
                  </button>
                  <input
                    ref="cookieFileInput"
                    type="file"
                    accept=".txt,text/plain"
                    class="hidden"
                    @change="importCookiesFromFile"
                  />
                  <button
                    type="button"
                    :disabled="cookieImporting"
                    class="px-4 py-2 bg-white/10 hover:bg-white/15 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition"
                    @click="selectCookieFile"
                  >
                    匯入 cookies.txt
                  </button>
                  <p
                    v-if="cookieImportResult"
                    class="text-sm"
                    :class="cookieImportResult.type === 'success' ? 'text-emerald-300' : 'text-rose-300'"
                  >
                    {{ cookieImportResult.message }}
                  </p>
                  <p v-else-if="selectedPlatformCookiePath" class="text-white/45 text-sm truncate">
                    {{ selectedPlatformCookiePath }}
                  </p>
                </div>

                <div class="mt-5">
                  <label class="block text-white/70 font-semibold mb-2">其他網站 Cookies（Fallback）</label>
                  <input
                    v-model="localConfig.input.cookies"
                    type="text"
                    placeholder="未匹配平台時使用的 cookies.txt"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400"
                  />
                </div>
              </div>

              <div>
                <label class="block text-white/70 font-semibold mb-2">代理伺服器</label>
                <input v-model="localConfig.input.proxy" type="text" placeholder="http://127.0.0.1:7890"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
              </div>

              <div>
                <label class="block text-white/70 font-semibold mb-2">超時時間（秒）</label>
                <input v-model.number="localConfig.input.timeout" type="number" placeholder="30"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
              </div>

              <div>
                <label class="block text-white/70 font-semibold mb-2 flex items-center gap-1.5">
                  設備錄音間隔（秒）
                  <span class="tooltip-container text-white/40 hover:text-blue-300 transition text-sm">
                    ⓘ
                    <span class="tooltip-text">
                      僅用於設備/Loopback 模式。間隔越短延遲越低但 CPU 使用率越高，直播建議 0.1 秒。
                    </span>
                  </span>
                </label>
                <input v-model.number="localConfig.input.device_recording_interval" type="number" step="0.05" min="0.05" max="1.0" placeholder="0.1"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
              </div>
            </div>
          </div>
</template>

<style scoped src="./settings-shared.css"></style>
