<script setup lang="ts">
import { asrModelLabel } from '../../utils/asrModelLabels';
import { defineAsyncComponent } from 'vue';
import { useSettingsTabBindings } from '../../composables/settings/settingsContext';
const AsrModelGroup = defineAsyncComponent(() => import('../AsrModelGroup.vue'));
const {
  applyModelStoragePath, canCancelCpuAsrSidecar, canInstallCpuAsrSidecar, canStartDownload, cancelCpuAsrSidecarInstall, cpuAsrOfflineArchive, cpuAsrSidecarBusy, cpuAsrSidecarStatus, cpuFunAsrDescriptions, cpuFunAsrModels, cpuParakeetDescriptions, cpuParakeetModels, cpuQwenDescriptions, cpuQwenModels, cpuSenseVoiceDescriptions, cpuSenseVoiceModels, deleteDownloadedModel, fasterWhisperModelList, funAsrModelList, getModelStatusClass, getModelStatusText, getModelTask, gpuFasterWhisperModels, gpuFunAsrModels, gpuParakeetModels, gpuQwenModels, gpuSenseVoiceModels, importCpuAsrSidecarOffline, installCpuAsrSidecar, localConfig, managedDownloadedModels, modelDownloadStore, modelManagementBackend, parakeetModelList, qwenModelList, runtimeStatus, senseVoiceModelList, startModelDownload
} = useSettingsTabBindings();
</script>

<template>
          <div class="settings-paint-section apple-settings apple-asr">
            <header class="apple-page-header"><h2>ASR 模型管理</h2><p>依執行環境挑選語音模型，查看下載狀態與本機檔案。</p></header>
            <div class="apple-backend-choice" role="group" aria-label="ASR 模型執行環境">
              <button type="button" :aria-pressed="modelManagementBackend === 'gpu'" @click="modelManagementBackend = 'gpu'" :class="['px-4 py-2 rounded-lg font-semibold transition', modelManagementBackend === 'gpu' ? 'bg-blue-600 text-white' : 'text-white/60 hover:bg-white/10']">GPU 原生模型</button>
              <button type="button" :aria-pressed="modelManagementBackend === 'cpu'" @click="modelManagementBackend = 'cpu'" :class="['px-4 py-2 rounded-lg font-semibold transition', modelManagementBackend === 'cpu' ? 'bg-cyan-600 text-white' : 'text-white/60 hover:bg-white/10']">Sherpa-ONNX CPU 模型</button>
            </div>

            <div class="bg-cyan-500/10 rounded-xl p-4 border border-cyan-500/20">
              <p class="text-cyan-200 text-sm">
                <template v-if="modelManagementBackend === 'cpu'">此分頁下載 Sherpa-ONNX 專用 INT8 ONNX bundle，不能與同名的 PyTorch／NeMo GPU 模型互換。</template>
                <template v-else>此分頁管理 GPU 原生模型；模型格式與 Sherpa-ONNX CPU bundle 分開。</template>
              </p>
              <p class="text-white/50 text-xs mt-2">
                <template v-if="modelManagementBackend === 'cpu'">模型儲存在 models\\sherpa-onnx，使用 CPU 離線推論，不需要 CUDA、ROCm 或 PyTorch；只列出目前已支援的 bundle。</template>
                <template v-else>GPU 使用 Hugging Face／ModelScope cache；GPU 與 CPU 兩種格式可同時存在。</template>
              </p>
            </div>

            <div v-if="modelDownloadStore.errorMessage" class="p-3 rounded-lg border border-red-500/40 bg-red-500/20 text-red-200 text-sm">
              {{ modelDownloadStore.errorMessage }}
            </div>
            <div v-if="modelDownloadStore.successMessage" class="p-3 rounded-lg border border-green-500/40 bg-green-500/20 text-green-200 text-sm">
              {{ modelDownloadStore.successMessage }}
            </div>

            <AsrModelGroup title="Qwen3-ASR" engine="qwen3-asr" :compute-backend="modelManagementBackend" :models="modelManagementBackend === 'cpu' ? cpuQwenModels : gpuQwenModels" :descriptions="modelManagementBackend === 'cpu' ? cpuQwenDescriptions : {}" />
            <AsrModelGroup
              title="SenseVoice 模型"
              engine="sensevoice"
              :compute-backend="modelManagementBackend"
              :models="modelManagementBackend === 'cpu' ? cpuSenseVoiceModels : gpuSenseVoiceModels"
              :descriptions="modelManagementBackend === 'cpu' ? cpuSenseVoiceDescriptions : {}"
              :default-description="modelManagementBackend === 'cpu' ? '' : 'GPU 原生模型；ROCm 在 AMD 實機驗證前維持 experimental。'"
            />
            <AsrModelGroup
              title="Fun-ASR Nano 模型"
              engine="fun-asr-nano"
              :compute-backend="modelManagementBackend"
              :models="modelManagementBackend === 'cpu' ? cpuFunAsrModels : gpuFunAsrModels"
              :descriptions="modelManagementBackend === 'cpu' ? cpuFunAsrDescriptions : {
                'FunAudioLLM/Fun-ASR-Nano-2512': '中文／英文／日文與中文方言模型',
                'FunAudioLLM/Fun-ASR-MLT-Nano-2512': '31 種語言模型',
              }"
            />
            <AsrModelGroup
              title="NVIDIA Parakeet 模型"
              engine="parakeet-ctc-ja"
              :compute-backend="modelManagementBackend"
              :models="modelManagementBackend === 'cpu' ? cpuParakeetModels : gpuParakeetModels"
              :descriptions="modelManagementBackend === 'cpu' ? cpuParakeetDescriptions : {}"
              :default-description="modelManagementBackend === 'cpu' ? '' : 'CUDA experimental；官方模型採 CC-BY-4.0，透過 NVIDIA NeMo 執行。'"
            />
            <AsrModelGroup v-if="modelManagementBackend === 'gpu'" title="Faster-Whisper" engine="faster-whisper" compute-backend="gpu" :models="gpuFasterWhisperModels" />

            <details class="apple-disclosure"><summary>模型儲存位置<span>路徑與資料夾</span></summary><div class="apple-disclosure-body">

              <label class="block text-white/70 text-sm mb-1">自訂位置（留空使用程式旁的預設位置）</label>
              <div class="flex flex-col lg:flex-row gap-2">
                <input
                  v-model="localConfig.models.storage_path"
                  type="text"
                  placeholder="例如 D:\\StreamTranslatorModels"
                  class="flex-1 px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400"
                />
                <button @click="applyModelStoragePath" class="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold transition">
                  套用路徑
                </button>
                <button @click="modelDownloadStore.openStorage()" class="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-white font-semibold transition">
                  開啟資料夾
                </button>
              </div>
              <p class="text-white/50 text-xs mt-2 break-all">
                目前位置：{{ modelDownloadStore.storageInfo?.storage_path || '讀取中...' }}
              </p>
              <p class="text-yellow-200/70 text-xs mt-1">
                變更位置不會自動搬移既有模型；需要保留時請搬移 huggingface、modelscope 與 sherpa-onnx 子資料夾。
              </p>
            </div></details>

            <details class="apple-disclosure"
              v-if="['cuda', 'rocm'].includes(runtimeStatus?.profile || '')"
            ><summary>CPU 語音執行環境<span>{{ cpuAsrSidecarBusy ? '安裝中' : cpuAsrSidecarStatus?.healthy ? '已就緒' : cpuAsrSidecarStatus?.installed ? '需要修復' : '尚未安裝' }}</span></summary><div class="apple-disclosure-body">
              <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                <div>
                  <h3 class="text-lg font-semibold text-cyan-300">CPU ASR Sidecar</h3>
                  <p class="text-white/60 text-sm mt-1">
                    安裝獨立 sherpa-onnx CPU runtime，讓目前的 {{ runtimeStatus?.profile?.toUpperCase() }} 包可切換 GPU ASR / CPU ASR。
                  </p>
                  <p v-if="cpuAsrSidecarStatus?.healthy" class="text-green-300 text-sm mt-2">CPU ASR runtime 已安裝且健康檢查通過。</p>
                  <p v-else-if="cpuAsrSidecarStatus?.installed" class="text-yellow-200 text-sm mt-2 break-words">
                    已偵測到 Runtime，但健康檢查失敗：{{ cpuAsrSidecarStatus.health_error }}
                  </p>
                </div>
                <div class="flex flex-wrap gap-2">
                  <button
                    @click="installCpuAsrSidecar"
                    :disabled="!canInstallCpuAsrSidecar"
                    class="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold transition"
                  >
                    {{ cpuAsrSidecarBusy ? '安裝中…' : (cpuAsrSidecarStatus?.healthy ? '重新安裝' : (cpuAsrSidecarStatus?.installed ? '修復安裝' : '下載並安裝')) }}
                  </button>
                  <button
                    v-if="cpuAsrSidecarBusy"
                    @click="cancelCpuAsrSidecarInstall"
                    :disabled="!canCancelCpuAsrSidecar"
                    class="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold transition"
                  >
                    {{ cpuAsrSidecarStatus?.status === 'installing' ? '正在套用，無法取消' : '取消下載' }}
                  </button>
                </div>
              </div>
              <div v-if="cpuAsrSidecarBusy" class="mt-4">
                <div class="h-2 rounded-full bg-white/10 overflow-hidden">
                  <div class="h-full bg-cyan-500 transition-all" :style="{ width: `${Math.max(2, (cpuAsrSidecarStatus?.progress || 0) * 100)}%` }"></div>
                </div>
                <p class="text-white/60 text-xs mt-2">{{ cpuAsrSidecarStatus?.message }} · {{ Math.round((cpuAsrSidecarStatus?.progress || 0) * 100) }}%</p>
              </div>
              <p v-if="cpuAsrSidecarStatus?.status === 'error'" class="text-red-300 text-sm mt-3 break-words">
                安裝失敗：{{ cpuAsrSidecarStatus.error }}
              </p>
              <p v-if="cpuAsrSidecarStatus?.status === 'cancelled'" class="text-white/60 text-sm mt-3">
                已取消下載；可以隨時重新開始，既有 Runtime 不受影響。
              </p>
              <p v-if="cpuAsrSidecarStatus?.restart_required" class="text-yellow-200 text-sm mt-3">
                安裝完成，請重新啟動程式後再切換至 CPU / sherpa-onnx。
              </p>
              <div class="mt-4 border-t border-white/10 pt-4">
                <label class="block text-white/70 text-sm mb-1">離線 CPU ASR Runtime ZIP</label>
                <div class="flex flex-col lg:flex-row gap-2">
                  <input v-model="cpuAsrOfflineArchive" type="text" placeholder="例如 D:\\Downloads\\StreamTranslator-CPU-ASR-Sidecar.zip" class="flex-1 px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30" />
                  <button @click="importCpuAsrSidecarOffline" :disabled="cpuAsrSidecarBusy || !cpuAsrOfflineArchive.trim()" class="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 disabled:opacity-40 text-white font-semibold">匯入離線套件</button>
                </div>
              </div>
            </div></details>
            <div v-if="false" class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">Qwen3-ASR 模型</h3>
              <div class="space-y-3">
                <div v-for="modelId in qwenModelList" :key="`qwen-${modelId}`" class="p-4 rounded-lg bg-white/5 border border-white/10">
                  <div class="flex items-center justify-between gap-4">
                    <div class="min-w-0 flex-1">
                      <div class="text-white font-semibold break-all">{{ asrModelLabel(modelId) }}</div>
                      <div v-if="asrModelLabel(modelId) !== modelId" class="text-xs text-white/50 mt-1 break-all">{{ modelId }}</div>
                      <div :class="['text-sm mt-1', getModelStatusClass('qwen3-asr', modelId)]">
                        {{ getModelStatusText('qwen3-asr', modelId) }}
                      </div>
                    </div>
                    <button
                      @click="startModelDownload('qwen3-asr', modelId)"
                      :disabled="!canStartDownload('qwen3-asr', modelId)"
                      class="shrink-0 px-4 py-2 rounded-lg font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-700 text-white"
                    >
                      {{ modelDownloadStore.isDownloaded('qwen3-asr', modelId) ? '已下載' : '預下載' }}
                    </button>
                  </div>
                  <div v-if="getModelTask('qwen3-asr', modelId) && ['pending', 'downloading'].includes(getModelTask('qwen3-asr', modelId)!.status)" class="mt-3">
                    <div class="h-2 bg-white/10 rounded-full overflow-hidden">
                      <div
                        class="h-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all"
                        :style="{ width: `${Math.max(5, (getModelTask('qwen3-asr', modelId)?.progress || 0) * 100)}%` }"
                      />
                    </div>
                    <div class="text-xs text-white/60 mt-1">{{ getModelTask('qwen3-asr', modelId)?.message }}</div>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="false" class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">SenseVoice 模型</h3>
              <div class="space-y-3">
                <div v-for="modelId in senseVoiceModelList" :key="`sensevoice-${modelId}`" class="p-4 rounded-lg bg-white/5 border border-white/10">
                  <div class="flex items-center justify-between gap-4">
                    <div class="min-w-0 flex-1">
                      <div class="text-white font-semibold break-all">{{ asrModelLabel(modelId) }}</div>
                      <div v-if="asrModelLabel(modelId) !== modelId" class="text-xs text-white/50 mt-1 break-all">{{ modelId }}</div>
                      <div class="text-white/50 text-xs mt-1">CPU capable; ROCm remains experimental until AMD validation.</div>
                      <div :class="['text-sm mt-1', getModelStatusClass('sensevoice', modelId)]">
                        {{ getModelStatusText('sensevoice', modelId) }}
                      </div>
                    </div>
                    <button
                      @click="startModelDownload('sensevoice', modelId)"
                      :disabled="!canStartDownload('sensevoice', modelId)"
                      class="shrink-0 px-4 py-2 rounded-lg font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-700 text-white"
                    >
                      {{ modelDownloadStore.isDownloaded('sensevoice', modelId) ? '已下載' : '預下載' }}
                    </button>
                  </div>
                  <div v-if="getModelTask('sensevoice', modelId) && ['pending', 'downloading'].includes(getModelTask('sensevoice', modelId)!.status)" class="mt-3">
                    <div class="h-2 bg-white/10 rounded-full overflow-hidden">
                      <div
                        class="h-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all"
                        :style="{ width: `${Math.max(5, (getModelTask('sensevoice', modelId)?.progress || 0) * 100)}%` }"
                      />
                    </div>
                    <div class="text-xs text-white/60 mt-1">{{ getModelTask('sensevoice', modelId)?.message }}</div>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="false" class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">Fun-ASR Nano 模型</h3>
              <div class="space-y-3">
                <div v-for="modelId in funAsrModelList" :key="`fun-asr-${modelId}`" class="p-4 rounded-lg bg-white/5 border border-white/10">
                  <div class="flex items-center justify-between gap-4">
                    <div class="min-w-0 flex-1">
                      <div class="text-white font-semibold break-all">{{ asrModelLabel(modelId) }}</div>
                      <div v-if="asrModelLabel(modelId) !== modelId" class="text-xs text-white/50 mt-1 break-all">{{ modelId }}</div>
                      <div class="text-white/50 text-xs mt-1">
                        {{ modelId.includes('-MLT-') ? '31 語言模型' : '中英日與中文方言模型' }}
                      </div>
                      <div :class="['text-sm mt-1', getModelStatusClass('fun-asr-nano', modelId)]">
                        {{ getModelStatusText('fun-asr-nano', modelId) }}
                      </div>
                    </div>
                    <button
                      @click="startModelDownload('fun-asr-nano', modelId)"
                      :disabled="!canStartDownload('fun-asr-nano', modelId)"
                      class="shrink-0 px-4 py-2 rounded-lg font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-700 text-white"
                    >
                      {{ modelDownloadStore.isDownloaded('fun-asr-nano', modelId) ? '已下載' : '預下載' }}
                    </button>
                  </div>
                  <div v-if="getModelTask('fun-asr-nano', modelId) && ['pending', 'downloading'].includes(getModelTask('fun-asr-nano', modelId)!.status)" class="mt-3">
                    <div class="h-2 bg-white/10 rounded-full overflow-hidden">
                      <div
                        class="h-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all"
                        :style="{ width: `${Math.max(5, (getModelTask('fun-asr-nano', modelId)?.progress || 0) * 100)}%` }"
                      />
                    </div>
                    <div class="text-xs text-white/60 mt-1">{{ getModelTask('fun-asr-nano', modelId)?.message }}</div>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="false" class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">NVIDIA Parakeet 模型</h3>
              <div class="space-y-3">
                <div v-for="modelId in parakeetModelList" :key="`parakeet-${modelId}`" class="p-4 rounded-lg bg-white/5 border border-white/10">
                  <div class="flex items-center justify-between gap-4">
                    <div class="min-w-0 flex-1">
                      <div class="text-white font-semibold break-all">{{ asrModelLabel(modelId) }}</div>
                      <div v-if="asrModelLabel(modelId) !== modelId" class="text-xs text-white/50 mt-1 break-all">{{ modelId }}</div>
                      <div class="text-white/50 text-xs mt-1">CUDA experimental；英文／日文依模型固定；官方模型採 CC-BY-4.0，需 NVIDIA NeMo。</div>
                      <div :class="['text-sm mt-1', getModelStatusClass('parakeet-ctc-ja', modelId)]">
                        {{ getModelStatusText('parakeet-ctc-ja', modelId) }}
                      </div>
                    </div>
                    <button
                      @click="startModelDownload('parakeet-ctc-ja', modelId)"
                      :disabled="!canStartDownload('parakeet-ctc-ja', modelId)"
                      class="shrink-0 px-4 py-2 rounded-lg font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-700 text-white"
                    >
                      {{ modelDownloadStore.isDownloaded('parakeet-ctc-ja', modelId) ? '已下載' : '預下載' }}
                    </button>
                  </div>
                  <div v-if="getModelTask('parakeet-ctc-ja', modelId) && ['pending', 'downloading'].includes(getModelTask('parakeet-ctc-ja', modelId)!.status)" class="mt-3">
                    <div class="h-2 bg-white/10 rounded-full overflow-hidden">
                      <div
                        class="h-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all"
                        :style="{ width: `${Math.max(5, (getModelTask('parakeet-ctc-ja', modelId)?.progress || 0) * 100)}%` }"
                      />
                    </div>
                    <div class="text-xs text-white/60 mt-1">{{ getModelTask('parakeet-ctc-ja', modelId)?.message }}</div>
                  </div>
                </div>
              </div>
            </div>

            <div v-if="false" class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">Faster-Whisper 模型</h3>
              <div class="space-y-3">
                <div v-for="modelId in fasterWhisperModelList" :key="`fw-${modelId}`" class="p-4 rounded-lg bg-white/5 border border-white/10">
                  <div class="flex items-center justify-between gap-4">
                    <div class="min-w-0 flex-1">
                      <div class="text-white font-semibold break-all">{{ asrModelLabel(modelId) }}</div>
                      <div v-if="asrModelLabel(modelId) !== modelId" class="text-xs text-white/50 mt-1 break-all">{{ modelId }}</div>
                      <div :class="['text-sm mt-1', getModelStatusClass('faster-whisper', modelId)]">
                        {{ getModelStatusText('faster-whisper', modelId) }}
                      </div>
                    </div>
                    <button
                      @click="startModelDownload('faster-whisper', modelId)"
                      :disabled="!canStartDownload('faster-whisper', modelId)"
                      class="shrink-0 px-4 py-2 rounded-lg font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-700 text-white"
                    >
                      {{ modelDownloadStore.isDownloaded('faster-whisper', modelId) ? '已下載' : '預下載' }}
                    </button>
                  </div>
                  <div v-if="getModelTask('faster-whisper', modelId) && ['pending', 'downloading'].includes(getModelTask('faster-whisper', modelId)!.status)" class="mt-3">
                    <div class="h-2 bg-white/10 rounded-full overflow-hidden">
                      <div
                        class="h-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all"
                        :style="{ width: `${Math.max(5, (getModelTask('faster-whisper', modelId)?.progress || 0) * 100)}%` }"
                      />
                    </div>
                    <div class="text-xs text-white/60 mt-1">{{ getModelTask('faster-whisper', modelId)?.message }}</div>
                  </div>
                </div>
              </div>
            </div>

            <div class="bg-white/5 rounded-xl p-5 border border-white/10">
              <div class="flex items-center justify-between mb-3">
                <h3 class="text-lg font-semibold text-blue-300">已下載模型</h3>
                <button
                  @click="modelDownloadStore.refreshAll()"
                  class="px-3 py-1.5 rounded-lg text-sm bg-white/10 hover:bg-white/20 text-white transition"
                >
                  重新整理
                </button>
              </div>

              <div v-if="managedDownloadedModels.length === 0" class="text-white/50 text-sm">
                尚無已下載模型
              </div>
              <div v-else class="space-y-2">
                <div v-for="item in managedDownloadedModels" :key="`${item.compute_backend}-${item.engine}-${item.repo_id}`" class="p-3 rounded-lg bg-black/20 border border-white/10">
                  <div class="flex items-center justify-between gap-4">
                    <div class="min-w-0 flex-1">
                      <div class="text-white font-medium break-all">{{ asrModelLabel(item.model_id) }}</div>
                      <div v-if="asrModelLabel(item.model_id) !== item.model_id" class="text-xs text-white/50 mt-1 break-all">{{ item.model_id }}</div>
                      <div class="text-xs text-white/50 mt-1 break-all">{{ item.compute_backend.toUpperCase() }} · {{ item.engine }} · {{ item.repo_id }}</div>
                    </div>
                    <div class="flex shrink-0 items-center gap-3">
                      <div class="text-sm text-white/70">{{ modelDownloadStore.formatSize(item.size_bytes) }}</div>
                      <button
                        @click="deleteDownloadedModel(item.engine, item.model_id, item.compute_backend)"
                        class="px-3 py-1.5 rounded-lg text-sm bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 text-red-200 transition"
                      >
                        刪除
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
</template>

<style scoped src="./settings-shared.css"></style>
