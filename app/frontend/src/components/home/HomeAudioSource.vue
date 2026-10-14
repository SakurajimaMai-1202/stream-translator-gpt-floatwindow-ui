<script setup lang="ts">
import { computed, nextTick } from 'vue';
import UiSelect, { type UiSelectOption } from '../UiSelect.vue';
import AppIcon from '../AppIcon.vue';
import { readinessApi } from '../../services/api';
import type { WindowWithPyQt } from '../../composables/home/homeContext';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  store, urlInput, urlInputRef, localFileInputRef, isLoading, isPreparingAsrModel, audioSource, availableDevices, selectedDeviceIndex, isLoadingDevices, sourceCheck, isCheckingSource, sourceControlsLocked, processAudioTargets, selectedProcessTargetKey, processAudioSupported, processAudioMessage, isLoadingProcessTargets, processTargetKey, selectedProcessTarget, loadProcessAudioTargets, addLog, loadDevices, onAudioSourceChange
} = useHomeContext();

const localMediaAccept = '.mp4,.mkv,.webm,.avi,.mov,.mp3,.wav,.m4a,.flac,.ogg,.aac,.wma';

const processTargetOptions = computed<UiSelectOption[]>(() => processAudioTargets.value.map(target => ({
  value: processTargetKey(target), label: `${target.process_name} — ${target.title}`,
})));

const deviceOptions = computed<UiSelectOption[]>(() => {
  const list = availableDevices.value || [];
  const defaultDevice = list.find((d) => d?.is_default);
  const nullLabel = defaultDevice
    ? `⭐ 預設: ${defaultDevice.name} (${defaultDevice.sample_rate}Hz)`
    : '自動選擇預設設備';
  const base: UiSelectOption[] = [{ value: null, label: nullLabel }];
  const deviceItems = list.map((device) => ({
    value: device.index,
    label: `[${device.index}] ${device.name} (${device.sample_rate}Hz)`
  }));
  return [...base, ...deviceItems];
});

async function runSourceCheck() {
  if (isCheckingSource.value || store.isRunning || isLoading.value || isPreparingAsrModel.value) return;
  if (audioSource.value === 'process_audio' && (!processAudioSupported.value || !selectedProcessTarget.value)) return;
  isCheckingSource.value = true;
  sourceCheck.value = null;
  try {
    sourceCheck.value = await readinessApi.checkSource({
      source: audioSource.value,
      value: (audioSource.value === 'url' || audioSource.value === 'file') ? urlInput.value.trim() : '',
      device_index: selectedDeviceIndex.value,
      ...(audioSource.value === 'process_audio' && selectedProcessTarget.value ? {
        process_id: selectedProcessTarget.value.process_id,
        process_start_time: selectedProcessTarget.value.process_start_time,
        window_handle: selectedProcessTarget.value.window_handle,
      } : {}),
      duration_seconds: 1,
    });
    addLog(`[來源檢查 ${sourceCheck.value.trace_id.slice(0, 8)}] ${sourceCheck.value.message} (${sourceCheck.value.elapsed_ms}ms)`);
  } catch (error: any) {
    sourceCheck.value = {
      source: audioSource.value, status: 'error', stage: 'request', trace_id: '', elapsed_ms: 0,
      message: error?.response?.data?.detail || error?.message || '來源檢查失敗',
      recovery: '確認後端仍在執行後重試。', details: {},
    };
  } finally { isCheckingSource.value = false; }
}

function chooseLocalFile() {
  const bridge = (window as WindowWithPyQt).pyqt;
  if (bridge?.chooseLocalFile) {
    try {
      // Qt WebChannel 的 result=str slot 會以 callback 回傳完整 Windows 路徑。
      bridge.chooseLocalFile((selectedPath: string) => {
        const path = String(selectedPath || '').trim();
        if (!path) return;
        urlInput.value = path;
        if (store.errorMessage === '瀏覽器模式無法取得檔案的完整路徑，請使用桌面版的「選擇檔案」或手動輸入路徑。') {
          store.errorMessage = '';
        }
        nextTick(() => urlInputRef.value?.focus());
      });
    } catch (error) {
      console.warn('[HomeView] 原生檔案選擇器開啟失敗:', error);
      store.errorMessage = '開啟檔案選擇器失敗，請改為手動輸入檔案路徑。';
    }
    return;
  }

  // 開發瀏覽器的備援入口；一般瀏覽器會隱藏絕對路徑，無法直接交給本機後端。
  localFileInputRef.value?.click();
}

function handleLocalFileInputChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;

  const browserFile = file as File & { path?: string };
  const path = String(browserFile.path || '').trim();
  if (path) {
    urlInput.value = path;
    store.errorMessage = '';
    nextTick(() => urlInputRef.value?.focus());
  } else {
    store.errorMessage = '瀏覽器模式無法取得檔案的完整路徑，請使用桌面版的「選擇檔案」或手動輸入路徑。';
  }
  // 允許再次選取同一個檔案時仍會觸發 change。
  input.value = '';
}
</script>

<template>
            <!-- 音訊來源選擇 -->
            <div class="mb-5">
              <label class="commercial-field-label">音訊來源</label>
              <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                <button
                  @click="audioSource = 'url'; onAudioSourceChange()"
                  :disabled="sourceControlsLocked"
                  type="button"
                  :class="[
                    'flex flex-col items-center justify-center p-3 rounded-xl border text-center transition-all duration-200 group relative overflow-hidden',
                    audioSource === 'url'
                      ? 'border-blue-400/50 bg-blue-500/15 text-white'
                      : 'bg-white/5 border-white/10 hover:border-white/20 text-white/70 hover:text-white',
                    sourceControlsLocked ? 'opacity-50 cursor-not-allowed' : 'active:scale-[0.98]'
                  ]"
                >
                  <AppIcon name="url" class="source-card-icon" />
                  <span class="font-bold text-xs">URL 串流</span>
                  <span class="text-xs text-white/60 mt-1 hidden sm:inline-block leading-tight">播放網路直播流</span>
                </button>
                <button
                  @click="audioSource = 'file'; onAudioSourceChange()"
                  :disabled="sourceControlsLocked"
                  type="button"
                  :class="[
                    'flex flex-col items-center justify-center p-3 rounded-xl border text-center transition-all duration-200 group relative overflow-hidden',
                    audioSource === 'file'
                      ? 'border-blue-400/50 bg-blue-500/15 text-white'
                      : 'bg-white/5 border-white/10 hover:border-white/20 text-white/70 hover:text-white',
                    sourceControlsLocked ? 'opacity-50 cursor-not-allowed' : 'active:scale-[0.98]'
                  ]"
                >
                  <AppIcon name="file" class="source-card-icon" />
                  <span class="font-bold text-xs"><span class="md:hidden">電腦</span>本地檔案</span>
                  <span class="text-xs text-white/60 mt-1 hidden sm:inline-block leading-tight">轉譯本機影音檔</span>
                </button>
                <button
                  @click="audioSource = 'microphone'; onAudioSourceChange()"
                  :disabled="sourceControlsLocked"
                  type="button"
                  :class="[
                    'flex flex-col items-center justify-center p-3 rounded-xl border text-center transition-all duration-200 group relative overflow-hidden',
                    audioSource === 'microphone'
                      ? 'border-blue-400/50 bg-blue-500/15 text-white'
                      : 'bg-white/5 border-white/10 hover:border-white/20 text-white/70 hover:text-white',
                    sourceControlsLocked ? 'opacity-50 cursor-not-allowed' : 'active:scale-[0.98]'
                  ]"
                >
                  <AppIcon name="microphone" class="source-card-icon" />
                  <span class="font-bold text-xs"><span class="md:hidden">電腦</span>麥克風</span>
                  <span class="text-xs text-white/60 mt-1 hidden sm:inline-block leading-tight">錄製麥克風輸入</span>
                </button>
                <button
                  @click="audioSource = 'system_audio'; onAudioSourceChange()"
                  :disabled="sourceControlsLocked"
                  type="button"
                  :class="[
                    'flex flex-col items-center justify-center p-3 rounded-xl border text-center transition-all duration-200 group relative overflow-hidden',
                    audioSource === 'system_audio'
                      ? 'border-blue-400/50 bg-blue-500/15 text-white'
                      : 'bg-white/5 border-white/10 hover:border-white/20 text-white/70 hover:text-white',
                    sourceControlsLocked ? 'opacity-50 cursor-not-allowed' : 'active:scale-[0.98]'
                  ]"
                >
                  <AppIcon name="system-audio" class="source-card-icon" />
                  <span class="font-bold text-xs"><span class="md:hidden">電腦</span>系統音訊</span>
                  <span class="text-xs text-white/60 mt-1 hidden sm:inline-block leading-tight">捕獲系統播放音</span>
                </button>
                <button type="button" @click="audioSource = 'process_audio'; onAudioSourceChange()"
                  :disabled="sourceControlsLocked"
                  :class="['flex flex-col items-center justify-center p-3 rounded-xl border text-center transition-colors', audioSource === 'process_audio' ? 'border-blue-500/80 bg-blue-500/10 text-white' : 'bg-white/5 border-white/10 text-white/70 hover:bg-white/10', sourceControlsLocked ? 'opacity-50 cursor-not-allowed' : '']">
                  <AppIcon name="app-audio" class="source-card-icon" />
                  <span class="font-bold text-xs">指定應用程式音訊</span>
                  <span class="text-xs text-white/60 mt-1 hidden sm:inline-block leading-tight">選擇要收音的視窗</span>
                </button>
              </div>
            </div>

            <!-- URL/檔案輸入 -->
            <div v-if="audioSource === 'url' || audioSource === 'file'" class="mb-5">
              <label class="block text-white/80 font-bold mb-1.5 text-xs tracking-wider uppercase">
                {{ audioSource === 'url' ? '直播網址（YouTube Live／Twitch／X／TikTok 等）' : '本地檔案' }}
              </label>
              <div class="flex flex-col gap-2 sm:flex-row">
                <input
                  :ref="(el: any) => (urlInputRef = el)"
                  v-model="urlInput"
                  type="text"
                  spellcheck="false"
                  :placeholder="audioSource === 'url' ? '貼上 YouTube Live、Twitch、X、TikTok 等直播網址' : 'C:\\path\\to\\video.mp4'"
                  :disabled="sourceControlsLocked"
                  class="flex-1 min-w-0 px-4 py-2.5 bg-white/5 border border-white/15 rounded-xl text-white placeholder-white/30 focus:outline-none focus:border-blue-500/80 focus:ring-1 focus:ring-blue-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition duration-200 text-sm"
                />
                <button
                  v-if="audioSource === 'file'"
                  type="button"
                  @click="chooseLocalFile"
                  :disabled="sourceControlsLocked"
                  class="shrink-0 px-4 py-2.5 bg-blue-600/90 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl transition border border-blue-400/40 text-sm font-semibold whitespace-nowrap"
                  title="開啟檔案選擇器"
                >
                  選擇檔案
                </button>
              </div>
              <input
                v-if="audioSource === 'file'"
                :ref="(el: any) => (localFileInputRef = el)"
                type="file"
                :accept="localMediaAccept"
                class="hidden"
                @change="handleLocalFileInputChange"
              />
              <p v-if="audioSource === 'file'" class="text-white/60 text-xs mt-1.5 tracking-wide">
                支援 MP4、MKV、WebM、MOV、MP3、WAV 等格式；桌面版按鈕會開啟原生檔案選擇器。
              </p>
            </div>

            <div v-if="audioSource === 'process_audio'" class="mb-5">
              <label class="commercial-field-label">選擇應用程式視窗</label>
              <div class="flex gap-2">
                <UiSelect v-model="selectedProcessTargetKey" :options="processTargetOptions" searchable
                  placeholder="請選擇目前開啟的視窗" aria-label="應用程式視窗"
                  :disabled="sourceControlsLocked || isLoadingProcessTargets || !processAudioSupported"
                  class="flex-1 min-w-0" />
                <button type="button" @click="loadProcessAudioTargets" :disabled="sourceControlsLocked || isLoadingProcessTargets"
                  class="px-4 py-2.5 bg-white/5 hover:bg-white/10 rounded-xl border border-white/15 text-sm disabled:opacity-50"
                  title="重新整理視窗清單" aria-label="重新整理視窗清單">
                  <AppIcon name="refresh" :class="['h-4 w-4', isLoadingProcessTargets ? 'animate-spin' : '']" />
                </button>
              </div>
              <p class="mt-2 text-sm leading-6" :class="processAudioSupported ? 'text-white/60' : 'text-amber-200'" role="status">{{ processAudioMessage }}</p>
              <p class="mt-1 text-xs leading-6 text-white/60">擷取所選程序及其子程序；同一瀏覽器的其他視窗或分頁可能一起被擷取。目標關閉後需重新選擇，開始後請先停止再切換。</p>
            </div>

            <!-- 設備選擇 -->
            <div v-if="audioSource === 'microphone' || audioSource === 'system_audio'" class="mb-5">
              <label class="block text-white/80 font-bold mb-1.5 text-xs tracking-wider uppercase">
                {{ audioSource === 'microphone' ? '麥克風設備' : '系統音訊設備' }}
              </label>
              <div class="flex gap-2">
                <UiSelect
                  v-model="selectedDeviceIndex"
                  :options="deviceOptions"
                  :disabled="sourceControlsLocked || isLoadingDevices"
                  class="flex-1 min-w-0"
                  button-class="flex-1 px-4 py-2.5 bg-white/5 border border-white/15 rounded-xl text-sm text-left hover:bg-white/10 transition"
                />
                <button
                  @click="loadDevices()"
                  :disabled="sourceControlsLocked || isLoadingDevices"
                  class="px-4 py-2.5 bg-white/5 hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl transition border border-white/15 text-sm flex items-center justify-center min-w-[46px]"
                  title="重新整理設備列表"
                >
                  <AppIcon name="refresh" :class="['h-4 w-4', isLoadingDevices ? 'animate-spin' : '']" />
                </button>
              </div>
              <p v-if="availableDevices.length > 0" class="text-white/60 text-xs mt-1.5 tracking-wide">
                已偵測到 {{ availableDevices.length }} 個音訊裝置
              </p>
            </div>

            <section class="mb-5 rounded-xl border border-white/10 bg-white/[0.03] p-4" aria-labelledby="source-check-title">
              <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h2 id="source-check-title" class="text-base font-bold text-white">先測試這個來源</h2>
                  <p class="mt-1 text-sm leading-6 text-white/60">
                    {{ audioSource === 'url' ? '解析網址並確認有音訊串流。' : audioSource === 'file' ? '檢查檔案可讀、含音軌且可解碼。' : audioSource === 'process_audio' ? '開啟所選應用程式一秒並量測聲音；不會保存音訊或呼叫翻譯。' : '開啟裝置一秒並量測是否收到聲音；不會保存音訊或呼叫翻譯。' }}
                  </p>
                </div>
                <button type="button" :disabled="sourceControlsLocked || (audioSource === 'process_audio' && (!selectedProcessTarget || !processAudioSupported || isLoadingProcessTargets)) || ((audioSource === 'url' || audioSource === 'file') && !urlInput.trim())"
                  class="shrink-0 rounded-lg border border-cyan-400/40 bg-cyan-500/10 px-4 py-2.5 text-sm font-bold text-cyan-100 disabled:opacity-40"
                  @click="runSourceCheck">
                  {{ isCheckingSource ? '檢查中…' : (audioSource === 'microphone' || audioSource === 'system_audio' || audioSource === 'process_audio' ? '開始收音測試' : '檢查來源') }}
                </button>
              </div>
              <div v-if="sourceCheck" class="mt-3 rounded-lg border p-3 text-sm" role="status"
                :class="sourceCheck.status === 'ready' ? 'border-emerald-400/30 bg-emerald-500/10 text-emerald-100' : sourceCheck.status === 'error' ? 'border-red-400/30 bg-red-500/10 text-red-100' : 'border-amber-400/30 bg-amber-500/10 text-amber-100'">
                <p class="font-bold">{{ sourceCheck.status === 'ready' ? '已就緒' : sourceCheck.status === 'error' ? '需要處理' : '狀態未知' }} · {{ sourceCheck.message }}</p>
                <p v-if="audioSource === 'process_audio' && typeof sourceCheck.details.peak_dbfs === 'number'" class="mt-1 text-xs opacity-80">測試音量峰值：{{ sourceCheck.details.peak_dbfs.toFixed(1) }} dBFS</p>
                <p v-if="sourceCheck.recovery" class="mt-1 leading-6">下一步：{{ sourceCheck.recovery }}</p>
                <p class="mt-1 text-xs opacity-65">階段 {{ sourceCheck.stage }} · {{ sourceCheck.elapsed_ms }} ms<span v-if="sourceCheck.trace_id"> · 追蹤 {{ sourceCheck.trace_id.slice(0, 8) }}</span></p>
              </div>
            </section>
</template>

<style scoped src="./home-shared.css"></style>
