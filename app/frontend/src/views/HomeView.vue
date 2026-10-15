<script setup lang="ts">
import HomeHeaderStatus from '../components/home/HomeHeaderStatus.vue';
import HomeUpdateNotice from '../components/home/HomeUpdateNotice.vue';
import HomeFfmpegNotice from '../components/home/HomeFfmpegNotice.vue';
import HomeReadinessNotice from '../components/home/HomeReadinessNotice.vue';
import HomeConfigWarnings from '../components/home/HomeConfigWarnings.vue';
import HomeErrorNotice from '../components/home/HomeErrorNotice.vue';
import HomeStatusNotice from '../components/home/HomeStatusNotice.vue';
import HomeAudioSource from '../components/home/HomeAudioSource.vue';
import HomeLanguageSettings from '../components/home/HomeLanguageSettings.vue';
import HomeModelDownload from '../components/home/HomeModelDownload.vue';
import HomeDesktopActions from '../components/home/HomeDesktopActions.vue';
import HomeLocalLlm from '../components/home/HomeLocalLlm.vue';
import HomeSubtitleWindow from '../components/home/HomeSubtitleWindow.vue';
import HomeLogs from '../components/home/HomeLogs.vue';
import HomeSharing from '../components/home/HomeSharing.vue';
import HomeMobileActions from '../components/home/HomeMobileActions.vue';
import type { UiSelectOption } from '../components/UiSelect.vue';
import { writeTextToClipboard } from '../composables/home/homeClipboard';
import { provideHomeContext, type WindowWithPyQt } from '../composables/home/homeContext';
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { useTranslationStore } from '../stores/translation';
import { useLlamaStore } from '../stores/llama';
import { llamaApi } from '../services/llamaApi';
import { useInterfaceModeStore } from '../stores/interfaceMode';
import { simpleAsrModel } from '../utils/simpleAsr';
import { sameLanguage } from '../utils/languageIdentity';
import { usesExternalFamilyEndpoint } from '../utils/translationFamily';
import { useModelDownloadStore } from '../stores/modelDownload';
import { translationApi, configApi, readinessApi, runtimeApi, serverApi, systemApi, type AppUpdateStatus, type AudioSource, type AudioDevice, type ProcessAudioTarget, type Config, type FfmpegCheckResult, type ModelComputeBackend, type ModelEngine, type SourceCheckResult } from '../services/api';
import { useAppSyncEvents } from '../composables/useAppSyncEvents';
import {
  coerceLanguageForModel,
} from '../utils/asrCapabilities';

const router = useRouter();
const interfaceMode = useInterfaceModeStore();
const store = useTranslationStore();
const llamaStore = useLlamaStore();
const modelDownloadStore = useModelDownloadStore();

// 公開端口（分享用）
const publicPort = ref(8765);
const activeCopyPath = ref<string | null>(null);
const subtitleSharingEnabled = ref(true);
const subtitleSharingStatusKnown = ref(false);
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

async function fetchPublicPort() {
  try {
    const data = await serverApi.getInfo();
    subtitleSharingStatusKnown.value = true;
    if (data.public_port) publicPort.value = data.public_port;
    if (typeof data.enable_subtitle_sharing === 'boolean') {
      subtitleSharingEnabled.value = data.enable_subtitle_sharing;
    }
  } catch {
    subtitleSharingStatusKnown.value = false;
  }
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
const isLoading = ref(false);
const isPreparingAsrModel = ref(false);

watch(
  () => store.isRunning && store.asrReady,
  (ready) => {
    (window as WindowWithPyQt).pyqt?.updateNativeRecordingState?.(ready);
  },
  { immediate: true }
);

// 音訊來源選擇
const audioSource = ref<AudioSource>('url');
const availableDevices = ref<AudioDevice[]>([]);
const selectedDeviceIndex = ref<number | null>(null);
const isLoadingDevices = ref(false);
const sourceCheck = ref<SourceCheckResult | null>(null);
const isCheckingSource = ref(false);
const sourceControlsLocked = computed(() => store.isRunning || isLoading.value || isPreparingAsrModel.value || isCheckingSource.value);
const processAudioTargets = ref<ProcessAudioTarget[]>([]);
const selectedProcessTargetKey = ref<string | number | null>(null);
const processAudioSupported = ref(false);
const processAudioMessage = ref('請重新整理視窗清單。');
const isLoadingProcessTargets = ref(false);
const processTargetKey = (target: ProcessAudioTarget) => `${target.window_handle}:${target.process_id}:${target.process_start_time}`;
const selectedProcessTarget = computed(() => processAudioTargets.value.find(target => processTargetKey(target) === selectedProcessTargetKey.value));

async function loadProcessAudioTargets() {
  if (store.isRunning || isLoadingProcessTargets.value) return;
  isLoadingProcessTargets.value = true;
  try {
    const result = await readinessApi.getProcessAudioTargets();
    processAudioSupported.value = result.supported;
    processAudioMessage.value = result.message;
    processAudioTargets.value = result.supported ? result.targets : [];
    if (!selectedProcessTarget.value) selectedProcessTargetKey.value = null;
  } catch (error: any) {
    processAudioSupported.value = false;
    processAudioTargets.value = [];
    selectedProcessTargetKey.value = null;
    processAudioMessage.value = error?.response?.data?.detail || error?.message || '無法讀取視窗清單，請重新整理。';
  } finally { isLoadingProcessTargets.value = false; }
}

watch(selectedProcessTargetKey, () => { sourceCheck.value = null; });

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
const allFunAsrModelOptions: UiSelectOption[] = [
  { value: 'FunAudioLLM/Fun-ASR-Nano-2512', label: 'Fun-ASR Nano（中／英／日）' },
  { value: 'FunAudioLLM/Fun-ASR-MLT-Nano-2512', label: 'Fun-ASR MLT Nano（31 語言）' }
];

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

// 選擇的值
const selectedTranscriptionEngine = ref('faster-whisper');  // 🆕 新增: 轉錄引擎選擇
const selectedAsrComputeBackend = ref('auto');
const selectedWhisperModel = ref('base');
const selectedQwen3AsrModel = ref('Qwen/Qwen3-ASR-1.7B');  // 🆕 新增: Qwen3-ASR 模型
const selectedSenseVoiceModel = ref('iic/SenseVoiceSmall');
const selectedFunAsrModel = ref('FunAudioLLM/Fun-ASR-Nano-2512');
const selectedParakeetModel = ref('nvidia/parakeet-tdt_ctc-0.6b-ja');
const selectedOpenAiTranscriptionModel = ref('whisper-1');
const selectedInputLanguage = ref('auto');
const selectedOutputLanguage = ref('Traditional Chinese');
const selectedBackend = ref('gpt');
const externalFamilyEndpoint = computed(() => usesExternalFamilyEndpoint({
  ...store.config.translation, backend: selectedBackend.value,
}));
const translationEnabled = ref(true);  // 🔧 新增: 翻譯開關
const sameLanguageSelected = computed(() => sameLanguage(
  !interfaceMode.isSimple && selectedTranscriptionEngine.value === 'parakeet-ctc-ja'
    ? parakeetLanguageForModel(selectedParakeetModel.value) : selectedInputLanguage.value,
  selectedOutputLanguage.value,
));
const effectiveTranslationEnabled = computed(() => translationEnabled.value && !sameLanguageSelected.value);
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
const readinessItems = computed(() => [
  { label: '音訊來源', status: sourceCheck.value?.status || 'unknown', detail: sourceCheck.value?.message || '請先選擇來源並執行來源測試' },
  { label: '語音辨識', status: selectedAsrModelDownloaded.value ? 'ready' : (selectedAsrDownloadTask.value?.status === 'failed' ? 'error' : 'unknown'), detail: selectedAsrModelDownloaded.value ? '辨識模型已準備完成' : '請先完成辨識模型設定' },
]);
const showReadinessChecklist = computed(() => readinessItems.value.some(item => item.status !== 'ready'));

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
  if (interfaceMode.isSimple) {
    applySimpleAsr();
    return;
  }
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
    selectedOpenAiTranscriptionModel: cfg.transcription?.openai_transcription_model || 'whisper-1',
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
    selectedOpenAiTranscriptionModel: selectedOpenAiTranscriptionModel.value,
    selectedInputLanguage: selectedInputLanguage.value,
    selectedOutputLanguage: selectedOutputLanguage.value,
    selectedBackend: selectedBackend.value,
    translationEnabled: translationEnabled.value,
    publicPort: publicPort.value,
    subtitleSharingEnabled: subtitleSharingEnabled.value,
  });
}

/** 將 HomeView UI ref 的值逆向映射並批次寫回 config.yaml */
let homeConfigSave: Promise<void> = Promise.resolve();
function saveHomeConfigToBackend(requireSuccess = false) {
  homeConfigSave = homeConfigSave.catch(() => {}).then(() => persistHomeConfigToBackend(requireSuccess));
  return homeConfigSave;
}

async function persistHomeConfigToBackend(requireSuccess = false) {
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
      openai_transcription_model: selectedOpenAiTranscriptionModel.value,
      nemo_asr_dtype: store.config.transcription?.nemo_asr_dtype || 'bfloat16',
      language: !interfaceMode.isSimple && engine === 'parakeet-ctc-ja'
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
    if (requireSuccess) throw e;
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

  if (effectiveTranslationEnabled.value && !externalFamilyEndpoint.value && selectedBackend.value === 'gpt' && !config.translation?.openai_api_key) {
    warnings.push({
      level: 'error',
      message: 'OpenAI API Key 未設定',
      page: 'translation'
    });
  }

  if (effectiveTranslationEnabled.value && !externalFamilyEndpoint.value && selectedBackend.value === 'gemini' && !config.translation?.google_api_key) {
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

  if (audioSource.value === 'process_audio') return processAudioSupported.value && !!selectedProcessTarget.value && !isLoadingProcessTargets.value;

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
  sourceCheck.value = null;
  selectedDeviceIndex.value = null;
  availableDevices.value = [];
  selectedProcessTargetKey.value = null;
  if (audioSource.value === 'process_audio') await loadProcessAudioTargets();

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
    selectedProcessTargetKey.value = null;
    if (audioSource.value === 'process_audio') await loadProcessAudioTargets();
    selectedDeviceIndex.value = cfg.input?.device_index ?? null;
    selectedAsrComputeBackend.value = cfg.transcription?.asr_compute_backend || 'auto';
    selectedWhisperModel.value = cfg.transcription?.model || 'base';
    selectedQwen3AsrModel.value = cfg.transcription?.qwen3_asr_model || 'Qwen/Qwen3-ASR-1.7B';
    selectedSenseVoiceModel.value = cfg.transcription?.sensevoice_model || 'iic/SenseVoiceSmall';
    selectedFunAsrModel.value = cfg.transcription?.fun_asr_model || 'FunAudioLLM/Fun-ASR-Nano-2512';
    selectedParakeetModel.value = cfg.transcription?.nemo_asr_model || 'nvidia/parakeet-tdt_ctc-0.6b-ja';
    selectedOpenAiTranscriptionModel.value = cfg.transcription?.openai_transcription_model || 'whisper-1';
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

function applySimpleAsr() {
  if (!interfaceMode.isSimple || store.isRunning) return;
  selectedAsrComputeBackend.value = 'cpu';
  const model = simpleAsrModel(selectedInputLanguage.value);
  if (model === 'iic/SenseVoiceSmall') {
    selectedTranscriptionEngine.value = 'sensevoice';
    selectedSenseVoiceModel.value = model;
  } else {
    selectedTranscriptionEngine.value = 'parakeet-ctc-ja';
    selectedParakeetModel.value = model || 'nvidia/parakeet-tdt-0.6b-v3';
  }
}

watch([() => interfaceMode.isSimple, selectedInputLanguage, () => store.isRunning], applySimpleAsr);

watch(
  [selectedAsrModelId, () => runtimeCapabilities.value?.asr_model_capabilities],
  () => {
    if (interfaceMode.isSimple) return;
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
  applySimpleAsr();
  (window as WindowWithPyQt).pyqt?.updateNativeRecordingState?.(store.isRunning && store.asrReady);

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
      selectedOpenAiTranscriptionModel,
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
  if (audioSource.value === 'process_audio') {
    await loadProcessAudioTargets();
    if (!processAudioSupported.value || !selectedProcessTarget.value) {
      store.errorMessage = !processAudioSupported.value ? processAudioMessage.value : '請從目前視窗清單重新選擇應用程式。';
      return;
    }
  }
  if (interfaceMode.isSimple) {
    if (!simpleAsrModel(selectedInputLanguage.value)) {
      store.errorMessage = '請選擇簡單模式支援的輸入語言；韓文等未列出的語言請使用進階模式。';
      return;
    }
    applySimpleAsr();
    try {
      await saveHomeConfigToBackend(true);
    } catch {
      store.errorMessage = 'CPU ASR 設定儲存失敗，請重試。';
      return;
    }
  }
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
  } else if (audioSource.value === 'process_audio') {
    addLog(`目標: ${selectedProcessTarget.value?.process_name} — ${selectedProcessTarget.value?.title}`);
  } else {
    addLog(`設備: ${selectedDeviceIndex.value === null ? '自動選擇' : selectedDeviceIndex.value}`);
  }
  addLog(`轉錄引擎: ${selectedTranscriptionEngine.value}`);
  addLog(`模型: ${selectedTranscriptionEngine.value === 'qwen3-asr' ? selectedQwen3AsrModel.value : selectedTranscriptionEngine.value === 'sensevoice' ? selectedSenseVoiceModel.value : selectedTranscriptionEngine.value === 'fun-asr-nano' ? selectedFunAsrModel.value : selectedWhisperModel.value}`);
  addLog(`輸入語言: ${selectedInputLanguage.value}`);
  addLog(`翻譯後端: ${selectedBackend.value}`);
  addLog(`目標語言: ${selectedOutputLanguage.value}`);

  try {
    if (effectiveTranslationEnabled.value && ['llama', 'localllm'].includes(selectedBackend.value) && !externalFamilyEndpoint.value) {
      // A compatible server may have started after launch on the configured port; adopt it first.
      try { await llamaApi.probeServer(); } catch { /* fall back to the cached status */ }
      await llamaStore.refreshServerStatus();
      if (llamaStore.isServerRunning && !llamaStore.isServerReady) {
        addLog('正在等待本機翻譯模型就緒…');
        // Match the store's startup polling limit and interval.
        const maxRetries = 60;
        for (let retries = 0; retries < maxRetries; retries++) {
          await llamaStore.refreshServerStatus();
          if (llamaStore.isServerReady) break;
          if (!llamaStore.isServerRunning) {
            throw new Error(llamaStore.serverStatus.last_error || 'llama.cpp 啟動後立即結束');
          }
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
        if (!llamaStore.isServerReady) {
          throw new Error('伺服器啟動超時，請檢查日誌');
        }
        addLog('本機翻譯模型已就緒');
      } else if (!llamaStore.isServerReady) {
        if (!llamaStore.selectedModelPath) {
          store.errorMessage = '尚未選擇本機翻譯模型，請先到「本地翻譯」頁選擇或下載。';
          return;
        }
        addLog('正在啟動本機翻譯模型…');
        await llamaStore.setLocalLlmEnabled(true);
        addLog('本機翻譯模型已就緒');
      }
    }
    // 使用新的 API 格式
    if (_homeAutoSaveTimer !== null) {
      clearTimeout(_homeAutoSaveTimer);
      _homeAutoSaveTimer = null;
    }
    await saveHomeConfigToBackend(true);
    const result = await translationApi.start({
      audio_source: audioSource.value,
      ...(audioSource.value === 'process_audio' && selectedProcessTarget.value ? {
        process_id: selectedProcessTarget.value.process_id,
        process_start_time: selectedProcessTarget.value.process_start_time,
        window_handle: selectedProcessTarget.value.window_handle,
        process_name: selectedProcessTarget.value.process_name,
        title: selectedProcessTarget.value.title,
      } : {}),
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
      input_language: !interfaceMode.isSimple && selectedTranscriptionEngine.value === 'parakeet-ctc-ja'
        ? parakeetLanguageForModel(selectedParakeetModel.value)
        : selectedInputLanguage.value,
      target_language: translationEnabled.value ? selectedOutputLanguage.value : undefined,
      gpt_model: translationEnabled.value ? store.config.translation?.gpt_model : undefined,
      translation_backend: translationEnabled.value ? selectedBackend.value : undefined,
      translation_enabled: effectiveTranslationEnabled.value
    });

    // 更新 store 狀態
    await store.markSessionStarted();
    store.isRunning = true;
    store.asrReady = false;
    store.currentTaskId = result.task_id;
    if (audioSource.value === 'url' || audioSource.value === 'file') {
      store.currentUrl = urlInput.value;
    } else {
      store.currentUrl = audioSource.value === 'process_audio' ? `${selectedProcessTarget.value?.process_name} — ${selectedProcessTarget.value?.title}` : `${audioSource.value}${selectedDeviceIndex.value !== null ? ` (設備 ${selectedDeviceIndex.value})` : ''}`;
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
    const message = error.response?.data?.detail || error.message || '啟動失敗';
    addLog(`❌ 啟動失敗: ${message}`);
    store.errorMessage = message;
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

provideHomeContext({
  router, store, configWarnings, hasErrors, availableAppUpdate,
  appUpdateNoticeDismissed, openAppUpdateSettings, ffmpegWarningDismissed, interfaceMode, readinessItems,
  goToWarningPage, urlInput, urlInputRef, localFileInputRef, isLoading,
  isPreparingAsrModel, audioSource, availableDevices, selectedDeviceIndex, isLoadingDevices,
  sourceCheck, isCheckingSource, sourceControlsLocked, processAudioTargets, selectedProcessTargetKey,
  processAudioSupported, processAudioMessage, isLoadingProcessTargets, processTargetKey, selectedProcessTarget,
  loadProcessAudioTargets, addLog, loadDevices, onAudioSourceChange, whisperModels,
  qwen3AsrModels, parakeetModels, allFunAsrModelOptions, selectedAsrModelId, selectedAsrCapability,
  selectedTranscriptionEngine, selectedAsrComputeBackend, selectedWhisperModel, selectedQwen3AsrModel, selectedSenseVoiceModel,
  selectedFunAsrModel, selectedParakeetModel, selectedOpenAiTranscriptionModel, selectedInputLanguage, selectedOutputLanguage,
  selectedBackend, translationEnabled, sameLanguageSelected, runtimeCapabilities, allowedTranscriptionEngines,
  allowedFasterWhisperModels, allowedQwen3AsrModels, allowedParakeetModels, modelDownloadStore, selectedDownloadEngine,
  selectedModelComputeBackend, selectedAsrDownloadTask, selectedAsrModelDownloaded, isConfigReady, handleStart,
  handleStop, openSubtitleWindow, llamaStore, externalFamilyEndpoint, logs,
  logContainer, publicPort, activeCopyPath, subtitleSharingEnabled, subtitleSharingStatusKnown,
  isUpdatingSubtitleSharing, getPublicBase, copyLink, toggleSubtitleSharing,
});
</script>

<template>
  <div class="fw-page commercial-page commercial-home mx-auto flex min-h-full max-w-7xl flex-col justify-between p-3 sm:p-5">
    <div>
      <!-- Header Status Bar -->
      <HomeHeaderStatus />

      <!-- System notification blocks -->
      <HomeUpdateNotice v-if="availableAppUpdate && !appUpdateNoticeDismissed" />

      <HomeFfmpegNotice v-if="showFfmpegWarning" />

      <HomeReadinessNotice v-if="showReadinessChecklist" />

      <!-- 配置警告面板 (僅在有警告/錯誤時動態顯示) -->
      <HomeConfigWarnings v-if="configWarnings.length > 0" />

      <!-- Error/Status Messages -->
      <HomeErrorNotice v-if="store.errorMessage" />

      <HomeStatusNotice v-if="store.statusMessage" />

      <!-- Dashboard Grid Layout -->
      <div class="grid grid-cols-1 items-start gap-6 lg:grid-cols-12 lg:items-stretch">

        <!-- Left Column: Controls & Configuration (col-span-7 or 8) -->
        <div class="lg:col-span-7 xl:col-span-8 space-y-6">

          <!-- Main Control Card -->
          <div class="fw-panel rounded-2xl border border-white/10 bg-slate-950/90 p-4 shadow-sm sm:p-5">

            <HomeAudioSource />

            <HomeLanguageSettings />

            <HomeModelDownload v-if="selectedDownloadEngine && (!selectedAsrModelDownloaded || (selectedAsrDownloadTask && ['pending', 'downloading', 'failed'].includes(selectedAsrDownloadTask.status)))" />

            <HomeDesktopActions />

          </div>

          <HomeLocalLlm />

        </div>

        <!-- Right Column: Monitoring & Sharing (col-span-5 or 4) -->
        <div class="home-monitoring flex min-w-0 flex-col gap-6 lg:col-span-5 xl:col-span-4">

          <HomeSubtitleWindow />

          <HomeLogs v-if="!interfaceMode.isSimple" />

          <HomeSharing v-if="!interfaceMode.isSimple" />

        </div>

      </div>
    </div>

    <!-- Reserve real scroll space so the fixed mobile action bar never hides the final card. -->
    <div class="mobile-action-spacer flex-shrink-0 md:hidden" aria-hidden="true"></div>

    <HomeMobileActions />
  </div>
</template>

<style scoped src="../components/home/home-shared.css"></style>
