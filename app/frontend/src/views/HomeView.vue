<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { useTranslationStore } from '../stores/translation';
import { useLlamaStore } from '../stores/llama';
import { useModelDownloadStore } from '../stores/modelDownload';
import { translationApi, configApi, runtimeApi, serverApi, systemApi, type AppUpdateStatus, type AudioSource, type AudioDevice, type Config, type FfmpegCheckResult, type ModelComputeBackend, type ModelEngine } from '../services/api';
import UiSelect, { type UiSelectOption } from '../components/UiSelect.vue';
import { useAppSyncEvents } from '../composables/useAppSyncEvents';
import {
  coerceLanguageForModel,
  isModelLanguageCompatible,
  languageOptionsForModel,
} from '../utils/asrCapabilities';

const router = useRouter();
const store = useTranslationStore();
const llamaStore = useLlamaStore();
const modelDownloadStore = useModelDownloadStore();

// 公開端口（分享用）
const publicPort = ref(8765);
const activeCopyPath = ref<string | null>(null);
const subtitleSharingEnabled = ref(true);
const isUpdatingSubtitleSharing = ref(false);
const ffmpegStatus = ref<FfmpegCheckResult | null>(null);
const ffmpegWarningDismissed = ref(false);
const availableAppUpdate = ref<AppUpdateStatus | null>(null);
const appUpdateNoticeDismissed = ref(false);
const APP_UPDATE_CHECKED_KEY = 'stream-translator-app-update-checked';

const showFfmpegWarning = computed(() => {
  return !!ffmpegStatus.value && !ffmpegStatus.value.available && !ffmpegWarningDismissed.value;
});

async function checkAppUpdateOnceAfterStartup() {
  if (sessionStorage.getItem(APP_UPDATE_CHECKED_KEY) === '1') return;
  sessionStorage.setItem(APP_UPDATE_CHECKED_KEY, '1');
  try {
    const status = await runtimeApi.checkAppUpdate();
    if (status.status === 'available' && status.available) availableAppUpdate.value = status;
  } catch (error) {
    // The startup check is informational; manual checking remains available.
    console.warn('[HomeView] automatic update check failed:', error);
  }
}

function openAppUpdateSettings() {
  router.push({ path: '/settings', query: { tab: 'general' } });
}

interface PyQtClipboardBridge {
  copyToClipboard?: (text: string, callback?: (result: boolean) => void) => void;
  chooseLocalFile?: (callback: (path: string) => void) => void;
  updateNativeRecordingState?: (isRecording: boolean) => void;
}

type WindowWithPyQt = Window & {
  pyqt?: PyQtClipboardBridge;
};

async function fetchPublicPort() {
  try {
    const data = await serverApi.getInfo();
    if (data.public_port) publicPort.value = data.public_port;
    if (typeof data.enable_subtitle_sharing === 'boolean') {
      subtitleSharingEnabled.value = data.enable_subtitle_sharing;
    }
  } catch {}
}

async function checkSystemDependencies() {
  try {
    const result = await systemApi.checkDependencies();
    ffmpegStatus.value = result.ffmpeg;
    if (!result.ffmpeg.available) {
      addLog('⚠️ 未偵測到 ffmpeg，部分音訊處理功能可能無法正常運作');
    }
  } catch {}
}
function getPublicBase() {
  const host = location.hostname;
  return `http://${host}:${publicPort.value}`;
}

async function writeTextToClipboard(text: string): Promise<boolean> {
  const win = window as WindowWithPyQt;

  // 1) 桌面版 bridge（PyQt QWebChannel）
  //    QWebChannel slot 用 callback 方式回傳結果，需要包成 Promise
  if (win.pyqt?.copyToClipboard) {
    try {
      const result = await new Promise<boolean>((resolve) => {
        win.pyqt!.copyToClipboard!(text, (ok: boolean) => resolve(ok));
      });
      if (result) return true;
    } catch (error) {
      console.warn('[copyLink] pyqt.copyToClipboard failed:', error);
    }
  }

  // 2) 標準 Clipboard API（需要 HTTPS 或 localhost）
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (error) {
      console.warn('[copyLink] navigator.clipboard.writeText failed:', error);
    }
  }

  // 3) 備援：execCommand('copy')
  try {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.setAttribute('readonly', '');
    textArea.style.position = 'fixed';
    textArea.style.left = '-9999px';
    textArea.style.top = '0';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    const successful = document.execCommand('copy');
    document.body.removeChild(textArea);
    return successful;
  } catch (error) {
    console.warn('[copyLink] execCommand fallback failed:', error);
    return false;
  }
}

async function copyLink(path: string) {
  if (!subtitleSharingEnabled.value) {
    store.errorMessage = '字幕分享功能目前已關閉';
    return;
  }

  const fullUrl = `${getPublicBase()}${path}`;
  const copied = await writeTextToClipboard(fullUrl);

  if (copied) {
    activeCopyPath.value = path;
    store.statusMessage = '已複製分享連結';
    setTimeout(() => {
      activeCopyPath.value = null;
      if (store.statusMessage === '已複製分享連結') {
        store.statusMessage = '';
      }
    }, 2000);
    return;
  }

  store.errorMessage = '複製失敗，請手動複製連結';
  window.prompt('請複製此連結：', fullUrl);
}

async function toggleSubtitleSharing() {
  if (isUpdatingSubtitleSharing.value) return;

  isUpdatingSubtitleSharing.value = true;
  const nextValue = !subtitleSharingEnabled.value;

  try {
    const currentServerConfig = store.config.server || {};
    await configApi.updateSection('server', {
      ...currentServerConfig,
      public_port: publicPort.value,
      enable_subtitle_sharing: nextValue,
    });

    await store.loadConfig();
    subtitleSharingEnabled.value = !!store.config.server?.enable_subtitle_sharing;
    addLog(`字幕分享已${subtitleSharingEnabled.value ? '啟用' : '關閉'}`);
    store.statusMessage = `字幕分享已${subtitleSharingEnabled.value ? '啟用' : '關閉'}`;
    setTimeout(() => {
      if (store.statusMessage === `字幕分享已${subtitleSharingEnabled.value ? '啟用' : '關閉'}`) {
        store.statusMessage = '';
      }
    }, 3000);
  } catch (error: any) {
    store.errorMessage = `更新字幕分享設定失敗: ${error.message}`;
    addLog(`❌ 更新字幕分享設定失敗: ${error.message}`);
  } finally {
    isUpdatingSubtitleSharing.value = false;
  }
}

// 基本控制
const urlInput = ref('');
const urlInputRef = ref<HTMLInputElement | null>(null);
const localFileInputRef = ref<HTMLInputElement | null>(null);
const localMediaAccept = '.mp4,.mkv,.webm,.avi,.mov,.mp3,.wav,.m4a,.flac,.ogg,.aac,.wma';
const isLoading = ref(false);
const isPreparingAsrModel = ref(false);
const showAdvancedConfig = ref(true);

watch(
  () => store.isRunning,
  (isRunning) => {
    (window as WindowWithPyQt).pyqt?.updateNativeRecordingState?.(isRunning);
  },
  { immediate: true }
);

// 音訊來源選擇
const audioSource = ref<AudioSource>('url');
const availableDevices = ref<AudioDevice[]>([]);
const selectedDeviceIndex = ref<number | null>(null);
const isLoadingDevices = ref(false);

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

// 模型選擇
const whisperModels = ['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3', 'large-v3-turbo'];
const qwen3AsrModels = [
  { value: 'Qwen/Qwen3-ASR-1.7B', label: 'Qwen3-ASR-1.7B (推薦)' },
  { value: 'Qwen/Qwen3-ASR-0.6B', label: 'Qwen3-ASR-0.6B (更快)' },
  { value: 'jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame', label: 'Qwen3-ASR-1.7B-JA-Anime' }
];
const legacyQwen3JaModel = 'neosophie/Qwen3-ASR-1.7B-JA';
const qwen3AnimeModel = 'jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame';
const parakeetModels = [
  { value: 'nvidia/parakeet-tdt-0.6b-v3', label: 'Parakeet TDT 0.6B v3（CPU INT8・25 語言）' },
  { value: 'nvidia/parakeet-tdt_ctc-0.6b-ja', label: 'NVIDIA Parakeet 0.6B（日文）' },
  { value: 'nvidia/parakeet-tdt_ctc-1.1b', label: 'NVIDIA Parakeet 1.1B（英文）' },
  { value: 'grider-transwithai/parakeet-ctc-1.1b-ja', label: 'parakeet-ctc-1.1b-ja（日文）' }
];
const parakeetLanguageForModel = (modelId: string) =>
  modelId === 'nvidia/parakeet-tdt-0.6b-v3'
    ? 'auto'
    : modelId === 'nvidia/parakeet-tdt_ctc-1.1b' ? 'en' : 'ja';
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
const allFunAsrModelOptions: UiSelectOption[] = [
  { value: 'FunAudioLLM/Fun-ASR-Nano-2512', label: 'Fun-ASR Nano（中／英／日）' },
  { value: 'FunAudioLLM/Fun-ASR-MLT-Nano-2512', label: 'Fun-ASR MLT Nano（31 語言）' }
];
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

const selectedAsrModelId = computed(() => {
  if (selectedTranscriptionEngine.value === 'qwen3-asr') return selectedQwen3AsrModel.value;
  if (selectedTranscriptionEngine.value === 'sensevoice') return selectedSenseVoiceModel.value;
  if (selectedTranscriptionEngine.value === 'fun-asr-nano') return selectedFunAsrModel.value;
  if (selectedTranscriptionEngine.value === 'parakeet-ctc-ja') return selectedParakeetModel.value;
  return selectedWhisperModel.value;
});
const selectedAsrCapability = computed(() =>
  runtimeCapabilities.value?.asr_model_capabilities?.find(
    (item) => item.model_id === selectedAsrModelId.value
  )
);
const inputLanguageOptions = computed<UiSelectOption[]>(() =>
  languageOptionsForModel(
    runtimeCapabilities.value?.asr_model_capabilities,
    selectedAsrModelId.value,
  )
);
const isInputLanguageLocked = computed(() => selectedAsrCapability.value?.language_mode === 'fixed');

const outputLanguageOptions = computed<UiSelectOption[]>(() =>
  outputLanguages.map((lang) => ({ value: lang.value, label: lang.label }))
);

const backendOptions = computed<UiSelectOption[]>(() => {
  const base: UiSelectOption[] = [
    { value: 'none', label: '不翻譯' },
    { value: 'gpt', label: 'OpenAI GPT' },
    { value: 'gemini', label: 'Google Gemini' },
    { value: 'llama', label: '🦙 Llama (本地)' }
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

const llamaPresetOptions = computed<UiSelectOption[]>(() => {
  const options: UiSelectOption[] = [{ value: '', label: '-- 自訂參數 (未保存) --' }];

  const system = Object.keys(llamaStore.systemPresets || {}).map((name) => ({
    value: name,
    label: name,
    group: '系統預設'
  }));

  const custom = Object.keys(llamaStore.customPresets || {}).map((name) => ({
    value: `custom:${name}`,
    label: `📦 ${name}`,
    group: '我的配置'
  }));

  return [...options, ...system, ...custom];
});

// 選擇的值
const selectedTranscriptionEngine = ref('faster-whisper');  // 🆕 新增: 轉錄引擎選擇
const selectedAsrComputeBackend = ref('auto');
const selectedWhisperModel = ref('base');
const selectedQwen3AsrModel = ref('Qwen/Qwen3-ASR-1.7B');  // 🆕 新增: Qwen3-ASR 模型
const selectedSenseVoiceModel = ref('iic/SenseVoiceSmall');
const selectedFunAsrModel = ref('FunAudioLLM/Fun-ASR-Nano-2512');
const selectedParakeetModel = ref('nvidia/parakeet-tdt_ctc-0.6b-ja');
const selectedInputLanguage = ref('auto');
const selectedOutputLanguage = ref('Traditional Chinese');
const selectedBackend = ref('gpt');
const translationEnabled = ref(true);  // 🔧 新增: 翻譯開關

const localLlmModelName = computed(() => {
  const value = llamaStore.currentModel || llamaStore.selectedModelPath;
  if (!value) return '尚未選擇模型';
  return value.split(/[\\/]/).pop()?.replace(/\.gguf$/i, '') || value;
});
const selectedDownloadEngine = computed<ModelEngine | null>(() => {
  if (['faster-whisper', 'simul-streaming', 'faster-whisper-simul'].includes(selectedTranscriptionEngine.value)) return 'faster-whisper';
  if (['qwen3-asr', 'sensevoice', 'fun-asr-nano', 'parakeet-ctc-ja'].includes(selectedTranscriptionEngine.value)) {
    return selectedTranscriptionEngine.value as ModelEngine;
  }
  return null;
});
const selectedModelComputeBackend = computed<ModelComputeBackend>(() =>
  store.runtimeStatus?.effective_asr_compute_backend === 'cpu' || selectedAsrComputeBackend.value === 'cpu' ? 'cpu' : 'gpu'
);
const selectedAsrDownloadTask = computed(() => selectedDownloadEngine.value
  ? modelDownloadStore.getTask(selectedDownloadEngine.value, selectedAsrModelId.value, selectedModelComputeBackend.value)
  : undefined
);
const selectedAsrModelDownloaded = computed(() => !selectedDownloadEngine.value || modelDownloadStore.isDownloaded(
  selectedDownloadEngine.value,
  selectedAsrModelId.value,
  selectedModelComputeBackend.value,
));

const localLlmStatusLabel = computed(() => {
  if (llamaStore.isLoading) return llamaStore.localLlmEnabled ? '正在啟動' : '正在停止';
  if (llamaStore.isServerReady) return '服務已就緒';
  if (llamaStore.isServerRunning) return '模型載入中';
  if (llamaStore.localLlmEnabled && llamaStore.serverStatus.last_error) return '啟動失敗';
  return llamaStore.localLlmEnabled ? '等待啟動' : '目前關閉';
});

const localLlmStatusDescription = computed(() => {
  if (!llamaStore.selectedModelPath) return '請先到「LLM 模型管理」選擇 GGUF 模型';
  if (llamaStore.isServerReady) return '即時轉譯會使用此模型進行本地翻譯';
  if (llamaStore.isLoading || llamaStore.isServerRunning) return '正在載入模型，完成後即可開始轉譯';
  if (llamaStore.localLlmEnabled && llamaStore.serverStatus.last_error) return llamaStore.serverStatus.last_error;
  return '開啟後會啟動 llama.cpp，關閉則不使用本地模型';
});

// 自動保存 debounce timer
const runtimeCapabilities = computed(() => store.runtimeStatus?.asr_capabilities || store.runtimeStatus?.capabilities || null);
const allowedLocalAsrEngines = computed<string[]>(() =>
  runtimeCapabilities.value?.local_asr_engines?.length
    ? runtimeCapabilities.value.local_asr_engines
    : ['faster-whisper', 'simul-streaming', 'faster-whisper-simul', 'qwen3-asr', 'sensevoice', 'fun-asr-nano', 'parakeet-ctc-ja']
);
const allowedRemoteAsrEngines = computed<string[]>(() =>
  runtimeCapabilities.value?.remote_asr_engines?.length
    ? runtimeCapabilities.value.remote_asr_engines
    : ['openai-api']
);
const allowedTranscriptionEngines = computed<string[]>(() => [
  ...allowedLocalAsrEngines.value,
  ...allowedRemoteAsrEngines.value,
]);
const transcriptionEngineOptions = computed<UiSelectOption[]>(() =>
  allTranscriptionEngineOptions.filter((option) =>
    allowedTranscriptionEngines.value.includes(String(option.value))
  )
);
const allowedFasterWhisperModels = computed<string[]>(() =>
  runtimeCapabilities.value?.faster_whisper_model_ids?.length
    ? runtimeCapabilities.value.faster_whisper_model_ids
    : whisperModels
);
const allowedQwen3AsrModels = computed<string[]>(() =>
  runtimeCapabilities.value?.qwen3_asr_model_ids?.length
    ? runtimeCapabilities.value.qwen3_asr_model_ids
    : qwen3AsrModels.map((model) => model.value)
);
const allowedSenseVoiceModels = computed<string[]>(() =>
  runtimeCapabilities.value?.sensevoice_model_ids?.length
    ? runtimeCapabilities.value.sensevoice_model_ids
    : ['iic/SenseVoiceSmall']
);
const allowedFunAsrModels = computed<string[]>(() =>
  runtimeCapabilities.value?.fun_asr_model_ids?.length
    ? runtimeCapabilities.value.fun_asr_model_ids
    : allFunAsrModelOptions.map((model) => String(model.value))
);
const allowedParakeetModels = computed<string[]>(() =>
  runtimeCapabilities.value?.parakeet_model_ids?.length
    ? runtimeCapabilities.value.parakeet_model_ids
    : parakeetModels.map((model) => model.value)
);

function coerceRuntimeLimitedSelections() {
  if (!allowedTranscriptionEngines.value.includes(selectedTranscriptionEngine.value)) {
    selectedTranscriptionEngine.value = allowedTranscriptionEngines.value.includes('qwen3-asr')
      ? 'qwen3-asr'
      : allowedTranscriptionEngines.value[0] || 'openai-api';
  }
  if (!allowedFasterWhisperModels.value.includes(selectedWhisperModel.value)) {
    selectedWhisperModel.value = allowedFasterWhisperModels.value[0] || 'small';
  }
  if (selectedQwen3AsrModel.value === legacyQwen3JaModel) {
    selectedQwen3AsrModel.value = qwen3AnimeModel;
  }
  if (!allowedQwen3AsrModels.value.includes(selectedQwen3AsrModel.value)) {
    selectedQwen3AsrModel.value = allowedQwen3AsrModels.value[0] || 'Qwen/Qwen3-ASR-0.6B';
  }
  if (!allowedSenseVoiceModels.value.includes(selectedSenseVoiceModel.value)) {
    selectedSenseVoiceModel.value = allowedSenseVoiceModels.value[0] || 'iic/SenseVoiceSmall';
  }
  if (!allowedFunAsrModels.value.includes(selectedFunAsrModel.value)) {
    selectedFunAsrModel.value = allowedFunAsrModels.value[0] || 'FunAudioLLM/Fun-ASR-Nano-2512';
  }
  if (!allowedParakeetModels.value.includes(selectedParakeetModel.value)) {
    selectedParakeetModel.value = allowedParakeetModels.value[0] || 'nvidia/parakeet-tdt_ctc-0.6b-ja';
  }
}

let _homeAutoSaveTimer: ReturnType<typeof setTimeout> | null = null;
let _homeConfigSyncTimer: ReturnType<typeof setInterval> | null = null;
let _homeRunningSyncTimer: ReturnType<typeof setInterval> | null = null;
const isApplyingExternalConfig = ref(false);
const lastAppliedHomeConfigSnapshot = ref('');

function getTranscriptionEngineFromConfig(cfg: Config): string {
  if (cfg.transcription?.use_qwen3_asr) return 'qwen3-asr';
  if (cfg.transcription?.use_fun_asr) return 'fun-asr-nano';
  if (cfg.transcription?.use_sensevoice_asr) return 'sensevoice';
  if (cfg.transcription?.use_nemo_asr) return 'parakeet-ctc-ja';
  if (cfg.transcription?.use_openai_transcription_api) return 'openai-api';
  if (cfg.transcription?.use_faster_whisper && cfg.transcription?.use_simul_streaming) return 'faster-whisper-simul';
  if (cfg.transcription?.use_simul_streaming) return 'simul-streaming';
  return 'faster-whisper';
}

function normalizeInputLanguage(language: string | null | undefined): string {
  const normalized = String(language || 'auto').trim().toLowerCase();
  if (!normalized) return 'auto';
  if (normalized === 'zh') return 'zh-tw';
  if (normalized === 'zh-hant' || normalized === 'traditional chinese' || normalized === '繁體中文') return 'zh-tw';
  if (normalized === 'zh-hans' || normalized === 'simplified chinese' || normalized === '簡體中文') return 'zh-cn';
  return normalized;
}

function buildHomeConfigSnapshotFromConfig(cfg: Config): string {
  return JSON.stringify({
    urlInput: cfg.input?.url || '',
    audioSource: cfg.input?.audio_source || 'url',
    selectedDeviceIndex: cfg.input?.device_index ?? null,
    selectedTranscriptionEngine: getTranscriptionEngineFromConfig(cfg),
    selectedAsrComputeBackend: cfg.transcription?.asr_compute_backend || 'auto',
    selectedWhisperModel: cfg.transcription?.model || 'base',
    selectedQwen3AsrModel: cfg.transcription?.qwen3_asr_model || 'Qwen/Qwen3-ASR-1.7B',
    selectedSenseVoiceModel: cfg.transcription?.sensevoice_model || 'iic/SenseVoiceSmall',
    selectedFunAsrModel: cfg.transcription?.fun_asr_model || 'FunAudioLLM/Fun-ASR-Nano-2512',
    selectedParakeetModel: cfg.transcription?.nemo_asr_model || 'nvidia/parakeet-tdt_ctc-0.6b-ja',
    selectedInputLanguage: normalizeInputLanguage(cfg.transcription?.language),
    selectedOutputLanguage: cfg.translation?.target_language || 'Traditional Chinese',
    selectedBackend: cfg.translation?.backend || 'gpt',
    translationEnabled: cfg.translation?.backend !== 'none',
    publicPort: cfg.server?.public_port ?? 8765,
    subtitleSharingEnabled: cfg.server?.enable_subtitle_sharing !== false,
  });
}

function buildHomeConfigSnapshotFromRefs(): string {
  return JSON.stringify({
    urlInput: urlInput.value,
    audioSource: audioSource.value,
    selectedDeviceIndex: selectedDeviceIndex.value,
    selectedTranscriptionEngine: selectedTranscriptionEngine.value,
    selectedAsrComputeBackend: selectedAsrComputeBackend.value,
    selectedWhisperModel: selectedWhisperModel.value,
    selectedQwen3AsrModel: selectedQwen3AsrModel.value,
    selectedSenseVoiceModel: selectedSenseVoiceModel.value,
    selectedFunAsrModel: selectedFunAsrModel.value,
    selectedParakeetModel: selectedParakeetModel.value,
    selectedInputLanguage: selectedInputLanguage.value,
    selectedOutputLanguage: selectedOutputLanguage.value,
    selectedBackend: selectedBackend.value,
    translationEnabled: translationEnabled.value,
    publicPort: publicPort.value,
    subtitleSharingEnabled: subtitleSharingEnabled.value,
  });
}

/** 將 HomeView UI ref 的值逆向映射並批次寫回 config.yaml */
async function saveHomeConfigToBackend() {
  try {
    const engine = selectedTranscriptionEngine.value;
    const computeBackendChanged = store.config.transcription?.asr_compute_backend !== selectedAsrComputeBackend.value;
    const transcriptionPatch = {
      ...store.config.transcription,
      asr_compute_backend: selectedAsrComputeBackend.value,
      model: selectedWhisperModel.value,
      qwen3_asr_model: selectedQwen3AsrModel.value,
      sensevoice_model: selectedSenseVoiceModel.value,
      fun_asr_model: selectedFunAsrModel.value,
      nemo_asr_model: selectedParakeetModel.value,
      nemo_asr_dtype: store.config.transcription?.nemo_asr_dtype || 'bfloat16',
      language: engine === 'parakeet-ctc-ja'
        ? parakeetLanguageForModel(selectedParakeetModel.value)
        : selectedInputLanguage.value,
      backend: engine,
      use_qwen3_asr: engine === 'qwen3-asr',
      use_sensevoice_asr: engine === 'sensevoice',
      use_fun_asr: engine === 'fun-asr-nano',
      use_nemo_asr: engine === 'parakeet-ctc-ja',
      use_openai_transcription_api: engine === 'openai-api',
      use_faster_whisper: engine === 'faster-whisper' || engine === 'faster-whisper-simul',
      use_simul_streaming: engine === 'faster-whisper-simul' || engine === 'simul-streaming',
    };
    const inputPatch = {
      ...store.config.input,
      url: urlInput.value,
      audio_source: audioSource.value,
      device_index: selectedDeviceIndex.value,
    };
    const translationPatch = {
      ...store.config.translation,
      backend: translationEnabled.value ? selectedBackend.value : 'none',
      target_language: selectedOutputLanguage.value,
    };
    const updatedConfig = await configApi.updateConfig({
      input: inputPatch,
      transcription: transcriptionPatch,
      translation: translationPatch,
    });
    store.applyConfigSections({
      input: updatedConfig.input,
      transcription: updatedConfig.transcription,
      translation: updatedConfig.translation,
    });
    if (computeBackendChanged) {
      await store.loadRuntimeStatus();
      coerceRuntimeLimitedSelections();
    }
    // 更新本地 store 快照
    lastAppliedHomeConfigSnapshot.value = buildHomeConfigSnapshotFromConfig(store.config);
  } catch (e) {
    console.warn('[HomeView] 自動保存 config 失敗:', e);
  }
}

function debouncedSaveHomeConfig() {
  if (_homeAutoSaveTimer !== null) clearTimeout(_homeAutoSaveTimer);
  _homeAutoSaveTimer = setTimeout(() => {
    _homeAutoSaveTimer = null;
    saveHomeConfigToBackend();
  }, 800);
}

// 配置狀態檢查
interface ConfigWarning {
  level: 'warning' | 'error';
  message: string;
  page?: string;
  actionLabel?: string;
}

const configWarnings = computed<ConfigWarning[]>(() => {
  const warnings: ConfigWarning[] = [];
  const config = store.config;
  if (!config) return warnings;
  
  const requiresUrlInput = audioSource.value === 'url' || audioSource.value === 'file';
  if (requiresUrlInput && !(urlInput.value || '').trim()) {
    warnings.push({
      level: 'warning',
      message: audioSource.value === 'url' ? '未設定 YouTube Live／Twitch／X／TikTok 直播網址' : '未選擇檔案或未輸入檔案路徑',
      page: 'home-input',
      actionLabel: audioSource.value === 'url' ? '前往直播網址' : '選擇檔案',
    });
  }

  const requiresDeviceSelection = audioSource.value === 'microphone' || audioSource.value === 'system_audio';
  if (requiresDeviceSelection && (availableDevices.value || []).length === 0 && isLoadingDevices.value === false) {
    warnings.push({
      level: 'warning',
      message: '設備列表尚未載入，將使用系統預設設備'
    });
  }

  if (config.transcription?.use_openai_transcription_api && !config.transcription?.openai_api_key) {
    warnings.push({
      level: 'error',
      message: 'OpenAI ASR API Key 未設定',
      page: 'transcription'
    });
  }

  if (translationEnabled.value && selectedBackend.value === 'gpt' && !config.translation?.openai_api_key) {
    warnings.push({
      level: 'error',
      message: 'OpenAI API Key 未設定',
      page: 'translation'
    });
  }
  
  if (translationEnabled.value && selectedBackend.value === 'gemini' && !config.translation?.google_api_key) {
    warnings.push({
      level: 'error',
      message: 'Google API Key 未設定',
      page: 'translation'
    });
  }
  
  return warnings;
});

const hasErrors = computed(() => (configWarnings.value || []).some(w => w.level === 'error'));
const isConfigReady = computed(() => {
  if (hasErrors.value) return false;

  if (audioSource.value === 'url' || audioSource.value === 'file') {
    return !!(urlInput.value || '').trim();
  }

  if (audioSource.value === 'microphone' || audioSource.value === 'system_audio') {
    return true; // null = 使用系統預設設備，視為有效
  }

  return false;
});

// 日誌
const logs = ref<string[]>([]);
const logContainer = ref<HTMLElement | null>(null);

function addLog(message: string) {
  const timestamp = new Date().toLocaleTimeString();
  logs.value.push(`[${timestamp}] ${message}`);
  // 自動捲動到底部
  if (logContainer.value) {
    setTimeout(() => {
      if (logContainer.value) {
        logContainer.value.scrollTop = logContainer.value.scrollHeight;
      }
    }, 10);
  }
}

// 載入設備列表
async function loadDevices() {
  if (audioSource.value !== 'microphone' && audioSource.value !== 'system_audio') {
    return;
  }
  
  isLoadingDevices.value = true;
  try {
    const result = await translationApi.getDevices();
    if (audioSource.value === 'microphone') {
      availableDevices.value = result.devices.microphones;
    } else if (audioSource.value === 'system_audio') {
      availableDevices.value = result.devices.system_audio;
    }
    addLog(`已載入 ${availableDevices.value.length} 個設備`);
    // 自動選取預設設備，如果目前未選擇
    if (selectedDeviceIndex.value === null && !isApplyingExternalConfig.value) {
      const defaultDevice = availableDevices.value.find((d) => d.is_default);
      if (defaultDevice) {
        selectedDeviceIndex.value = defaultDevice.index;
        addLog(`已自動選取預設設備: ${defaultDevice.name}`);
      }
    }
  } catch (error: any) {
    addLog(`❌ 載入設備失敗: ${error.message}`);
  } finally {
    isLoadingDevices.value = false;
  }
}

// 當音訊來源改變時
async function onAudioSourceChange() {
  selectedDeviceIndex.value = null;
  availableDevices.value = [];
  
  if (audioSource.value === 'microphone' || audioSource.value === 'system_audio') {
    await loadDevices();
  }
}

/** 將後端 config 對應至 HomeView 各 ref（僅首次載入時呼叫） */
async function applyConfigToRefs(cfg: Config) {
  isApplyingExternalConfig.value = true;
  try {
    urlInput.value = cfg.input?.url || '';
    audioSource.value = cfg.input?.audio_source || 'url';
    selectedDeviceIndex.value = cfg.input?.device_index ?? null;
    selectedAsrComputeBackend.value = cfg.transcription?.asr_compute_backend || 'auto';
    selectedWhisperModel.value = cfg.transcription?.model || 'base';
    selectedQwen3AsrModel.value = cfg.transcription?.qwen3_asr_model || 'Qwen/Qwen3-ASR-1.7B';
    selectedSenseVoiceModel.value = cfg.transcription?.sensevoice_model || 'iic/SenseVoiceSmall';
    selectedFunAsrModel.value = cfg.transcription?.fun_asr_model || 'FunAudioLLM/Fun-ASR-Nano-2512';
    selectedParakeetModel.value = cfg.transcription?.nemo_asr_model || 'nvidia/parakeet-tdt_ctc-0.6b-ja';
    selectedTranscriptionEngine.value = getTranscriptionEngineFromConfig(cfg);
    coerceRuntimeLimitedSelections();
    selectedInputLanguage.value = normalizeInputLanguage(cfg.transcription?.language);
    selectedOutputLanguage.value = cfg.translation?.target_language || 'Traditional Chinese';
    selectedBackend.value = cfg.translation?.backend || 'gpt';
    translationEnabled.value = cfg.translation?.backend !== 'none';
    subtitleSharingEnabled.value = cfg.server?.enable_subtitle_sharing !== false;
    publicPort.value = cfg.server?.public_port ?? publicPort.value;

    if (audioSource.value === 'microphone' || audioSource.value === 'system_audio') {
      await loadDevices();
    } else {
      availableDevices.value = [];
    }

    lastAppliedHomeConfigSnapshot.value = buildHomeConfigSnapshotFromConfig(cfg);
  } finally {
    nextTick(() => {
      isApplyingExternalConfig.value = false;
    });
  }
}

async function syncHomeStateFromBackend(force = false, syncLlama = false) {
  if (!force && _homeAutoSaveTimer !== null) {
    return;
  }

  await store.loadConfig();
  if (force || !store.runtimeStatus) {
    try {
      await store.loadRuntimeStatus();
    } catch (error) {
      console.warn('[HomeView] runtime status refresh failed:', error);
    }
  }
  const incomingSnapshot = buildHomeConfigSnapshotFromConfig(store.config);

  if (!force && incomingSnapshot === lastAppliedHomeConfigSnapshot.value) {
    return;
  }

  if (!force && buildHomeConfigSnapshotFromRefs() !== lastAppliedHomeConfigSnapshot.value) {
    return;
  }

  await applyConfigToRefs(store.config);

  if (syncLlama) {
    try {
      await llamaStore.loadConfig();
      await llamaStore.refreshServerStatus();
    } catch (error) {
      console.warn('[HomeView] 同步 Llama 狀態失敗:', error);
    }
  }
}

useAppSyncEvents({
  onConfigUpdated: async (payload) => {
    if (payload.config) store.applyConfigSnapshot(payload.config);
    else await store.loadConfig(true);
    await syncHomeStateFromBackend(true, payload.section === '*' || payload.section === 'llama');
  },
  onConfigReset: async (payload) => {
    if (payload.config) store.applyConfigSnapshot(payload.config);
    else await store.loadConfig(true);
    await syncHomeStateFromBackend(true, true);
  },
  onConfigImported: async (payload) => {
    if (payload.config) store.applyConfigSnapshot(payload.config);
    else await store.loadConfig(true);
    await syncHomeStateFromBackend(true, true);
  },
  onTranslationStarted: async () => {
    await store.syncRunningState();
  },
  onTranslationStopped: async () => {
    store.clearStatus();
    await store.syncRunningState();
  }
});

// 監聽並將後端狀態及錯誤日誌輸出至介面日誌面板
watch(() => store.statusMessage, (newVal) => {
  if (newVal && newVal !== '已複製分享連結' && !newVal.startsWith('字幕分享已')) {
    addLog(`ℹ️ ${newVal}`);
  }
});

watch(() => store.errorMessage, (newVal) => {
  if (newVal) {
    addLog(`❌ ${newVal}`);
  }
});

watch(translationEnabled, (newVal) => {
  if (newVal && selectedBackend.value === 'none') {
    selectedBackend.value = 'gpt';
  }
});

watch(selectedBackend, (newVal) => {
  if (newVal === 'none') {
    translationEnabled.value = false;
  } else {
    translationEnabled.value = true;
  }
});

watch(runtimeCapabilities, () => {
  coerceRuntimeLimitedSelections();
});

watch(
  [selectedAsrModelId, () => runtimeCapabilities.value?.asr_model_capabilities],
  () => {
    selectedInputLanguage.value = coerceLanguageForModel(
      runtimeCapabilities.value?.asr_model_capabilities,
      selectedAsrModelId.value,
      selectedInputLanguage.value,
    );
  },
  { immediate: true, flush: 'post' },
);

function stopHomePolling() {
  if (_homeConfigSyncTimer !== null) {
    clearInterval(_homeConfigSyncTimer);
    _homeConfigSyncTimer = null;
  }
  if (_homeRunningSyncTimer !== null) {
    clearInterval(_homeRunningSyncTimer);
    _homeRunningSyncTimer = null;
  }
}

function startHomePolling() {
  if (document.hidden) return;
  if (_homeConfigSyncTimer === null) {
    _homeConfigSyncTimer = setInterval(() => {
      void syncHomeStateFromBackend();
    }, 2000);
  }
  if (_homeRunningSyncTimer === null) {
    _homeRunningSyncTimer = setInterval(() => {
      void store.syncRunningState();
    }, 1500);
  }
}

function handleHomeVisibilityChange() {
  if (document.hidden) {
    stopHomePolling();
    return;
  }
  void syncHomeStateFromBackend();
  void store.syncRunningState();
  startHomePolling();
}

onMounted(async () => {
  // Check once per application/browser session. Never download or apply here.
  void checkAppUpdateOnceAfterStartup();
  // 載入公開端口資訊
  await fetchPublicPort();
  await checkSystemDependencies();
  await modelDownloadStore.refreshAll();
  // Llama 初始化在背景執行，不阻塞頁面顯示
  llamaStore.initialize().catch((e: any) => {
    console.warn('[HomeView] llamaStore 初始化失敗:', e);
  });

  if (!store.isConfigInitialized) {
    // 首次開啟：從後端載入配置並套用
    await syncHomeStateFromBackend(true, true);
    store.isConfigInitialized = true;
    addLog('應用程式已初始化');
  } else {
    await syncHomeStateFromBackend(true, true);
    addLog('已同步最新設定');
  }

  await store.syncRunningState();
  (window as WindowWithPyQt).pyqt?.updateNativeRecordingState?.(store.isRunning);

  // 初始化完成後，延後建立 watch 避免初始化誤觸發自動保存
  await nextTick();
  watch(
    [
      urlInput,
      audioSource,
      selectedDeviceIndex,
      selectedAsrComputeBackend,
      selectedTranscriptionEngine,
      selectedWhisperModel,
      selectedQwen3AsrModel,
      selectedSenseVoiceModel,
      selectedFunAsrModel,
      selectedParakeetModel,
      selectedInputLanguage,
      selectedOutputLanguage,
      selectedBackend,
      translationEnabled,
    ],
    () => {
      if (isApplyingExternalConfig.value) return;
      debouncedSaveHomeConfig();
    },
    { flush: 'post' }
  );

  document.addEventListener('visibilitychange', handleHomeVisibilityChange);
  startHomePolling();
});

onBeforeUnmount(() => {
  // 清除未完成的 debounce timer
  if (_homeAutoSaveTimer !== null) {
    clearTimeout(_homeAutoSaveTimer);
    _homeAutoSaveTimer = null;
    void saveHomeConfigToBackend();
  }
  document.removeEventListener('visibilitychange', handleHomeVisibilityChange);
  stopHomePolling();
  // 離開首頁前儲存目前輸入狀態，以便返回時還原
  store.saveHomeInput({
    urlInput: urlInput.value,
    audioSource: audioSource.value,
    selectedDeviceIndex: selectedDeviceIndex.value,
    selectedTranscriptionEngine: selectedTranscriptionEngine.value,
    selectedWhisperModel: selectedWhisperModel.value,
    selectedQwen3AsrModel: selectedQwen3AsrModel.value,
    selectedInputLanguage: selectedInputLanguage.value,
    selectedOutputLanguage: selectedOutputLanguage.value,
    selectedBackend: selectedBackend.value,
    translationEnabled: translationEnabled.value
  });
});

async function handleStart() {
  // 驗證輸入
  if (audioSource.value === 'url' || audioSource.value === 'file') {
    if (!urlInput.value.trim()) {
      store.errorMessage = audioSource.value === 'url'
        ? '請輸入 YouTube Live、Twitch、X、TikTok 等直播網址'
        : '請輸入檔案路徑';
      return;
    }
  }

  if (hasErrors.value) {
    store.errorMessage = '請先修正配置錯誤';
    return;
  }

  if (selectedDownloadEngine.value && !selectedAsrModelDownloaded.value) {
    const confirmed = window.confirm(
      `尚未下載 ASR 模型「${selectedAsrModelId.value}」。\n\n要現在下載嗎？下載完成後會自動繼續啟動即時轉譯。`
    );
    if (!confirmed) {
      store.errorMessage = '需要先下載所選的 ASR 模型才能開始轉譯';
      return;
    }
    try {
      isPreparingAsrModel.value = true;
      addLog(`⬇️ 開始下載 ASR 模型：${selectedAsrModelId.value}`);
      await modelDownloadStore.ensureDownloaded(
        selectedDownloadEngine.value,
        selectedAsrModelId.value,
        selectedModelComputeBackend.value,
      );
      addLog(`✅ ASR 模型下載完成：${selectedAsrModelId.value}`);
    } catch (error: any) {
      const message = error.response?.data?.detail || error.message || '模型下載失敗';
      store.errorMessage = message;
      addLog(`❌ ASR 模型下載失敗：${message}`);
      return;
    } finally {
      isPreparingAsrModel.value = false;
    }
  }
  isLoading.value = true;
  addLog('啟動翻譯系統...');
  addLog(`音訊來源: ${audioSource.value}`);
  if (audioSource.value === 'url' || audioSource.value === 'file') {
    addLog(`URL: ${urlInput.value}`);
  } else {
    addLog(`設備: ${selectedDeviceIndex.value === null ? '自動選擇' : selectedDeviceIndex.value}`);
  }
  addLog(`轉錄引擎: ${selectedTranscriptionEngine.value}`);
  addLog(`模型: ${selectedTranscriptionEngine.value === 'qwen3-asr' ? selectedQwen3AsrModel.value : selectedTranscriptionEngine.value === 'sensevoice' ? selectedSenseVoiceModel.value : selectedTranscriptionEngine.value === 'fun-asr-nano' ? selectedFunAsrModel.value : selectedWhisperModel.value}`);
  addLog(`輸入語言: ${selectedInputLanguage.value}`);
  addLog(`翻譯後端: ${selectedBackend.value}`);
  addLog(`目標語言: ${selectedOutputLanguage.value}`);
  
  try {
    if (llamaStore.localLlmEnabled && !llamaStore.isServerReady) {
      addLog('🦙 正在啟動本地 LLM...');
      await llamaStore.startServer();
      addLog('✅ 本地 LLM 已就緒');
    }
    // 使用新的 API 格式
    const result = await translationApi.start({
      audio_source: audioSource.value,
      url: (audioSource.value === 'url' || audioSource.value === 'file') ? urlInput.value : undefined,
      device_index: (audioSource.value === 'microphone' || audioSource.value === 'system_audio') 
        ? (selectedDeviceIndex.value ?? undefined) 
        : undefined,
      model: selectedTranscriptionEngine.value === 'qwen3-asr'
        ? selectedQwen3AsrModel.value
        : selectedTranscriptionEngine.value === 'sensevoice'
          ? selectedSenseVoiceModel.value
          : selectedTranscriptionEngine.value === 'fun-asr-nano'
            ? selectedFunAsrModel.value
          : selectedTranscriptionEngine.value === 'parakeet-ctc-ja'
            ? selectedParakeetModel.value
            : selectedWhisperModel.value,
      transcription_engine: selectedTranscriptionEngine.value,
      qwen3_asr_model: selectedTranscriptionEngine.value === 'qwen3-asr'
        ? selectedQwen3AsrModel.value : undefined,
      sensevoice_model: selectedTranscriptionEngine.value === 'sensevoice'
        ? selectedSenseVoiceModel.value : undefined,
      fun_asr_model: selectedTranscriptionEngine.value === 'fun-asr-nano'
        ? selectedFunAsrModel.value : undefined,
      nemo_asr_model: selectedTranscriptionEngine.value === 'parakeet-ctc-ja'
        ? selectedParakeetModel.value : undefined,
      nemo_asr_dtype: selectedTranscriptionEngine.value === 'parakeet-ctc-ja'
        ? (store.config.transcription?.nemo_asr_dtype || 'bfloat16') : undefined,
      qwen3_flash_attention: selectedTranscriptionEngine.value === 'qwen3-asr' 
        ? store.config.transcription?.qwen3_flash_attention : undefined,
      qwen3_dtype: selectedTranscriptionEngine.value === 'qwen3-asr' 
        ? store.config.transcription?.qwen3_dtype : undefined,
      input_language: selectedTranscriptionEngine.value === 'parakeet-ctc-ja'
        ? parakeetLanguageForModel(selectedParakeetModel.value)
        : selectedInputLanguage.value,
      target_language: translationEnabled.value ? selectedOutputLanguage.value : undefined,
      gpt_model: translationEnabled.value ? store.config.translation?.gpt_model : undefined,
      translation_backend: translationEnabled.value ? selectedBackend.value : undefined,
      translation_enabled: translationEnabled.value
    });
    
    // 更新 store 狀態
    store.isRunning = true;
    store.currentTaskId = result.task_id;
    if (audioSource.value === 'url' || audioSource.value === 'file') {
      store.currentUrl = urlInput.value;
    } else {
      store.currentUrl = `${audioSource.value}${selectedDeviceIndex.value !== null ? ` (設備 ${selectedDeviceIndex.value})` : ''}`;
    }
    
    // 清空字幕歷史
    store.subtitles = [];
    
    // 🔧 重要: 連接 SSE 以接收字幕事件
    store.connectEventSource(result.task_id);
    
    addLog('✅ 翻譯系統已啟動');
    addLog(`Task ID: ${result.task_id}`);
    addLog('📡 SSE 連接已建立');
    await store.syncRunningState();
  } catch (error: any) {
    addLog(`❌ 啟動失敗: ${error.message}`);
    store.errorMessage = error.message;
  } finally {
    isLoading.value = false;
  }
}

async function handleLocalLlmToggle(event: Event) {
  const enabled = (event.target as HTMLInputElement).checked;
  try {
    await llamaStore.setLocalLlmEnabled(enabled);
    addLog(enabled ? '✅ 已啟用本地 LLM' : '⏹️ 已停用本地 LLM');
  } catch (error: any) {
    addLog(`❌ 本地 LLM 切換失敗: ${error.response?.data?.detail || error.message}`);
  }
}

async function downloadSelectedAsrModel() {
  if (!selectedDownloadEngine.value || selectedAsrModelDownloaded.value) return;
  try {
    isPreparingAsrModel.value = true;
    addLog(`⬇️ 開始下載 ASR 模型：${selectedAsrModelId.value}`);
    await modelDownloadStore.ensureDownloaded(
      selectedDownloadEngine.value,
      selectedAsrModelId.value,
      selectedModelComputeBackend.value,
    );
    addLog(`✅ ASR 模型下載完成：${selectedAsrModelId.value}`);
  } catch (error: any) {
    const message = error.response?.data?.detail || error.message || '模型下載失敗';
    store.errorMessage = message;
    addLog(`❌ ASR 模型下載失敗：${message}`);
  } finally {
    isPreparingAsrModel.value = false;
  }
}

async function handleStop() {
  isLoading.value = true;
  addLog('停止翻譯系統...');
  
  try {
    await store.stopTranslation();
    addLog('✅ 翻譯系統已停止');
    await store.syncRunningState();
  } catch (error: any) {
    addLog(`❌ 停止失敗: ${error.message}`);
  } finally {
    isLoading.value = false;
  }
}

function goToSettings() {
  router.push('/settings');
}

function openSubtitleWindow() {
  // 通知主進程開啟字幕視窗
  if ((window as any).pyqt) {
    (window as any).pyqt.openSubtitleWindow();
  } else {
    // 在瀏覽器中開啟新分頁
    window.open('/subtitle', '_blank', 'width=800,height=300');
  }
}

function goToWarningPage(page?: string) {
  if (!page) return;
  if (page === 'home-input') {
    nextTick(() => {
      urlInputRef.value?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      urlInputRef.value?.focus();
    });
    return;
  }
  router.push(`/settings?tab=${page}`);
}

function getFileName(path: string): string {
  if (!path) return '';
  return path.split(/[\\/]/).pop() || path;
}

function clearLogs() {
  logs.value = [];
}
</script>

<template>
  <div class="mx-auto flex min-h-full max-w-7xl flex-col justify-between p-3 sm:p-5">
    <div>
      <!-- Header Status Bar -->
      <div class="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2.5 sm:gap-3">
        <div class="flex flex-wrap items-center gap-2 sm:gap-3">
          <!-- Status dot -->
          <div class="flex items-center gap-1.5 bg-white/5 px-2.5 py-0.5 rounded-full border border-white/10 text-[10px]">
            <div :class="[
              'w-1.5 h-1.5 rounded-full',
              store.isRunning ? 'bg-green-400 animate-pulse shadow shadow-green-400/50' : 'bg-gray-500'
            ]"></div>
            <span class="text-white/70 font-semibold">
              {{ store.isRunning ? '即時轉譯中' : '系統閒置' }}
            </span>
          </div>

          <!-- Configuration Status dot -->
          <div class="flex items-center gap-1.5 bg-white/5 px-2.5 py-0.5 rounded-full border border-white/10 text-[10px]">
            <div :class="[
              'w-1.5 h-1.5 rounded-full',
              hasErrors ? 'bg-red-400 animate-pulse' : (configWarnings.length > 0 ? 'bg-yellow-400 animate-pulse' : 'bg-green-400')
            ]"></div>
            <span class="text-white/70 font-semibold">
              {{ hasErrors ? '配置錯誤' : (configWarnings.length > 0 ? '配置警告' : '配置正常') }}
            </span>
          </div>
        </div>
        <div class="flex min-w-0 items-center gap-2 max-md:w-full max-md:justify-between">
          <div v-if="store.currentUrl" class="text-white/40 text-[10px] truncate max-w-xs sm:max-w-md font-mono bg-white/5 px-2.5 py-0.5 rounded-lg border border-white/5">
            {{ store.currentUrl }}
          </div>
          <button type="button" class="rounded-lg border border-cyan-400/20 bg-cyan-400/10 px-2.5 py-1 text-[10px] font-bold text-cyan-200 transition hover:bg-cyan-400/20" @click="router.push('/guide')">
            ？ 使用教學
          </button>
        </div>
      </div>

      <!-- System notification blocks -->
      <div v-if="availableAppUpdate && !appUpdateNoticeDismissed" class="mb-4 rounded-xl border border-cyan-400/30 bg-cyan-950/70 p-3.5 text-cyan-100 shadow-lg shadow-cyan-950/20">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div class="min-w-0">
            <div class="text-sm font-bold">✨ Stream Translator v{{ availableAppUpdate.latest_version }} 已可更新</div>
            <p class="mt-1 text-xs leading-relaxed text-cyan-100/65">
              目前版本 v{{ availableAppUpdate.current_version }}。程式只會通知，不會自動下載或安裝。
            </p>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <button type="button" class="rounded-lg bg-cyan-500 px-3 py-1.5 text-xs font-bold text-slate-950 transition hover:bg-cyan-400" @click="openAppUpdateSettings">查看更新</button>
            <button type="button" class="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold text-white/65 transition hover:bg-white/10 hover:text-white" @click="appUpdateNoticeDismissed = true">稍後</button>
          </div>
        </div>
      </div>

      <div v-if="showFfmpegWarning" class="mb-4 p-3.5 bg-yellow-950/70 border border-yellow-500/30 text-yellow-200 rounded-xl flex justify-between items-start gap-3">
        <div class="flex-1">
          <div class="font-bold text-sm">⚠️ 未偵測到 ffmpeg</div>
          <p class="text-xs text-yellow-100/70 mt-1 leading-relaxed">
            目前系統找不到 ffmpeg，可先安裝或確認路徑。這不會阻止 UI 啟動，但音訊處理可能失敗。
          </p>
        </div>
        <button @click="ffmpegWarningDismissed = true" class="text-yellow-400/60 hover:text-white transition font-bold text-lg leading-none p-1">✕</button>
      </div>

      <!-- 配置警告面板 (僅在有警告/錯誤時動態顯示) -->
      <div v-if="configWarnings.length > 0" class="mb-4 p-4 rounded-xl bg-slate-950/90 border"
        :class="hasErrors ? 'border-red-500/30 bg-red-500/10' : 'border-yellow-500/30 bg-yellow-500/10'">
        <div class="flex items-center gap-2 mb-2">
          <span class="text-base">{{ hasErrors ? '❌' : '⚠️' }}</span>
          <span class="font-bold text-white text-xs tracking-wider uppercase">配置檢查</span>
        </div>
        <ul class="space-y-1.5">
          <li v-for="(warning, idx) in configWarnings" :key="idx" 
            class="flex items-center justify-between text-xs"
            :class="warning.level === 'error' ? 'text-red-300/90' : 'text-yellow-300/90'">
            <span class="flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full" :class="warning.level === 'error' ? 'bg-red-400' : 'bg-yellow-400'"></span>
              {{ warning.message }}
            </span>
            <button v-if="warning.page" type="button" @click="goToWarningPage(warning.page)"
              class="px-2 py-0.5 bg-white/10 hover:bg-white/20 text-white rounded text-[10px] transition border border-white/5">
              {{ warning.actionLabel || '前往設定' }}
            </button>
          </li>
        </ul>
      </div>

      <!-- Error/Status Messages -->
      <div v-if="store.errorMessage" class="mb-4 p-3.5 bg-red-950/80 border border-red-500/30 text-red-200 rounded-xl flex justify-between items-center text-sm">
        <span class="flex items-center gap-2"><span>❌</span> {{ store.errorMessage }}</span>
        <button @click="store.clearError()" class="text-red-400 hover:text-white transition font-bold text-lg p-1">✕</button>
      </div>

      <div v-if="store.statusMessage" class="mb-4 p-3.5 bg-green-950/80 border border-green-500/30 text-green-200 rounded-xl flex justify-between items-center text-sm">
        <span class="flex items-center gap-2"><span>ℹ️</span> {{ store.statusMessage }}</span>
        <button @click="store.clearStatus()" class="text-green-400 hover:text-white transition font-bold text-lg p-1">✕</button>
      </div>

      <!-- Dashboard Grid Layout -->
      <div class="grid grid-cols-1 items-start gap-6 lg:grid-cols-12 lg:items-stretch">
        
        <!-- Left Column: Controls & Configuration (col-span-7 or 8) -->
        <div class="lg:col-span-7 xl:col-span-8 space-y-6">
          
          <!-- Main Control Card -->
          <div class="rounded-2xl border border-white/10 bg-slate-950/90 p-4 shadow-2xl sm:p-5">
            
            <!-- 音訊來源選擇 -->
            <div class="mb-5">
              <label class="block text-white/80 font-bold mb-2.5 text-xs tracking-wider uppercase">🎵 音訊來源</label>
              <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <button
                  @click="audioSource = 'url'; onAudioSourceChange()"
                  :disabled="store.isRunning"
                  type="button"
                  :class="[
                    'flex flex-col items-center justify-center p-3 rounded-xl border text-center transition-all duration-200 group relative overflow-hidden',
                    audioSource === 'url' 
                      ? 'border-blue-500/80 bg-gradient-to-b from-blue-500/20 to-blue-500/5 text-white shadow-lg shadow-blue-500/10' 
                      : 'bg-white/5 border-white/10 hover:border-white/20 text-white/70 hover:text-white',
                    store.isRunning ? 'opacity-50 cursor-not-allowed' : 'hover:scale-[1.02] active:scale-[0.98]'
                  ]"
                >
                  <span class="text-2xl mb-1.5 transition-transform group-hover:scale-110 duration-200">🌐</span>
                  <span class="font-bold text-xs">URL 串流</span>
                  <span class="text-[9px] text-white/40 mt-1 hidden sm:inline-block leading-tight">播放網路直播流</span>
                </button>
                <button
                  @click="audioSource = 'file'; onAudioSourceChange()"
                  :disabled="store.isRunning"
                  type="button"
                  :class="[
                    'flex flex-col items-center justify-center p-3 rounded-xl border text-center transition-all duration-200 group relative overflow-hidden',
                    audioSource === 'file' 
                      ? 'border-blue-500/80 bg-gradient-to-b from-blue-500/20 to-blue-500/5 text-white shadow-lg shadow-blue-500/10' 
                      : 'bg-white/5 border-white/10 hover:border-white/20 text-white/70 hover:text-white',
                    store.isRunning ? 'opacity-50 cursor-not-allowed' : 'hover:scale-[1.02] active:scale-[0.98]'
                  ]"
                >
                  <span class="text-2xl mb-1.5 transition-transform group-hover:scale-110 duration-200">📁</span>
                  <span class="font-bold text-xs"><span class="md:hidden">電腦</span>本地檔案</span>
                  <span class="text-[9px] text-white/40 mt-1 hidden sm:inline-block leading-tight">轉譯本機影音檔</span>
                </button>
                <button
                  @click="audioSource = 'microphone'; onAudioSourceChange()"
                  :disabled="store.isRunning"
                  type="button"
                  :class="[
                    'flex flex-col items-center justify-center p-3 rounded-xl border text-center transition-all duration-200 group relative overflow-hidden',
                    audioSource === 'microphone' 
                      ? 'border-blue-500/80 bg-gradient-to-b from-blue-500/20 to-blue-500/5 text-white shadow-lg shadow-blue-500/10' 
                      : 'bg-white/5 border-white/10 hover:border-white/20 text-white/70 hover:text-white',
                    store.isRunning ? 'opacity-50 cursor-not-allowed' : 'hover:scale-[1.02] active:scale-[0.98]'
                  ]"
                >
                  <span class="text-2xl mb-1.5 transition-transform group-hover:scale-110 duration-200">🎤</span>
                  <span class="font-bold text-xs"><span class="md:hidden">電腦</span>麥克風</span>
                  <span class="text-[9px] text-white/40 mt-1 hidden sm:inline-block leading-tight">錄製麥克風輸入</span>
                </button>
                <button
                  @click="audioSource = 'system_audio'; onAudioSourceChange()"
                  :disabled="store.isRunning"
                  type="button"
                  :class="[
                    'flex flex-col items-center justify-center p-3 rounded-xl border text-center transition-all duration-200 group relative overflow-hidden',
                    audioSource === 'system_audio' 
                      ? 'border-blue-500/80 bg-gradient-to-b from-blue-500/20 to-blue-500/5 text-white shadow-lg shadow-blue-500/10' 
                      : 'bg-white/5 border-white/10 hover:border-white/20 text-white/70 hover:text-white',
                    store.isRunning ? 'opacity-50 cursor-not-allowed' : 'hover:scale-[1.02] active:scale-[0.98]'
                  ]"
                >
                  <span class="text-2xl mb-1.5 transition-transform group-hover:scale-110 duration-200">🔊</span>
                  <span class="font-bold text-xs"><span class="md:hidden">電腦</span>系統音訊</span>
                  <span class="text-[9px] text-white/40 mt-1 hidden sm:inline-block leading-tight">捕獲系統播放音</span>
                </button>
              </div>
            </div>

            <!-- URL/檔案輸入 -->
            <div v-if="audioSource === 'url' || audioSource === 'file'" class="mb-5">
              <label class="block text-white/80 font-bold mb-1.5 text-xs tracking-wider uppercase">
                {{ audioSource === 'url' ? '🔗 直播網址（YouTube Live／Twitch／X／TikTok 等）' : '📁 本地檔案' }}
              </label>
              <div class="flex flex-col gap-2 sm:flex-row">
                <input
                  ref="urlInputRef"
                  v-model="urlInput"
                  type="text"
                  spellcheck="false"
                  :placeholder="audioSource === 'url' ? '貼上 YouTube Live、Twitch、X、TikTok 等直播網址' : 'C:\\path\\to\\video.mp4'"
                  :disabled="store.isRunning"
                  class="flex-1 min-w-0 px-4 py-2.5 bg-white/5 border border-white/15 rounded-xl text-white placeholder-white/30 focus:outline-none focus:border-blue-500/80 focus:ring-1 focus:ring-blue-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition duration-200 text-sm"
                />
                <button
                  v-if="audioSource === 'file'"
                  type="button"
                  @click="chooseLocalFile"
                  :disabled="store.isRunning"
                  class="shrink-0 px-4 py-2.5 bg-blue-600/90 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl transition border border-blue-400/40 text-sm font-semibold whitespace-nowrap"
                  title="開啟檔案選擇器"
                >
                  📂 選擇檔案
                </button>
              </div>
              <input
                v-if="audioSource === 'file'"
                ref="localFileInputRef"
                type="file"
                :accept="localMediaAccept"
                class="hidden"
                @change="handleLocalFileInputChange"
              />
              <p v-if="audioSource === 'file'" class="text-white/40 text-[10px] mt-1.5 tracking-wide">
                支援 MP4、MKV、WebM、MOV、MP3、WAV 等格式；桌面版按鈕會開啟原生檔案選擇器。
              </p>
            </div>

            <!-- 設備選擇 -->
            <div v-if="audioSource === 'microphone' || audioSource === 'system_audio'" class="mb-5">
              <label class="block text-white/80 font-bold mb-1.5 text-xs tracking-wider uppercase">
                {{ audioSource === 'microphone' ? '🎤 麥克風設備' : '🔊 系統音訊設備' }}
              </label>
              <div class="flex gap-2">
                <UiSelect
                  v-model="selectedDeviceIndex"
                  :options="deviceOptions"
                  :disabled="store.isRunning || isLoadingDevices"
                  class="flex-1 min-w-0"
                  button-class="flex-1 px-4 py-2.5 bg-white/5 border border-white/15 rounded-xl text-sm text-left hover:bg-white/10 transition"
                />
                <button
                  @click="loadDevices()"
                  :disabled="store.isRunning || isLoadingDevices"
                  class="px-4 py-2.5 bg-white/5 hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl transition border border-white/15 text-sm flex items-center justify-center min-w-[46px]"
                  title="重新整理設備列表"
                >
                  {{ isLoadingDevices ? '⏳' : '🔄' }}
                </button>
              </div>
              <p v-if="availableDevices.length > 0" class="text-white/40 text-[10px] mt-1.5 tracking-wide">
                ✓ 偵測到 {{ availableDevices.length }} 個音訊裝置
              </p>
            </div>

            <!-- 快速設定 (輸入語言, 啟用翻譯, 目標語言) -->
            <div class="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4">
              <!-- 輸入語言 -->
              <div class="flex flex-col">
                <label class="text-white/60 text-[10px] font-bold tracking-wider uppercase mb-1.5">🎙️ 輸入語言</label>
                <UiSelect
                  v-model="selectedInputLanguage"
                  :options="inputLanguageOptions"
                  :disabled="store.isRunning || isInputLanguageLocked"
                  button-class="bg-white/5 border border-white/15 hover:bg-white/10 text-xs rounded-xl"
                />
                <p v-if="isInputLanguageLocked" class="text-amber-300/80 text-[9px] mt-1">
                  此模型為專用語言模型，輸入語言已自動鎖定。
                </p>
              </div>

              <!-- 啟用翻譯與目標語言 -->
              <div class="flex flex-col">
                <div class="flex items-center justify-between mb-1.5">
                  <label class="text-white/60 text-[10px] font-bold tracking-wider uppercase">🌐 目標語言</label>
                  <label class="flex items-center gap-1 cursor-pointer text-[10px] text-white/45 hover:text-white/80 transition">
                    <input type="checkbox" v-model="translationEnabled" :disabled="store.isRunning" class="w-3 h-3 accent-blue-500 rounded bg-white/5 border-white/15" />
                    <span>翻譯</span>
                  </label>
                </div>
                <UiSelect
                  v-model="selectedOutputLanguage"
                  :options="outputLanguageOptions"
                  :disabled="store.isRunning || !translationEnabled"
                  button-class="bg-white/5 border border-white/15 hover:bg-white/10 text-xs rounded-xl disabled:opacity-40"
                />
              </div>
            </div>

            <!-- 進階配置摺疊區 (轉錄引擎、模型選擇、翻譯後端) -->
            <div class="mb-5">
              <button
                @click="showAdvancedConfig = !showAdvancedConfig"
                type="button"
                class="flex min-h-10 w-full items-center justify-between gap-2 rounded-xl border border-indigo-400/15 bg-indigo-400/5 px-3 text-left text-[10px] font-semibold text-indigo-300 transition hover:bg-indigo-400/10 md:min-h-0 md:w-auto md:border-0 md:bg-transparent md:px-0 md:text-indigo-400"
              >
                <span>{{ showAdvancedConfig ? '▼ 收起進階配置' : '▶ 展開進階配置（引擎與模型）' }}</span>
                <span v-if="!showAdvancedConfig" class="truncate text-[9px] text-white/40 md:hidden">{{ selectedTranscriptionEngine }}</span>
              </button>

              <Transition name="fade-slide">
                <div v-show="showAdvancedConfig" class="grid grid-cols-1 md:grid-cols-3 gap-4 mt-3 p-3 bg-white/5 rounded-xl border border-white/5">
                  <div class="flex flex-col">
                    <label class="text-white/50 text-[9px] font-bold tracking-wider mb-1">ASR 運算模式</label>
                    <UiSelect
                      v-model="selectedAsrComputeBackend"
                      :options="asrComputeBackendOptions"
                      :disabled="store.isRunning || store.runtimeStatus?.profile === 'cpu'"
                      button-class="bg-white/5 border border-white/10 text-[10px] rounded-lg"
                    />
                  </div>
                  <!-- 轉錄引擎 -->
                  <div class="flex flex-col">
                    <label class="text-white/50 text-[9px] font-bold tracking-wider mb-1">轉錄引擎</label>
                    <UiSelect
                      v-model="selectedTranscriptionEngine"
                      :options="transcriptionEngineOptions"
                      :disabled="store.isRunning"
                      button-class="bg-white/5 border border-white/10 text-[10px] rounded-lg"
                    />
                  </div>

                  <!-- 模型選擇 -->
                  <div class="flex flex-col">
                    <label class="text-white/50 text-[9px] font-bold tracking-wider mb-1">模型選擇</label>
                    <UiSelect
                      v-if="selectedTranscriptionEngine === 'faster-whisper' || selectedTranscriptionEngine === 'simul-streaming' || selectedTranscriptionEngine === 'faster-whisper-simul'"
                      v-model="selectedWhisperModel"
                      :options="whisperModelOptions"
                      :disabled="store.isRunning"
                      button-class="bg-white/5 border border-white/10 text-[10px] rounded-lg"
                    />
                    <UiSelect
                      v-else-if="selectedTranscriptionEngine === 'qwen3-asr'"
                      v-model="selectedQwen3AsrModel"
                      :options="qwen3AsrModelOptions"
                      :disabled="store.isRunning"
                      button-class="bg-white/5 border border-white/10 text-[10px] rounded-lg"
                    />
                    <UiSelect
                      v-else-if="selectedTranscriptionEngine === 'sensevoice'"
                      v-model="selectedSenseVoiceModel"
                      :options="senseVoiceModelOptions"
                      :disabled="store.isRunning"
                      button-class="bg-white/5 border border-white/10 text-[10px] rounded-lg"
                    />
                    <UiSelect
                      v-else-if="selectedTranscriptionEngine === 'fun-asr-nano'"
                      v-model="selectedFunAsrModel"
                      :options="funAsrModelOptions"
                      :disabled="store.isRunning"
                      button-class="bg-white/5 border border-white/10 text-[10px] rounded-lg"
                    />
                    <UiSelect
                      v-else-if="selectedTranscriptionEngine === 'parakeet-ctc-ja'"
                      v-model="selectedParakeetModel"
                      :options="parakeetModelOptions"
                      :disabled="store.isRunning"
                      button-class="bg-white/5 border border-white/10 text-[10px] rounded-lg"
                    />
                    <input v-else-if="selectedTranscriptionEngine === 'openai-api'" 
                      value="whisper-1" disabled
                      class="w-full px-3 py-1.5 bg-white/5 border border-white/10 rounded-lg text-white/40 cursor-not-allowed text-[10px]"
                    />
                  </div>

                  <!-- 翻譯模型／後端 -->
                  <div class="flex flex-col md:col-span-3">
                    <label class="text-white/70 text-[10px] font-bold tracking-wider mb-1">🧠 翻譯模型／後端</label>
                    <UiSelect
                      v-model="selectedBackend"
                      :options="backendOptions"
                      :disabled="store.isRunning || !translationEnabled"
                      button-class="bg-white/5 border border-white/10 text-[10px] rounded-lg disabled:opacity-40"
                    />
                    <p class="mt-1 text-[9px] text-cyan-200/55">翻譯開關開啟後，ASR 只負責把聲音轉成文字；這裡的模型才負責翻譯成目標語言。</p>
                  </div>
                </div>
              </Transition>
            </div>

            <div
              v-if="selectedDownloadEngine && (!selectedAsrModelDownloaded || (selectedAsrDownloadTask && ['pending', 'downloading', 'failed'].includes(selectedAsrDownloadTask.status)))"
              class="mb-4 rounded-xl border p-3"
              :class="selectedAsrDownloadTask?.status === 'failed' ? 'border-rose-400/20 bg-rose-950/20' : 'border-cyan-400/15 bg-cyan-950/20'"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0">
                  <div class="flex items-center gap-2 text-[10px] font-bold text-cyan-200">
                    <span>{{ selectedAsrDownloadTask && ['pending', 'downloading'].includes(selectedAsrDownloadTask.status) ? '⬇️ ASR 模型下載中' : '📦 尚未下載 ASR 模型' }}</span>
                    <span v-if="selectedAsrDownloadTask && ['pending', 'downloading'].includes(selectedAsrDownloadTask.status)" class="rounded-full bg-cyan-400/10 px-2 py-0.5 text-cyan-300">
                      {{ (modelDownloadStore.displayProgress(selectedAsrDownloadTask) * 100).toFixed(1) }}%
                    </span>
                  </div>
                  <p class="mt-1 truncate text-[11px] font-semibold text-white/80">{{ selectedAsrModelId }}</p>
                  <p class="mt-0.5 text-[9px] text-white/40">
                    {{ selectedAsrDownloadTask?.error || selectedAsrDownloadTask?.message || '開始轉譯時會提醒並可自動下載，完成後接續啟動。' }}
                  </p>
                </div>
                <button
                  v-if="!selectedAsrDownloadTask || !['pending', 'downloading'].includes(selectedAsrDownloadTask.status)"
                  type="button"
                  class="flex-shrink-0 rounded-lg bg-cyan-600 px-3 py-1.5 text-[10px] font-bold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="isPreparingAsrModel"
                  @click="downloadSelectedAsrModel"
                >
                  {{ isPreparingAsrModel ? '準備中…' : '立即下載' }}
                </button>
              </div>
              <div v-if="selectedAsrDownloadTask && ['pending', 'downloading'].includes(selectedAsrDownloadTask.status)" class="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                <div
                  class="h-full rounded-full bg-gradient-to-r from-cyan-500 to-emerald-400 transition-all duration-500"
                  :style="{ width: `${Math.max(3, modelDownloadStore.displayProgress(selectedAsrDownloadTask) * 100)}%` }"
                ></div>
              </div>
            </div>

            <!-- 控制按鈕 (啟動/停止 與 字幕視窗) -->
            <div class="hidden gap-3 md:flex">
              <!-- 啟動/停止按鈕 -->
              <button
                v-if="!store.isRunning"
                @click="handleStart"
                :disabled="isLoading || isPreparingAsrModel || !isConfigReady"
                class="flex-1 bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:via-indigo-500 hover:to-purple-500 disabled:from-slate-800 disabled:to-slate-900 disabled:text-white/40 disabled:border-white/5 disabled:shadow-none text-white font-bold py-3.5 px-5 rounded-xl transition-all duration-200 active:scale-[0.98] shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2"
              >
                <span class="text-sm font-semibold">{{ isPreparingAsrModel ? '⬇️ 正在下載 ASR 模型...' : isLoading ? '⏳ 啟動中...' : '▶️ 啟動即時轉譯' }}</span>
              </button>

              <button
                v-else
                @click="handleStop"
                :disabled="isLoading"
                class="flex-1 bg-gradient-to-r from-rose-600 to-red-600 hover:from-rose-500 hover:to-red-500 disabled:from-slate-800 disabled:to-slate-900 disabled:text-white/40 disabled:border-white/5 disabled:shadow-none text-white font-bold py-3.5 px-5 rounded-xl transition-all duration-200 active:scale-[0.98] shadow-lg shadow-red-600/20 flex items-center justify-center gap-2"
              >
                <span class="text-sm font-semibold">{{ isLoading ? '⏳ 停止中...' : '⏹️ 停止即時轉譯' }}</span>
              </button>

              <!-- 字幕視窗按鈕 -->
              <button
                @click="openSubtitleWindow"
                class="px-5 py-3.5 bg-gradient-to-r from-cyan-600/90 to-teal-600/90 hover:from-cyan-500 hover:to-teal-500 text-white font-semibold rounded-xl transition-all shadow-md shadow-cyan-600/10 flex items-center justify-center gap-1.5 text-sm"
                title="開啟字幕懸浮視窗"
              >
                🪟 <span class="hidden sm:inline">字幕視窗</span>
              </button>
            </div>

          </div>

          <!-- 本地 LLM 快速控制 -->
          <div
            class="relative overflow-hidden rounded-2xl border p-4 transition-all duration-300"
            :class="llamaStore.localLlmEnabled
              ? 'border-emerald-400/25 bg-gradient-to-r from-emerald-950/35 via-slate-950/95 to-cyan-950/25 shadow-lg shadow-emerald-950/20'
              : 'border-white/5 bg-slate-950/90'"
          >
            <div v-if="llamaStore.localLlmEnabled" class="pointer-events-none absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-emerald-400 to-cyan-500"></div>
            <div class="flex items-center justify-between gap-4">
              <div class="flex min-w-0 items-center gap-3">
                <div
                  class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border text-lg transition-colors"
                  :class="llamaStore.localLlmEnabled ? 'border-emerald-400/20 bg-emerald-400/10' : 'border-white/5 bg-white/[0.03]'"
                >
                  🧠
                </div>
                <div class="min-w-0">
                  <div class="mb-1 flex flex-wrap items-center gap-2">
                    <h3 class="text-xs font-bold tracking-wide text-white">本地 LLM 翻譯</h3>
                    <span
                      class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[9px] font-bold"
                      :class="llamaStore.isServerReady
                        ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300'
                        : llamaStore.isServerRunning || llamaStore.isLoading
                          ? 'border-amber-400/25 bg-amber-400/10 text-amber-300'
                          : 'border-white/10 bg-white/5 text-white/40'"
                    >
                      <span
                        class="h-1.5 w-1.5 rounded-full"
                        :class="llamaStore.isServerReady ? 'bg-emerald-400' : llamaStore.isServerRunning || llamaStore.isLoading ? 'animate-pulse bg-amber-400' : 'bg-slate-500'"
                      ></span>
                      {{ localLlmStatusLabel }}
                    </span>
                  </div>
                  <p class="truncate text-[11px] font-semibold" :class="llamaStore.selectedModelPath ? 'text-cyan-200/90' : 'text-amber-300/80'">
                    {{ localLlmModelName }}
                  </p>
                  <p class="mt-0.5 max-w-[560px] truncate text-[9px] text-white/35" :title="localLlmStatusDescription">
                    {{ localLlmStatusDescription }}
                  </p>
                </div>
              </div>

              <label
                class="flex flex-shrink-0 items-center gap-2.5"
                :class="llamaStore.isLoading || (!llamaStore.selectedModelPath && !llamaStore.localLlmEnabled) ? 'cursor-not-allowed opacity-45' : 'cursor-pointer'"
                :title="!llamaStore.selectedModelPath ? '請先到 LLM 模型管理選擇模型' : llamaStore.localLlmEnabled ? '關閉本地 LLM' : '啟動本地 LLM'"
              >
                <span class="text-[10px] font-bold" :class="llamaStore.localLlmEnabled ? 'text-emerald-300' : 'text-white/45'">
                  {{ llamaStore.localLlmEnabled ? '開啟' : '關閉' }}
                </span>
                <span class="relative inline-flex">
                  <input
                    type="checkbox"
                    class="peer sr-only"
                    :checked="llamaStore.localLlmEnabled"
                    :disabled="llamaStore.isLoading || (!llamaStore.selectedModelPath && !llamaStore.localLlmEnabled)"
                    @change="handleLocalLlmToggle"
                  />
                  <span class="h-6 w-12 rounded-full border border-white/10 bg-slate-700 shadow-inner transition-all duration-300 peer-checked:border-emerald-400/40 peer-checked:bg-emerald-500 peer-focus-visible:ring-2 peer-focus-visible:ring-emerald-300/50"></span>
                  <span class="absolute left-1 top-1 h-4 w-4 rounded-full bg-white shadow-md transition-transform duration-300 peer-checked:translate-x-6"></span>
                </span>
              </label>
            </div>
          </div>

        </div>

        <!-- Right Column: Monitoring & Sharing (col-span-5 or 4) -->
        <div class="flex min-w-0 flex-col gap-6 lg:col-span-5 xl:col-span-4">
          
          <!-- 執行日誌 -->
          <div class="flex h-[420px] min-h-0 flex-col rounded-2xl border border-white/10 bg-slate-950/90 p-4 shadow-2xl lg:h-[500px]">
            <div class="flex items-center justify-between mb-2.5">
              <h2 class="text-xs font-bold text-white tracking-widest uppercase flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full bg-blue-400"></span>
                📋 系統執行日誌
              </h2>
              <button 
                @click="clearLogs"
                class="text-[10px] text-white/40 hover:text-white/80 transition-colors flex items-center gap-1 px-2.5 py-1 bg-white/5 hover:bg-white/10 rounded-lg border border-white/5"
              >
                🗑️ 清除
              </button>
            </div>
            <div ref="logContainer" class="min-h-0 flex-1 overflow-y-auto bg-black/40 rounded-xl p-3 font-mono text-[11px] leading-relaxed custom-scrollbar border border-white/5">
              <div v-for="(log, idx) in logs" :key="idx" class="mb-1 break-words text-green-400/80 last:mb-0">{{ log }}</div>
              <div v-if="logs.length === 0" class="text-white/20 h-full flex items-center justify-center italic">暫無執行日誌，等待啟動...</div>
            </div>
          </div>

          <!-- 🌐 公開分享連結 -->
          <div class="bg-slate-950/90 rounded-2xl border border-indigo-500/20 shadow-2xl p-4">
            <div class="flex items-center justify-between mb-2.5">
              <h2 class="text-xs font-bold text-white tracking-widest uppercase flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>
                🌐 字幕分享服務
              </h2>
              <button @click="toggleSubtitleSharing" :disabled="isUpdatingSubtitleSharing"
                class="px-2 py-1 text-[10px] rounded-lg transition duration-200 border"
                :class="subtitleSharingEnabled
                  ? 'bg-emerald-600/80 hover:bg-emerald-600 border-emerald-500/30 text-white'
                  : 'bg-rose-600/80 hover:bg-rose-600 border-rose-500/30 text-white'">
                {{ isUpdatingSubtitleSharing ? '同步中...' : (subtitleSharingEnabled ? '分享啟用' : '分享關閉') }}
              </button>
            </div>
            
            <div v-if="subtitleSharingEnabled" class="space-y-2.5">
              <p class="text-white/40 text-[9px] leading-tight">廣播服務已運行於連接埠 {{ publicPort }}。此連結僅顯示字幕，無設定權限。</p>
              
              <div class="space-y-2">
                <!-- 電腦版 -->
                <div class="flex items-center gap-2.5 bg-white/5 rounded-xl p-2.5 border border-white/5 group hover:bg-white/10 transition duration-200">
                  <span class="text-lg">🖥️</span>
                  <div class="flex-1 min-w-0">
                    <div class="text-white/60 text-[10px] font-bold">電腦端字幕</div>
                    <div class="text-white/35 text-[9px] truncate font-mono mt-0.5">{{ getPublicBase() }}/desktop</div>
                  </div>
                  <button @click="copyLink('/desktop')"
                    class="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white text-xs rounded-lg transition-all font-semibold shadow-sm shadow-indigo-600/10">
                    {{ activeCopyPath === '/desktop' ? '✓' : '複製' }}
                  </button>
                </div>
                
                <!-- 手機版 -->
                <div class="flex items-center gap-2.5 bg-white/5 rounded-xl p-2.5 border border-white/5 group hover:bg-white/10 transition duration-200">
                  <span class="text-lg">📱</span>
                  <div class="flex-1 min-w-0">
                    <div class="text-white/60 text-[10px] font-bold">行動端字幕</div>
                    <div class="text-white/35 text-[9px] truncate font-mono mt-0.5">{{ getPublicBase() }}/mobile</div>
                  </div>
                  <button @click="copyLink('/mobile')"
                    class="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white text-xs rounded-lg transition-all font-semibold shadow-sm shadow-indigo-600/10">
                    {{ activeCopyPath === '/mobile' ? '✓' : '複製' }}
                  </button>
                </div>
              </div>
              <p class="text-white/30 text-[9px] text-center tracking-wide mt-1">💡 請確保本機防火牆允許對外存取此連接埠</p>
            </div>
            
            <div v-else class="p-3 rounded-xl border border-rose-500/20 bg-rose-500/5 text-rose-300 text-[10px] leading-relaxed text-center">
              🚫 字幕廣播服務目前已關閉，外部裝置將無法存取字幕網頁。
            </div>
          </div>

        </div>

      </div>
    </div>

    <!-- Reserve real scroll space so the fixed mobile action bar never hides the final card. -->
    <div class="mobile-action-spacer flex-shrink-0 md:hidden" aria-hidden="true"></div>

    <!-- Mobile primary action bar -->
    <div class="mobile-action-bar fixed inset-x-0 bottom-0 z-30 border-t border-white/10 bg-slate-950/95 px-3 pb-3 pt-2 shadow-[0_-12px_35px_rgba(2,6,23,0.8)] backdrop-blur md:hidden">
      <div class="mx-auto flex max-w-7xl items-center gap-2">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5 text-[10px] font-bold text-white/80">
            <span :class="store.isRunning ? 'text-green-400' : 'text-slate-500'">●</span>
            <span>{{ store.isRunning ? '即時轉譯中' : '準備啟動' }}</span>
          </div>
          <p class="mt-0.5 truncate text-[9px] text-white/40">
            {{ selectedInputLanguage }} → {{ translationEnabled ? selectedOutputLanguage : '僅轉錄' }}
          </p>
        </div>
        <button
          v-if="!store.isRunning"
          type="button"
          class="min-h-12 min-w-[9.5rem] rounded-xl bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 px-4 text-sm font-bold text-white shadow-lg shadow-indigo-600/25 transition active:scale-[0.98] disabled:from-slate-800 disabled:to-slate-900 disabled:text-white/40 disabled:shadow-none"
          :disabled="isLoading || isPreparingAsrModel || !isConfigReady"
          @click="handleStart"
        >
          {{ isPreparingAsrModel ? '⬇️ 下載模型中' : isLoading ? '⏳ 啟動中' : '▶️ 開始轉譯' }}
        </button>
        <button
          v-else
          type="button"
          class="min-h-12 min-w-[9.5rem] rounded-xl bg-gradient-to-r from-rose-600 to-red-600 px-4 text-sm font-bold text-white shadow-lg shadow-red-600/25 transition active:scale-[0.98] disabled:from-slate-800 disabled:to-slate-900 disabled:text-white/40 disabled:shadow-none"
          :disabled="isLoading"
          @click="handleStop"
        >
          {{ isLoading ? '⏳ 停止中' : '⏹️ 停止轉譯' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Target language fade-slide animation */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  max-height: 80px;
  opacity: 1;
  overflow: hidden;
}
.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  max-height: 0px;
  transform: translateY(-8px);
  margin-bottom: 0px;
}

/* Custom Scrollbar for Logs */
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 9999px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.35);
}

.mobile-action-bar {
  padding-bottom: max(0.75rem, env(safe-area-inset-bottom));
}

.mobile-action-spacer {
  height: calc(9rem + env(safe-area-inset-bottom));
}
</style>
