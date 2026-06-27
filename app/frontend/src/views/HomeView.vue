<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { useTranslationStore } from '../stores/translation';
import { useLlamaStore } from '../stores/llama';
import { translationApi, configApi, serverApi, systemApi, type AudioSource, type AudioDevice, type Config, type FfmpegCheckResult } from '../services/api';
import UiSelect, { type UiSelectOption } from '../components/UiSelect.vue';
import { useAppSyncEvents } from '../composables/useAppSyncEvents';

const router = useRouter();
const store = useTranslationStore();
const llamaStore = useLlamaStore();

// 公開端口（分享用）
const publicPort = ref(8765);
const activeCopyPath = ref<string | null>(null);
const subtitleSharingEnabled = ref(true);
const isUpdatingSubtitleSharing = ref(false);
const ffmpegStatus = ref<FfmpegCheckResult | null>(null);
const ffmpegWarningDismissed = ref(false);

const showFfmpegWarning = computed(() => {
  return !!ffmpegStatus.value && !ffmpegStatus.value.available && !ffmpegWarningDismissed.value;
});

interface PyQtClipboardBridge {
  copyToClipboard?: (text: string, callback?: (result: boolean) => void) => void;
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
const isLoading = ref(false);
const showAdvancedConfig = ref(true);

// 音訊來源選擇
const audioSource = ref<AudioSource>('url');
const availableDevices = ref<AudioDevice[]>([]);
const selectedDeviceIndex = ref<number | null>(null);
const isLoadingDevices = ref(false);

// 模型選擇
const whisperModels = ['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3', 'large-v3-turbo'];
const qwen3AsrModels = [
  { value: 'Qwen/Qwen3-ASR-1.7B', label: 'Qwen3-ASR-1.7B (推薦)' },
  { value: 'Qwen/Qwen3-ASR-0.6B', label: 'Qwen3-ASR-0.6B (更快)' },
  { value: 'neosophie/Qwen3-ASR-1.7B-JA', label: 'Qwen3-ASR-1.7B-JA (Japanese fine-tune)' }
];
const inputLanguages = [
  { value: 'auto', label: '自動偵測' },
  { value: 'ja', label: '日文' },
  { value: 'en', label: '英文' },
  { value: 'ko', label: '韓文' },
  { value: 'zh-tw', label: '繁體中文' },
  { value: 'zh-cn', label: '簡體中文' }
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
    .map((model) => ({ value: model.value, label: model.label }))
);

const inputLanguageOptions = computed<UiSelectOption[]>(() =>
  inputLanguages.map((lang) => ({ value: lang.value, label: lang.label }))
);

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
const selectedWhisperModel = ref('base');
const selectedQwen3AsrModel = ref('Qwen/Qwen3-ASR-1.7B');  // 🆕 新增: Qwen3-ASR 模型
const selectedInputLanguage = ref('auto');
const selectedOutputLanguage = ref('Traditional Chinese');
const selectedBackend = ref('gpt');
const translationEnabled = ref(true);  // 🔧 新增: 翻譯開關

// 自動保存 debounce timer
const runtimeCapabilities = computed(() => store.runtimeStatus?.capabilities || null);
const allowedLocalAsrEngines = computed<string[]>(() =>
  runtimeCapabilities.value?.local_asr_engines?.length
    ? runtimeCapabilities.value.local_asr_engines
    : ['faster-whisper', 'simul-streaming', 'faster-whisper-simul', 'qwen3-asr']
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

function coerceRuntimeLimitedSelections() {
  if (!allowedTranscriptionEngines.value.includes(selectedTranscriptionEngine.value)) {
    selectedTranscriptionEngine.value = allowedTranscriptionEngines.value.includes('qwen3-asr')
      ? 'qwen3-asr'
      : allowedTranscriptionEngines.value[0] || 'openai-api';
  }
  if (!allowedFasterWhisperModels.value.includes(selectedWhisperModel.value)) {
    selectedWhisperModel.value = allowedFasterWhisperModels.value[0] || 'small';
  }
  if (!allowedQwen3AsrModels.value.includes(selectedQwen3AsrModel.value)) {
    selectedQwen3AsrModel.value = allowedQwen3AsrModels.value[0] || 'Qwen/Qwen3-ASR-0.6B';
  }
}

let _homeAutoSaveTimer: ReturnType<typeof setTimeout> | null = null;
let _homeConfigSyncTimer: ReturnType<typeof setInterval> | null = null;
let _homeRunningSyncTimer: ReturnType<typeof setInterval> | null = null;
const isApplyingExternalConfig = ref(false);
const lastAppliedHomeConfigSnapshot = ref('');

function getTranscriptionEngineFromConfig(cfg: Config): string {
  if (cfg.transcription?.use_qwen3_asr) return 'qwen3-asr';
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
    selectedWhisperModel: cfg.transcription?.model || 'base',
    selectedQwen3AsrModel: cfg.transcription?.qwen3_asr_model || 'Qwen/Qwen3-ASR-1.7B',
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
    selectedWhisperModel: selectedWhisperModel.value,
    selectedQwen3AsrModel: selectedQwen3AsrModel.value,
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
    const transcriptionPatch = {
      ...store.config.transcription,
      model: selectedWhisperModel.value,
      qwen3_asr_model: selectedQwen3AsrModel.value,
      language: selectedInputLanguage.value,
      use_qwen3_asr: engine === 'qwen3-asr',
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
    await Promise.all([
      configApi.updateSection('input', inputPatch),
      configApi.updateSection('transcription', transcriptionPatch),
      configApi.updateSection('translation', translationPatch),
    ]);
    // 更新本地 store 快照
    await store.loadConfig();
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
}

const configWarnings = computed<ConfigWarning[]>(() => {
  const warnings: ConfigWarning[] = [];
  const config = store.config;
  if (!config) return warnings;
  
  const requiresUrlInput = audioSource.value === 'url' || audioSource.value === 'file';
  if (requiresUrlInput && !(urlInput.value || '').trim()) {
    warnings.push({
      level: 'warning',
      message: audioSource.value === 'url' ? '未設定直播 URL' : '未設定檔案路徑',
      page: 'input'
    });
  }

  const requiresDeviceSelection = audioSource.value === 'microphone' || audioSource.value === 'system_audio';
  if (requiresDeviceSelection && (availableDevices.value || []).length === 0 && isLoadingDevices.value === false) {
    warnings.push({
      level: 'warning',
      message: '設備列表尚未載入，將使用系統預設設備'
    });
  }

  if (translationEnabled.value && selectedBackend.value === 'gpt' && !config.general?.openai_api_key) {
    warnings.push({
      level: 'error',
      message: 'OpenAI API Key 未設定',
      page: 'general'
    });
  }
  
  if (translationEnabled.value && selectedBackend.value === 'gemini' && !config.general?.google_api_key) {
    warnings.push({
      level: 'error',
      message: 'Google API Key 未設定',
      page: 'general'
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
    selectedWhisperModel.value = cfg.transcription?.model || 'base';
    selectedQwen3AsrModel.value = cfg.transcription?.qwen3_asr_model || 'Qwen/Qwen3-ASR-1.7B';
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
    await syncHomeStateFromBackend(true, payload.section === '*' || payload.section === 'llama');
  },
  onConfigReset: async () => {
    await syncHomeStateFromBackend(true, true);
  },
  onConfigImported: async () => {
    await syncHomeStateFromBackend(true, true);
  },
  onTranslationStarted: async () => {
    await store.syncRunningState();
  },
  onTranslationStopped: async () => {
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

onMounted(async () => {
  // 載入公開端口資訊
  await fetchPublicPort();
  await checkSystemDependencies();
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

  // 初始化完成後，延後建立 watch 避免初始化誤觸發自動保存
  await nextTick();
  watch(
    [
      urlInput,
      audioSource,
      selectedDeviceIndex,
      selectedTranscriptionEngine,
      selectedWhisperModel,
      selectedQwen3AsrModel,
      selectedInputLanguage,
      selectedOutputLanguage,
      selectedBackend,
      translationEnabled,
    ],
    () => {
      if (isApplyingExternalConfig.value) return;
      debouncedSaveHomeConfig();
    }
  );

  _homeConfigSyncTimer = setInterval(() => {
    void syncHomeStateFromBackend();
  }, 2000);

  _homeRunningSyncTimer = setInterval(() => {
    void store.syncRunningState();
  }, 1500);
});

onBeforeUnmount(() => {
  // 清除未完成的 debounce timer
  if (_homeAutoSaveTimer !== null) {
    clearTimeout(_homeAutoSaveTimer);
    _homeAutoSaveTimer = null;
    void saveHomeConfigToBackend();
  }
  if (_homeConfigSyncTimer !== null) {
    clearInterval(_homeConfigSyncTimer);
    _homeConfigSyncTimer = null;
  }
  if (_homeRunningSyncTimer !== null) {
    clearInterval(_homeRunningSyncTimer);
    _homeRunningSyncTimer = null;
  }
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
      store.errorMessage = audioSource.value === 'url' ? '請輸入直播 URL' : '請輸入檔案路徑';
      return;
    }
  }

  if (hasErrors.value) {
    store.errorMessage = '請先修正配置錯誤';
    return;
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
  addLog(`模型: ${selectedTranscriptionEngine.value === 'qwen3-asr' ? selectedQwen3AsrModel.value : selectedWhisperModel.value}`);
  addLog(`輸入語言: ${selectedInputLanguage.value}`);
  addLog(`翻譯後端: ${selectedBackend.value}`);
  addLog(`目標語言: ${selectedOutputLanguage.value}`);
  
  try {
    // 使用新的 API 格式
    const result = await translationApi.start({
      audio_source: audioSource.value,
      url: (audioSource.value === 'url' || audioSource.value === 'file') ? urlInput.value : undefined,
      device_index: (audioSource.value === 'microphone' || audioSource.value === 'system_audio') 
        ? (selectedDeviceIndex.value ?? undefined) 
        : undefined,
      model: selectedTranscriptionEngine.value === 'qwen3-asr'
        ? selectedQwen3AsrModel.value
        : selectedWhisperModel.value,
      transcription_engine: selectedTranscriptionEngine.value,
      qwen3_asr_model: selectedTranscriptionEngine.value === 'qwen3-asr'
        ? selectedQwen3AsrModel.value : undefined,
      qwen3_flash_attention: selectedTranscriptionEngine.value === 'qwen3-asr' 
        ? store.config.transcription?.qwen3_flash_attention : undefined,
      qwen3_dtype: selectedTranscriptionEngine.value === 'qwen3-asr' 
        ? store.config.transcription?.qwen3_dtype : undefined,
      input_language: selectedInputLanguage.value,
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
  if (page) {
    router.push(`/settings?tab=${page}`);
  }
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
  <div class="p-4 sm:p-5 h-full max-w-7xl mx-auto flex flex-col justify-between">
    <div>
      <!-- Header Status Bar -->
      <div class="flex items-center justify-between mb-4 border-b border-white/5 pb-2.5 gap-3">
        <div class="flex items-center gap-3">
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
        <div v-if="store.currentUrl" class="text-white/40 text-[10px] truncate max-w-xs sm:max-w-md font-mono bg-white/5 px-2.5 py-0.5 rounded-lg border border-white/5">
          {{ store.currentUrl }}
        </div>
      </div>

      <!-- System notification blocks -->
      <div v-if="showFfmpegWarning" class="mb-4 p-3.5 bg-yellow-500/10 border border-yellow-500/30 text-yellow-200 rounded-xl flex justify-between items-start gap-3 backdrop-blur-xl">
        <div class="flex-1">
          <div class="font-bold text-sm">⚠️ 未偵測到 ffmpeg</div>
          <p class="text-xs text-yellow-100/70 mt-1 leading-relaxed">
            目前系統找不到 ffmpeg，可先安裝或確認路徑。這不會阻止 UI 啟動，但音訊處理可能失敗。
          </p>
        </div>
        <button @click="ffmpegWarningDismissed = true" class="text-yellow-400/60 hover:text-white transition font-bold text-lg leading-none p-1">✕</button>
      </div>

      <!-- 配置警告面板 (僅在有警告/錯誤時動態顯示) -->
      <div v-if="configWarnings.length > 0" class="mb-4 p-4 rounded-xl backdrop-blur-xl bg-slate-900/60 border"
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
            <button v-if="warning.page" @click="goToWarningPage(warning.page)"
              class="px-2 py-0.5 bg-white/10 hover:bg-white/20 text-white rounded text-[10px] transition border border-white/5">
              前往設定
            </button>
          </li>
        </ul>
      </div>

      <!-- Error/Status Messages -->
      <div v-if="store.errorMessage" class="mb-4 p-3.5 bg-red-500/20 backdrop-blur-xl border border-red-500/30 text-red-200 rounded-xl flex justify-between items-center text-sm">
        <span class="flex items-center gap-2"><span>❌</span> {{ store.errorMessage }}</span>
        <button @click="store.clearError()" class="text-red-400 hover:text-white transition font-bold text-lg p-1">✕</button>
      </div>

      <div v-if="store.statusMessage" class="mb-4 p-3.5 bg-green-500/20 backdrop-blur-xl border border-green-500/30 text-green-200 rounded-xl flex justify-between items-center text-sm">
        <span class="flex items-center gap-2"><span>ℹ️</span> {{ store.statusMessage }}</span>
        <button @click="store.clearStatus()" class="text-green-400 hover:text-white transition font-bold text-lg p-1">✕</button>
      </div>

      <!-- Dashboard Grid Layout -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        
        <!-- Left Column: Controls & Configuration (col-span-7 or 8) -->
        <div class="lg:col-span-7 xl:col-span-8 space-y-6">
          
          <!-- Main Control Card -->
          <div class="bg-slate-950/40 backdrop-blur-xl rounded-2xl border border-white/10 shadow-2xl p-5">
            
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
                  <span class="font-bold text-xs">本地檔案</span>
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
                  <span class="font-bold text-xs">麥克風</span>
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
                  <span class="font-bold text-xs">系統音訊</span>
                  <span class="text-[9px] text-white/40 mt-1 hidden sm:inline-block leading-tight">捕獲系統播放音</span>
                </button>
              </div>
            </div>

            <!-- URL/檔案輸入 -->
            <div v-if="audioSource === 'url' || audioSource === 'file'" class="mb-5">
              <label class="block text-white/80 font-bold mb-1.5 text-xs tracking-wider uppercase">
                {{ audioSource === 'url' ? '🔗 直播 URL' : '📁 檔案路徑' }}
              </label>
              <input
                v-model="urlInput"
                type="text"
                spellcheck="false"
                :placeholder="audioSource === 'url' ? 'https://www.youtube.com/watch?v=... 或 Twitch/X 等' : 'C:\\path\\to\\video.mp4'"
                :disabled="store.isRunning"
                class="w-full px-4 py-2.5 bg-white/5 border border-white/15 rounded-xl text-white placeholder-white/30 focus:outline-none focus:border-blue-500/80 focus:ring-1 focus:ring-blue-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition duration-200 text-sm"
              />
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
            <div class="grid grid-cols-2 gap-4 mb-4">
              <!-- 輸入語言 -->
              <div class="flex flex-col">
                <label class="text-white/60 text-[10px] font-bold tracking-wider uppercase mb-1.5">🎙️ 輸入語言</label>
                <UiSelect
                  v-model="selectedInputLanguage"
                  :options="inputLanguageOptions"
                  :disabled="store.isRunning"
                  button-class="bg-white/5 border border-white/15 hover:bg-white/10 text-xs rounded-xl"
                />
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
                class="text-[10px] text-indigo-400 hover:text-indigo-300 transition flex items-center gap-1 font-semibold"
              >
                <span>{{ showAdvancedConfig ? '▼ 收起進階配置' : '▶ 展開進階配置 (引擎與模型)' }}</span>
              </button>

              <Transition name="fade-slide">
                <div v-show="showAdvancedConfig" class="grid grid-cols-2 gap-4 mt-3 p-3 bg-white/5 rounded-xl border border-white/5">
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
                    <input v-else-if="selectedTranscriptionEngine === 'openai-api'" 
                      value="whisper-1" disabled
                      class="w-full px-3 py-1.5 bg-white/5 border border-white/10 rounded-lg text-white/40 cursor-not-allowed text-[10px]"
                    />
                  </div>

                  <!-- 翻譯後端 -->
                  <div class="flex flex-col col-span-2">
                    <label class="text-white/50 text-[9px] font-bold tracking-wider mb-1">翻譯後端</label>
                    <UiSelect
                      v-model="selectedBackend"
                      :options="backendOptions"
                      :disabled="store.isRunning || !translationEnabled"
                      button-class="bg-white/5 border border-white/10 text-[10px] rounded-lg disabled:opacity-40"
                    />
                  </div>
                </div>
              </Transition>
            </div>

            <!-- 控制按鈕 (啟動/停止 與 字幕視窗) -->
            <div class="flex gap-3">
              <!-- 啟動/停止按鈕 -->
              <button
                v-if="!store.isRunning"
                @click="handleStart"
                :disabled="isLoading || !isConfigReady"
                class="flex-1 bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:from-blue-500 hover:via-indigo-500 hover:to-purple-500 disabled:from-slate-800 disabled:to-slate-900 disabled:text-white/40 disabled:border-white/5 disabled:shadow-none text-white font-bold py-3.5 px-5 rounded-xl transition-all duration-200 active:scale-[0.98] shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2"
              >
                <span class="text-sm font-semibold">{{ isLoading ? '⏳ 啟動中...' : '▶️ 啟動即時轉譯' }}</span>
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

          <!-- Llama 伺服器狀態列 (精簡版) -->
          <div v-if="selectedBackend === 'llama' || llamaStore.isServerRunning" class="p-3 bg-slate-950/40 rounded-2xl border border-white/5 backdrop-blur-md flex items-center justify-between gap-3">
            <div class="flex items-center gap-2.5 min-w-0">
              <div :class="[
                'w-2 h-2 rounded-full relative flex-shrink-0',
                llamaStore.isServerReady ? 'bg-green-400 shadow-md shadow-green-400/50' : 
                llamaStore.isServerRunning ? 'bg-orange-400 animate-pulse' : 'bg-gray-500'
              ]">
                <span v-if="llamaStore.isServerRunning && !llamaStore.isServerReady" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-orange-400 opacity-75"></span>
              </div>
              <div class="min-w-0">
                <h3 class="text-white/80 text-[10px] font-bold tracking-wide">Llama 本地翻譯伺服器</h3>
                <p class="text-white/40 text-[9px] truncate font-mono">
                  {{ 
                    llamaStore.isServerReady ? `就緒 (${llamaStore.currentModel || '未知模型'})` : 
                    llamaStore.isServerRunning ? '正在啟動服務...' : '已停止' 
                  }}
                </p>
              </div>
            </div>
            
            <button
              v-if="!llamaStore.isServerRunning"
              @click="llamaStore.startServer()"
              :disabled="!llamaStore.selectedModelPath || llamaStore.isLoading"
              class="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-800 disabled:text-white/40 disabled:cursor-not-allowed text-white rounded-lg transition font-bold text-[10px] flex items-center gap-1 shadow-sm"
            >
              {{ llamaStore.isLoading ? '⏳' : '🚀' }} 啟動
            </button>
            
            <button
              v-else
              @click="llamaStore.stopServer()"
              :disabled="llamaStore.isLoading"
              class="px-3 py-1.5 bg-red-600/80 hover:bg-red-500 text-white rounded-lg transition font-bold text-[10px] shadow-sm"
            >
              ⏹️ 停止
            </button>
          </div>

        </div>

        <!-- Right Column: Monitoring & Sharing (col-span-5 or 4) -->
        <div class="lg:col-span-5 xl:col-span-4 space-y-6">
          
          <!-- 執行日誌 -->
          <div class="bg-slate-950/40 backdrop-blur-xl rounded-2xl border border-white/10 shadow-2xl p-4 flex flex-col h-[270px]">
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
            <div ref="logContainer" class="flex-1 overflow-y-auto bg-black/40 rounded-xl p-3 font-mono text-[11px] leading-relaxed custom-scrollbar border border-white/5">
              <div v-for="(log, idx) in logs" :key="idx" class="text-green-400/80 mb-1 last:mb-0">{{ log }}</div>
              <div v-if="logs.length === 0" class="text-white/20 h-full flex items-center justify-center italic">暫無執行日誌，等待啟動...</div>
            </div>
          </div>

          <!-- 🌐 公開分享連結 -->
          <div class="bg-slate-950/40 backdrop-blur-xl rounded-2xl border border-indigo-500/20 shadow-2xl p-4">
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
</style>
