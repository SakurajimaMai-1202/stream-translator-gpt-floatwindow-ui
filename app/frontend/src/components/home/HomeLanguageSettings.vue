<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { configApi, translationApi } from '../../services/api';
import UiSelect, { type UiSelectOption } from '../UiSelect.vue';
import { simpleAsrModel, simpleAsrLanguages } from '../../utils/simpleAsr';
import { HAAS_MODEL_ID, isModelLanguageCompatible, languageOptionsForModel } from '../../utils/asrCapabilities';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  router, interfaceMode, store, whisperModels, qwen3AsrModels, parakeetModels, allFunAsrModelOptions, selectedAsrModelId, selectedAsrCapability, selectedTranscriptionEngine, selectedAsrComputeBackend, selectedWhisperModel, selectedQwen3AsrModel, selectedSenseVoiceModel, selectedFunAsrModel, selectedParakeetModel, selectedOpenAiTranscriptionModel, selectedInputLanguage, selectedOutputLanguage, selectedBackend, translationEnabled, sameLanguageSelected, runtimeCapabilities, allowedTranscriptionEngines, allowedFasterWhisperModels, allowedQwen3AsrModels, allowedParakeetModels
} = useHomeContext();

const showAdvancedConfig = ref(true);
const { llamaStore } = useHomeContext();
const isLocalTranslation = computed(() => ['llama', 'localllm'].includes(selectedBackend.value));
const cloudOptions = computed(() => [
  { value: 'gemini', label: 'Google Gemini' },
  { value: 'gpt', label: 'OpenAI GPT' },
  ...backendOptions.value.filter(option => String(option.value).startsWith('custom:')),
]);
let lastCloudBackend = '';
try { lastCloudBackend = localStorage.getItem('fw.simple.lastCloudBackend') || ''; } catch { /* Storage unavailable. */ }
// Not immediate: HomeView starts at the default 'gpt' before the saved config loads,
// which would overwrite the remembered service on every page load.
watch(selectedBackend, value => {
  if (value !== 'gpt' && value !== 'gemini' && !value.startsWith('custom:')) return;
  lastCloudBackend = value;
  try { localStorage.setItem('fw.simple.lastCloudBackend', value); } catch { /* Keep memory fallback. */ }
}, { flush: 'sync' });
function chooseTranslationMethod(local: boolean) {
  selectedBackend.value = local ? 'llama'
    : cloudOptions.value.some(option => option.value === lastCloudBackend) ? lastCloudBackend
    : store.config?.translation?.google_api_key ? 'gemini'
    : store.config?.translation?.openai_api_key ? 'gpt' : 'gemini';
}
const localModelName = computed(() => (llamaStore.selectedModelPath || '').split(/[\\/]/).pop()?.replace(/\.gguf$/i, '') || '');
const apiKeyField = computed(() => selectedBackend.value === 'gemini' ? 'google_api_key'
  : selectedBackend.value === 'gpt' ? 'openai_api_key' : null);
const hasApiKey = computed(() => !!(apiKeyField.value && store.config?.translation?.[apiKeyField.value]));
function cancelKeyEdit() {
  editingKey.value = false;
  apiKeyInput.value = '';
  keyError.value = '';
}
const editingKey = ref(false);
const apiKeyInput = ref('');
const savingKey = ref(false);
const keyError = ref('');
const keySaved = ref(false);
watch(selectedBackend, () => {
  editingKey.value = false;
  apiKeyInput.value = '';
  keyError.value = '';
  keySaved.value = false;
});
async function saveApiKey() {
  const field = apiKeyField.value;
  const key = apiKeyInput.value.trim();
  if (!field || !key || savingKey.value || store.isRunning || !translationEnabled.value) return;
  savingKey.value = true;
  keyError.value = '';
  keySaved.value = false;
  try {
    if (field === 'google_api_key') {
      await translationApi.testGemini(key, store.config.translation.gemini_model || 'gemini-2.5-flash-lite');
    }
    await configApi.updateSection('translation', { [field]: key });
    // Must match backend config_secrets._mask (MASK_PREFIX '••••'): a later Home save sends
    // this value back, and only that prefix is restored to the real key on the server.
    store.config.translation[field] = key.length >= 8 ? `••••${key.slice(-4)}` : '••••••••';
    if (apiKeyField.value === field) {
      apiKeyInput.value = '';
      editingKey.value = false;
      keySaved.value = true;
    }
  } catch (cause: any) {
    if (apiKeyField.value === field) {
      const message = cause?.response?.data?.detail || cause?.message || '儲存失敗，請重試。';
      keyError.value = String(message).split(key).join('〔已隱藏〕');
    }
  } finally { savingKey.value = false; }
}

const asrComputeBackendOptions: UiSelectOption[] = [
  { value: 'auto', label: '自動（GPU 優先）' },
  { value: 'gpu', label: 'GPU 原生 ASR' },
  { value: 'cpu', label: 'CPU / sherpa-onnx' },
];

const outputLanguages = [
  { value: 'Traditional Chinese', label: '繁體中文' },
  { value: 'Simplified Chinese', label: '簡體中文' },
  { value: 'Japanese', label: '日文' },
  { value: 'English', label: '英文' },
  { value: 'Korean', label: '韓文' }
];

const allTranscriptionEngineOptions: UiSelectOption[] = [
  { value: 'faster-whisper', label: 'Faster-Whisper', group: '本機 ASR' },
  { value: 'simul-streaming', label: 'SimulStreaming', group: '本機 ASR' },
  { value: 'faster-whisper-simul', label: 'Faster-Whisper + SimulStreaming', group: '本機 ASR' },
  { value: 'qwen3-asr', label: 'Qwen3-ASR', group: '本機 ASR' },
  { value: 'sensevoice', label: 'SenseVoiceSmall', group: '本機 ASR' },
  { value: 'fun-asr-nano', label: 'Fun-ASR Nano', group: '本機 ASR' },
  { value: 'parakeet-ctc-ja', label: 'Parakeet', group: '本機 ASR' },
  { value: 'openai-api', label: 'OpenAI API', group: '遠端 ASR' }
];

const whisperModelOptions = computed<UiSelectOption[]>(() =>
  whisperModels
    .filter((model) => allowedFasterWhisperModels.value.includes(model))
    .map((model) => ({ value: model, label: model }))
);

const qwen3AsrModelOptions = computed<UiSelectOption[]>(() =>
  qwen3AsrModels
    .filter((model) => allowedQwen3AsrModels.value.includes(model.value))
    .map((model) => ({
      value: model.value,
      label: model.label,
    }))
);

const senseVoiceModelOptions = computed<UiSelectOption[]>(() => [
  {
    value: 'iic/SenseVoiceSmall',
    label: 'SenseVoiceSmall（中／粵／英／日／韓）',
    disabled: selectedAsrCapability.value?.language_mode !== 'fixed'
      && !isModelLanguageCompatible(
        runtimeCapabilities.value?.asr_model_capabilities,
        'iic/SenseVoiceSmall',
        selectedInputLanguage.value,
      ),
  }
]);

const funAsrModelOptions = computed<UiSelectOption[]>(() =>
  allFunAsrModelOptions.map((model) => ({
    ...model,
    disabled: selectedAsrCapability.value?.language_mode !== 'fixed'
      && !isModelLanguageCompatible(
        runtimeCapabilities.value?.asr_model_capabilities,
        String(model.value),
        selectedInputLanguage.value,
      ),
  }))
);

const parakeetModelOptions = computed<UiSelectOption[]>(() => {
  // Haas only runs on the CPU sidecar.  When the runtime is on the GPU path the
  // backend list omits it, which used to hide the model with no explanation.
  // Keep it visible but disabled so the reason is discoverable.
  const allowed = allowedParakeetModels.value;
  const showHaasDisabled = allowed.length > 0
    && !allowed.includes(HAAS_MODEL_ID)
    && allowedTranscriptionEngines.value.includes('parakeet-ctc-ja');
  return parakeetModels
    .filter((model) => allowed.includes(model.value)
      || (showHaasDisabled && model.value === HAAS_MODEL_ID))
    .map((model) => {
      const needsCpuBackend = showHaasDisabled && model.value === HAAS_MODEL_ID;
      return {
        value: model.value,
        label: needsCpuBackend ? `${model.label} · 請先把 ASR 運算模式切到 CPU` : model.label,
        disabled: needsCpuBackend
          || (selectedAsrCapability.value?.language_mode !== 'fixed'
            && !isModelLanguageCompatible(
              runtimeCapabilities.value?.asr_model_capabilities,
              model.value,
              selectedInputLanguage.value,
            )),
      };
    });
});

const inputLanguageOptions = computed<UiSelectOption[]>(() =>
  interfaceMode.isSimple ? simpleAsrLanguages : languageOptionsForModel(
    runtimeCapabilities.value?.asr_model_capabilities,
    selectedAsrModelId.value,
  )
);

const isInputLanguageLocked = computed(() => !interfaceMode.isSimple && selectedAsrCapability.value?.language_mode === 'fixed');

const outputLanguageOptions = computed<UiSelectOption[]>(() =>
  outputLanguages.map((lang) => ({ value: lang.value, label: lang.label }))
);

const backendOptions = computed<UiSelectOption[]>(() => {
  const base: UiSelectOption[] = [
    { value: 'none', label: '不翻譯' },
    { value: 'gpt', label: 'OpenAI GPT' },
    { value: 'gemini', label: 'Google Gemini' },
    { value: 'llama', label: 'Llama（本機／相容服務）' }
  ];

  const customModels = store.config?.translation?.custom_models || [];
  const custom = customModels
    .filter((model: any) => model && model.name)
    .map((model: any) => ({
      value: `custom:${model.name}`,
      label: model.name,
      group: '自訂模型'
    }));

  return [...base, ...custom];
});

const OPENAI_TRANSCRIPTION_MODELS = ['whisper-1', 'gpt-4o-transcribe', 'gpt-4o-mini-transcribe'];

const openAiTranscriptionModelOptions = computed<UiSelectOption[]>(() => {
  const current = selectedOpenAiTranscriptionModel.value;
  const models = OPENAI_TRANSCRIPTION_MODELS.includes(current) ? OPENAI_TRANSCRIPTION_MODELS : [...OPENAI_TRANSCRIPTION_MODELS, current];
  return models.map((model) => ({ value: model, label: model }));
});

const transcriptionEngineOptions = computed<UiSelectOption[]>(() =>
  allTranscriptionEngineOptions.filter((option) =>
    allowedTranscriptionEngines.value.includes(String(option.value))
  )
);
</script>

<template>
            <!-- 快速設定 (輸入語言, 啟用翻譯, 目標語言) -->
            <p v-if="interfaceMode.isSimple" class="mb-3 text-xs text-indigo-200" role="status">
              {{ simpleAsrModel(selectedInputLanguage) === 'iic/SenseVoiceSmall' ? 'CPU ASR · SenseVoice Small' : simpleAsrModel(selectedInputLanguage) ? (selectedInputLanguage === 'ja' ? 'CPU ASR · Parakeet 日文 0.6B' : 'CPU ASR · Parakeet v3 多語言 0.6B') : '請選擇輸入語言，以自動配置 CPU ASR 模型。' }}
              <span class="block mt-1 text-white/65">中文使用 SenseVoice，日文使用 Parakeet 日文模型，其餘 25 種支援語言使用 Parakeet v3。其他語言請切換進階模式。</span>
            </p>
            <div class="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
              <!-- 輸入語言 -->
              <div class="flex flex-col">
                <!-- Same header height as the target column so both selects line up. -->
                <div class="language-field-header mb-1.5 flex items-center">
                  <label class="commercial-field-label !mb-0">輸入語言</label>
                </div>
                <UiSelect
                  v-model="selectedInputLanguage"
                  :options="inputLanguageOptions"
                  :disabled="store.isRunning || isInputLanguageLocked"
                  button-class="bg-white/5 border border-white/15 hover:bg-white/10 text-xs rounded-xl"
                />
                <p v-if="isInputLanguageLocked" class="text-amber-300/80 text-xs mt-1">
                  此模型為專用語言模型，輸入語言已自動鎖定。
                </p>
              </div>

              <!-- 啟用翻譯與目標語言 -->
              <div class="flex flex-col">
                <div class="language-field-header mb-1.5 flex flex-wrap items-center justify-between gap-2">
                  <label class="commercial-field-label !mb-0">目標語言</label>
                  <div class="inline-flex rounded-lg border border-white/15 bg-white/5 p-0.5" role="group" aria-label="轉譯模式">
                    <button
                      v-for="option in [{ value: false, label: '僅轉錄' }, { value: true, label: '轉錄＋翻譯' }]"
                      :key="option.label"
                      type="button"
                      class="translation-mode-option rounded-md px-3 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50"
                      :class="translationEnabled === option.value ? 'bg-blue-600 text-white' : 'text-white/65 hover:text-white'"
                      :aria-pressed="translationEnabled === option.value"
                      :disabled="store.isRunning"
                      @click="translationEnabled = option.value"
                    >
                      {{ option.label }}
                    </button>
                  </div>
                </div>
                <UiSelect
                  v-model="selectedOutputLanguage"
                  :options="outputLanguageOptions"
                  :disabled="store.isRunning || !translationEnabled"
                  button-class="bg-white/5 border border-white/15 hover:bg-white/10 text-xs rounded-xl disabled:opacity-40"
                />
                <p v-if="translationEnabled && sameLanguageSelected" class="mt-2 text-xs text-indigo-200" role="status">輸入與目標語言相同，僅辨識並顯示原文，不呼叫翻譯模型。</p>
              </div>
            </div>

            <!-- 進階配置摺疊區 (轉錄引擎、模型選擇、翻譯後端) -->
            <div v-if="interfaceMode.isSimple" class="mb-5">
              <div class="mb-1">
                <label class="commercial-field-label">翻譯方式</label>
              </div>
              <div class="inline-flex rounded-lg border border-white/15 bg-white/5 p-0.5" role="group" aria-label="翻譯方式">
                <button v-for="option in [{ local: false, label: '雲端翻譯' }, { local: true, label: '本機翻譯' }]"
                  :key="option.label" type="button"
                  class="translation-mode-option rounded-md px-3 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-50"
                  :class="translationEnabled && isLocalTranslation === option.local ? 'bg-blue-600 text-white' : 'text-white/65 hover:text-white'"
                  :aria-pressed="translationEnabled && isLocalTranslation === option.local"
                  :disabled="store.isRunning || !translationEnabled || savingKey"
                  @click="chooseTranslationMethod(option.local)">{{ option.label }}</button>
              </div>
              <p class="mt-1 text-xs text-white/65">雲端：需要 API 金鑰，速度快。本機：免費、不用上網，需要先下載模型。</p>
              <p v-if="!translationEnabled" class="mt-3 text-xs text-white/65" role="status">目前為「僅轉錄」，不會翻譯。</p>
              <div v-else-if="!isLocalTranslation" class="mt-3 space-y-2">
                <div class="text-xs text-white/65">
                  <span aria-hidden="true">雲端服務</span>
                  <UiSelect v-model="selectedBackend" :options="cloudOptions" aria-label="雲端服務"
                    :disabled="store.isRunning || !translationEnabled || savingKey"
                    button-class="mt-1 bg-white/5 border border-white/15 text-xs rounded-xl disabled:opacity-40" />
                </div>
                <template v-if="apiKeyField">
                  <p v-if="hasApiKey" class="flex items-center gap-2 text-xs text-white/75">
                    已設定 API 金鑰
                    <button type="button" class="text-indigo-300 disabled:opacity-50"
                      :disabled="store.isRunning || !translationEnabled || savingKey" @click="editingKey = true; keySaved = false">更換</button>
                  </p>
                  <form v-if="!hasApiKey || editingKey" class="flex flex-col gap-2 min-[480px]:flex-row" @submit.prevent="saveApiKey">
                    <input v-model="apiKeyInput" type="password" aria-label="API 金鑰" placeholder="輸入 API 金鑰" autocomplete="off"
                      :disabled="store.isRunning || !translationEnabled || savingKey"
                      class="min-w-0 flex-1 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-xs text-white disabled:opacity-50" />
                    <button type="submit" :disabled="store.isRunning || !translationEnabled || savingKey || !apiKeyInput.trim()"
                      class="rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50">
                      {{ savingKey ? (selectedBackend === 'gemini' ? '正在測試…' : '正在儲存…') : '儲存' }}
                    </button>
                    <button v-if="hasApiKey" type="button" :disabled="savingKey"
                      class="rounded-lg border border-white/15 px-3 py-2 text-xs text-white/75 disabled:opacity-50" @click="cancelKeyEdit">取消</button>
                  </form>
                  <p v-if="keyError" role="alert" class="text-xs text-red-300">{{ keyError }}</p>
                  <p v-if="keySaved" role="status" class="text-xs text-emerald-300">已儲存</p>
                  <a v-if="selectedBackend === 'gemini' && !hasApiKey" href="https://aistudio.google.com/apikey" target="_blank" rel="noopener" class="inline-block text-xs text-indigo-300 underline">取得 Gemini API 金鑰</a>
                </template>
              </div>
              <div v-else class="mt-3 flex flex-wrap items-center gap-2 text-xs" role="status">
                <template v-if="!llamaStore.selectedModelPath">
                  <span class="text-amber-300">尚未設定本機翻譯模型</span>
                  <button type="button" class="text-indigo-300 underline" @click="router.push('/local-translation')">一鍵設定本機翻譯</button>
                </template>
                <template v-else>
                  <span class="break-all text-white/75">使用 {{ localModelName }}</span>
                  <span class="text-white/65">{{ llamaStore.isServerReady ? '模型已就緒' : '按下啟動時會自動載入模型' }}</span>
                  <button type="button" class="text-indigo-300 underline" @click="router.push('/local-translation')">更換模型</button>
                </template>
              </div>
            </div>
            <div v-if="!interfaceMode.isSimple" class="mb-5">
              <button
                @click="showAdvancedConfig = !showAdvancedConfig"
                type="button"
                class="flex min-h-10 w-full items-center justify-between gap-2 rounded-xl border border-indigo-400/15 bg-indigo-400/5 px-3 text-left text-xs font-semibold text-indigo-300 transition hover:bg-white/15/10 md:min-h-0 md:w-auto md:border-0 md:bg-transparent md:px-0 md:text-indigo-400"
              >
                <span>{{ showAdvancedConfig ? '收起進階配置' : '展開進階配置（引擎與模型）' }}</span>
                <span v-if="!showAdvancedConfig" class="truncate text-xs text-white/60 md:hidden">{{ selectedTranscriptionEngine }}</span>
              </button>

              <Transition name="fade-slide">
                <div v-show="showAdvancedConfig" class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-3 p-3 bg-white/5 rounded-xl border border-white/5">
                  <div class="flex flex-col">
                    <label class="text-white/65 text-xs font-bold tracking-wider mb-1">ASR 運算模式</label>
                    <UiSelect
                      v-model="selectedAsrComputeBackend"
                      :options="asrComputeBackendOptions"
                      :disabled="store.isRunning || store.runtimeStatus?.profile === 'cpu'"
                      button-class="bg-white/5 border border-white/10 text-xs rounded-lg"
                    />
                  </div>
                  <!-- 轉錄引擎 -->
                  <div class="flex flex-col">
                    <label class="text-white/65 text-xs font-bold tracking-wider mb-1">轉錄引擎</label>
                    <UiSelect
                      v-model="selectedTranscriptionEngine"
                      :options="transcriptionEngineOptions"
                      :disabled="store.isRunning"
                      button-class="bg-white/5 border border-white/10 text-xs rounded-lg"
                    />
                  </div>

                  <!-- 模型選擇 -->
                  <div class="flex flex-col">
                    <label class="text-white/65 text-xs font-bold tracking-wider mb-1">模型選擇</label>
                    <UiSelect
                      v-if="selectedTranscriptionEngine === 'faster-whisper' || selectedTranscriptionEngine === 'simul-streaming' || selectedTranscriptionEngine === 'faster-whisper-simul'"
                      v-model="selectedWhisperModel"
                      :options="whisperModelOptions"
                      :disabled="store.isRunning"
                      button-class="bg-white/5 border border-white/10 text-xs rounded-lg"
                    />
                    <UiSelect
                      v-else-if="selectedTranscriptionEngine === 'qwen3-asr'"
                      v-model="selectedQwen3AsrModel"
                      :options="qwen3AsrModelOptions"
                      :disabled="store.isRunning"
                      button-class="bg-white/5 border border-white/10 text-xs rounded-lg"
                    />
                    <UiSelect
                      v-else-if="selectedTranscriptionEngine === 'sensevoice'"
                      v-model="selectedSenseVoiceModel"
                      :options="senseVoiceModelOptions"
                      :disabled="store.isRunning"
                      button-class="bg-white/5 border border-white/10 text-xs rounded-lg"
                    />
                    <UiSelect
                      v-else-if="selectedTranscriptionEngine === 'fun-asr-nano'"
                      v-model="selectedFunAsrModel"
                      :options="funAsrModelOptions"
                      :disabled="store.isRunning"
                      button-class="bg-white/5 border border-white/10 text-xs rounded-lg"
                    />
                    <UiSelect
                      v-else-if="selectedTranscriptionEngine === 'parakeet-ctc-ja'"
                      v-model="selectedParakeetModel"
                      :options="parakeetModelOptions"
                      :disabled="store.isRunning"
                      button-class="bg-white/5 border border-white/10 text-xs rounded-lg"
                    />
                    <UiSelect
                      v-else-if="selectedTranscriptionEngine === 'openai-api'"
                      v-model="selectedOpenAiTranscriptionModel"
                      :options="openAiTranscriptionModelOptions"
                      :disabled="store.isRunning"
                      button-class="bg-white/5 border border-white/10 text-xs rounded-lg"
                    />
                  </div>

                  <!-- 翻譯模型／後端 -->
                  <div class="flex flex-col md:col-span-3">
                    <label class="commercial-field-label">翻譯模型／後端</label>
                    <UiSelect
                      v-model="selectedBackend"
                      :options="backendOptions"
                      :disabled="store.isRunning || !translationEnabled"
                      button-class="bg-white/5 border border-white/10 text-xs rounded-lg disabled:opacity-40"
                    />
                    <p class="mt-1 text-xs text-cyan-200/75">翻譯開關開啟後，ASR 只負責把聲音轉成文字；這裡的模型才負責翻譯成目標語言。</p>
                  </div>
                </div>
              </Transition>
            </div>
</template>

<style scoped src="./home-shared.css"></style>
