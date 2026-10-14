<script setup lang="ts">
import { ref, computed } from 'vue';
import UiSelect, { type UiSelectOption } from '../UiSelect.vue';
import { simpleAsrModel, simpleAsrLanguages } from '../../utils/simpleAsr';
import { isModelLanguageCompatible, languageOptionsForModel } from '../../utils/asrCapabilities';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  router, interfaceMode, store, whisperModels, qwen3AsrModels, parakeetModels, allFunAsrModelOptions, selectedAsrModelId, selectedAsrCapability, selectedTranscriptionEngine, selectedAsrComputeBackend, selectedWhisperModel, selectedQwen3AsrModel, selectedSenseVoiceModel, selectedFunAsrModel, selectedParakeetModel, selectedOpenAiTranscriptionModel, selectedInputLanguage, selectedOutputLanguage, selectedBackend, translationEnabled, sameLanguageSelected, runtimeCapabilities, allowedTranscriptionEngines, allowedFasterWhisperModels, allowedQwen3AsrModels, allowedParakeetModels
} = useHomeContext();

const showAdvancedConfig = ref(true);

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

const parakeetModelOptions = computed<UiSelectOption[]>(() =>
  parakeetModels
    .filter((model) => allowedParakeetModels.value.includes(model.value))
    .map((model) => ({
      value: model.value,
      label: model.label,
      disabled: selectedAsrCapability.value?.language_mode !== 'fixed'
        && !isModelLanguageCompatible(
          runtimeCapabilities.value?.asr_model_capabilities,
          model.value,
          selectedInputLanguage.value,
        ),
    }))
);

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
              <div class="mb-1 flex items-center justify-between gap-3">
                <label class="commercial-field-label">翻譯模型／後端</label>
                <button type="button" class="text-xs text-indigo-300 hover:text-indigo-200" @click="router.push({ path: '/settings', query: { tab: 'translation' } })">翻譯詳細設定</button>
              </div>
              <UiSelect
                v-model="selectedBackend"
                :options="backendOptions"
                :disabled="store.isRunning || !translationEnabled"
                button-class="bg-white/5 border border-white/15 text-xs rounded-xl disabled:opacity-40"
              />
              <p class="mt-1 text-xs text-white/65">選擇翻譯服務或模型；API 金鑰等選項可在翻譯詳細設定中調整。</p>
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
