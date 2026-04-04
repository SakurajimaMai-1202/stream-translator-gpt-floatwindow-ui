<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { useTranslationStore } from '../stores/translation';
import { translationApi, configApi, serverApi, systemApi, type AudioSource, type AudioDevice, type Config, type FfmpegCheckResult } from '../services/api';
import UiSelect, { type UiSelectOption } from '../components/UiSelect.vue';

const router = useRouter();
const store = useTranslationStore();
import { useLlamaStore } from '../stores/llama';
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

// 音訊來源選擇
const audioSource = ref<AudioSource>('url');
const availableDevices = ref<AudioDevice[]>([]);
const selectedDeviceIndex = ref<number | null>(null);
const isLoadingDevices = ref(false);

// 模型選擇
const whisperModels = ['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3', 'large-v3-turbo'];
const qwen3AsrModels = [
  { value: 'Qwen/Qwen3-ASR-1.7B', label: 'Qwen3-ASR-1.7B (推薦)' },
  { value: 'Qwen/Qwen3-ASR-0.6B', label: 'Qwen3-ASR-0.6B (更快)' }
];
const inputLanguages = [
  { value: 'auto', label: '自動偵測' },
  { value: 'ja', label: '日文' },
  { value: 'en', label: '英文' },
  { value: 'ko', label: '韓文' },
  { value: 'zh', label: '中文' }
];
const outputLanguages = [
  { value: 'Traditional Chinese', label: '繁體中文' },
  { value: 'Simplified Chinese', label: '簡體中文' },
  { value: 'Japanese', label: '日文' },
  { value: 'English', label: '英文' },
  { value: 'Korean', label: '韓文' }
];

const deviceOptions = computed<UiSelectOption[]>(() => {
  const defaultDevice = availableDevices.value.find((d) => d.is_default);
  const nullLabel = defaultDevice
    ? `⭐ 預設: ${defaultDevice.name} (${defaultDevice.sample_rate}Hz)`
    : '自動選擇預設設備';
  const base: UiSelectOption[] = [{ value: null, label: nullLabel }];
  const deviceItems = availableDevices.value.map((device) => ({
    value: device.index,
    label: `[${device.index}] ${device.name} (${device.sample_rate}Hz)`
  }));
  return [...base, ...deviceItems];
});

const transcriptionEngineOptions: UiSelectOption[] = [
  { value: 'faster-whisper', label: 'Faster-Whisper' },
  { value: 'simul-streaming', label: 'SimulStreaming' },
  { value: 'faster-whisper-simul', label: 'Faster-Whisper + SimulStreaming' },
  { value: 'qwen3-asr', label: 'Qwen3-ASR' },
  { value: 'openai-api', label: 'OpenAI API' }
];

const whisperModelOptions = computed<UiSelectOption[]>(() =>
  whisperModels.map((model) => ({ value: model, label: model }))
);

const qwen3AsrModelOptions = computed<UiSelectOption[]>(() =>
  qwen3AsrModels.map((model) => ({ value: model.value, label: model.label }))
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
    { value: 'gemini', label: 'Google Gemini' }
  ];

  const customModels = store.config.translation?.custom_models || [];
  const custom = customModels.map((model) => ({
    value: `custom:${model.name}`,
    label: model.name,
    group: '自訂模型'
  }));

  return [...base, ...custom];
});

const llamaPresetOptions = computed<UiSelectOption[]>(() => {
  const options: UiSelectOption[] = [{ value: '', label: '-- 自訂參數 (未保存) --' }];

  const system = Object.keys(llamaStore.systemPresets).map((name) => ({
    value: name,
    label: name,
    group: '系統預設'
  }));

  const custom = Object.keys(llamaStore.customPresets).map((name) => ({
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
let _homeAutoSaveTimer: ReturnType<typeof setTimeout> | null = null;

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
      use_faster_whisper: engine === 'faster-whisper-simul',
      use_simul_streaming: engine === 'faster-whisper-simul' || engine === 'simul-streaming',
    };
    const inputPatch = {
      ...store.config.input,
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
  
  const requiresUrlInput = audioSource.value === 'url' || audioSource.value === 'file';
  if (requiresUrlInput && !urlInput.value.trim()) {
    warnings.push({
      level: 'warning',
      message: audioSource.value === 'url' ? '未設定直播 URL' : '未設定檔案路徑',
      page: 'input'
    });
  }

  const requiresDeviceSelection = audioSource.value === 'microphone' || audioSource.value === 'system_audio';
  if (requiresDeviceSelection && availableDevices.value.length === 0 && isLoadingDevices.value === false) {
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

const hasErrors = computed(() => configWarnings.value.some(w => w.level === 'error'));
const isConfigReady = computed(() => {
  if (hasErrors.value) return false;

  if (audioSource.value === 'url' || audioSource.value === 'file') {
    return !!urlInput.value.trim();
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
    if (selectedDeviceIndex.value === null) {
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
function applyConfigToRefs(cfg: Config) {
  if (cfg.transcription?.model) {
    selectedWhisperModel.value = cfg.transcription.model;
  }
  if (cfg.transcription?.qwen3_asr_model) {
    selectedQwen3AsrModel.value = cfg.transcription.qwen3_asr_model;
  }
  // 載入轉錄引擎設定
  if (cfg.transcription?.use_qwen3_asr) {
    selectedTranscriptionEngine.value = 'qwen3-asr';
  } else if (cfg.transcription?.use_openai_transcription_api) {
    selectedTranscriptionEngine.value = 'openai-api';
  } else if (cfg.transcription?.use_faster_whisper && cfg.transcription?.use_simul_streaming) {
    selectedTranscriptionEngine.value = 'faster-whisper-simul';
  } else if (cfg.transcription?.use_simul_streaming) {
    selectedTranscriptionEngine.value = 'simul-streaming';
  } else {
    selectedTranscriptionEngine.value = 'faster-whisper';
  }
  if (cfg.transcription?.language) {
    selectedInputLanguage.value = cfg.transcription.language;
  }
  if (cfg.translation?.target_language) {
    selectedOutputLanguage.value = cfg.translation.target_language;
  }
  if (cfg.translation?.backend) {
    selectedBackend.value = cfg.translation.backend;
  }
  // 載入翻譯開關狀態
  translationEnabled.value = cfg.translation?.backend !== 'none';
  subtitleSharingEnabled.value = cfg.server?.enable_subtitle_sharing !== false;
}

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
    await store.loadConfig();
    applyConfigToRefs(store.config);
    store.isConfigInitialized = true;
    addLog('應用程式已初始化');
  } else {
    // 從設定頁或其他頁返回：先刷新 store.config（確保自動保存的基準是最新的）
    await store.loadConfig();
    // 還原使用者先前輸入的狀態
    const s = store.homeInputState;
    urlInput.value = s.urlInput;
    audioSource.value = s.audioSource;
    selectedDeviceIndex.value = s.selectedDeviceIndex;
    selectedTranscriptionEngine.value = s.selectedTranscriptionEngine;
    selectedWhisperModel.value = s.selectedWhisperModel;
    selectedQwen3AsrModel.value = s.selectedQwen3AsrModel;
    selectedInputLanguage.value = s.selectedInputLanguage;
    selectedOutputLanguage.value = s.selectedOutputLanguage;
    selectedBackend.value = s.selectedBackend;
    translationEnabled.value = s.translationEnabled;
    addLog('已還原先前輸入狀態');
    // 若來源需要設備列表，補充載入
    if (audioSource.value === 'microphone' || audioSource.value === 'system_audio') {
      await loadDevices();
    }
  }

  // 初始化完成後，延後建立 watch 避免初始化誤觸發自動保存
  await nextTick();
  watch(
    [
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
    () => debouncedSaveHomeConfig()
  );
});

onBeforeUnmount(() => {
  // 清除未完成的 debounce timer
  if (_homeAutoSaveTimer !== null) {
    clearTimeout(_homeAutoSaveTimer);
    _homeAutoSaveTimer = null;
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
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-slate-900 via-cyan-900 to-slate-900 p-6">
    <div class="max-w-5xl mx-auto">
      <!-- Header -->
      <div class="text-center mb-8">
        <h1 class="text-4xl font-bold text-white mb-2 tracking-wide">
          🎙️ Stream Translator
        </h1>
        <p class="text-blue-300 text-lg">即時字幕翻譯系統</p>
      </div>

      <div v-if="showFfmpegWarning" class="mb-4 p-4 bg-yellow-500/20 border border-yellow-500/50 text-yellow-200 rounded-xl flex justify-between items-start gap-3">
        <div>
          <div class="font-semibold">⚠️ 未偵測到 ffmpeg</div>
          <p class="text-sm text-yellow-100/90 mt-1">
            目前系統找不到 ffmpeg，可先安裝或確認路徑。這不會阻止 UI 啟動，但音訊處理可能失敗。
          </p>
        </div>
        <button @click="ffmpegWarningDismissed = true" class="hover:text-white font-bold text-xl leading-none">✕</button>
      </div>

      <!-- 配置警告面板 -->
      <div v-if="configWarnings.length > 0" class="mb-6 p-4 rounded-xl backdrop-blur-xl"
        :class="hasErrors ? 'bg-red-500/20 border border-red-500/50' : 'bg-yellow-500/20 border border-yellow-500/50'">
        <div class="flex items-center gap-2 mb-2">
          <span class="text-xl">{{ hasErrors ? '❌' : '⚠️' }}</span>
          <span class="font-semibold text-white">配置檢查</span>
        </div>
        <ul class="space-y-1">
          <li v-for="(warning, idx) in configWarnings" :key="idx" 
            class="flex items-center justify-between text-sm"
            :class="warning.level === 'error' ? 'text-red-300' : 'text-yellow-300'">
            <span>{{ warning.message }}</span>
            <button v-if="warning.page" @click="goToWarningPage(warning.page)"
              class="px-3 py-1 bg-white/10 hover:bg-white/20 rounded text-xs transition">
              前往設定
            </button>
          </li>
        </ul>
      </div>

      <div v-else class="mb-6 p-4 rounded-xl backdrop-blur-xl bg-green-500/20 border border-green-500/50">
        <div class="flex items-center gap-2">
          <span class="text-xl">✅</span>
          <span class="font-semibold text-green-300">配置正常，可以啟動</span>
        </div>
      </div>

      <!-- Error/Status Messages -->
      <div v-if="store.errorMessage" class="mb-4 p-4 bg-red-500/30 backdrop-blur-xl border border-red-500/50 text-red-200 rounded-xl flex justify-between items-center">
        <span>{{ store.errorMessage }}</span>
        <button @click="store.clearError()" class="hover:text-white font-bold text-xl">✕</button>
      </div>

      <div v-if="store.statusMessage" class="mb-4 p-4 bg-green-500/30 backdrop-blur-xl border border-green-500/50 text-green-200 rounded-xl flex justify-between items-center">
        <span>{{ store.statusMessage }}</span>
        <button @click="store.clearStatus()" class="hover:text-white font-bold text-xl">✕</button>
      </div>

      <!-- Main Control Panel -->
      <div class="bg-slate-900/90 rounded-2xl border border-white/20 shadow-2xl p-6 mb-6">
        <!-- 音訊來源選擇 -->
        <div class="mb-6">
          <label class="block text-white/80 font-semibold mb-3">🎵 音訊來源</label>
          <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
            <button
              @click="audioSource = 'url'; onAudioSourceChange()"
              :disabled="store.isRunning"
              :class="[
                'px-4 py-3 rounded-xl font-medium transition-all',
                audioSource === 'url' 
                  ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/30' 
                  : 'bg-white/5 text-white/70 hover:bg-white/10 border border-white/20',
                store.isRunning ? 'opacity-50 cursor-not-allowed' : ''
              ]"
            >
              🌐 URL 串流
            </button>
            <button
              @click="audioSource = 'file'; onAudioSourceChange()"
              :disabled="store.isRunning"
              :class="[
                'px-4 py-3 rounded-xl font-medium transition-all',
                audioSource === 'file' 
                  ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/30' 
                  : 'bg-white/5 text-white/70 hover:bg-white/10 border border-white/20',
                store.isRunning ? 'opacity-50 cursor-not-allowed' : ''
              ]"
            >
              📁 本地檔案
            </button>
            <button
              @click="audioSource = 'microphone'; onAudioSourceChange()"
              :disabled="store.isRunning"
              :class="[
                'px-4 py-3 rounded-xl font-medium transition-all',
                audioSource === 'microphone' 
                  ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/30' 
                  : 'bg-white/5 text-white/70 hover:bg-white/10 border border-white/20',
                store.isRunning ? 'opacity-50 cursor-not-allowed' : ''
              ]"
            >
              🎤 麥克風
            </button>
            <button
              @click="audioSource = 'system_audio'; onAudioSourceChange()"
              :disabled="store.isRunning"
              :class="[
                'px-4 py-3 rounded-xl font-medium transition-all',
                audioSource === 'system_audio' 
                  ? 'bg-blue-500 text-white shadow-lg shadow-blue-500/30' 
                  : 'bg-white/5 text-white/70 hover:bg-white/10 border border-white/20',
                store.isRunning ? 'opacity-50 cursor-not-allowed' : ''
              ]"
            >
              🔊 系統音訊
            </button>
          </div>
        </div>

        <!-- URL/檔案輸入 -->
        <div v-if="audioSource === 'url' || audioSource === 'file'" class="mb-6">
          <label class="block text-white/80 font-semibold mb-2">
            {{ audioSource === 'url' ? '直播 URL' : '檔案路徑' }}
          </label>
          <input
            v-model="urlInput"
            type="text"
            spellcheck="false"
            :placeholder="audioSource === 'url' ? 'https://www.youtube.com/watch?v=... 或 Twitch/X 等' : 'C:\\path\\to\\video.mp4'"
            :disabled="store.isRunning"
            class="w-full px-4 py-3 bg-white/5 border-2 border-white/20 rounded-xl text-white placeholder-white/40 focus:outline-none focus:border-blue-400 disabled:opacity-50 disabled:cursor-not-allowed transition"
          />
        </div>

        <!-- 設備選擇 -->
        <div v-if="audioSource === 'microphone' || audioSource === 'system_audio'" class="mb-6">
          <label class="block text-white/80 font-semibold mb-2">
            {{ audioSource === 'microphone' ? '🎤 選擇麥克風' : '🔊 選擇系統音訊設備' }}
          </label>
          <div class="flex gap-3">
            <UiSelect
              v-model="selectedDeviceIndex"
              :options="deviceOptions"
              :disabled="store.isRunning || isLoadingDevices"
              button-class="flex-1 px-4 py-3 border-2 border-white/20 rounded-xl"
            />
            <button
              @click="loadDevices()"
              :disabled="store.isRunning || isLoadingDevices"
              class="px-4 py-3 bg-white/10 hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl transition border border-white/20"
              title="重新整理設備列表"
            >
              {{ isLoadingDevices ? '⏳' : '🔄' }}
            </button>
          </div>
          <p v-if="availableDevices.length > 0" class="text-white/50 text-sm mt-2">
            找到 {{ availableDevices.length }} 個設備
          </p>
        </div>

        <!-- 🔧 新增: 翻譯開關 -->
        <div class="mb-6 p-4 bg-white/5 rounded-xl border border-white/20">
          <div class="flex items-center justify-between">
            <div>
              <label class="block text-white font-semibold mb-1">🌐 翻譯功能</label>
              <p class="text-white/50 text-sm">關閉後僅顯示轉錄文字,不進行翻譯</p>
            </div>
            <button
              @click="translationEnabled = !translationEnabled"
              :disabled="store.isRunning"
              type="button"
              :class="[
                'relative inline-flex h-8 w-16 items-center rounded-full transition-colors',
                translationEnabled ? 'bg-blue-500' : 'bg-gray-600',
                store.isRunning ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
              ]"
            >
              <span
                :class="[
                  'inline-block h-6 w-6 transform rounded-full bg-white transition-transform',
                  translationEnabled ? 'translate-x-9' : 'translate-x-1'
                ]"
              />
            </button>
          </div>
        </div>

        <!-- 基本設定 -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <!-- 轉錄引擎 -->
          <div>
            <label class="block text-white/70 text-sm mb-1">轉錄引擎</label>
            <UiSelect
              v-model="selectedTranscriptionEngine"
              :options="transcriptionEngineOptions"
              :disabled="store.isRunning"
            />
          </div>

          <!-- 模型選擇 (根據引擎動態顯示) -->
          <div>
            <label class="block text-white/70 text-sm mb-1">模型選擇</label>
            <!-- Whisper 模型 (Faster-Whisper, SimulStreaming, 組合模式) -->
            <UiSelect
              v-if="selectedTranscriptionEngine === 'faster-whisper' || selectedTranscriptionEngine === 'simul-streaming' || selectedTranscriptionEngine === 'faster-whisper-simul'"
              v-model="selectedWhisperModel"
              :options="whisperModelOptions"
              :disabled="store.isRunning"
            />
            <!-- Qwen3-ASR 模型 -->
            <UiSelect
              v-else-if="selectedTranscriptionEngine === 'qwen3-asr'"
              v-model="selectedQwen3AsrModel"
              :options="qwen3AsrModelOptions"
              :disabled="store.isRunning"
            />
            <!-- OpenAI API 模型 -->
            <input v-else-if="selectedTranscriptionEngine === 'openai-api'" 
              value="whisper-1" disabled
              class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white/50 cursor-not-allowed">
          </div>

          <!-- 輸入語言 -->
          <div>
            <label class="block text-white/70 text-sm mb-1">輸入語言</label>
            <UiSelect
              v-model="selectedInputLanguage"
              :options="inputLanguageOptions"
              :disabled="store.isRunning"
            />
          </div>

          <!-- 翻譯後端 (保持不變,但移到第4列) -->
          <div>
            <label class="block text-white/70 text-sm mb-1">翻譯模型</label>
            <UiSelect
              v-model="selectedBackend"
              :options="backendOptions"
              :disabled="store.isRunning || !translationEnabled"
            />
          </div>
        </div>

        <!-- 目標語言 (移到獨立一行) -->
        <div class="grid grid-cols-1 gap-4 mb-6">
          <div>
            <label class="block text-white/70 text-sm mb-1">目標語言</label>
            <UiSelect
              v-model="selectedOutputLanguage"
              :options="outputLanguageOptions"
              :disabled="store.isRunning || !translationEnabled"
            />
          </div>
        </div>

        <!-- 控制按鈕 -->
        <div class="flex flex-wrap gap-3 mb-6">
          <button
            v-if="!store.isRunning"
            @click="handleStart"
            :disabled="isLoading || !isConfigReady"
            class="flex-1 min-w-[200px] bg-gradient-to-r from-green-500 to-emerald-600 hover:from-green-600 hover:to-emerald-700 disabled:from-gray-500 disabled:to-gray-600 text-white font-bold py-4 px-6 rounded-xl transition-all shadow-lg shadow-green-500/30"
          >
            {{ isLoading ? '⏳ 啟動中...' : '▶️ 啟動轉譯' }}
          </button>

          <button
            v-else
            @click="handleStop"
            :disabled="isLoading"
            class="flex-1 min-w-[200px] bg-gradient-to-r from-red-500 to-rose-600 hover:from-red-600 hover:to-rose-700 disabled:from-gray-500 disabled:to-gray-600 text-white font-bold py-4 px-6 rounded-xl transition-all shadow-lg shadow-red-500/30"
          >
            {{ isLoading ? '⏳ 停止中...' : '⏹️ 停止翻譯' }}
          </button>

          <button
            @click="goToSettings"
            class="bg-white/10 hover:bg-white/20 text-white font-bold py-4 px-6 rounded-xl transition border border-white/20"
          >
            ⚙️ 設定
          </button>

          <button
            @click="openSubtitleWindow"
            class="bg-gradient-to-r from-blue-500 to-indigo-600 hover:from-blue-600 hover:to-indigo-700 text-white font-bold py-4 px-6 rounded-xl transition-all shadow-lg shadow-blue-500/30"
          >
            🪟 字幕視窗
          </button>

        </div>
        
        <!-- Llama 伺服器控制 (獨立區域) -->
        <div class="mb-6 p-4 bg-slate-800/50 rounded-xl border border-white/10">
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-3">
              <div :class="[
                'w-3 h-3 rounded-full',
                llamaStore.isServerReady ? 'bg-green-400 shadow-lg shadow-green-400/50' : 
                llamaStore.isServerRunning ? 'bg-orange-400 animate-pulse' : 'bg-gray-500'
              ]"></div>
              <div>
                <h3 class="text-white font-bold">🦙 Llama 伺服器</h3>
                <p class="text-white/50 text-xs">
                  {{ 
                    llamaStore.isServerReady ? `就緒 (${llamaStore.currentModel || '未知模型'})` : 
                    llamaStore.isServerRunning ? '啟動中...' : 
                    `已停止${llamaStore.selectedModelPath ? ` (設定: ${getFileName(llamaStore.selectedModelPath)})` : ''}` 
                  }}
                </p>
              </div>
            </div>
            
            <button
              v-if="!llamaStore.isServerRunning"
              @click="llamaStore.startServer()"
              :disabled="!llamaStore.selectedModelPath || llamaStore.isLoading"
              class="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:cursor-not-allowed text-white rounded-lg transition font-medium text-sm flex items-center gap-2"
              :title="!llamaStore.selectedModelPath ? '請先在設定中選擇模型' : ''"
            >
              {{ llamaStore.isLoading ? '⏳' : '🚀' }} 啟動伺服器
            </button>
            
            <button
              v-else
              @click="llamaStore.stopServer()"
              :disabled="llamaStore.isLoading"
              class="px-4 py-2 bg-red-600/80 hover:bg-red-700 text-white rounded-lg transition font-medium text-sm"
            >
              ⏹️ 停止伺服器
            </button>
          </div>

          <div class="mt-3">
            <label class="block text-white/60 text-xs mb-1">⚡ 快速切換配置</label>
            <UiSelect
              v-model="llamaStore.selectedPreset"
              :options="llamaPresetOptions"
              :disabled="llamaStore.isServerRunning"
              button-class="text-sm"
            />
            <div class="flex justify-between items-center mt-1">
              <p v-if="llamaStore.selectedPreset" class="text-white/40 text-xs">
                已選擇: {{ llamaStore.selectedPreset.startsWith('custom:') ? llamaStore.selectedPreset.substring(7) : llamaStore.selectedPreset }}
              </p>
              <p v-if="llamaStore.defaultPreset && llamaStore.defaultPreset === llamaStore.selectedPreset" class="text-yellow-400/60 text-xs">
                ⭐ 預設啟動
              </p>
            </div>
          </div>
        </div>

        <!-- 狀態顯示 -->
        <div class="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/10">
          <div class="flex items-center gap-3">
            <div :class="[
              'w-3 h-3 rounded-full',
              store.isRunning ? 'bg-green-400 animate-pulse shadow-lg shadow-green-400/50' : 'bg-gray-500'
            ]"></div>
            <span class="text-white font-medium">
              狀態: {{ store.isRunning ? '🟢 執行中' : '⚪ 閒置' }}
            </span>
          </div>
          <div v-if="store.currentUrl" class="text-white/50 text-sm truncate max-w-md">
            {{ store.currentUrl }}
          </div>
        </div>
      </div>

      <!-- 執行日誌 -->
      <div class="bg-slate-900/90 rounded-2xl border border-white/20 shadow-2xl p-6 mb-6">
        <h2 class="text-xl font-bold text-white mb-4">📋 執行日誌</h2>
        <div ref="logContainer" class="h-48 overflow-y-auto bg-black/30 rounded-lg p-4 font-mono text-sm">
          <div v-for="(log, idx) in logs" :key="idx" class="text-green-400/80 leading-relaxed">{{ log }}</div>
          <div v-if="logs.length === 0" class="text-white/30">等待執行...</div>
        </div>
      </div>

      <!-- 🌐 公開分享連結 -->
      <div class="bg-slate-900/90 rounded-2xl border border-indigo-500/30 shadow-2xl p-6">
        <div class="flex items-center justify-between mb-1">
          <h2 class="text-xl font-bold text-white">🌐 分享字幕連結</h2>
          <button @click="toggleSubtitleSharing" :disabled="isUpdatingSubtitleSharing"
            class="px-3 py-1 text-xs rounded-lg transition font-medium"
            :class="subtitleSharingEnabled
              ? 'bg-emerald-600 hover:bg-emerald-700 text-white'
              : 'bg-red-600 hover:bg-red-700 text-white'">
            {{ isUpdatingSubtitleSharing ? '更新中...' : (subtitleSharingEnabled ? '分享已啟用' : '分享已關閉') }}
          </button>
        </div>
        <div v-if="subtitleSharingEnabled">
          <p class="text-white/40 text-sm mb-4">公開端口 {{ publicPort }}，僅暴露字幕顯示功能，不含管理設定</p>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div class="flex items-center gap-3 bg-white/5 rounded-xl p-3 border border-white/10">
              <span class="text-2xl">🖥️</span>
              <div class="flex-1 min-w-0">
                <div class="text-white/70 text-xs mb-0.5">電腦版字幕</div>
                <div class="text-white/50 text-xs truncate font-mono">{{ getPublicBase() }}/desktop</div>
              </div>
              <button @click="copyLink('/desktop')"
                class="flex-shrink-0 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm rounded-lg transition font-medium">
                {{ activeCopyPath === '/desktop' ? '✅' : '複製' }}
              </button>
            </div>
            <div class="flex items-center gap-3 bg-white/5 rounded-xl p-3 border border-white/10">
              <span class="text-2xl">📱</span>
              <div class="flex-1 min-w-0">
                <div class="text-white/70 text-xs mb-0.5">手機版字幕</div>
                <div class="text-white/50 text-xs truncate font-mono">{{ getPublicBase() }}/mobile</div>
              </div>
              <button @click="copyLink('/mobile')"
                class="flex-shrink-0 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white text-sm rounded-lg transition font-medium">
                {{ activeCopyPath === '/mobile' ? '✅' : '複製' }}
              </button>
            </div>
          </div>
          <p class="text-white/30 text-xs mt-3">💡 確保防火牆已開放端口 {{ publicPort }} 以允許區網存取</p>
        </div>
        <div v-else class="mt-3 p-3 rounded-lg border border-red-500/40 bg-red-500/10 text-red-200 text-sm">
          字幕分享功能已停用。外部裝置將無法存取 /desktop、/mobile 以及公開字幕 API。
        </div>
      </div>
    </div>
  </div>
</template>
