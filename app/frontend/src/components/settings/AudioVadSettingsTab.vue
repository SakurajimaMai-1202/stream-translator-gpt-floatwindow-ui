<script setup lang="ts">
import { computed } from 'vue';
import { useSettingsContext, useSettingsTabBindings } from '../../composables/settings/settingsContext';
import UiSelect, { type UiSelectOption } from '../UiSelect.vue';
const { localConfig, audioValidationMessage } = useSettingsContext();
const { store } = useSettingsTabBindings();
function restoreEmptyNumber(field: string) {
  const value = localConfig.value.audio_slicing_vad[field];
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    localConfig.value.audio_slicing_vad[field] = store.config.audio_slicing_vad[field];
  }
}
const vadLockedByNativeMode = computed(() => localConfig.value?.audio_slicing_vad?.slicing_mode === 'omnivad_native');
const vadBackendOptions: UiSelectOption[] = [
  { value: 'silero', label: 'Silero VAD' },
  { value: 'firered', label: 'FireRed VAD' },
];
const slicingModeOptions: UiSelectOption[] = [
  { value: 'legacy', label: '目前切段（動態門檻）' },
  { value: 'omnivad_native', label: 'OmniStreamVAD 原生事件' },
];
</script>

<template>
<div class="settings-paint-section apple-settings">
            <header class="apple-page-header"><h2>音訊切片 & VAD 設定</h2><p>調整語音切片、靜音判斷與辨識節奏。</p></header>

            <!-- 音訊切片 -->
            <div class="bg-white/5 rounded-xl p-4 border border-white/10">
              <h3 class="commercial-section-title">音訊切片</h3>
              <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div>
                  <label class="block text-white/70 text-sm mb-1">最小音訊長度 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.min_audio_length" type="number" @blur="restoreEmptyNumber('min_audio_length')" step="0.1" min="0.1" max="30"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>
                <div v-if="localConfig.audio_slicing_vad.slicing_mode === 'legacy'">
                  <label class="block text-white/70 text-sm mb-1">目標音訊長度 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.target_audio_length" type="number" @blur="restoreEmptyNumber('target_audio_length')" step="0.1" min="0.1" max="60"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-xs text-white/40 mt-1">動態句尾判斷會盡量在接近此長度時完成片段。</p>
                </div>
                <div v-if="localConfig.audio_slicing_vad.slicing_mode === 'legacy'">
                  <label class="block text-white/70 text-sm mb-1">最大音訊長度 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.max_audio_length" type="number" @blur="restoreEmptyNumber('max_audio_length')" step="0.1" min="0.1" max="120"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>
                <div v-else>
                  <label class="block text-white/70 text-sm mb-1">原生模式最大音訊長度 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.omnivad_max_audio_length" type="number" @blur="restoreEmptyNumber('omnivad_max_audio_length')" step="0.1" min="0.1" max="120"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-xs text-white/40 mt-1">正式回歸使用 6 秒；長語音達上限後會延續原生 SPEECH 狀態。</p>
                </div>
                <p v-if="audioValidationMessage" role="alert" class="text-sm text-rose-400 md:col-span-2 lg:col-span-3">{{ audioValidationMessage }}</p>
                <div v-if="localConfig.audio_slicing_vad.slicing_mode === 'legacy'">
                  <label class="block text-white/70 text-sm mb-1">句尾連續靜音 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.continuous_no_speech_threshold" type="number" @blur="restoreEmptyNumber('continuous_no_speech_threshold')"
                    step="0.05" min="0.1" max="5"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-xs text-white/40 mt-1">偵測到連續靜音後結束片段；直播建議 0.4 到 0.7 秒。</p>
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">前綴重疊長度 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.prefix_retention_length" type="number" @blur="restoreEmptyNumber('prefix_retention_length')"
                    step="0.05" min="0" max="5"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-xs text-white/40 mt-1">將上一片段結尾接到下一片段開頭；設為 0 可完全停用。</p>
                </div>
                <label v-if="localConfig.audio_slicing_vad.slicing_mode === 'legacy'"
                  class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer">
                  <input v-model="localConfig.audio_slicing_vad.disable_dynamic_no_speech_threshold" type="checkbox"
                    class="w-5 h-5 accent-blue-500 mt-0.5" />
                  <span>
                    <span class="block text-white font-medium">停用動態句尾門檻</span>
                    <span class="block text-xs text-white/40 mt-1">勾選後固定使用句尾連續靜音值，不再依片段長度調整。</span>
                  </span>
                </label>
              </div>
            </div>

            <!-- VAD 設定 -->
            <div class="bg-white/5 rounded-xl p-4 border border-white/10">
              <div class="flex items-center justify-between mb-4">
                <h3 class="commercial-section-title mb-0">VAD（語音活動偵測）</h3>
                <!-- 原生事件模式依賴 VAD，SettingsView 會強制開啟，因此鎖定開關並說明原因 -->
                <label class="flex items-center gap-2"
                       :class="vadLockedByNativeMode ? 'cursor-not-allowed opacity-70' : 'cursor-pointer'"
                       :title="vadLockedByNativeMode ? 'OmniStreamVAD 原生事件模式需要 VAD；改用其他切段模式才能關閉' : undefined">
                  <input v-model="localConfig.audio_slicing_vad.vad_enabled" type="checkbox" class="w-5 h-5 accent-blue-500"
                         :disabled="vadLockedByNativeMode" />
                  <span class="text-white">啟用 VAD</span>
                </label>
              </div>

              <div v-if="localConfig.audio_slicing_vad.vad_enabled" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div>
                  <label class="block text-white/70 text-sm mb-1 font-semibold">切段模式</label>
                  <UiSelect v-model="localConfig.audio_slicing_vad.slicing_mode" :options="slicingModeOptions" />
                  <p class="text-white/30 text-xs mt-1">原生模式使用 OmniStreamVAD 的 START／END 事件，仍保留最短、最長與前綴保護。</p>
                </div>
                <div v-if="localConfig.audio_slicing_vad.slicing_mode === 'legacy'">
                  <label class="block text-white/70 text-sm mb-1 font-semibold">VAD 演算法</label>
                  <UiSelect v-model="localConfig.audio_slicing_vad.vad_backend" :options="vadBackendOptions" />
                </div>
                <div v-else class="p-3 bg-blue-500/10 rounded-lg border border-blue-400/20">
                  <span class="block text-white/70 text-sm mb-1 font-semibold">原生事件引擎</span>
                  <span class="block text-white">FireRed OmniStreamVAD</span>
                  <span class="block text-xs text-white/40 mt-1">原生模式固定使用此引擎並逐一處理 10 ms frame。</span>
                </div>
                <div v-if="localConfig.audio_slicing_vad.vad_backend === 'firered'">
                  <label class="block text-white/70 text-sm mb-1 font-semibold">FireRed VAD 模型路徑</label>
                  <input v-model="localConfig.audio_slicing_vad.firered_vad_model_path" type="text" placeholder="留空或填寫 auto"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                  <p class="text-white/30 text-xs mt-1">預設使用內建模型</p>
                </div>
                <div v-if="localConfig.audio_slicing_vad.slicing_mode === 'legacy'">
                  <label class="block text-white/70 text-sm mb-1 flex items-center gap-1.5">
                    目前切段語音閾值
                    <span class="tooltip-container text-white/40 hover:text-blue-300 transition text-xs">
                      ⓘ
                      <span class="tooltip-text">
                        聲音被判定為語音的閾值。範圍 0.0 ~ 1.0，預設 0.35。數值越低越靈敏。
                      </span>
                    </span>
                  </label>
                  <input v-model.number="localConfig.audio_slicing_vad.vad_threshold" type="number" @blur="restoreEmptyNumber('vad_threshold')" step="0.05" min="0" max="1"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>
                <div v-else>
                  <label class="block text-white/70 text-sm mb-1">OmniStreamVAD 語音閾值</label>
                  <input v-model.number="localConfig.audio_slicing_vad.omnivad_threshold" type="number" @blur="restoreEmptyNumber('omnivad_threshold')" step="0.05" min="0" max="1"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-xs text-white/40 mt-1">本程式預設為 0.35；FireRed 官方原生預設為 0.5。</p>
                </div>
                <label v-if="localConfig.audio_slicing_vad.slicing_mode === 'legacy'"
                  class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer">
                  <input v-model="localConfig.audio_slicing_vad.disable_dynamic_vad_threshold" type="checkbox"
                    class="w-5 h-5 accent-blue-500 mt-0.5" />
                  <span>
                    <span class="block text-white font-medium">停用動態 VAD 門檻</span>
                    <span class="block text-xs text-white/40 mt-1">勾選後固定使用上方語音閾值。</span>
                  </span>
                </label>
                <div v-if="localConfig.audio_slicing_vad.slicing_mode === 'legacy'">
                  <label class="block text-white/70 text-sm mb-1">VAD 計算頻率</label>
                  <input v-model.number="localConfig.audio_slicing_vad.vad_every_n_frames" type="number" @blur="restoreEmptyNumber('vad_every_n_frames')"
                    min="1" max="10" step="1"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-xs text-white/40 mt-1">1 為每個 32 ms frame 計算；提高可降低 CPU，但會增加判斷延遲。</p>
                </div>
                <template v-if="localConfig.audio_slicing_vad.slicing_mode === 'omnivad_native'">
                  <div>
                    <label class="block text-white/70 text-sm mb-1">平滑視窗（10 ms frame）</label>
                    <input v-model.number="localConfig.audio_slicing_vad.omnivad_smooth_window_size" type="number" @blur="restoreEmptyNumber('omnivad_smooth_window_size')" min="1" max="100" step="1"
                      class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                    <p class="text-xs text-white/40 mt-1">預設 5，相當於 50 ms。</p>
                  </div>
                  <div>
                    <label class="block text-white/70 text-sm mb-1">起音回溯 frame</label>
                    <input v-model.number="localConfig.audio_slicing_vad.omnivad_pad_start_frame" type="number" @blur="restoreEmptyNumber('omnivad_pad_start_frame')" min="0" max="100" step="1"
                      class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                    <p class="text-xs text-white/40 mt-1">預設 5，保留起音前 50 ms。</p>
                  </div>
                  <div>
                    <label class="block text-white/70 text-sm mb-1">最短語音 frame</label>
                    <input v-model.number="localConfig.audio_slicing_vad.omnivad_min_speech_frame" type="number" @blur="restoreEmptyNumber('omnivad_min_speech_frame')" min="1" max="1000" step="1"
                      class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                    <p class="text-xs text-white/40 mt-1">預設 8，相當於 80 ms。</p>
                  </div>
                  <div>
                    <label class="block text-white/70 text-sm mb-1">最長語音 frame</label>
                    <input v-model.number="localConfig.audio_slicing_vad.omnivad_max_speech_frame" type="number" @blur="restoreEmptyNumber('omnivad_max_speech_frame')" min="1" max="10000" step="1"
                      class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                    <p class="text-xs text-white/40 mt-1">預設 2000，相當於 20 秒；應用層仍以 6 秒安全切片。</p>
                  </div>
                  <div>
                    <label class="block text-white/70 text-sm mb-1">句尾靜音 frame</label>
                    <input v-model.number="localConfig.audio_slicing_vad.omnivad_min_silence_frame" type="number" @blur="restoreEmptyNumber('omnivad_min_silence_frame')" min="1" max="1000" step="1"
                      class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                    <p class="text-xs text-white/40 mt-1">預設 20，相當於 200 ms。</p>
                  </div>
                </template>
              </div>
            </div>
          </div>
</template>

<style scoped src="./settings-shared.css"></style>
