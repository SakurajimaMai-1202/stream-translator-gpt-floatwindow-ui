<script setup lang="ts">
import { defineAsyncComponent } from 'vue';
import UiSelect from '../UiSelect.vue';
import { useSettingsTabBindings } from '../../composables/settings/settingsContext';
const WhisperFilterSettings = defineAsyncComponent(() => import('../WhisperFilterSettings.vue'));
const {
  asrComputeBackendLocked, asrComputeBackendOptions, canUseFasterWhisper, canUseFasterWhisperSimul, canUseFunAsr, canUseOpenAiAsr, canUseParakeet, canUseQwen3Asr, canUseSenseVoice, canUseSimulStreaming, cpuAsrRuntimeAvailable, effectiveAsrComputeBackend, effectiveAsrRuntimeLabel, funAsrModelOptions, ignoredRuntimeDevices, isAsrEngineSelected, isSherpaOnnxMode, isTranscriptionLanguageLocked, localConfig, packageProfileLabel, parakeetDecodingOptions, parakeetModelOptions, qwen3AsrModelOptions, qwen3DtypeOptions, runtimeCapabilities, runtimeDeviceLine, runtimeDevicePolicyOptions, runtimeDiagnosticNotice, runtimeSelection, runtimeStatus, runtimeStatusLabel, selectAsrEngine, selectedRuntimeDevice, senseVoiceModelOptions, store, testOpenAiAsrConnection, testingGpt, transcriptionLanguageOptions, whisperModelSelectOptions
} = useSettingsTabBindings();
</script>

<template>
          <div class="settings-paint-section apple-settings">
            <header class="apple-page-header"><h2>轉錄選項</h2><p>選擇語音辨識引擎，調整語言與推論設定。</p></header>

            <div class="bg-white/5 rounded-xl p-4 border border-white/10">
              <div class="flex flex-col md:flex-row md:items-start md:justify-between gap-4 mb-4">
                <div>
                  <h3 class="text-lg font-semibold text-cyan-300 mb-1">ASR 執行環境</h3>
                  <p class="text-white/50 text-sm">
                    套件 Profile 決定可用的 GPU runtime；ASR 後端可另外切換為獨立的 Sherpa-ONNX CPU runtime。
                  </p>
                </div>
                <button type="button"
                  class="px-3 py-2 bg-white/10 hover:bg-white/15 border border-white/10 rounded-lg text-white text-sm transition"
                  @click="store.loadRuntimeStatus()">
                  Refresh
                </button>
              </div>

              <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                <div>
                  <label class="block text-white/70 font-semibold mb-2">目前套件（唯讀）</label>
                  <div class="w-full px-4 py-2.5 bg-white/5 border border-white/15 rounded-lg text-white font-medium">
                    {{ packageProfileLabel }}
                  </div>
                  <p class="text-white/40 text-xs mt-1">
                    CUDA 與 ROCm 使用不同 runtime，需啟動對應套件，無法在此動態切換。
                  </p>
                </div>
                <div>
                  <label class="block text-white/70 font-semibold mb-2">ASR 執行後端</label>
                  <UiSelect
                    v-model="localConfig.transcription.asr_compute_backend"
                    :options="asrComputeBackendOptions"
                    :disabled="asrComputeBackendLocked"
                  />
                  <p class="text-white/40 text-xs mt-1">
                    目前實際使用：{{ effectiveAsrRuntimeLabel }}
                  </p>
                </div>
                <div>
                  <label class="block text-white/70 font-semibold mb-2">GPU 裝置策略</label>
                  <UiSelect v-model="localConfig.runtime.device_policy" :options="runtimeDevicePolicyOptions" :disabled="effectiveAsrComputeBackend === 'cpu'" />
                  <p v-if="isSherpaOnnxMode" class="text-white/40 text-xs mt-1">Sherpa-ONNX 固定使用 CPU，此設定不適用。</p>
                </div>
                <div class="flex items-end">
                  <label :class="['flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 w-full', isSherpaOnnxMode ? 'opacity-45 cursor-not-allowed' : 'cursor-pointer']">
                    <input v-model="localConfig.runtime.allow_integrated_gpu" :disabled="isSherpaOnnxMode" type="checkbox" class="w-5 h-5 accent-yellow-400 mt-0.5" />
                    <div>
                      <span class="text-white font-medium">Allow integrated GPU</span>
                      <p class="text-white/45 text-xs mt-1">只建議 ROCm APU/iGPU 實驗測試時開啟。</p>
                    </div>
                  </label>
                </div>
              </div>

              <div
                v-if="localConfig.transcription.asr_compute_backend === 'cpu' && !cpuAsrRuntimeAvailable"
                class="mt-4 bg-yellow-500/10 border border-yellow-500/25 rounded-lg p-3"
              >
                <div class="text-yellow-200 text-sm font-semibold">CPU ASR sidecar 尚未安裝</div>
                <p class="text-white/65 text-xs mt-1">
                  CUDA／ROCm 包需要獨立的 <code>_runtime_cpu_asr</code>。請使用包含 CPU ASR sidecar 的套件，
                  或以 <code>-IncludeCpuAsrSidecar</code> 建置；GPU runtime 不會被修改。
                </p>
              </div>

              <div class="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div class="bg-black/20 rounded-lg p-3 border border-white/10">
                  <div class="flex items-center justify-between gap-3 mb-2">
                    <span class="text-white/60 text-sm">Status</span>
                    <span class="px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-200 text-xs">{{ runtimeStatusLabel }}</span>
                  </div>
                  <div class="text-white font-medium">
                    {{ isSherpaOnnxMode
                      ? `${runtimeStatus?.cpu?.name || 'CPU'}${runtimeStatus?.cpu?.logical_cores ? ` (${runtimeStatus.cpu.logical_cores} logical processors)` : ''}`
                      : (selectedRuntimeDevice ? runtimeDeviceLine(selectedRuntimeDevice) : 'No GPU selected') }}
                  </div>
                  <p class="text-white/45 text-xs mt-2">{{ runtimeSelection?.reason || store.runtimeStatusError || 'Runtime status not loaded yet.' }}</p>
                </div>
                <div class="bg-black/20 rounded-lg p-3 border border-white/10">
                  <div class="text-white/60 text-sm mb-2">目前後端能力</div>
                  <div class="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                    <template v-if="isSherpaOnnxMode">
                      <div class="text-white/80">引擎：<span class="text-cyan-200">Sherpa-ONNX</span></div>
                      <div class="text-white/80">裝置：<span class="text-cyan-200">CPU</span></div>
                      <div class="text-white/80">模型格式：<span class="text-cyan-200">ONNX INT8 bundle</span></div>
                      <div class="text-white/80">PyTorch / CUDA：<span class="text-cyan-200">不需要</span></div>
                    </template>
                    <template v-else>
                      <div class="text-white/80">Qwen3 dtype: <span class="text-cyan-200">{{ runtimeCapabilities?.qwen3_default_dtype || '-' }}</span></div>
                      <div class="text-white/80">Faster-Whisper: <span class="text-cyan-200">{{ runtimeCapabilities?.faster_whisper_status || '-' }}</span></div>
                      <div class="text-white/80">SenseVoice: <span class="text-cyan-200">{{ runtimeCapabilities?.sensevoice_status || '-' }}</span></div>
                      <div class="text-white/80">NVIDIA Parakeet: <span class="text-cyan-200">{{ runtimeCapabilities?.parakeet_status || '-' }}</span></div>
                    </template>
                    <div class="text-white/80">Package: <span class="text-white/70">{{ runtimeStatus?.package_suffix || '-' }}</span></div>
                  </div>
                </div>
              </div>

              <div v-if="ignoredRuntimeDevices.length" class="mt-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg p-3">
                <div class="text-yellow-200 text-sm font-semibold mb-2">Ignored devices</div>
                <div v-for="device in ignoredRuntimeDevices" :key="`${device.source}-${device.index}-${device.name}`" class="text-white/70 text-sm">
                  {{ runtimeDeviceLine(device) }}
                </div>
              </div>

              <div v-if="runtimeDiagnosticNotice" class="mt-4 bg-cyan-500/10 border border-cyan-500/20 rounded-lg p-3">
                <div class="text-cyan-200 text-sm font-semibold mb-2">ROCm diagnostics</div>
                <p class="text-white/70 text-sm">{{ runtimeDiagnosticNotice }}</p>
              </div>
            </div>

            <!-- Whisper 引擎模式選擇 (移到最上面) -->
            <div class="bg-white/5 rounded-xl p-4 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">🎯 轉錄引擎</h3>
              <p class="text-white/60 text-sm mb-4">
                <template v-if="isSherpaOnnxMode">目前為 Sherpa-ONNX CPU 模式；下列引擎會載入各自的 INT8 ONNX bundle，GPU 專屬選項會停用。</template>
                <template v-else>GPU 原生模式會依套件能力提供引擎；Faster-Whisper 可搭配 SimulStreaming 使用。</template>
              </p>
              <div class="space-y-3">
                <label
                  @click.prevent="canUseFasterWhisper && selectAsrEngine('faster_whisper')"
                  :class="['flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 transition', canUseFasterWhisper ? 'cursor-pointer hover:bg-white/10' : 'opacity-45 cursor-not-allowed']"
                >
                  <input :checked="isAsrEngineSelected('faster_whisper')" :disabled="!canUseFasterWhisper" type="checkbox" class="w-5 h-5 accent-blue-500 mt-0.5 pointer-events-none" />
                  <div class="flex-1">
                    <span class="text-white font-medium">使用 Faster-Whisper</span>
                    <p class="text-white/50 text-sm mt-1">
                      使用優化過的 Faster-Whisper 引擎,提升轉錄速度。
                      <br />✨ 與 SimulStreaming 組合:作為編碼器提供更高效能
                    </p>
                  </div>
                </label>

                <label
                  @click.prevent="(canUseSimulStreaming || canUseFasterWhisperSimul) && selectAsrEngine('simul_streaming')"
                  :class="['flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 transition', (canUseSimulStreaming || canUseFasterWhisperSimul) ? 'cursor-pointer hover:bg-white/10' : 'opacity-45 cursor-not-allowed']"
                >
                  <input :checked="isAsrEngineSelected('simul_streaming')" :disabled="!canUseSimulStreaming && !canUseFasterWhisperSimul" type="checkbox" class="w-5 h-5 accent-blue-500 mt-0.5 pointer-events-none" />
                  <div class="flex-1">
                    <span class="text-white font-medium">使用 SimulStreaming</span>
                    <p class="text-white/50 text-sm mt-1">
                      使用 SimulStreaming 進行即時串流轉錄,降低延遲。
                      <br />✨ 與 Faster-Whisper 組合:使用 Faster-Whisper 作為編碼器
                    </p>
                  </div>
                </label>

                <label
                  @click.prevent="canUseOpenAiAsr && selectAsrEngine('openai')"
                  :class="['flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 transition', canUseOpenAiAsr ? 'cursor-pointer hover:bg-white/10' : 'opacity-45 cursor-not-allowed']"
                >
                  <input :checked="isAsrEngineSelected('openai')" :disabled="!canUseOpenAiAsr" type="checkbox" class="w-5 h-5 accent-blue-500 mt-0.5 pointer-events-none" />
                  <div class="flex-1">
                    <span class="text-white font-medium">使用 OpenAI Transcription API</span>
                    <p class="text-white/50 text-sm mt-1">
                      使用 OpenAI 官方雲端轉錄 API,無需本地模型但需要 API 額度。
                      <br /><strong>注意：</strong>此選項與上述兩項互斥
                    </p>
                  </div>
                </label>

                <label
                  @click.prevent="canUseQwen3Asr && selectAsrEngine('qwen3')"
                  :class="['flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 transition', canUseQwen3Asr ? 'cursor-pointer hover:bg-white/10' : 'opacity-45 cursor-not-allowed']"
                >
                  <input :checked="isAsrEngineSelected('qwen3')" :disabled="!canUseQwen3Asr" type="checkbox" class="w-5 h-5 accent-blue-500 mt-0.5 pointer-events-none" />
                  <div class="flex-1">
                    <span class="text-white font-medium">使用 Qwen3-ASR</span>
                    <p class="text-white/50 text-sm mt-1">
                      <template v-if="isSherpaOnnxMode">使用 Qwen3-ASR 0.6B／1.7B 的 Sherpa-ONNX INT8 CPU bundle；不套用 dtype、4-bit 或 GPU 裝置設定。</template>
                      <template v-else>使用 Qwen3-ASR GPU 原生模型進行多語言轉錄；CUDA 可攜版已內建所需執行環境。</template>
                    </p>
                  </div>
                </label>

                <label
                  @click.prevent="canUseSenseVoice && selectAsrEngine('sensevoice')"
                  :class="['flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 transition', canUseSenseVoice ? 'cursor-pointer hover:bg-white/10' : 'opacity-45 cursor-not-allowed']"
                >
                  <input :checked="isAsrEngineSelected('sensevoice')" :disabled="!canUseSenseVoice" type="checkbox" class="w-5 h-5 accent-blue-500 mt-0.5 pointer-events-none" />
                  <div class="flex-1">
                    <span class="text-white font-medium">使用 SenseVoiceSmall</span>
                    <p class="text-white/50 text-sm mt-1">
                      <template v-if="isSherpaOnnxMode">Sherpa-ONNX INT8 CPU 推論，支援中文、英文、日文、韓文與粵語。</template>
                      <template v-else>GPU 原生多語 ASR；CUDA 可加速，ROCm 在 AMD 實機驗證前維持 experimental。</template>
                    </p>
                  </div>
                </label>

                <label
                  @click.prevent="canUseFunAsr && selectAsrEngine('fun_asr')"
                  :class="['flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 transition', canUseFunAsr ? 'cursor-pointer hover:bg-white/10' : 'opacity-45 cursor-not-allowed']"
                >
                  <input :checked="isAsrEngineSelected('fun_asr')" :disabled="!canUseFunAsr" type="checkbox" class="w-5 h-5 accent-blue-500 mt-0.5 pointer-events-none" />
                  <div class="flex-1">
                    <span class="text-white font-medium">使用 Fun-ASR Nano</span>
                    <p class="text-white/50 text-sm mt-1">
                      <template v-if="isSherpaOnnxMode">Sherpa-ONNX INT8 CPU bundle，支援中英日與中文方言；目前不提供時間戳。</template>
                      <template v-else>可選中英日／中文方言版或 31 語言 MLT 版；目前採分段轉錄且不提供時間戳。</template>
                    </p>
                  </div>
                </label>

                <label
                  @click.prevent="canUseParakeet && selectAsrEngine('parakeet')"
                  :class="['flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 transition', canUseParakeet ? 'cursor-pointer hover:bg-white/10' : 'opacity-45 cursor-not-allowed']"
                >
                  <input :checked="isAsrEngineSelected('parakeet')" :disabled="!canUseParakeet" type="checkbox" class="w-5 h-5 accent-blue-500 mt-0.5 pointer-events-none" />
                  <div class="flex-1">
                    <span class="text-white font-medium">Parakeet</span>
                    <p class="text-white/50 text-sm mt-1">
                      <template v-if="isSherpaOnnxMode">Sherpa-ONNX INT8 CPU 推論；可選 25 語言 TDT 或日文專用 CTC bundle，不需要 NVIDIA GPU／NeMo。</template>
                      <template v-else>CUDA 實驗性離線 ASR；官方模型透過 NVIDIA NeMo 執行。</template>
                    </p>
                  </div>
                </label>
              </div>
            </div>

            <!-- 轉錄模型與語言設定 -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label class="block text-white/70 font-semibold mb-2">轉錄模型</label>
                <!-- Whisper 模型選擇 -->
                <UiSelect v-if="!localConfig.transcription.use_qwen3_asr && !localConfig.transcription.use_openai_transcription_api && !localConfig.transcription.use_sensevoice_asr && !localConfig.transcription.use_fun_asr && !localConfig.transcription.use_nemo_asr"
                  v-model="localConfig.transcription.model"
                  :options="whisperModelSelectOptions" />
                <div v-if="localConfig.transcription.use_openai_transcription_api" class="md:col-span-2 bg-gradient-to-br from-emerald-500/10 to-blue-500/10 rounded-xl p-5 border border-emerald-500/20">
                  <h3 class="text-lg font-semibold text-emerald-300 mb-2">OpenAI 雲端語音轉錄</h3>
                  <p class="text-white/60 text-sm mb-4">音訊會上傳至 OpenAI Transcription API 進行語音辨識。這組金鑰只供 ASR 使用，不會提供給 GPT 或 Gemini 翻譯；雲端轉錄可能產生 API 費用。</p>
                  <label class="block text-white/70 font-semibold mb-2">OpenAI ASR API Key</label>
                  <div class="flex gap-2">
                    <input v-model="localConfig.transcription.openai_api_key" type="password" placeholder="sk-..."
                      class="flex-1 px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-emerald-400" />
                    <button @click="testOpenAiAsrConnection" :disabled="testingGpt"
                      class="bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 font-semibold px-4 rounded-lg transition text-xs whitespace-nowrap">測試 ASR 金鑰</button>
                  </div>
                  <p class="text-white/45 text-xs mt-2">若同時使用 OpenAI GPT 翻譯，請到「翻譯選項」另外輸入翻譯金鑰。</p>
                </div>
                <!-- OpenAI 模型選擇 -->
                <input v-else-if="localConfig.transcription.use_openai_transcription_api" 
                  v-model="localConfig.transcription.openai_transcription_model" 
                  type="text" 
                  placeholder="whisper-1"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                <UiSelect v-else-if="localConfig.transcription.use_sensevoice_asr"
                  v-model="localConfig.transcription.sensevoice_model"
                  :options="senseVoiceModelOptions" />
                <UiSelect v-else-if="localConfig.transcription.use_fun_asr"
                  v-model="localConfig.transcription.fun_asr_model"
                  :options="funAsrModelOptions" />
                <UiSelect v-else-if="localConfig.transcription.use_nemo_asr"
                  v-model="localConfig.transcription.nemo_asr_model"
                  :options="parakeetModelOptions" />
                <div v-if="localConfig.transcription.use_nemo_asr && !isSherpaOnnxMode" class="mt-4">
                  <label class="block text-white/70 font-semibold mb-2">解碼器</label>
                  <UiSelect v-model="localConfig.transcription.nemo_asr_decoding" :options="parakeetDecodingOptions" />
                  <p class="text-white/45 text-xs mt-2">TDT 為官方預設；CTC 保留作相容或比較用途。模型語言會依英文／日文模型自動綁定。</p>
                </div>
                <!-- Qwen3-ASR 模型選擇 (下拉選單) -->
                <UiSelect v-else-if="localConfig.transcription.use_qwen3_asr"
                  v-model="localConfig.transcription.qwen3_asr_model"
                  :options="qwen3AsrModelOptions" />
                <div v-if="localConfig.transcription.use_qwen3_asr && !isSherpaOnnxMode" class="mt-4 grid grid-cols-1 gap-4">
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">模型精度</label>
                    <UiSelect v-model="localConfig.transcription.qwen3_dtype" :options="qwen3DtypeOptions" />
                    <p class="text-white/45 text-xs mt-2">
                      BF16 適合支援 BF16 的 NVIDIA GPU；FP32 較慢且需要更多顯存，但可用於排查精度或相容性問題。
                    </p>
                  </div>
                  <div>
                    <label class="flex items-center gap-2 cursor-pointer mt-2">
                      <input v-model="localConfig.transcription.qwen3_load_in_4bit" type="checkbox" class="w-5 h-5 accent-purple-400" />
                      <div>
                        <span class="text-white">啟用 4-bit 量化（省顯存）</span>
                        <p class="text-white/50 text-xs mt-0.5">
                          <template v-if="localConfig.transcription.qwen3_load_in_4bit">
                            <span class="text-green-400 font-medium">✓ 已啟用</span>　顯存需求：
                            <span class="text-yellow-300 font-medium">{{ localConfig.transcription.qwen3_asr_model === 'Qwen/Qwen3-ASR-1.7B' ? '~1.5 GB' : '~0.5 GB' }}</span>
                            （原 {{ localConfig.transcription.qwen3_asr_model === 'Qwen/Qwen3-ASR-1.7B' ? '~3.5 GB' : '~1.2 GB' }}，節省約 60%）
                          </template>
                          <template v-else>
                            未啟用 — 顯存需求：
                            <span class="text-yellow-300 font-medium">{{ localConfig.transcription.qwen3_asr_model === 'Qwen/Qwen3-ASR-1.7B' ? '~3.5 GB' : '~1.2 GB' }}</span>
                            　啟用後可降至 {{ localConfig.transcription.qwen3_asr_model === 'Qwen/Qwen3-ASR-1.7B' ? '~1.5 GB' : '~0.5 GB' }}
                          </template>
                          <br/>CUDA 可攜版已內建量化支援
                        </p>
                      </div>
                    </label>
                  </div>
                </div>
                <p class="text-white/40 text-xs mt-2">
                  <span v-if="localConfig.transcription.use_qwen3_asr">1.7B 模型準確度更高,0.6B 模型速度更快</span>
                  <span v-else-if="localConfig.transcription.use_openai_transcription_api">OpenAI 轉錄模型</span>
                  <span v-else>Whisper 本地模型</span>
                </p>
              </div>

              <div>
                <label class="block text-white/70 font-semibold mb-2">語言</label>
                <UiSelect
                  v-model="localConfig.transcription.language"
                  :options="transcriptionLanguageOptions"
                  :disabled="isTranscriptionLanguageLocked"
                />
                <p v-if="isTranscriptionLanguageLocked" class="text-amber-300/80 text-xs mt-2">
                  此模型為專用語言模型，輸入語言已自動鎖定。
                </p>
              </div>

              <div class="md:col-span-2" v-if="!isSherpaOnnxMode && !localConfig.transcription.use_qwen3_asr && !localConfig.transcription.use_nemo_asr">
                <label class="block text-white/70 font-semibold mb-2">轉錄提示詞</label>
                <textarea v-model="localConfig.transcription.transcription_initial_prompt" placeholder="提示詞1, 提示詞2, ..." rows="3"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400"></textarea>
                <p class="text-white/40 text-sm mt-1">通用的轉錄固定提示詞/術語表。格式:"提示詞1, 提示詞2, ..."。此文本將始終包含在傳遞給模型的提示詞中。</p>
              </div>
              <div class="md:col-span-2" v-else>
                <p class="text-yellow-400 text-sm">{{ isSherpaOnnxMode ? 'Sherpa-ONNX bundle 不使用提示詞、GPU dtype、4-bit 或 NeMo 解碼器設定。' : '此引擎不支援自訂提示詞。' }}</p>
              </div>
            </div>

            <WhisperFilterSettings v-model="localConfig.transcription.whisper_filters" />

            <!-- 其他設定 -->
            <div class="mt-6 grid grid-cols-1 gap-6">
              <div class="flex items-center">
                <label class="flex items-center gap-2 cursor-pointer">
                  <input v-model="localConfig.transcription.disable_transcription_context" type="checkbox" class="w-5 h-5 accent-blue-500" />
                  <span class="text-white">停用轉錄上下文</span>
                </label>
              </div>
            </div>
          </div>
</template>

<style scoped src="./settings-shared.css"></style>
