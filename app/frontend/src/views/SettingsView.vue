<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick, toRaw, defineAsyncComponent } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import axios from 'axios';
import { useTranslationStore } from '../stores/translation';
import { useModelDownloadStore } from '../stores/modelDownload';
import { useLlamaStore } from '../stores/llama';
import UiSelect, { type UiSelectOption } from '../components/UiSelect.vue';
import { useTranscriptionMutex } from '../composables/useTranscriptionMutex';
import { useAppSyncEvents } from '../composables/useAppSyncEvents';
import { runtimeApi, serverApi, type CpuAsrSidecarInstallStatus, type ModelComputeBackend, type ModelEngine } from '../services/api';
import {
  ASR_LANGUAGE_OPTIONS,
  coerceLanguageForModel,
  isModelLanguageCompatible,
  languageOptionsForModel,
} from '../utils/asrCapabilities';

const testingGpt = ref(false);
const testingGemini = ref(false);
const LlamaSettings = defineAsyncComponent(() => import('../components/LlamaSettings.vue'));
const AsrModelGroup = defineAsyncComponent(() => import('../components/AsrModelGroup.vue'));
const WhisperFilterSettings = defineAsyncComponent(() => import('../components/WhisperFilterSettings.vue'));

const autoSaveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle');
const settingsReady = ref(false);
const sharingLanAddresses = ref<string[]>([]);
const copiedSharingUrl = ref('');
let autoSaveStatusTimeout: ReturnType<typeof setTimeout> | null = null;


const router = useRouter();
const route = useRoute();
const store = useTranslationStore();
const modelDownloadStore = useModelDownloadStore();
const llamaStore = useLlamaStore();

const sharingHost = computed(() => {
  const browserHost = window.location.hostname;
  if (browserHost && !['localhost', '127.0.0.1', '::1'].includes(browserHost)) return browserHost;
  return sharingLanAddresses.value[0] || '127.0.0.1';
});
const sharingBaseUrl = computed(() => `http://${sharingHost.value}:${localConfig.value.server.public_port || 8765}`);
const desktopSharingUrl = computed(() => `${sharingBaseUrl.value}/desktop`);
const mobileSharingUrl = computed(() => `${sharingBaseUrl.value}/mobile`);

async function copySharingUrl(url: string) {
  try {
    await navigator.clipboard.writeText(url);
  } catch {
    const input = document.createElement('textarea');
    input.value = url;
    input.style.position = 'fixed';
    input.style.left = '-9999px';
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    input.remove();
  }
  copiedSharingUrl.value = url;
  window.setTimeout(() => {
    if (copiedSharingUrl.value === url) copiedSharingUrl.value = '';
  }, 1800);
}

const allQwenModels = ['Qwen/Qwen3-ASR-0.6B', 'Qwen/Qwen3-ASR-1.7B', 'jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame'];
const legacyQwen3JaModel = 'neosophie/Qwen3-ASR-1.7B-JA';
const qwen3AnimeModel = 'jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame';
const allFasterWhisperModels = ['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3', 'large-v3-turbo'];
const allSenseVoiceModels = ['iic/SenseVoiceSmall'];
const allFunAsrModels = ['FunAudioLLM/Fun-ASR-Nano-2512', 'FunAudioLLM/Fun-ASR-MLT-Nano-2512'];
const allParakeetModels = [
  'nvidia/parakeet-tdt-0.6b-v3',
  'nvidia/parakeet-tdt_ctc-0.6b-ja',
  'nvidia/parakeet-tdt_ctc-1.1b',
  'grider-transwithai/parakeet-ctc-1.1b-ja',
];

const logLevelOptions: UiSelectOption[] = [
  { value: 'DEBUG', label: 'DEBUG' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
];
const sourceTypeOptions: UiSelectOption[] = [
  { value: 'youtube', label: 'YouTube' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'twitch', label: 'Twitch' },
  { value: 'bilibili', label: 'Bilibili' },
  { value: 'x', label: 'X (Twitter)' },
];
const cookiePlatformOptions: UiSelectOption[] = [
  { value: 'youtube', label: 'YouTube' },
  { value: 'tiktok', label: 'TikTok' },
  { value: 'twitter', label: 'X (Twitter)' },
  { value: 'twitch', label: 'Twitch' },
  { value: 'bilibili', label: 'Bilibili' },
];
const cookieBrowserOptions: UiSelectOption[] = [
  { value: 'chrome', label: 'Google Chrome' },
  { value: 'edge', label: 'Microsoft Edge' },
  { value: 'firefox', label: 'Mozilla Firefox' },
  { value: 'brave', label: 'Brave' },
  { value: 'chromium', label: 'Chromium' },
];
const whisperModelSelectOptions = computed<UiSelectOption[]>(() =>
  allFasterWhisperModels
    .filter(m => allowedFasterWhisperModels.value.includes(m))
    .map(m => ({ value: m, label: m }))
);
const allQwen3AsrModelOptions: UiSelectOption[] = [
  { value: 'Qwen/Qwen3-ASR-1.7B', label: 'Qwen3-ASR-1.7B (推薦)' },
  { value: 'Qwen/Qwen3-ASR-0.6B', label: 'Qwen3-ASR-0.6B (更快)' },
  { value: 'jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame', label: 'Qwen3-ASR-1.7B-JA-Anime' },
];
const qwen3AsrModelOptions = computed<UiSelectOption[]>(() =>
  allQwen3AsrModelOptions
    .filter(option => allowedQwen3AsrModels.value.includes(String(option.value)))
    .map(option => ({
      ...option,
      disabled: selectedSettingsAsrCapability.value?.language_mode !== 'fixed'
        && !isModelLanguageCompatible(
          runtimeCapabilities.value?.asr_model_capabilities,
          String(option.value),
          localConfig.value.transcription.language,
        ),
    }))
);
const senseVoiceModelOptions = computed<UiSelectOption[]>(() =>
  allSenseVoiceModels
    .filter(model => allowedSenseVoiceModels.value.includes(model))
    .map(model => ({
      value: model,
      label: 'SenseVoiceSmall（中／粵／英／日／韓）',
      disabled: selectedSettingsAsrCapability.value?.language_mode !== 'fixed'
        && !isModelLanguageCompatible(
          runtimeCapabilities.value?.asr_model_capabilities,
          model,
          localConfig.value.transcription.language,
        ),
    }))
);
const parakeetModelOptions = computed<UiSelectOption[]>(() =>
  allParakeetModels
    .filter(model => allowedParakeetModels.value.includes(model))
    .map(model => ({
      value: model,
      label: model === 'nvidia/parakeet-tdt-0.6b-v3'
        ? 'NVIDIA Parakeet TDT 0.6B v3（25 種語言）'
        : model === 'nvidia/parakeet-tdt_ctc-0.6b-ja'
        ? 'NVIDIA Parakeet 0.6B（日文）'
        : model === 'nvidia/parakeet-tdt_ctc-1.1b'
          ? 'NVIDIA Parakeet 1.1B（英文）'
          : 'parakeet-ctc-1.1b-ja（日文）',
    }))
);
const parakeetDecodingOptions: UiSelectOption[] = [
  { value: 'tdt', label: 'TDT（建議）' },
  { value: 'ctc', label: 'CTC' },
];
const qwen3DtypeOptions: UiSelectOption[] = [
  { value: 'bfloat16', label: 'BF16（建議，速度快、顯存較低）' },
  { value: 'float32', label: 'FP32（相容性高、顯存約兩倍）' },
];
const asrComputeBackendOptions = computed<UiSelectOption[]>(() => {
  const profile = String(runtimeStatus.value?.profile || localConfig.value.runtime?.profile || 'cuda').toLowerCase();
  const gpuLabel = profile === 'rocm' ? 'ROCm GPU 原生 ASR' : 'CUDA GPU 原生 ASR';
  return [
    { value: 'auto', label: `自動（${profile === 'cpu' ? 'CPU' : profile.toUpperCase()}）` },
    { value: 'gpu', label: gpuLabel, disabled: profile === 'cpu' },
    { value: 'cpu', label: 'CPU · Sherpa-ONNX INT8' },
  ];
});
const runtimeDevicePolicyOptions: UiSelectOption[] = [
  { value: 'auto_discrete', label: 'Auto discrete GPU' },
  { value: 'auto_any', label: 'Auto any GPU' },
  { value: 'manual', label: 'Manual' },
  { value: 'cpu', label: 'CPU' },
];
const vadBackendOptions: UiSelectOption[] = [
  { value: 'silero', label: 'Silero VAD' },
  { value: 'firered', label: 'FireRed VAD' },
];
const translationModelFamilyOptions: UiSelectOption[] = [
  { value: 'auto', label: '自動判斷' },
  { value: 'hy_mt2', label: 'Hy-MT2 專用翻譯模型' },
  { value: 'generic_chat', label: '通用聊天模型（Gemma 等）' },
  { value: 'structured_api', label: '結構化 API（OpenAI / Gemini）' },
];
const translationOutputFormatOptions: UiSelectOption[] = [
  { value: 'auto', label: '自動' },
  { value: 'text', label: '純文字' },
  { value: 'json', label: 'JSON' },
];
const fallbackTranscriptionLanguageOptions = ASR_LANGUAGE_OPTIONS;
const targetLanguageOptions: UiSelectOption[] = [
  { value: 'Traditional Chinese', label: '繁體中文' },
  { value: 'Simplified Chinese', label: '簡體中文' },
  { value: 'Japanese', label: '日文' },
  { value: 'English', label: '英文' },
  { value: 'Korean', label: '韓文' },
];

const localConfig = ref<any>({
  general: {
    log_level: 'INFO'
  },
  server: {
    public_port: 8765,
    enable_subtitle_sharing: true
  },
  runtime: {
    profile: 'cuda',
    device_policy: 'auto_discrete',
    device_index: null,
    device_name: '',
    allow_integrated_gpu: false
  },
  models: {
    storage_path: ''
  },
  input: {
    url: '',
    source_type: 'youtube',
    format: 'ba/wa*',
    cookies: '',
    cookies_by_site: {
      youtube: '',
      tiktok: '',
      twitter: '',
      twitch: '',
      bilibili: ''
    },
    proxy: '',
    timeout: 30,
    device_recording_interval: 0.1
  },
  audio_slicing_vad: {
    min_audio_length: 0.7,
    max_audio_length: 6.0,
    target_audio_length: 3.0,
    continuous_no_speech_threshold: 0.5,
    disable_dynamic_no_speech_threshold: false,
    prefix_retention_length: 0.25,
    vad_enabled: true,
    vad_threshold: 0.35,
    disable_dynamic_vad_threshold: false,
    vad_every_n_frames: 1,
    vad_backend: 'firered',
    firered_vad_model_path: ''
  },
  transcription: {
    openai_api_key: '',
    asr_compute_backend: 'auto',
    model: 'base',
    language: 'auto',
    transcription_initial_prompt: '',
    disable_transcription_context: false,
    use_faster_whisper: false,
    use_simul_streaming: false,
    use_openai_transcription_api: false,
    use_qwen3_asr: false,
    use_sensevoice_asr: false,
    use_nemo_asr: false,
    qwen3_asr_model: 'Qwen/Qwen3-ASR-1.7B',
    qwen3_dtype: 'bfloat16',
    qwen3_load_in_4bit: false,
    sensevoice_model: 'iic/SenseVoiceSmall',
    nemo_asr_model: 'nvidia/parakeet-tdt_ctc-0.6b-ja',
    nemo_asr_device: 'auto',
    nemo_asr_decoding: 'tdt',
    nemo_asr_dtype: 'bfloat16',
    asr_corrections_enabled: false,
    asr_correction_log_enabled: false,
    asr_correction_learning_enabled: false,
    asr_corrections_case_sensitive: false,
    asr_correction_rules: [],
    openai_transcription_model: 'whisper-1',
    whisper_filters: ['emoji_filter', 'repetition_filter']
  },
  translation: {
    openai_api_key: '',
    google_api_key: '',
    backend: 'gpt',
    target_language: 'Traditional Chinese',
    gpt_model: 'gpt-4o-mini',
    gemini_model: 'gemini-2.0-flash-exp',
    gpt_base_url: 'https://api.openai.com/v1',
    gemini_base_url: 'https://generativelanguage.googleapis.com',
    translation_history_size: 0,
    translation_timeout: 10,
    processing_proxy: '',
    use_json_result: false,
    translation_model_family: 'auto',
    translation_output_format: 'auto',
    translation_max_concurrency: 0,
    translation_max_output_tokens: 128,
    paired_subtitle_mode: true,
    deduplicate_asr_overlap: true,
    subtitle_assembler_enabled: true,
    subtitle_assembler_wait_ms: 400,
    subtitle_assembler_max_duration: 6.0,
    subtitle_assembler_gap_threshold: 0.8,
    use_smart_prompt: true,
    smart_prompt_enabled: true,
    translation_prompt: '',
    custom_models: []
  },
  terminology: {
    use_terminology_glossary: false,  // 🔧 新增: 術語表啟用開關
    translation_glossary_audit_enabled: false,
    glossary: '',
    glossary_list: []
  },
  output: {
    output_dir: './output',
    output_srt: true,
    output_txt: false,
    output_ass: false,
    max_history: 20
  },
  output_notification: {
    discord_enabled: false,
    discord_webhook_url: '',
    telegram_enabled: false,
    telegram_bot_token: '',
    telegram_chat_id: '',
    output_file_path: '',
    hide_transcribe_result: false
  },
  ui: {
    theme: 'dark'
  }
});
const isSaving = ref(false);
const cookiePlatform = ref('youtube');
const cookieBrowser = ref('chrome');
const cookieBrowserProfile = ref('');
const cookieImporting = ref(false);
const cookieFileInput = ref<HTMLInputElement | null>(null);
const cookieImportResult = ref<{ type: 'success' | 'error'; message: string } | null>(null);
const selectedPlatformCookiePath = computed(() =>
  localConfig.value?.input?.cookies_by_site?.[cookiePlatform.value] || ''
);
const funAsrModelOptions = computed<UiSelectOption[]>(() =>
  allFunAsrModels
    .filter(model => allowedFunAsrModels.value.includes(model))
    .map(model => ({
      value: model,
      label: model.endsWith('MLT-Nano-2512')
        ? 'Fun-ASR MLT Nano（31 種語言）'
        : 'Fun-ASR Nano（中文／英文／日文）',
      disabled: selectedSettingsAsrCapability.value?.language_mode !== 'fixed'
        && !isModelLanguageCompatible(
          runtimeCapabilities.value?.asr_model_capabilities,
          model,
          localConfig.value.transcription.language,
        ),
    }))
);
const selectedBrowserMayLockCookies = computed(() =>
  ['chrome', 'edge', 'brave', 'chromium'].includes(cookieBrowser.value)
);
watch(cookiePlatform, () => {
  cookieImportResult.value = null;
});

async function importCookiesFromBrowser() {
  cookieImporting.value = true;
  cookieImportResult.value = null;
  try {
    const response = await axios.post('/api/cookies/import-browser', {
      platform: cookiePlatform.value,
      browser: cookieBrowser.value,
      profile: cookieBrowserProfile.value.trim(),
    });
    const result = response.data?.data;
    if (!localConfig.value.input.cookies_by_site) {
      localConfig.value.input.cookies_by_site = {};
    }
    localConfig.value.input.cookies_by_site[cookiePlatform.value] = result.path;
    cookieImportResult.value = {
      type: 'success',
      message: `${result.platform_label} Cookies 已更新（${result.cookie_count} 筆）`,
    };
  } catch (error: any) {
    cookieImportResult.value = {
      type: 'error',
      message: error.response?.data?.detail || error.message || 'Cookies 更新失敗',
    };
  } finally {
    cookieImporting.value = false;
  }
}

function selectCookieFile() {
  cookieFileInput.value?.click();
}

async function importCookiesFromFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;

  cookieImporting.value = true;
  cookieImportResult.value = null;
  try {
    const formData = new FormData();
    formData.append('platform', cookiePlatform.value);
    formData.append('cookie_file', file);
    const response = await axios.post('/api/cookies/import-file', formData);
    const result = response.data?.data;
    if (!localConfig.value.input.cookies_by_site) {
      localConfig.value.input.cookies_by_site = {};
    }
    localConfig.value.input.cookies_by_site[cookiePlatform.value] = result.path;
    cookieImportResult.value = {
      type: 'success',
      message: `${result.platform_label} Cookies 已匯入（${result.cookie_count} 筆）`,
    };
  } catch (error: any) {
    cookieImportResult.value = {
      type: 'error',
      message: error.response?.data?.detail || error.message || 'cookies.txt 匯入失敗',
    };
  } finally {
    cookieImporting.value = false;
    input.value = '';
  }
}
const settingsTabIds = new Set([
  'general',
  'input',
  'output',
  'audio_vad',
  'transcription',
  'model_management',
  'translation',
  'llama',
  'terminology',
]);

function normalizeSettingsTab(tab: unknown): string {
  const value = Array.isArray(tab) ? tab[0] : tab;
  return typeof value === 'string' && settingsTabIds.has(value) ? value : 'general';
}

const activeTab = ref(normalizeSettingsTab(route.query.tab));
const isApplyingRemoteConfig = ref(false);

function syncActiveTabFromRoute(tab: unknown = route.query.tab) {
  const normalized = normalizeSettingsTab(tab);
  if (activeTab.value !== normalized) {
    activeTab.value = normalized;
  }
}

const translationBackendOptions = computed<UiSelectOption[]>(() => {
  const base: UiSelectOption[] = [
    { value: 'none', label: '不翻譯' },
    { value: 'gpt', label: 'OpenAI GPT' },
    { value: 'gemini', label: 'Google Gemini' },
    { value: 'llama', label: '🦙 Llama (本地)' },
  ];
  const customModels: any[] = localConfig.value?.translation?.custom_models || [];
  const customOptions: UiSelectOption[] = customModels.map((m: any) => ({
    value: `custom:${m.name}`,
    label: m.name,
    group: '自訂模型',
  }));
  return [...base, ...customOptions];
});

// Each config section saves independently so a small UI edit does not traverse,
// serialize, replace, and re-render the complete configuration tree.
const sectionSaveTimers = new Map<string, ReturnType<typeof setTimeout>>();
const sectionSaveInFlight = new Map<string, Promise<void>>();

function markAutoSaveCompleted() {
  autoSaveStatus.value = 'saved';
  if (autoSaveStatusTimeout) clearTimeout(autoSaveStatusTimeout);
  autoSaveStatusTimeout = setTimeout(() => {
    autoSaveStatus.value = 'idle';
  }, 3000);
}

async function saveSectionNow(section: string): Promise<void> {
  const existing = sectionSaveInFlight.get(section);
  if (existing) await existing;
  const sectionSnapshot = structuredClone(toRaw(localConfig.value[section] ?? {}));
  const runtimeChanged = section === 'runtime'
    && !configsEqual(store.config.runtime, sectionSnapshot);
  const asrComputeChanged = section === 'transcription'
    && store.config.transcription?.asr_compute_backend !== sectionSnapshot.asr_compute_backend;
  const request = (async () => {
    try {
      await store.saveConfigSection(section, sectionSnapshot);
      if (runtimeChanged || asrComputeChanged) await store.loadRuntimeStatus();
      markAutoSaveCompleted();
    } catch (e) {
      console.warn(`[SettingsView] ${section} 自動保存失敗:`, e);
      autoSaveStatus.value = 'error';
      throw e;
    } finally {
      sectionSaveInFlight.delete(section);
    }
  })();
  sectionSaveInFlight.set(section, request);
  await request;
}

function debouncedAutoSaveSection(section: string) {
  autoSaveStatus.value = 'saving';
  const currentTimer = sectionSaveTimers.get(section);
  if (currentTimer) clearTimeout(currentTimer);
  sectionSaveTimers.set(section, setTimeout(() => {
    sectionSaveTimers.delete(section);
    void saveSectionNow(section);
  }, 1000));
}

async function flushPendingSectionSaves() {
  const pendingSections = [...sectionSaveTimers.keys()];
  for (const timer of sectionSaveTimers.values()) clearTimeout(timer);
  sectionSaveTimers.clear();
  await Promise.all(pendingSections.map((section) => saveSectionNow(section)));
  await Promise.all(sectionSaveInFlight.values());
}

async function testConnection(backend: 'gpt' | 'gemini') {
  const isGpt = backend === 'gpt';
  if (isGpt) {
    testingGpt.value = true;
  } else {
    testingGemini.value = true;
  }
  
  try {
    const apiKey = isGpt
      ? localConfig.value.translation.openai_api_key
      : localConfig.value.translation.google_api_key;
      
    const baseUrl = isGpt ? localConfig.value.translation.gpt_base_url : localConfig.value.translation.gemini_base_url;
    const proxy = localConfig.value.translation.processing_proxy || localConfig.value.input.proxy;

    if (!apiKey) {
      alert(`請先輸入 ${isGpt ? 'OpenAI' : 'Gemini'} API 金鑰`);
      return;
    }

    const res = await axios.post('/api/config/test-connection', {
      backend,
      api_key: apiKey,
      base_url: baseUrl || null,
      proxy: proxy || null
    });
    
    if (res.data && res.data.success) {
      alert(`✓ ${isGpt ? 'OpenAI' : 'Gemini'} 連線測試成功！`);
    } else {
      alert(`❌ 連線測試失敗：${res.data?.message || '未知錯誤'}`);
    }
  } catch (err: any) {
    alert(`❌ 連線測試發生異常：${err.response?.data?.detail || err.message}`);
  } finally {
    if (isGpt) {
      testingGpt.value = false;
    } else {
      testingGemini.value = false;
    }
  }
}

// 術語表
const newTermOriginal = ref('');
const newTermTranslated = ref('');
const termSearchQuery = ref('');
const newAsrCanonical = ref('');
const newAsrAliases = ref('');
const asrCorrectionSearchQuery = ref('');
const LARGE_LIST_BATCH_SIZE = 100;
const glossaryRenderLimit = ref(LARGE_LIST_BATCH_SIZE);
const asrCorrectionRenderLimit = ref(LARGE_LIST_BATCH_SIZE);

// 自訂模型
const showCustomModelDialog = ref(false);
const editingModelIndex = ref(-1);
const customModelForm = ref({
  name: '',
  base_url: '',
  api_key: '',
  model_name: ''
});

const categorizedTabs = [
  {
    groupName: '系統與輸入',
    items: [
      { id: 'general', name: '一般設定', icon: '⚙️' },
      { id: 'input', name: '輸入選項', icon: '📥' },
      { id: 'output', name: '輸出與通知', icon: '📤' }
    ]
  },
  {
    groupName: '語音辨識與切片',
    items: [
      { id: 'audio_vad', name: '音訊切片/VAD', icon: '🔊' },
      { id: 'transcription', name: '轉錄選項', icon: '🎤' },
      { id: 'model_management', name: 'ASR模型管理', icon: '📦' }
    ]
  },
  {
    groupName: '翻譯與術語',
    items: [
      { id: 'translation', name: '翻譯選項', icon: '🌐' },
      { id: 'llama', name: 'Llama 設定', icon: '🦙' },
      { id: 'terminology', name: '術語表', icon: '📖' }
    ]
  }
];


// 過濾後的術語表
const filteredGlossary = computed(() => {
  const list = localConfig.value.terminology?.glossary_list || [];
  if (!termSearchQuery.value.trim()) return list;
  const query = termSearchQuery.value.toLowerCase();
  return list.filter((item: any) => 
    item.original?.toLowerCase().includes(query) ||
    item.translated?.toLowerCase().includes(query)
  );
});

const filteredAsrCorrections = computed(() => {
  const rules = localConfig.value.transcription?.asr_correction_rules || [];
  const query = asrCorrectionSearchQuery.value.trim().toLowerCase();
  if (!query) return rules;
  return rules.filter((rule: any) =>
    rule.canonical?.toLowerCase().includes(query) ||
    (rule.aliases || []).some((alias: string) => alias.toLowerCase().includes(query))
  );
});

// 互斥邏輯: 轉錄引擎互斥規則
const runtimeStatus = computed(() => store.runtimeStatus);
const asrComputeBackendLocked = computed(() => runtimeStatus.value?.profile === 'cpu');
const runtimeCapabilities = computed(() => runtimeStatus.value?.asr_capabilities || runtimeStatus.value?.capabilities || null);
const effectiveAsrComputeBackend = computed(() =>
  runtimeStatus.value?.effective_asr_compute_backend
    || (localConfig.value.transcription?.asr_compute_backend === 'cpu' ? 'cpu' : 'gpu')
);
const isSherpaOnnxMode = computed(() => effectiveAsrComputeBackend.value === 'cpu');
const effectiveRuntimeKind = computed(() => {
  if (isSherpaOnnxMode.value) return 'CPU';
  return String(runtimeStatus.value?.profile || localConfig.value.runtime?.profile || 'cuda').toUpperCase() === 'ROCM'
    ? 'ROCm'
    : 'CUDA';
});
const effectiveAsrRuntimeLabel = computed(() =>
  isSherpaOnnxMode.value ? 'CPU · Sherpa-ONNX INT8' : `${effectiveRuntimeKind.value} · GPU 原生 ASR`
);
const packageProfileLabel = computed(() => {
  const profile = String(runtimeStatus.value?.profile || localConfig.value.runtime?.profile || 'unknown').toLowerCase();
  if (profile === 'cuda') return 'CUDA 套件';
  if (profile === 'rocm') return 'ROCm 套件（Experimental）';
  if (profile === 'cpu') return 'CPU 套件';
  return profile.toUpperCase();
});
const modelManagementBackend = ref<ModelComputeBackend>(effectiveAsrComputeBackend.value);
const cpuQwenModels = ['Qwen/Qwen3-ASR-0.6B'];
const cpuSenseVoiceModels = ['iic/SenseVoiceSmall'];
const cpuFunAsrModels = ['FunAudioLLM/Fun-ASR-Nano-2512'];
const cpuParakeetModels = ['nvidia/parakeet-tdt-0.6b-v3', 'nvidia/parakeet-tdt_ctc-0.6b-ja'];
const cpuQwenDescriptions = {
  'Qwen/Qwen3-ASR-0.6B': 'Sherpa-ONNX 專用 INT8 ONNX bundle；CPU 離線推論，不使用 PyTorch、CUDA dtype 或 4-bit 設定。',
};
const cpuSenseVoiceDescriptions = {
  'iic/SenseVoiceSmall': 'Sherpa-ONNX INT8 多語言模型，支援中文、英文、日文、韓文與粵語；CPU 離線推論。',
};
const cpuFunAsrDescriptions = {
  'FunAudioLLM/Fun-ASR-Nano-2512': 'Sherpa-ONNX INT8 CPU bundle，支援中文、英文、日文及中文方言；目前不提供時間戳。',
};
const cpuParakeetDescriptions = {
  'nvidia/parakeet-tdt-0.6b-v3': 'Sherpa-ONNX INT8 TDT bundle；支援 25 種語言及自動語言辨識，不需要 NVIDIA GPU 或 NeMo。',
  'nvidia/parakeet-tdt_ctc-0.6b-ja': 'Sherpa-ONNX INT8 CTC 日文專用 bundle；語言固定為日文，不需要 NVIDIA GPU 或 NeMo。',
};
const gpuQwenModels = computed(() => runtimeStatus.value?.capabilities?.qwen3_asr_model_ids || allQwenModels);
const gpuSenseVoiceModels = computed(() => runtimeStatus.value?.capabilities?.sensevoice_model_ids || allSenseVoiceModels);
const gpuFunAsrModels = computed(() => runtimeStatus.value?.capabilities?.fun_asr_model_ids || allFunAsrModels);
const gpuParakeetModels = computed(() => runtimeStatus.value?.capabilities?.parakeet_model_ids || allParakeetModels);
const gpuFasterWhisperModels = computed(() => runtimeStatus.value?.capabilities?.faster_whisper_model_ids || allFasterWhisperModels);
const managedDownloadedModels = computed(() =>
  modelDownloadStore.downloadedModels.filter((item) => item.compute_backend === modelManagementBackend.value)
);
const cpuAsrRuntimeAvailable = computed(() => Boolean(runtimeStatus.value?.cpu_asr_runtime?.available));
const cpuAsrSidecarStatus = ref<CpuAsrSidecarInstallStatus | null>(null);
const cpuAsrSidecarBusy = computed(() =>
  ['starting', 'downloading', 'verifying', 'installing'].includes(cpuAsrSidecarStatus.value?.status || '')
);
const canInstallCpuAsrSidecar = computed(() =>
  ['cuda', 'rocm'].includes(runtimeStatus.value?.profile || '')
  && !cpuAsrSidecarStatus.value?.installed
  && !cpuAsrSidecarBusy.value
);
let cpuAsrSidecarPollTimer: ReturnType<typeof setInterval> | null = null;

function stopCpuAsrSidecarPolling() {
  if (cpuAsrSidecarPollTimer) clearInterval(cpuAsrSidecarPollTimer);
  cpuAsrSidecarPollTimer = null;
}

async function refreshCpuAsrSidecarStatus() {
  try {
    cpuAsrSidecarStatus.value = await runtimeApi.getCpuAsrSidecarStatus();
  } catch (error: any) {
    cpuAsrSidecarStatus.value = {
      status: 'error', progress: 0, message: '', installed: false, restart_required: false,
      bytes_downloaded: 0, bytes_total: 0, version: '', asset_name: '',
      error: error?.response?.data?.detail || error?.message || '無法取得 sidecar 狀態',
    };
  }
  if (!cpuAsrSidecarBusy.value) {
    stopCpuAsrSidecarPolling();
    if (cpuAsrSidecarStatus.value.installed) await store.loadRuntimeStatus();
  }
}

async function installCpuAsrSidecar() {
  try {
    cpuAsrSidecarStatus.value = await runtimeApi.installCpuAsrSidecar();
  } catch (error: any) {
    cpuAsrSidecarStatus.value = {
      status: 'error', progress: 0, message: '', installed: false, restart_required: false,
      bytes_downloaded: 0, bytes_total: 0, version: '', asset_name: '',
      error: error?.response?.data?.detail || error?.message || '無法啟動 sidecar 安裝',
    };
    return;
  }
  stopCpuAsrSidecarPolling();
  cpuAsrSidecarPollTimer = setInterval(() => void refreshCpuAsrSidecarStatus(), 1000);
}
const selectedSettingsAsrModelId = computed<string>(() => {
  const transcription = localConfig.value.transcription;
  if (transcription.use_qwen3_asr) return transcription.qwen3_asr_model;
  if (transcription.use_sensevoice_asr) return transcription.sensevoice_model;
  if (transcription.use_fun_asr) return transcription.fun_asr_model;
  if (transcription.use_nemo_asr) return transcription.nemo_asr_model;
  return transcription.model;
});
const visibleGlossary = computed(() => filteredGlossary.value.slice(0, glossaryRenderLimit.value));
const visibleAsrCorrections = computed(() => filteredAsrCorrections.value.slice(0, asrCorrectionRenderLimit.value));

watch(termSearchQuery, () => {
  glossaryRenderLimit.value = LARGE_LIST_BATCH_SIZE;
});
watch(asrCorrectionSearchQuery, () => {
  asrCorrectionRenderLimit.value = LARGE_LIST_BATCH_SIZE;
});
const selectedSettingsAsrCapability = computed(() =>
  runtimeCapabilities.value?.asr_model_capabilities?.find(
    (item) => item.model_id === selectedSettingsAsrModelId.value
  )
);
const transcriptionLanguageOptions = computed<UiSelectOption[]>(() => {
  const options = languageOptionsForModel(
    runtimeCapabilities.value?.asr_model_capabilities,
    selectedSettingsAsrModelId.value,
  );
  return options.length > 0 ? options : fallbackTranscriptionLanguageOptions;
});
const isTranscriptionLanguageLocked = computed(
  () => selectedSettingsAsrCapability.value?.language_mode === 'fixed'
);
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
const canUseFasterWhisper = computed(() => allowedLocalAsrEngines.value.includes('faster-whisper'));
const canUseSimulStreaming = computed(() => allowedLocalAsrEngines.value.includes('simul-streaming'));
const canUseFasterWhisperSimul = computed(() => allowedLocalAsrEngines.value.includes('faster-whisper-simul'));
const canUseQwen3Asr = computed(() => allowedLocalAsrEngines.value.includes('qwen3-asr'));
const canUseSenseVoice = computed(() => allowedLocalAsrEngines.value.includes('sensevoice'));
const canUseFunAsr = computed(() => allowedLocalAsrEngines.value.includes('fun-asr-nano'));
const canUseParakeet = computed(() => allowedLocalAsrEngines.value.includes('parakeet-ctc-ja'));
const canUseOpenAiAsr = computed(() => allowedRemoteAsrEngines.value.includes('openai-api'));
const allowedFasterWhisperModels = computed<string[]>(() =>
  runtimeCapabilities.value?.faster_whisper_model_ids?.length
    ? runtimeCapabilities.value.faster_whisper_model_ids
    : allFasterWhisperModels
);
const allowedQwen3AsrModels = computed<string[]>(() =>
  runtimeCapabilities.value?.qwen3_asr_model_ids?.length
    ? runtimeCapabilities.value.qwen3_asr_model_ids
    : allQwenModels
);
const allowedSenseVoiceModels = computed<string[]>(() =>
  runtimeCapabilities.value?.sensevoice_model_ids?.length
    ? runtimeCapabilities.value.sensevoice_model_ids
    : allSenseVoiceModels
);
const allowedFunAsrModels = computed<string[]>(() =>
  runtimeCapabilities.value?.fun_asr_model_ids?.length
    ? runtimeCapabilities.value.fun_asr_model_ids
    : allFunAsrModels
);
const allowedParakeetModels = computed<string[]>(() =>
  runtimeCapabilities.value?.parakeet_model_ids?.length
    ? runtimeCapabilities.value.parakeet_model_ids
    : allParakeetModels
);

const qwenModelList = computed(() =>
  allQwenModels.filter(modelId => allowedQwen3AsrModels.value.includes(modelId))
);
const fasterWhisperModelList = computed(() =>
  allFasterWhisperModels.filter(modelId => allowedFasterWhisperModels.value.includes(modelId))
);
const senseVoiceModelList = computed(() =>
  allSenseVoiceModels.filter(modelId => allowedSenseVoiceModels.value.includes(modelId))
);
const funAsrModelList = computed(() =>
  allFunAsrModels.filter(modelId => allowedFunAsrModels.value.includes(modelId))
);
const parakeetModelList = computed(() =>
  allParakeetModels.filter(modelId => allowedParakeetModels.value.includes(modelId))
);
const runtimeSelection = computed(() => runtimeStatus.value?.selection || null);
const selectedRuntimeDevice = computed(() => runtimeSelection.value?.device || null);
const ignoredRuntimeDevices = computed(() => runtimeSelection.value?.ignored_devices || []);
const runtimeStatusLabel = computed(() => {
  const status = runtimeStatus.value?.status || 'unknown';
  if (status === 'official') return 'Official';
  if (status === 'compatibility') return 'Compatibility';
  if (status === 'experimental') return 'Experimental';
  return status;
});
const runtimeDiagnosticNotice = computed(() => {
  const profile = runtimeStatus.value?.profile || localConfig.value?.runtime?.profile;
  if (profile !== 'rocm') return '';
  if (runtimeSelection.value?.kind === 'gpu') {
    return 'ROCm package/profile is selected. Run diagnose_runtime.ps1 on an AMD GPU machine to confirm HIP GPU execution; ASR inference is still not marked verified by package validation alone.';
  }
  return 'ROCm package/profile is selected, but no suitable AMD discrete GPU is selected on this machine. Package validation can still pass; ROCm GPU inference remains unverified until diagnose_runtime.ps1 passes on AMD hardware.';
});

function formatRuntimeMemory(memoryMb: number | null | undefined): string {
  if (!memoryMb) return 'unknown VRAM';
  if (memoryMb >= 1024) return `${(memoryMb / 1024).toFixed(1)} GB VRAM`;
  return `${memoryMb} MB VRAM`;
}

function runtimeDeviceLine(device: any): string {
  if (!device) return 'None';
  const integrated = device.is_integrated ? 'integrated' : 'discrete';
  const details = [formatRuntimeMemory(device.memory_mb), integrated];
  if (device.arch_name) details.push(device.arch_name);
  if (device.is_supported_by_torch === false) details.push('unsupported by torch');
  if (device.is_supported_by_torch === true) details.push('torch supported');
  if (device.is_supported_by_torch === null || device.is_supported_by_torch === undefined) details.push('torch support unknown');
  if (device.source === 'runtime_python') details.push('runtime probe');
  if (device.source === 'win32_video_controller') details.push('Windows estimate');
  return `${device.name} (${details.join(', ')})`;
}

function coerceAsrSettingsForRuntime() {
  const transcription = localConfig.value.transcription || {};
  if (!canUseFasterWhisper.value) {
    transcription.use_faster_whisper = false;
  }
  if (!canUseSimulStreaming.value && !canUseFasterWhisperSimul.value) {
    transcription.use_simul_streaming = false;
  }
  if (!canUseQwen3Asr.value) {
    transcription.use_qwen3_asr = false;
  }
  if (!canUseSenseVoice.value) {
    transcription.use_sensevoice_asr = false;
  }
  if (!canUseParakeet.value) {
    transcription.use_nemo_asr = false;
  }
  if (!canUseOpenAiAsr.value) {
    transcription.use_openai_transcription_api = false;
  }
  if (!allowedFasterWhisperModels.value.includes(transcription.model)) {
    transcription.model = allowedFasterWhisperModels.value[0] || 'small';
  }
  if (transcription.qwen3_asr_model === legacyQwen3JaModel) {
    transcription.qwen3_asr_model = qwen3AnimeModel;
  }
  if (!canUseFunAsr.value) {
    transcription.use_fun_asr = false;
  }
  if (!allowedQwen3AsrModels.value.includes(transcription.qwen3_asr_model)) {
    transcription.qwen3_asr_model = allowedQwen3AsrModels.value[0] || 'Qwen/Qwen3-ASR-0.6B';
  }
  if (!allowedSenseVoiceModels.value.includes(transcription.sensevoice_model)) {
    transcription.sensevoice_model = allowedSenseVoiceModels.value[0] || 'iic/SenseVoiceSmall';
  }
  if (!allowedFunAsrModels.value.includes(transcription.fun_asr_model)) {
    transcription.fun_asr_model = allowedFunAsrModels.value[0] || 'FunAudioLLM/Fun-ASR-Nano-2512';
  }
  if (!allowedParakeetModels.value.includes(transcription.nemo_asr_model)) {
    transcription.nemo_asr_model = allowedParakeetModels.value[0] || 'nvidia/parakeet-tdt_ctc-0.6b-ja';
  }
  normalizeAsrEngineSelection();
  if (
    !transcription.use_faster_whisper &&
    !transcription.use_simul_streaming &&
    !transcription.use_qwen3_asr &&
    !transcription.use_sensevoice_asr &&
    !transcription.use_fun_asr &&
    !transcription.use_nemo_asr &&
    !transcription.use_openai_transcription_api
  ) {
    if (canUseQwen3Asr.value) {
      transcription.use_qwen3_asr = true;
    } else if (canUseSenseVoice.value) {
      transcription.use_sensevoice_asr = true;
    } else if (canUseFasterWhisper.value) {
      transcription.use_faster_whisper = true;
    } else if (canUseOpenAiAsr.value) {
      transcription.use_openai_transcription_api = true;
    }
  }
}

type AsrEngine =
  | 'faster_whisper'
  | 'simul_streaming'
  | 'openai'
  | 'qwen3'
  | 'sensevoice'
  | 'fun_asr'
  | 'parakeet';

function clearExclusiveAsrEngines(transcription: any) {
  transcription.use_openai_transcription_api = false;
  transcription.use_qwen3_asr = false;
  transcription.use_sensevoice_asr = false;
  transcription.use_fun_asr = false;
  transcription.use_nemo_asr = false;
}

function clearAllAsrEngines(transcription: any) {
  transcription.use_faster_whisper = false;
  transcription.use_simul_streaming = false;
  clearExclusiveAsrEngines(transcription);
}

function normalizeAsrEngineSelection() {
  const transcription = localConfig.value.transcription || {};
  const selectedExclusive = [
    transcription.use_fun_asr ? 'fun_asr' : '',
    transcription.use_sensevoice_asr ? 'sensevoice' : '',
    transcription.use_nemo_asr ? 'parakeet' : '',
    transcription.use_qwen3_asr ? 'qwen3' : '',
    transcription.use_openai_transcription_api ? 'openai' : '',
  ].filter(Boolean);

  if (selectedExclusive.length > 0) {
    const selected = selectedExclusive[0];
    transcription.use_faster_whisper = false;
    transcription.use_simul_streaming = false;
    transcription.use_sensevoice_asr = selected === 'sensevoice';
    transcription.use_fun_asr = selected === 'fun_asr';
    transcription.use_nemo_asr = selected === 'parakeet';
    transcription.use_qwen3_asr = selected === 'qwen3';
    transcription.use_openai_transcription_api = selected === 'openai';
  }
}

function isAsrEngineSelected(engine: AsrEngine): boolean {
  const transcription = localConfig.value.transcription || {};
  if (engine === 'faster_whisper') return !!transcription.use_faster_whisper;
  if (engine === 'simul_streaming') return !!transcription.use_simul_streaming;
  if (engine === 'openai') return !!transcription.use_openai_transcription_api;
  if (engine === 'qwen3') return !!transcription.use_qwen3_asr;
  if (engine === 'sensevoice') return !!transcription.use_sensevoice_asr;
  if (engine === 'fun_asr') return !!transcription.use_fun_asr;
  if (engine === 'parakeet') return !!transcription.use_nemo_asr;
  return false;
}

function selectAsrEngine(engine: AsrEngine) {
  const transcription = localConfig.value.transcription || {};

  if (engine === 'faster_whisper') {
    clearExclusiveAsrEngines(transcription);
    transcription.use_faster_whisper = !transcription.use_faster_whisper;
    return;
  }

  if (engine === 'simul_streaming') {
    clearExclusiveAsrEngines(transcription);
    transcription.use_simul_streaming = !transcription.use_simul_streaming;
    return;
  }

  clearAllAsrEngines(transcription);
  if (engine === 'openai') transcription.use_openai_transcription_api = true;
  if (engine === 'qwen3') transcription.use_qwen3_asr = true;
  if (engine === 'sensevoice') transcription.use_sensevoice_asr = true;
  if (engine === 'fun_asr') transcription.use_fun_asr = true;
  if (engine === 'parakeet') transcription.use_nemo_asr = true;
}

function normalizeInputLanguage(language: string | null | undefined): string {
  const normalized = String(language || 'auto').trim().toLowerCase();
  if (!normalized) return 'auto';
  if (normalized === 'zh') return 'zh-tw';
  if (normalized === 'zh-hant' || normalized === 'traditional chinese' || normalized === '繁體中文') return 'zh-tw';
  if (normalized === 'zh-hans' || normalized === 'simplified chinese' || normalized === '簡體中文') return 'zh-cn';
  return normalized;
}

useTranscriptionMutex(() => localConfig.value.transcription);

function mergeConfig(defaults: any, loaded: any) {
  if (!loaded || typeof loaded !== 'object') {
    return Array.isArray(defaults) ? [...defaults] : { ...defaults };
  }

  const result = {
    ...(defaults || {}),
    ...loaded,
  };

  for (const key of Object.keys(defaults || {})) {
    const defaultValue = defaults[key];
    const loadedValue = loaded[key];
    if (
      defaultValue &&
      loadedValue &&
      typeof defaultValue === 'object' &&
      typeof loadedValue === 'object' &&
      !Array.isArray(defaultValue) &&
      !Array.isArray(loadedValue)
    ) {
      result[key] = mergeConfig(defaultValue, loadedValue);
    }
  }

  return result;
}

function configsEqual(left: any, right: any): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

function replaceObjectContents(target: Record<string, any>, source: Record<string, any>) {
  for (const key of Object.keys(target)) {
    if (!(key in source)) delete target[key];
  }
  Object.assign(target, source);
}

function applyConfigSection(section: string, loadedSection: any) {
  if (!loadedSection || typeof loadedSection !== 'object') return;
  const currentSection = localConfig.value[section] || {};
  const mergedSection = mergeConfig(currentSection, loadedSection);
  if (configsEqual(currentSection, mergedSection)) return;

  if (!Array.isArray(currentSection) && !Array.isArray(mergedSection)) {
    replaceObjectContents(currentSection, mergedSection);
    return;
  }
  localConfig.value[section] = mergedSection;
}

async function applyStoreConfigToLocalConfig(config?: any, syncLlama = false) {
  isApplyingRemoteConfig.value = true;
  try {
    const loadedConfig = config || store.config || {};

    for (const section of [
      'general', 'server', 'runtime', 'models', 'input', 'audio_slicing_vad', 'transcription',
      'translation', 'terminology', 'output', 'output_notification', 'ui', 'llama'
    ]) {
      applyConfigSection(section, loadedConfig[section]);
    }

    if (!['bfloat16', 'float32'].includes(localConfig.value.transcription.qwen3_dtype)) {
      localConfig.value.transcription.qwen3_dtype = 'bfloat16';
    }
    localConfig.value.transcription.language = normalizeInputLanguage(localConfig.value.transcription.language);

    if (loadedConfig.translation?.custom_models) {
      if (!configsEqual(localConfig.value.translation.custom_models, loadedConfig.translation.custom_models)) {
        localConfig.value.translation.custom_models = loadedConfig.translation.custom_models;
      }
    } else if (loadedConfig.custom_models) {
      if (!configsEqual(localConfig.value.translation.custom_models, loadedConfig.custom_models)) {
        localConfig.value.translation.custom_models = loadedConfig.custom_models;
      }
    }

    coerceAsrSettingsForRuntime();

    if (syncLlama) {
      await llamaStore.loadConfig();
      await llamaStore.refreshServerStatus();
    }
  } finally {
    await nextTick();
    isApplyingRemoteConfig.value = false;
  }
}

useAppSyncEvents({
  onConfigUpdated: async (payload) => {
    if (payload.config) store.applyConfigSnapshot(payload.config);
    else await store.loadConfig(true);
    if (payload.section === '*' || payload.section === 'runtime') {
      await store.loadRuntimeStatus();
    }
    await applyStoreConfigToLocalConfig(store.config, payload.section === '*' || payload.section === 'llama');
  },
  onConfigReset: async (payload) => {
    if (payload.config) store.applyConfigSnapshot(payload.config);
    else await store.loadConfig(true);
    await store.loadRuntimeStatus();
    await applyStoreConfigToLocalConfig(store.config, true);
  },
  onConfigImported: async (payload) => {
    if (payload.config) store.applyConfigSnapshot(payload.config);
    else await store.loadConfig(true);
    await store.loadRuntimeStatus();
    await applyStoreConfigToLocalConfig(store.config, true);
  },
  onTranslationStarted: async () => {
    await store.syncRunningState();
  },
  onTranslationStopped: async () => {
    await store.syncRunningState();
  }
});

watch(() => route.query.tab, (newTab) => {
  syncActiveTabFromRoute(newTab);
}, { immediate: true });

watch(activeTab, async (tab) => {
  if (tab !== 'model_management') {
    modelDownloadStore.stopPolling();
    stopCpuAsrSidecarPolling();
    return;
  }
  await refreshCpuAsrSidecarStatus();
  await modelDownloadStore.refreshAll();
  if (modelDownloadStore.activeTasks.length > 0) {
    modelDownloadStore.startPolling();
  }
}, { flush: 'post' });

onMounted(async () => {
  settingsReady.value = false;
  try {
    const [, , serverInfo] = await Promise.all([
      store.loadConfig(),
      store.loadRuntimeStatus(),
      serverApi.getInfo().catch(() => null),
    ]);
    if (serverInfo?.lan_addresses) sharingLanAddresses.value = serverInfo.lan_addresses;
    await applyStoreConfigToLocalConfig(store.config, true);
  } finally {
    await nextTick();
    settingsReady.value = true;
  }
  
  // 從 URL 參數設定 tab
  syncActiveTabFromRoute();

  if (activeTab.value === 'model_management') {
    await refreshCpuAsrSidecarStatus();
    await modelDownloadStore.refreshAll();
    if (modelDownloadStore.activeTasks.length > 0) {
      modelDownloadStore.startPolling();
    }
  }

  // Watch each section independently. This avoids traversing the entire config
  // and allows PATCH /config/{section} to update only affected consumers.
  await nextTick();
  for (const section of Object.keys(localConfig.value)) {
    watch(() => localConfig.value[section], () => {
      if (isApplyingRemoteConfig.value) return;
      debouncedAutoSaveSection(section);
    }, { deep: true, flush: 'post' });
  }

  watch(runtimeCapabilities, () => {
    if (isApplyingRemoteConfig.value) return;
    coerceAsrSettingsForRuntime();
  }, { flush: 'post' });

  watch(
    [selectedSettingsAsrModelId, () => runtimeCapabilities.value?.asr_model_capabilities],
    () => {
      if (isApplyingRemoteConfig.value) return;
      localConfig.value.transcription.language = coerceLanguageForModel(
        runtimeCapabilities.value?.asr_model_capabilities,
        selectedSettingsAsrModelId.value,
        localConfig.value.transcription.language,
      );
    },
    { immediate: true, flush: 'post' },
  );
});

onUnmounted(() => {
  for (const timer of sectionSaveTimers.values()) clearTimeout(timer);
  sectionSaveTimers.clear();
  modelDownloadStore.stopPolling();
  stopCpuAsrSidecarPolling();
});

async function applyModelStoragePath() {
  await store.saveConfig(localConfig.value);
  await modelDownloadStore.refreshAll();
}

async function deleteDownloadedModel(engine: ModelEngine, modelId: string, computeBackend: ModelComputeBackend) {
  if (!confirm(`確定要刪除模型「${modelId}」嗎？之後使用時需要重新下載。`)) return;
  await modelDownloadStore.deleteModel(engine, modelId, computeBackend);
}

async function handleSave() {
  isSaving.value = true;
  try {
    await store.saveConfig(localConfig.value);
  } finally {
    isSaving.value = false;
  }
}

async function handleCancel() {
  // 離開前確保待處理的 debounce 變更都被儲存
  try {
    await flushPendingSectionSaves();
  } catch (e) {
    console.warn('[SettingsView] 離開保存失敗:', e);
  }
  router.push('/');
}

async function resetToDefault() {
  if (confirm('確定要重置為後端預設值嗎？此操作無法復原。')) {
    await store.resetConfig();
    await applyStoreConfigToLocalConfig(store.config, true);
  }
}

// 術語表操作
function addTerm() {
  if (!newTermOriginal.value.trim() || !newTermTranslated.value.trim()) return;
  if (!localConfig.value.terminology.glossary_list) {
    localConfig.value.terminology.glossary_list = [];
  }
  localConfig.value.terminology.glossary_list.push({
    original: newTermOriginal.value.trim(),
    translated: newTermTranslated.value.trim()
  });
  newTermOriginal.value = '';
  newTermTranslated.value = '';
}

function removeTerm(index: number) {
  localConfig.value.terminology.glossary_list.splice(index, 1);
}

function removeTermEntry(term: any) {
  const list = localConfig.value.terminology.glossary_list || [];
  const index = list.indexOf(term);
  if (index >= 0) removeTerm(index);
}

function importGlossary() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.txt,.csv';
  input.onchange = async (e: any) => {
    const file = e.target.files[0];
    if (!file) return;
    const text = await file.text();
    const lines = text.split('\n').filter((l: string) => l.trim());
    const newTerms: any[] = [];
    for (const line of lines) {
      const parts = line.split(/[,\t]/);
      if (parts.length >= 2) {
        newTerms.push({ original: parts[0].trim(), translated: parts[1].trim() });
      }
    }
    localConfig.value.terminology.glossary_list = [
      ...(localConfig.value.terminology.glossary_list || []),
      ...newTerms
    ];
    store.statusMessage = `已匯入 ${newTerms.length} 個術語`;
  };
  input.click();
}

function exportGlossary() {
  const list = localConfig.value.terminology.glossary_list || [];
  const csv = list.map((t: any) => `${t.original},${t.translated}`).join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'glossary.csv';
  a.click();
  URL.revokeObjectURL(url);
}

function addAsrCorrection() {
  const canonical = newAsrCanonical.value.trim();
  const aliases = newAsrAliases.value
    .split(/[,，\n]/)
    .map(value => value.trim())
    .filter((value, index, values) => value && value !== canonical && values.indexOf(value) === index);
  if (!canonical || aliases.length === 0) return;
  if (!localConfig.value.transcription.asr_correction_rules) {
    localConfig.value.transcription.asr_correction_rules = [];
  }
  localConfig.value.transcription.asr_correction_rules.push({ canonical, aliases });
  newAsrCanonical.value = '';
  newAsrAliases.value = '';
}

function removeAsrCorrection(rule: any) {
  const rules = localConfig.value.transcription.asr_correction_rules || [];
  const index = rules.indexOf(rule);
  if (index >= 0) rules.splice(index, 1);
}

function importAsrCorrections() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.txt,.csv';
  input.onchange = async (event: any) => {
    const file = event.target.files[0];
    if (!file) return;
    const imported = (await file.text())
      .split(/\r?\n/)
      .map((line: string) => line.split(/[,，\t]/).map(value => value.trim()).filter(Boolean))
      .filter((parts: string[]) => parts.length >= 2)
      .map((parts: string[]) => ({ canonical: parts[0], aliases: parts.slice(1) }));
    localConfig.value.transcription.asr_correction_rules = [
      ...(localConfig.value.transcription.asr_correction_rules || []),
      ...imported,
    ];
    store.statusMessage = `已匯入 ${imported.length} 筆 ASR 修正規則`;
  };
  input.click();
}

function exportAsrCorrections() {
  const rules = localConfig.value.transcription.asr_correction_rules || [];
  const csv = rules.map((rule: any) => [rule.canonical, ...(rule.aliases || [])].join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'asr-name-corrections.csv';
  anchor.click();
  URL.revokeObjectURL(url);
}

// 自訂模型操作
function openCustomModelDialog(index = -1) {
  editingModelIndex.value = index;
  if (index >= 0) {
    const model = localConfig.value.translation.custom_models[index];
    customModelForm.value = { ...model };
  } else {
    customModelForm.value = { name: '', base_url: '', api_key: '', model_name: '' };
  }
  showCustomModelDialog.value = true;
}

function saveCustomModel() {
  if (!customModelForm.value.name.trim() || !customModelForm.value.base_url.trim()) {
    store.errorMessage = '請填寫模型名稱和 Base URL';
    return;
  }
  
  if (!localConfig.value.translation.custom_models) {
      localConfig.value.translation.custom_models = [];
  }

  if (editingModelIndex.value >= 0) {
    localConfig.value.translation.custom_models[editingModelIndex.value] = { ...customModelForm.value };
  } else {
    localConfig.value.translation.custom_models.push({ ...customModelForm.value });
  }
  showCustomModelDialog.value = false;
}

function deleteCustomModel(index: number) {
  if (confirm('確定要刪除此自訂模型嗎？')) {
    localConfig.value.translation.custom_models.splice(index, 1);
  }
}

// Whisper 濾鏡切換
// 匯入匯出設定
const fileInput = ref<HTMLInputElement | null>(null);

function handleImportClick() {
  fileInput.value?.click();
}

function handleExportClick() {
  store.exportConfig();
}

async function testOpenAiAsrConnection() {
  testingGpt.value = true;
  try {
    const apiKey = localConfig.value.transcription.openai_api_key;
    if (!apiKey) {
      alert('請先輸入 OpenAI ASR API Key');
      return;
    }
    const res = await axios.post('/api/config/test-connection', {
      backend: 'gpt',
      api_key: apiKey,
      base_url: 'https://api.openai.com/v1',
      proxy: localConfig.value.input.proxy || null
    });
    alert(res.data?.success ? '✓ OpenAI ASR 金鑰連線成功' : `OpenAI ASR 連線失敗：${res.data?.message || '未知錯誤'}`);
  } catch (err: any) {
    alert(`OpenAI ASR 連線失敗：${err.response?.data?.detail || err.message}`);
  } finally {
    testingGpt.value = false;
  }
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  if (!input.files || input.files.length === 0) return;
  
  const file = input.files[0];
  try {
    await store.importConfig(file);
    // 重新載入頁面配置以反映更改
    await store.loadRuntimeStatus();
    await applyStoreConfigToLocalConfig(store.config, true);
  } catch (error) {
    console.error('匯入失敗:', error);
  }
  
  // 清空輸入框以允許再次選擇同一檔案
  input.value = '';
}
</script>

<template>
  <div class="p-4 sm:p-5 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between mb-5 gap-3 border-b border-white/5 pb-2.5">
      <div>
        <div class="flex items-center gap-3">
          <h1 class="text-base font-bold text-white tracking-wide">⚙️ 系統設定</h1>
          <!-- Auto-save Status Badge -->
          <div class="flex items-center gap-2 transition-all duration-300 bg-white/5 border border-white/10 px-2.5 py-0.5 rounded-full">
            <span v-if="autoSaveStatus === 'saving'" class="text-blue-300 flex items-center gap-1 text-[10px] font-semibold">
              <span class="inline-block w-2.5 h-2.5 border-2 border-blue-300 border-t-transparent rounded-full animate-spin"></span>
              儲存中...
            </span>
            <span v-else-if="autoSaveStatus === 'saved'" class="text-emerald-400 font-semibold flex items-center gap-0.5 text-[10px]">
              ✓ 已自動儲存
            </span>
            <span v-else-if="autoSaveStatus === 'error'" class="text-rose-400 font-semibold flex items-center gap-0.5 text-[10px]">
              ⚠️ 儲存失敗
            </span>
            <span v-else class="text-white/40 text-[10px] font-semibold">
              ✓ 已儲存
            </span>
          </div>
        </div>
      </div>
      
      <!-- Import/Export & Reset Buttons -->
      <div class="flex flex-wrap gap-2">
        <button @click="handleImportClick" class="bg-blue-600/85 hover:bg-blue-600 text-white font-semibold py-1.5 px-3 rounded-lg transition text-xs flex items-center gap-1.5 shadow-sm">
          📥 匯入
        </button>
        <button @click="handleExportClick" class="bg-emerald-600/85 hover:bg-emerald-600 text-white font-semibold py-1.5 px-3 rounded-lg transition text-xs flex items-center gap-1.5 shadow-sm">
          📤 匯出
        </button>
        <button @click="resetToDefault" class="bg-yellow-600/20 hover:bg-yellow-600/30 text-yellow-300 border border-yellow-500/20 font-semibold py-1.5 px-3 rounded-lg transition text-xs flex items-center gap-1.5">
          🔄 重置預設值
        </button>
      </div>
    </div>
    
    <!-- 隱藏的檔案輸入框 -->
    <input type="file" ref="fileInput" accept=".yaml,.yml" class="hidden" @change="handleFileChange" />

    <!-- Error/Status Messages -->
    <div v-if="store.errorMessage" class="mb-4 p-3 bg-red-500/20 border border-red-500/30 text-red-200 rounded-xl flex justify-between items-center text-xs backdrop-blur-xl">
      <span>{{ store.errorMessage }}</span>
      <button @click="store.clearError()" class="hover:text-white font-bold text-lg leading-none p-1">✕</button>
    </div>

    <div v-if="store.statusMessage" class="mb-4 p-3 bg-green-500/20 border border-green-500/30 text-green-200 rounded-xl flex justify-between items-center text-xs backdrop-blur-xl">
      <span>{{ store.statusMessage }}</span>
      <button @click="store.clearStatus()" class="hover:text-white font-bold text-lg leading-none p-1">✕</button>
    </div>

    <!-- Content Container (Card Layout) -->
    <!-- 長捲動內容不使用 backdrop-filter：Qt WebEngine/Chromium 在 Windows
         重新合成大型毛玻璃 layer 時可能短暫露出底層視窗。 -->
    <div v-if="!settingsReady" class="bg-gradient-to-br from-slate-950/95 via-slate-950/85 to-indigo-950/65 rounded-2xl border border-white/10 shadow-2xl p-6 sm:p-8 min-h-[550px]" aria-busy="true">
      <div class="animate-pulse space-y-6">
        <div class="h-7 w-40 rounded bg-white/10"></div>
        <div class="h-4 w-72 max-w-full rounded bg-white/5"></div>
        <div class="h-12 rounded-xl bg-white/5"></div>
        <div class="h-36 rounded-xl bg-white/5"></div>
      </div>
      <p class="mt-6 text-sm text-white/45">正在讀取設定…</p>
    </div>
    <div v-else class="bg-gradient-to-br from-slate-950/95 via-slate-950/85 to-indigo-950/65 rounded-2xl border border-white/10 shadow-2xl p-6 sm:p-8 min-h-[550px]">
          <!-- General Settings -->
          <div v-if="activeTab === 'general'" class="settings-paint-section space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">一般設定</h2>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div v-if="false">
                <label class="block text-white/70 font-semibold mb-2">OpenAI API Key</label>
                <div class="flex gap-2">
                  <input disabled value="" type="password" placeholder="sk-..."
                    class="flex-1 px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                  <button @click="testConnection('gpt')" :disabled="testingGpt" 
                    class="bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 font-semibold px-4 rounded-lg transition text-xs whitespace-nowrap flex items-center justify-center gap-1.5 min-w-[95px]">
                    <span v-if="testingGpt" class="inline-block w-3 h-3 border-2 border-blue-300 border-t-transparent rounded-full animate-spin"></span>
                    <span>⚡ 測試連線</span>
                  </button>
                </div>
                <p class="text-white/40 text-sm mt-1">用於 GPT 翻譯</p>
              </div>

              <div v-if="false">
                <label class="block text-white/70 font-semibold mb-2">Google API Key (Gemini)</label>
                <div class="flex gap-2">
                  <input disabled value="" type="password" placeholder="AIza..."
                    class="flex-1 px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                  <button @click="testConnection('gemini')" :disabled="testingGemini" 
                    class="bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 font-semibold px-4 rounded-lg transition text-xs whitespace-nowrap flex items-center justify-center gap-1.5 min-w-[95px]">
                    <span v-if="testingGemini" class="inline-block w-3 h-3 border-2 border-blue-300 border-t-transparent rounded-full animate-spin"></span>
                    <span>⚡ 測試連線</span>
                  </button>
                </div>
                <p class="text-white/40 text-sm mt-1">用於 Gemini 翻譯</p>
              </div>

              <div>
                <label class="block text-white/70 font-semibold mb-2">日誌等級</label>
                <UiSelect v-model="localConfig.general.log_level" :options="logLevelOptions" />
              </div>

              <div class="md:col-span-2 rounded-xl p-5 border border-white/10 bg-gradient-to-br from-emerald-500/10 via-white/5 to-blue-500/10 space-y-5">
                <label class="flex items-start justify-between gap-5 cursor-pointer">
                  <div>
                    <div class="flex items-center gap-2">
                      <span class="text-white font-semibold">即時字幕分享</span>
                      <span :class="['px-2 py-0.5 rounded-full text-xs border', localConfig.server.enable_subtitle_sharing ? 'text-emerald-300 bg-emerald-500/10 border-emerald-500/25' : 'text-white/45 bg-white/5 border-white/10']">
                        {{ localConfig.server.enable_subtitle_sharing ? '已啟用' : '已關閉' }}
                      </span>
                    </div>
                    <p class="text-white/55 text-sm mt-2 leading-6">讓同一個區域網路中的手機、平板或另一台電腦，透過瀏覽器觀看目前的即時原文與翻譯字幕。</p>
                  </div>
                  <input v-model="localConfig.server.enable_subtitle_sharing" type="checkbox" class="w-5 h-5 accent-emerald-500 mt-1 shrink-0" />
                </label>

                <div v-if="localConfig.server.enable_subtitle_sharing" class="space-y-3">
                  <div class="grid grid-cols-1 lg:grid-cols-2 gap-3">
                    <div class="rounded-lg border border-white/10 bg-black/15 p-4">
                      <div class="text-white/80 font-semibold text-sm">桌面版字幕</div>
                      <p class="text-white/40 text-xs mt-1">適合電腦、投影幕與直播監看畫面。</p>
                      <div class="flex items-center gap-2 mt-3">
                        <code class="min-w-0 flex-1 truncate text-xs text-cyan-300 bg-black/20 rounded px-3 py-2">{{ desktopSharingUrl }}</code>
                        <button type="button" @click="copySharingUrl(desktopSharingUrl)" class="px-3 py-2 rounded-lg bg-blue-600/25 hover:bg-blue-600/40 text-blue-200 text-xs border border-blue-500/25">
                          {{ copiedSharingUrl === desktopSharingUrl ? '已複製' : '複製' }}
                        </button>
                      </div>
                    </div>
                    <div class="rounded-lg border border-white/10 bg-black/15 p-4">
                      <div class="text-white/80 font-semibold text-sm">行動版字幕</div>
                      <p class="text-white/40 text-xs mt-1">適合手機與平板，版面會依螢幕自動調整。</p>
                      <div class="flex items-center gap-2 mt-3">
                        <code class="min-w-0 flex-1 truncate text-xs text-cyan-300 bg-black/20 rounded px-3 py-2">{{ mobileSharingUrl }}</code>
                        <button type="button" @click="copySharingUrl(mobileSharingUrl)" class="px-3 py-2 rounded-lg bg-blue-600/25 hover:bg-blue-600/40 text-blue-200 text-xs border border-blue-500/25">
                          {{ copiedSharingUrl === mobileSharingUrl ? '已複製' : '複製' }}
                        </button>
                      </div>
                    </div>
                  </div>

                  <div class="rounded-lg border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-xs text-white/55 leading-5">
                    <span class="text-amber-300 font-semibold">使用方式：</span>
                    分享裝置需與本機位於同一個 Wi-Fi／區域網路。若無法開啟，請允許 Windows 防火牆存取連接埠 {{ localConfig.server.public_port || 8765 }}。此功能沒有登入驗證，請勿直接暴露至公網；關閉後，分享頁與公開字幕 API 都會停止存取。
                  </div>
                </div>

                <p v-else class="text-white/40 text-sm">分享頁面與公開字幕 API 已停用，區域網路中的其他裝置無法讀取字幕。</p>
              </div>
            </div>
          </div>

          <!-- Input Settings -->
          <div v-if="activeTab === 'input'" class="settings-paint-section space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">輸入選項</h2>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label class="block text-white/70 font-semibold mb-2">來源類型</label>
                <UiSelect v-model="localConfig.input.source_type" :options="sourceTypeOptions" />
              </div>

              <div>
                <label class="block text-white/70 font-semibold mb-2">格式</label>
                <input v-model="localConfig.input.format" type="text" placeholder="ba/wa*"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
              </div>

              <div class="md:col-span-2 border-t border-white/10 pt-5">
                <div class="flex items-center justify-between gap-3 mb-4">
                  <div>
                    <h3 class="text-white font-semibold">網站 Cookies</h3>
                    <p class="text-white/40 text-sm mt-1">從已登入的瀏覽器更新平台專用 Cookies</p>
                  </div>
                  <span
                    v-if="selectedPlatformCookiePath"
                    class="text-xs px-2 py-1 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/25"
                  >
                    已設定
                  </span>
                </div>

                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">平台</label>
                    <UiSelect v-model="cookiePlatform" :options="cookiePlatformOptions" />
                  </div>
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">瀏覽器</label>
                    <UiSelect v-model="cookieBrowser" :options="cookieBrowserOptions" />
                    <p v-if="selectedBrowserMayLockCookies" class="text-amber-300/70 text-xs mt-2">
                      Windows 新版 Chromium 可能無法直接解密；可改用 Firefox 或匯入 cookies.txt
                    </p>
                  </div>
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">瀏覽器 Profile</label>
                    <input
                      v-model="cookieBrowserProfile"
                      type="text"
                      placeholder="留空使用預設 Profile"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400"
                    />
                  </div>
                </div>

                <div class="mt-4 flex flex-col md:flex-row md:items-center gap-3">
                  <button
                    type="button"
                    :disabled="cookieImporting"
                    class="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition"
                    @click="importCookiesFromBrowser"
                  >
                    {{ cookieImporting ? '更新中...' : '從瀏覽器更新' }}
                  </button>
                  <input
                    ref="cookieFileInput"
                    type="file"
                    accept=".txt,text/plain"
                    class="hidden"
                    @change="importCookiesFromFile"
                  />
                  <button
                    type="button"
                    :disabled="cookieImporting"
                    class="px-4 py-2 bg-white/10 hover:bg-white/15 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition"
                    @click="selectCookieFile"
                  >
                    匯入 cookies.txt
                  </button>
                  <p
                    v-if="cookieImportResult"
                    class="text-sm"
                    :class="cookieImportResult.type === 'success' ? 'text-emerald-300' : 'text-rose-300'"
                  >
                    {{ cookieImportResult.message }}
                  </p>
                  <p v-else-if="selectedPlatformCookiePath" class="text-white/45 text-sm truncate">
                    {{ selectedPlatformCookiePath }}
                  </p>
                </div>

                <div class="mt-5">
                  <label class="block text-white/70 font-semibold mb-2">其他網站 Cookies（Fallback）</label>
                  <input
                    v-model="localConfig.input.cookies"
                    type="text"
                    placeholder="未匹配平台時使用的 cookies.txt"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400"
                  />
                </div>
              </div>

              <div>
                <label class="block text-white/70 font-semibold mb-2">代理伺服器</label>
                <input v-model="localConfig.input.proxy" type="text" placeholder="http://127.0.0.1:7890"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
              </div>

              <div>
                <label class="block text-white/70 font-semibold mb-2">超時時間（秒）</label>
                <input v-model.number="localConfig.input.timeout" type="number" placeholder="30"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
              </div>

              <div>
                <label class="block text-white/70 font-semibold mb-2 flex items-center gap-1.5">
                  設備錄音間隔（秒）
                  <span class="tooltip-container text-white/40 hover:text-blue-300 transition text-sm">
                    ⓘ
                    <span class="tooltip-text">
                      僅用於設備/Loopback 模式。間隔越短延遲越低但 CPU 使用率越高，直播建議 0.1 秒。
                    </span>
                  </span>
                </label>
                <input v-model.number="localConfig.input.device_recording_interval" type="number" step="0.05" min="0.05" max="1.0" placeholder="0.1"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
              </div>
            </div>
          </div>

          <!-- Audio Slicing & VAD Settings -->
          <div v-if="activeTab === 'audio_vad'" class="settings-paint-section space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">音訊切片 & VAD 設定</h2>
            
            <!-- 音訊切片 -->
            <div class="bg-white/5 rounded-xl p-4 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">🔊 音訊切片</h3>
              <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div>
                  <label class="block text-white/70 text-sm mb-1">最小音訊長度 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.min_audio_length" type="number" step="0.1" min="0.1" max="30"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">目標音訊長度 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.target_audio_length" type="number" step="0.1" min="0.1" max="60"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-xs text-white/40 mt-1">動態句尾判斷會盡量在接近此長度時完成片段。</p>
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">最大音訊長度 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.max_audio_length" type="number" step="0.1" min="0.1" max="120"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">句尾連續靜音 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.continuous_no_speech_threshold" type="number"
                    step="0.05" min="0.1" max="5"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-xs text-white/40 mt-1">偵測到連續靜音後結束片段；直播建議 0.4 到 0.7 秒。</p>
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">前綴重疊長度 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.prefix_retention_length" type="number"
                    step="0.05" min="0" max="5"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-xs text-white/40 mt-1">將上一片段結尾接到下一片段開頭；設為 0 可完全停用。</p>
                </div>
                <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer">
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
                <h3 class="text-lg font-semibold text-blue-300">🎙️ VAD (Voice Activity Detection)</h3>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input v-model="localConfig.audio_slicing_vad.vad_enabled" type="checkbox" class="w-5 h-5 accent-blue-500" />
                  <span class="text-white">啟用 VAD</span>
                </label>
              </div>
              
              <div v-if="localConfig.audio_slicing_vad.vad_enabled" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                <div>
                  <label class="block text-white/70 text-sm mb-1 font-semibold">VAD 演算法</label>
                  <UiSelect v-model="localConfig.audio_slicing_vad.vad_backend" :options="vadBackendOptions" />
                </div>
                <div v-if="localConfig.audio_slicing_vad.vad_backend === 'firered'">
                  <label class="block text-white/70 text-sm mb-1 font-semibold">FireRed VAD 模型路徑</label>
                  <input v-model="localConfig.audio_slicing_vad.firered_vad_model_path" type="text" placeholder="留空或填寫 auto"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                  <p class="text-white/30 text-xs mt-1">預設使用內建模型</p>
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1 flex items-center gap-1.5">
                    語音閾值
                    <span class="tooltip-container text-white/40 hover:text-blue-300 transition text-xs">
                      ⓘ
                      <span class="tooltip-text">
                        聲音被判定為語音的閾值。範圍 0.0 ~ 1.0，預設 0.35。數值越低越靈敏。
                      </span>
                    </span>
                  </label>
                  <input v-model.number="localConfig.audio_slicing_vad.vad_threshold" type="number" step="0.05" min="0" max="1"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>
                <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer">
                  <input v-model="localConfig.audio_slicing_vad.disable_dynamic_vad_threshold" type="checkbox"
                    class="w-5 h-5 accent-blue-500 mt-0.5" />
                  <span>
                    <span class="block text-white font-medium">停用動態 VAD 門檻</span>
                    <span class="block text-xs text-white/40 mt-1">勾選後固定使用上方語音閾值。</span>
                  </span>
                </label>
                <div>
                  <label class="block text-white/70 text-sm mb-1">VAD 計算頻率</label>
                  <input v-model.number="localConfig.audio_slicing_vad.vad_every_n_frames" type="number"
                    min="1" max="10" step="1"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-xs text-white/40 mt-1">1 為每個 32 ms frame 計算；提高可降低 CPU，但會增加判斷延遲。</p>
                </div>
              </div>
            </div>
          </div>

          <!-- Transcription Settings -->
          <div v-if="activeTab === 'transcription'" class="settings-paint-section space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">轉錄選項</h2>
            
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
                      <br />⚠️ 此選項與上述兩項互斥
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
                      <template v-if="isSherpaOnnxMode">使用 Qwen3-ASR 0.6B 的 Sherpa-ONNX INT8 CPU bundle；不套用 dtype、4-bit 或 GPU 裝置設定。</template>
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
                          <br/>📦 CUDA 可攜版已內建量化支援
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

          <!-- Model Management Settings -->
          <div v-if="activeTab === 'model_management'" class="settings-paint-section space-y-6">
            <div
              v-if="['cuda', 'rocm'].includes(runtimeStatus?.profile || '')"
              class="bg-white/5 rounded-xl p-5 border border-cyan-500/30"
            >
              <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                <div>
                  <h3 class="text-lg font-semibold text-cyan-300">CPU ASR Sidecar</h3>
                  <p class="text-white/60 text-sm mt-1">
                    安裝獨立 sherpa-onnx CPU runtime，讓目前的 {{ runtimeStatus?.profile?.toUpperCase() }} 包可切換 GPU ASR / CPU ASR。
                  </p>
                  <p v-if="cpuAsrSidecarStatus?.installed" class="text-green-300 text-sm mt-2">已安裝 CPU ASR runtime。</p>
                </div>
                <button
                  @click="installCpuAsrSidecar"
                  :disabled="!canInstallCpuAsrSidecar"
                  class="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-700 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold transition"
                >
                  {{ cpuAsrSidecarBusy ? '安裝中…' : (cpuAsrSidecarStatus?.installed ? '已安裝' : '下載並安裝') }}
                </button>
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
              <p v-if="cpuAsrSidecarStatus?.restart_required" class="text-yellow-200 text-sm mt-3">
                安裝完成，請重新啟動程式後再切換至 CPU / sherpa-onnx。
              </p>
            </div>
            <h2 class="text-xl font-bold text-white mb-4">ASR 模型管理</h2>
            <div class="grid grid-cols-2 gap-2 p-1 rounded-xl bg-black/20 border border-white/10">
              <button @click="modelManagementBackend = 'gpu'" :class="['px-4 py-2 rounded-lg font-semibold transition', modelManagementBackend === 'gpu' ? 'bg-blue-600 text-white' : 'text-white/60 hover:bg-white/10']">GPU 原生模型</button>
              <button @click="modelManagementBackend = 'cpu'" :class="['px-4 py-2 rounded-lg font-semibold transition', modelManagementBackend === 'cpu' ? 'bg-cyan-600 text-white' : 'text-white/60 hover:bg-white/10']">Sherpa-ONNX CPU 模型</button>
            </div>

            <div class="bg-cyan-500/10 rounded-xl p-4 border border-cyan-500/20">
              <p class="text-cyan-200 text-sm">
                <template v-if="modelManagementBackend === 'cpu'">📦 此分頁下載 Sherpa-ONNX 專用 INT8 ONNX bundle，不能與同名的 PyTorch／NeMo GPU 模型互換。</template>
                <template v-else>📦 此分頁管理 GPU 原生模型；模型格式與 Sherpa-ONNX CPU bundle 分開。</template>
              </p>
              <p class="text-white/50 text-xs mt-2">
                <template v-if="modelManagementBackend === 'cpu'">模型儲存在 models\\sherpa-onnx，使用 CPU 離線推論，不需要 CUDA、ROCm 或 PyTorch；只列出目前已支援的 bundle。</template>
                <template v-else>GPU 使用 Hugging Face／ModelScope cache；GPU 與 CPU 兩種格式可同時存在。</template>
              </p>
            </div>

            <div class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-3">模型儲存位置</h3>
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

            <div v-if="false" class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">Qwen3-ASR 模型</h3>
              <div class="space-y-3">
                <div v-for="modelId in qwenModelList" :key="`qwen-${modelId}`" class="p-4 rounded-lg bg-white/5 border border-white/10">
                  <div class="flex items-center justify-between gap-4">
                    <div>
                      <div class="text-white font-semibold">{{ modelId }}</div>
                      <div :class="['text-sm mt-1', getModelStatusClass('qwen3-asr', modelId)]">
                        {{ getModelStatusText('qwen3-asr', modelId) }}
                      </div>
                    </div>
                    <button
                      @click="startModelDownload('qwen3-asr', modelId)"
                      :disabled="!canStartDownload('qwen3-asr', modelId)"
                      class="px-4 py-2 rounded-lg font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-700 text-white"
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
                    <div>
                      <div class="text-white font-semibold">{{ modelId }}</div>
                      <div class="text-white/50 text-xs mt-1">CPU capable; ROCm remains experimental until AMD validation.</div>
                      <div :class="['text-sm mt-1', getModelStatusClass('sensevoice', modelId)]">
                        {{ getModelStatusText('sensevoice', modelId) }}
                      </div>
                    </div>
                    <button
                      @click="startModelDownload('sensevoice', modelId)"
                      :disabled="!canStartDownload('sensevoice', modelId)"
                      class="px-4 py-2 rounded-lg font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-700 text-white"
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
                    <div>
                      <div class="text-white font-semibold">{{ modelId }}</div>
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
                      class="px-4 py-2 rounded-lg font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-700 text-white"
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
                    <div>
                      <div class="text-white font-semibold">{{ modelId }}</div>
                      <div class="text-white/50 text-xs mt-1">CUDA experimental；英文／日文依模型固定；官方模型採 CC-BY-4.0，需 NVIDIA NeMo。</div>
                      <div :class="['text-sm mt-1', getModelStatusClass('parakeet-ctc-ja', modelId)]">
                        {{ getModelStatusText('parakeet-ctc-ja', modelId) }}
                      </div>
                    </div>
                    <button
                      @click="startModelDownload('parakeet-ctc-ja', modelId)"
                      :disabled="!canStartDownload('parakeet-ctc-ja', modelId)"
                      class="px-4 py-2 rounded-lg font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-700 text-white"
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
                    <div>
                      <div class="text-white font-semibold">{{ modelId }}</div>
                      <div :class="['text-sm mt-1', getModelStatusClass('faster-whisper', modelId)]">
                        {{ getModelStatusText('faster-whisper', modelId) }}
                      </div>
                    </div>
                    <button
                      @click="startModelDownload('faster-whisper', modelId)"
                      :disabled="!canStartDownload('faster-whisper', modelId)"
                      class="px-4 py-2 rounded-lg font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-700 text-white"
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
                    <div>
                      <div class="text-white font-medium">{{ item.model_id }}</div>
                      <div class="text-xs text-white/50 mt-1">{{ item.compute_backend.toUpperCase() }} · {{ item.engine }} · {{ item.repo_id }}</div>
                    </div>
                    <div class="flex items-center gap-3">
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

          <!-- Translation Settings -->
          <div v-if="activeTab === 'translation'" class="settings-paint-section space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">翻譯選項</h2>
            
            <!-- 基本翻譯設定 -->
            <div class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">🌐 基本設定</h3>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label class="block text-white/70 font-semibold mb-2">翻譯後端</label>
                  <UiSelect v-model="localConfig.translation.backend" :options="translationBackendOptions" />
                  <p class="text-white/40 text-xs mt-1">選擇翻譯服務提供商</p>
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2">目標語言</label>
                  <UiSelect v-model="localConfig.translation.target_language" :options="targetLanguageOptions" />
                  <p class="text-white/40 text-xs mt-1">翻譯的目標語言</p>
                </div>
              </div>
            </div>

            <!-- OpenAI GPT 設定 -->
            <div v-if="localConfig.translation.backend === 'gpt'" class="bg-gradient-to-br from-green-500/10 to-blue-500/10 rounded-xl p-5 border border-green-500/20">
              <h3 class="text-lg font-semibold text-green-300 mb-4">🤖 OpenAI GPT 設定</h3>
              <div class="space-y-4">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">GPT 模型</label>
                    <input v-model="localConfig.translation.gpt_model" type="text" placeholder="gpt-4o-mini"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-green-400" />
                    <p class="text-white/40 text-xs mt-1">例如: gpt-4o, gpt-4o-mini, gpt-3.5-turbo</p>
                  </div>

                  <div>
                    <label class="block text-white/70 font-semibold mb-2">API Key <span class="text-white/40 text-xs">(選填)</span></label>
                    <div class="flex gap-2">
                      <input v-model="localConfig.translation.openai_api_key" type="password" placeholder="sk-..."
                        class="flex-1 px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-green-400" />
                      <button @click="testConnection('gpt')" :disabled="testingGpt" 
                        class="bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 font-semibold px-4 rounded-lg transition text-xs whitespace-nowrap flex items-center justify-center gap-1.5 min-w-[95px]">
                        <span v-if="testingGpt" class="inline-block w-3 h-3 border-2 border-blue-300 border-t-transparent rounded-full animate-spin"></span>
                        <span>⚡ 測試連線</span>
                      </button>
                    </div>
                    <p class="text-white/50 text-xs mt-1">僅供 OpenAI GPT 雲端翻譯使用，不會提供給 OpenAI 語音轉錄或 Gemini。</p>
                  </div>

                  <div class="md:col-span-2">
                    <label class="block text-white/70 font-semibold mb-2">API Base URL</label>
                    <input v-model="localConfig.translation.gpt_base_url" type="text" placeholder="https://api.openai.com/v1"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-green-400" />
                    <p class="text-white/40 text-xs mt-1">OpenAI 預設端點；使用相容服務時可自行修改。</p>
                  </div>
                </div>
              </div>
            </div>

            <!-- Google Gemini 設定 -->
            <div v-if="localConfig.translation.backend === 'gemini'" class="bg-gradient-to-br from-blue-500/10 to-indigo-500/10 rounded-xl p-5 border border-blue-500/20">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">💎 Google Gemini 設定</h3>
              <div class="space-y-4">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">Gemini 模型</label>
                    <input v-model="localConfig.translation.gemini_model" type="text" placeholder="gemini-2.0-flash-exp"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                    <p class="text-white/40 text-xs mt-1">例如: gemini-2.0-flash-exp, gemini-1.5-pro</p>
                  </div>

                  <div>
                    <label class="block text-white/70 font-semibold mb-2">API Key <span class="text-white/40 text-xs">(選填)</span></label>
                    <div class="flex gap-2">
                      <input v-model="localConfig.translation.google_api_key" type="password" placeholder="AIza..."
                        class="flex-1 px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                      <button @click="testConnection('gemini')" :disabled="testingGemini" 
                        class="bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 font-semibold px-4 rounded-lg transition text-xs whitespace-nowrap flex items-center justify-center gap-1.5 min-w-[95px]">
                        <span v-if="testingGemini" class="inline-block w-3 h-3 border-2 border-blue-300 border-t-transparent rounded-full animate-spin"></span>
                        <span>⚡ 測試連線</span>
                      </button>
                    </div>
                    <p class="text-white/50 text-xs mt-1">僅供 Google Gemini 雲端翻譯使用，不會用於 ASR 或 OpenAI GPT。</p>
                  </div>

                  <div class="md:col-span-2">
                    <label class="block text-white/70 font-semibold mb-2">API Base URL</label>
                    <input v-model="localConfig.translation.gemini_base_url" type="text" placeholder="https://generativelanguage.googleapis.com"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                    <p class="text-white/40 text-xs mt-1">Google Gemini 預設端點；使用代理端點時可自行修改。</p>
                  </div>
                </div>
              </div>
            </div>

            <!-- 自訂模型設定 -->
            <div v-if="localConfig.translation.backend.startsWith('custom:')" class="bg-gradient-to-br from-orange-500/10 to-yellow-500/10 rounded-xl p-5 border border-orange-500/20">
              <h3 class="text-lg font-semibold text-orange-300 mb-4">⚙️ 自訂模型設定</h3>
              <div class="space-y-3">
                <div class="p-4 bg-white/5 rounded-lg border border-white/10">
                  <p class="text-white/60 text-sm">
                    已選擇自訂模型: <span class="text-orange-300 font-semibold">{{ localConfig.translation.backend.replace('custom:', '') }}</span>
                  </p>
                  <p class="text-white/40 text-xs mt-2">
                    💡 自訂模型的 API 端點和金鑰設定在下方「自訂模型管理」區塊中管理
                  </p>
                </div>
              </div>

              <!-- 自訂模型管理 (移至自訂模型設定內部) -->
              <div class="mt-6 pt-6 border-t border-orange-500/20">
                <div class="flex items-center justify-between mb-4">
                  <div>
                    <h4 class="text-base font-semibold text-orange-200">🤖 自訂模型管理</h4>
                    <p class="text-white/50 text-xs mt-1">管理相容 OpenAI API 的自訂模型端點</p>
                  </div>
                  <button @click="openCustomModelDialog()" class="bg-orange-600 hover:bg-orange-700 text-white font-semibold py-2 px-4 rounded-lg transition flex items-center gap-2">
                    <span>+</span>
                    <span>新增模型</span>
                  </button>
                </div>
                
                <div v-if="localConfig.translation.custom_models && localConfig.translation.custom_models.length > 0" class="space-y-2">
                  <div v-for="(model, idx) in localConfig.translation.custom_models" :key="idx"
                    class="flex items-center justify-between p-4 bg-white/5 rounded-lg border border-white/10 hover:border-orange-500/30 transition">
                    <div class="flex-1">
                      <div class="flex items-center gap-2">
                        <span class="text-white font-medium">{{ model.name }}</span>
                        <span class="px-2 py-0.5 bg-orange-500/20 text-orange-300 text-xs rounded">自訂</span>
                      </div>
                      <div class="flex items-center gap-3 mt-1 text-sm text-white/40">
                        <span>{{ model.model_name }}</span>
                        <span>•</span>
                        <span class="truncate max-w-xs">{{ model.api_base || '預設端點' }}</span>
                      </div>
                    </div>
                    <div class="flex gap-2 ml-4">
                      <button @click="openCustomModelDialog(idx)" class="px-3 py-1.5 bg-blue-500/20 hover:bg-blue-500/30 text-blue-400 rounded transition">
                        編輯
                      </button>
                      <button @click="deleteCustomModel(idx)" class="px-3 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded transition">
                        刪除
                      </button>
                    </div>
                  </div>
                </div>
                <div v-else class="text-center py-6 text-white/40">
                  <div class="text-3xl mb-2">📦</div>
                  <div class="text-sm">尚未新增自訂模型</div>
                  <div class="text-xs mt-1">點擊上方按鈕新增第一個模型</div>
                </div>
              </div>
            </div>

            <!-- 自訂模型管理（固定顯示，避免切換後端時找不到） -->
            <div v-if="!localConfig.translation.backend.startsWith('custom:')" class="bg-gradient-to-br from-orange-500/10 to-yellow-500/10 rounded-xl p-5 border border-orange-500/20">
              <div class="flex items-center justify-between mb-4">
                <div>
                  <h3 class="text-lg font-semibold text-orange-300">🤖 自訂模型管理</h3>
                  <p class="text-white/50 text-xs mt-1">管理相容 OpenAI API 的自訂模型端點</p>
                </div>
                <button @click="openCustomModelDialog()" class="bg-orange-600 hover:bg-orange-700 text-white font-semibold py-2 px-4 rounded-lg transition flex items-center gap-2">
                  <span>+</span>
                  <span>新增模型</span>
                </button>
              </div>

              <div v-if="localConfig.translation.custom_models && localConfig.translation.custom_models.length > 0" class="space-y-2">
                <div v-for="(model, idx) in localConfig.translation.custom_models" :key="idx"
                  class="flex items-center justify-between p-4 bg-white/5 rounded-lg border border-white/10 hover:border-orange-500/30 transition">
                  <div class="flex-1">
                    <div class="flex items-center gap-2">
                      <span class="text-white font-medium">{{ model.name }}</span>
                      <span class="px-2 py-0.5 bg-orange-500/20 text-orange-300 text-xs rounded">自訂</span>
                    </div>
                    <div class="flex items-center gap-3 mt-1 text-sm text-white/40">
                      <span>{{ model.model_name }}</span>
                      <span>•</span>
                      <span class="truncate max-w-xs">{{ model.base_url || model.api_base || '預設端點' }}</span>
                    </div>
                  </div>
                  <div class="flex gap-2 ml-4">
                    <button @click="openCustomModelDialog(idx)" class="px-3 py-1.5 bg-blue-500/20 hover:bg-blue-500/30 text-blue-400 rounded transition">
                      編輯
                    </button>
                    <button @click="deleteCustomModel(idx)" class="px-3 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded transition">
                      刪除
                    </button>
                  </div>
                </div>
              </div>
              <div v-else class="text-center py-6 text-white/40">
                <div class="text-3xl mb-2">📦</div>
                <div class="text-sm">尚未新增自訂模型</div>
                <div class="text-xs mt-1">點擊上方按鈕新增第一個模型</div>
              </div>
            </div>

            <!-- 進階翻譯設定 (所有後端共用，但不翻譯時隱藏) -->
            <div v-if="localConfig.translation.backend !== 'none'" class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">🔧 進階設定</h3>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label class="block text-white/70 font-semibold mb-2">模型翻譯策略</label>
                  <UiSelect v-model="localConfig.translation.translation_model_family" :options="translationModelFamilyOptions" />
                  <p class="text-white/40 text-xs mt-1">本地模型名稱不明確時，請手動指定策略。</p>
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2">輸出格式</label>
                  <UiSelect v-model="localConfig.translation.translation_output_format" :options="translationOutputFormatOptions" />
                  <p class="text-white/40 text-xs mt-1">Hy-MT2 固定使用純文字；支援的 API 才會使用 JSON。</p>
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2 flex items-center gap-1.5">
                    歷史訊息數量
                    <span class="tooltip-container text-white/40 hover:text-blue-300 transition text-sm">
                      ⓘ
                      <span class="tooltip-text">
                        提供最近字幕作為理解背景。大於 0 時會強制單工翻譯，避免上下文順序錯亂。
                      </span>
                    </span>
                  </label>
                  <input v-model.number="localConfig.translation.translation_history_size" type="number" min="0" max="20"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2 flex items-center gap-1.5">
                    翻譯超時 (秒)
                    <span class="tooltip-container text-white/40 hover:text-blue-300 transition text-sm">
                      ⓘ
                      <span class="tooltip-text">
                        翻譯 API 的最長等待時間，超過此時間將跳過該句以避免延遲累積。
                      </span>
                    </span>
                  </label>
                  <input v-model.number="localConfig.translation.translation_timeout" type="number" min="5" max="60"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2">最大並行翻譯數</label>
                  <input v-model.number="localConfig.translation.translation_max_concurrency" type="number" min="0" max="8"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-white/40 text-xs mt-1">0 使用策略預設；本地模型建議 1，線上 API 建議 2。</p>
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2">每段最大輸出 Token</label>
                  <input v-model.number="localConfig.translation.translation_max_output_tokens" type="number" min="16" max="2048" step="16"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-white/40 text-xs mt-1">直播短字幕建議 128，較長字幕可使用 192 或 256。</p>
                </div>

                <div class="md:col-span-2">
                  <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition">
                    <input v-model="localConfig.translation.paired_subtitle_mode" type="checkbox"
                      class="w-5 h-5 accent-blue-500 mt-0.5" />
                    <div>
                      <span class="text-white font-medium">原文與翻譯成對顯示</span>
                      <p class="text-white/50 text-sm mt-1">翻譯完成前不顯示該組字幕；翻譯失敗時略過整組，避免原文與譯文錯位。</p>
                    </div>
                  </label>
                </div>

                <div>
                  <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer">
                    <input v-model="localConfig.translation.deduplicate_asr_overlap" type="checkbox"
                      class="w-5 h-5 accent-blue-500 mt-0.5" />
                    <span>
                      <span class="block text-white font-medium">跨片段重疊去重</span>
                      <span class="block text-white/50 text-sm mt-1">翻譯前移除相鄰 ASR 片段重複的開頭文字。</span>
                    </span>
                  </label>
                </div>

                <div>
                  <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer">
                    <input v-model="localConfig.translation.subtitle_assembler_enabled" type="checkbox"
                      class="w-5 h-5 accent-blue-500 mt-0.5" />
                    <span>
                      <span class="block text-white font-medium">字幕組句器</span>
                      <span class="block text-white/50 text-sm mt-1">不完整句短暫等待下一個 ASR 片段，再一起翻譯。</span>
                    </span>
                  </label>
                </div>

                <template v-if="localConfig.translation.subtitle_assembler_enabled">
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">組句等待上限 (ms)</label>
                    <input v-model.number="localConfig.translation.subtitle_assembler_wait_ms" type="number"
                      min="0" max="2000" step="50"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  </div>
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">組句最大音訊跨度 (秒)</label>
                    <input v-model.number="localConfig.translation.subtitle_assembler_max_duration" type="number"
                      min="1" max="20" step="0.5"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  </div>
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">可合併片段間隔 (秒)</label>
                    <input v-model.number="localConfig.translation.subtitle_assembler_gap_threshold" type="number"
                      min="0" max="5" step="0.1"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  </div>
                </template>

                <div class="md:col-span-2">
                  <label class="block text-white/70 font-semibold mb-2 flex items-center gap-1.5">
                    處理代理伺服器 <span class="text-white/40 text-xs">(選填)</span>
                    <span class="tooltip-container text-white/40 hover:text-blue-300 transition text-sm">
                      ⓘ
                      <span class="tooltip-text">
                        為 Whisper 和 GPT API 的呼叫設定 HTTP/S 代理伺服器（Google Gemini API 目前不支援此代理設定）。
                      </span>
                    </span>
                  </label>
                  <input v-model="localConfig.translation.processing_proxy" type="text" placeholder="http://127.0.0.1:7890"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                </div>

              </div>
            </div>

            <!-- 翻譯提示詞設定 (所有後端共用，但不翻譯時隱藏) -->
            <div v-if="localConfig.translation.backend !== 'none'" class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">💬 提示詞設定</h3>
              <div class="space-y-4">
                <label class="flex items-center gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition">
                  <input v-model="localConfig.translation.use_smart_prompt" type="checkbox" class="w-5 h-5 accent-blue-500" />
                  <div class="flex-1">
                    <span class="text-white font-medium">啟用智能提示詞</span>
                    <p class="text-white/50 text-sm mt-1">使用系統預設的智能提示詞進行翻譯優化</p>
                  </div>
                </label>

                <!-- 自訂翻譯提示詞（當關閉智能提示詞時顯示） -->
                <div v-if="!localConfig.translation.use_smart_prompt" class="pt-2">
                  <label class="block text-white/70 font-semibold mb-2">自訂翻譯提示詞</label>
                  <textarea v-model="localConfig.translation.translation_prompt" placeholder='例如: "Translate from Japanese to Traditional Chinese"' rows="5"
                    class="w-full px-4 py-3 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400 font-mono text-sm"></textarea>
                  <p class="text-white/40 text-sm mt-2">💡 當關閉智能提示詞時，將使用此提示詞進行翻譯</p>
                </div>
              </div>
            </div>
          </div>

          <!-- Llama Settings -->
          <div v-if="activeTab === 'llama'" class="settings-paint-section space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">🦙 Llama 設定</h2>
            <div class="bg-gradient-to-br from-yellow-500/10 to-orange-500/10 rounded-xl p-5 border border-yellow-500/20 mb-4">
              <p class="text-yellow-200 mb-2">💡 使用本地 llama.cpp 進行翻譯</p>
              <p class="text-white/60 text-sm">無需網路連線，支援 GPU 加速，保護資料隱私</p>
            </div>
            <LlamaSettings />
          </div>

          <!-- Terminology Settings -->
          <div v-if="activeTab === 'terminology'" class="settings-paint-section space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">術語表</h2>

            <div class="bg-gradient-to-br from-cyan-500/10 to-blue-500/10 rounded-xl p-5 border border-cyan-500/20">
              <div class="flex items-center justify-between gap-4">
                <div>
                  <h3 class="text-lg font-semibold text-cyan-300 mb-2">ASR 人名／專有名詞修正</h3>
                  <p class="text-white/60 text-sm">辨識完成後、翻譯之前，將常見誤辨統一成標準原文。長詞優先且不會連鎖替換。</p>
                </div>
                <label class="flex items-center gap-3 cursor-pointer shrink-0">
                  <input v-model="localConfig.transcription.asr_corrections_enabled" type="checkbox" class="w-6 h-6 accent-cyan-500" />
                  <span class="text-white font-semibold">{{ localConfig.transcription.asr_corrections_enabled ? '已啟用' : '已停用' }}</span>
                </label>
              </div>

              <label class="flex items-center gap-2 cursor-pointer mt-4 text-sm text-white/70">
                <input v-model="localConfig.transcription.asr_corrections_case_sensitive" type="checkbox" class="w-4 h-4 accent-cyan-500" />
                英文別名區分大小寫
              </label>

              <label class="flex items-center gap-2 cursor-pointer mt-3 text-sm text-white/70">
                <input v-model="localConfig.transcription.asr_correction_log_enabled" type="checkbox" class="w-4 h-4 accent-cyan-500" />
                記錄已套用的 ASR 修正（app/logs/asr_corrections.log）
              </label>

              <label class="flex items-center gap-2 cursor-pointer mt-3 text-sm text-white/70">
                <input v-model="localConfig.transcription.asr_correction_learning_enabled" type="checkbox" class="w-4 h-4 accent-cyan-500" />
                收集未命中詞與 alias 建議（app/logs/asr_correction_suggestions.json）
              </label>
            </div>

            <div class="rounded-xl p-5 border border-white/10 bg-white/[0.03] space-y-4">
              <div class="grid grid-cols-1 lg:grid-cols-[minmax(180px,0.8fr)_minmax(260px,1.4fr)_auto] gap-3">
                <input v-model="newAsrCanonical" type="text" placeholder="標準名稱，例如：桜島麻衣"
                  class="px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-cyan-400" />
                <input v-model="newAsrAliases" type="text" placeholder="常見誤辨，以逗號分隔：櫻島舞衣, 桜島舞衣"
                  class="px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-cyan-400"
                  @keyup.enter="addAsrCorrection" />
                <button @click="addAsrCorrection" class="bg-cyan-600 hover:bg-cyan-700 text-white font-semibold py-2 px-4 rounded-lg transition">
                  + 新增修正
                </button>
              </div>

              <div class="flex flex-wrap gap-3">
                <input v-model="asrCorrectionSearchQuery" type="text" placeholder="搜尋標準名稱或誤辨文字..."
                  class="flex-1 min-w-[220px] px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-cyan-400" />
                <button @click="importAsrCorrections" class="bg-white/10 hover:bg-white/20 text-white font-semibold py-2 px-4 rounded-lg transition border border-white/20">
                  匯入 CSV
                </button>
                <button @click="exportAsrCorrections" class="bg-white/10 hover:bg-white/20 text-white font-semibold py-2 px-4 rounded-lg transition border border-white/20">
                  匯出 CSV
                </button>
              </div>

              <div class="max-h-80 overflow-y-auto space-y-2">
                <div v-for="rule in visibleAsrCorrections" :key="`${rule.canonical}-${(rule.aliases || []).join('|')}`"
                  class="flex items-center justify-between gap-4 p-3 bg-white/5 rounded-lg border border-white/10">
                  <div class="min-w-0">
                    <div class="text-cyan-300 font-semibold">{{ rule.canonical }}</div>
                    <div class="text-white/55 text-sm break-words mt-1">誤辨：{{ (rule.aliases || []).join('、') }}</div>
                  </div>
                  <button @click="removeAsrCorrection(rule)" class="text-red-400 hover:text-red-300 shrink-0">刪除</button>
                </div>
                <div v-if="filteredAsrCorrections.length === 0" class="text-white/40 text-center py-6">
                  {{ (localConfig.transcription?.asr_correction_rules?.length || 0) === 0 ? '尚未新增 ASR 修正規則' : '沒有符合搜尋的規則' }}
                </div>
                <button
                  v-if="visibleAsrCorrections.length < filteredAsrCorrections.length"
                  @click="asrCorrectionRenderLimit += LARGE_LIST_BATCH_SIZE"
                  class="w-full py-2 text-sm text-cyan-300 hover:text-cyan-200 bg-white/5 hover:bg-white/10 rounded-lg"
                >
                  顯示更多（尚有 {{ filteredAsrCorrections.length - visibleAsrCorrections.length }} 筆）
                </button>
              </div>

              <div class="text-white/40 text-sm">共 {{ localConfig.transcription?.asr_correction_rules?.length || 0 }} 筆修正規則</div>
            </div>

            <h3 class="text-lg font-semibold text-purple-300 pt-4">翻譯術語表</h3>
            
            <!-- 啟用術語表開關 -->
            <div class="bg-gradient-to-br from-purple-500/10 to-blue-500/10 rounded-xl p-5 border border-purple-500/20 mb-6">
              <div class="flex items-center justify-between">
                <div class="flex-1">
                  <h3 class="text-lg font-semibold text-purple-300 mb-2">📖 術語表功能</h3>
                  <p class="text-white/60 text-sm">
                    啟用後,翻譯時會參考您設定的術語對照表,確保專有名詞翻譯一致性
                  </p>
                </div>
                <label class="flex items-center gap-3 cursor-pointer ml-6">
                  <input v-model="localConfig.terminology.use_terminology_glossary" type="checkbox" class="w-6 h-6 accent-purple-500" />
                  <span class="text-white font-semibold">{{ localConfig.terminology.use_terminology_glossary ? '已啟用' : '已停用' }}</span>
                </label>
              </div>
              <label class="flex items-center gap-2 cursor-pointer mt-4 text-sm text-white/70">
                <input v-model="localConfig.terminology.translation_glossary_audit_enabled" type="checkbox" class="w-4 h-4 accent-purple-500" />
                記錄術語遵循狀況與重複未命中（app/logs/translation_glossary_audit.log、translation_glossary_issues.json）
              </label>
            </div>
            
            <!-- 新增術語 -->
            <div class="flex flex-wrap gap-3 mb-6">
              <input v-model="newTermOriginal" type="text" placeholder="原文術語" 
                class="flex-1 min-w-[150px] px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
              <input v-model="newTermTranslated" type="text" placeholder="翻譯結果"
                class="flex-1 min-w-[150px] px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
              <button @click="addTerm" class="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg transition">
                + 新增
              </button>
            </div>

            <!-- 搜尋 & 匯入匯出 -->
            <div class="flex flex-wrap gap-3 mb-4">
              <input v-model="termSearchQuery" type="text" placeholder="搜尋術語..."
                class="flex-1 min-w-[200px] px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
              <button @click="importGlossary" class="bg-white/10 hover:bg-white/20 text-white font-semibold py-2 px-4 rounded-lg transition border border-white/20">
                📂 匯入 CSV
              </button>
              <button @click="exportGlossary" class="bg-white/10 hover:bg-white/20 text-white font-semibold py-2 px-4 rounded-lg transition border border-white/20">
                💾 匯出 CSV
              </button>
            </div>

            <!-- 術語列表 -->
            <div class="max-h-80 overflow-y-auto space-y-2">
              <div v-for="term in visibleGlossary" :key="`${term.original}-${term.translated}`"
                class="flex items-center justify-between p-3 bg-white/5 rounded-lg border border-white/10">
                <div class="flex-1 grid grid-cols-2 gap-4">
                  <span class="text-white">{{ term.original }}</span>
                  <span class="text-yellow-300">→ {{ term.translated }}</span>
                </div>
                <button @click="removeTermEntry(term)" class="text-red-400 hover:text-red-300 ml-4">✕</button>
              </div>
              <div v-if="filteredGlossary.length === 0" class="text-white/40 text-center py-8">
                {{ (localConfig.terminology?.glossary_list?.length || 0) === 0 ? '尚未新增術語' : '無符合搜尋的術語' }}
              </div>
              <button
                v-if="visibleGlossary.length < filteredGlossary.length"
                @click="glossaryRenderLimit += LARGE_LIST_BATCH_SIZE"
                class="w-full py-2 text-sm text-purple-300 hover:text-purple-200 bg-white/5 hover:bg-white/10 rounded-lg"
              >
                顯示更多（尚有 {{ filteredGlossary.length - visibleGlossary.length }} 筆）
              </button>
            </div>

            <div class="text-white/40 text-sm mt-4">
              共 {{ localConfig.terminology?.glossary_list?.length || 0 }} 個術語
            </div>
          </div>

          <!-- Output & Notification Settings -->
          <div v-if="activeTab === 'output'" class="settings-paint-section space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">輸出選項</h2>
            
            <div class="bg-white/5 rounded-xl p-4 border border-white/10 mb-6">
              <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                  <label class="block text-white/70 font-semibold mb-2">輸出目錄</label>
                  <input v-model="localConfig.output.output_dir" type="text" placeholder="./output"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2">最大歷史紀錄數</label>
                  <input v-model.number="localConfig.output.max_history" type="number" min="5" max="100"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>

                <div class="md:col-span-2">
                  <label class="block text-white/70 font-semibold mb-3">輸出格式</label>
                  <div class="flex flex-wrap gap-6">
                    <label class="flex items-center gap-2 cursor-pointer">
                      <input v-model="localConfig.output.output_srt" type="checkbox" class="w-5 h-5 accent-blue-500" />
                      <span class="text-white">SRT 字幕</span>
                    </label>
                    <label class="flex items-center gap-2 cursor-pointer">
                      <input v-model="localConfig.output.output_txt" type="checkbox" class="w-5 h-5 accent-blue-500" />
                      <span class="text-white">純文字</span>
                    </label>
                    <label class="flex items-center gap-2 cursor-pointer">
                      <input v-model="localConfig.output.output_ass" type="checkbox" class="w-5 h-5 accent-blue-500" />
                      <span class="text-white">ASS 字幕</span>
                    </label>
                  </div>
                </div>

                <div class="md:col-span-2">
                  <label class="block text-white/70 font-semibold mb-2">
                    自訂輸出檔案路徑
                    <span class="text-white/40 font-normal text-xs ml-2">（選填，留空則根據上方目錄與格式自動命名）</span>
                  </label>
                  <input v-model="localConfig.output_notification.output_file_path" type="text"
                    placeholder="例如：F:\subtitle\result.srt（留空則自動生成）"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                  <p class="text-white/40 text-xs mt-1">填寫後以此路徑為準，覆蓋自動生成的路徑。副檔名決定輸出格式（.srt/.txt/.ass）</p>
                </div>

                <div class="md:col-span-2">
                  <label class="flex items-center gap-2 cursor-pointer group">
                    <input v-model="localConfig.output_notification.hide_transcribe_result" type="checkbox" class="w-5 h-5 accent-blue-500" />
                    <div class="flex flex-col">
                      <span class="text-white group-hover:text-blue-300 transition">隱藏 Whisper 轉錄結果</span>
                      <span class="text-white/50 text-xs">開啟後只輸出翻譯結果，不顯示原始轉錄文字</span>
                    </div>
                  </label>
                </div>
              </div>
            </div>

            <!-- 通知設定 -->
            <h3 class="text-lg font-bold text-white mb-4">🔔 通知推播</h3>
            
            <!-- Discord -->
            <div class="bg-white/5 rounded-xl p-4 border border-white/10 mb-4">
              <div class="flex items-center justify-between mb-4">
                <h4 class="text-blue-300 font-semibold">Discord Webhook</h4>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input v-model="localConfig.output_notification.discord_enabled" type="checkbox" class="w-5 h-5 accent-blue-500" />
                  <span class="text-white">啟用</span>
                </label>
              </div>
              <div>
                <input v-model="localConfig.output_notification.discord_webhook_url" :disabled="!localConfig.output_notification.discord_enabled" type="text" placeholder="https://discord.com/api/webhooks/..."
                  :class="[
                    'w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400',
                    !localConfig.output_notification.discord_enabled ? 'opacity-50 cursor-not-allowed' : ''
                  ]" />
              </div>
            </div>

            <!-- Telegram -->
            <div class="bg-white/5 rounded-xl p-4 border border-white/10">
              <div class="flex items-center justify-between mb-4">
                <h4 class="text-blue-300 font-semibold">Telegram Bot</h4>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input v-model="localConfig.output_notification.telegram_enabled" type="checkbox" class="w-5 h-5 accent-blue-500" />
                  <span class="text-white">啟用</span>
                </label>
              </div>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label class="block text-white/70 text-sm mb-1">Bot Token</label>
                  <input v-model="localConfig.output_notification.telegram_bot_token" :disabled="!localConfig.output_notification.telegram_enabled" type="password" placeholder="123456:ABC-DEF..."
                    :class="[
                      'w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400',
                      !localConfig.output_notification.telegram_enabled ? 'opacity-50 cursor-not-allowed' : ''
                    ]" />
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">Chat ID</label>
                  <input v-model="localConfig.output_notification.telegram_chat_id" :disabled="!localConfig.output_notification.telegram_enabled" type="text" placeholder="@channel_name 或 -123456789"
                    :class="[
                      'w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400',
                      !localConfig.output_notification.telegram_enabled ? 'opacity-50 cursor-not-allowed' : ''
                    ]" />
                </div>
              </div>
            </div>
          </div>
        </div>



    <!-- Custom Model Dialog -->
    <div v-if="showCustomModelDialog" class="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      <div class="bg-gray-900 rounded-2xl border border-white/20 shadow-2xl p-6 w-full max-w-md mx-4">
        <h3 class="text-xl font-bold text-white mb-4">{{ editingModelIndex >= 0 ? '編輯' : '新增' }}自訂模型</h3>
        
        <div class="space-y-4">
          <div>
            <label class="block text-white/70 text-sm mb-1">模型名稱 *</label>
            <input v-model="customModelForm.name" type="text" placeholder="例如: Claude 3.5"
              class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
          </div>
          <div>
            <label class="block text-white/70 text-sm mb-1">Base URL *</label>
            <input v-model="customModelForm.base_url" type="text" placeholder="https://api.anthropic.com/v1"
              class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
          </div>
          <div>
            <label class="block text-white/70 text-sm mb-1">API Key</label>
            <input v-model="customModelForm.api_key" type="password" placeholder="選填"
              class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
          </div>
          <div>
            <label class="block text-white/70 text-sm mb-1">模型名稱 (API 參數)</label>
            <input v-model="customModelForm.model_name" type="text" placeholder="claude-3-5-sonnet-20241022"
              class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
          </div>
        </div>

        <div class="flex justify-end gap-3 mt-6">
          <button @click="showCustomModelDialog = false" class="bg-white/10 hover:bg-white/20 text-white font-semibold py-2 px-4 rounded-lg transition">
            取消
          </button>
          <button @click="saveCustomModel" class="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-4 rounded-lg transition">
            儲存
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-paint-section {
  contain: layout style;
}

.settings-paint-section > :not(.llama-settings) {
  /* Qt WebEngine 在長頁面使用 paint containment 時可能短暫漏畫 tile。 */
  contain: layout style;
}

.tooltip-container {
  position: relative;
  display: inline-flex;
  align-items: center;
  cursor: pointer;
}

.tooltip-text {
  visibility: hidden;
  position: absolute;
  bottom: 125%;
  left: 50%;
  transform: translateX(-50%);
  background-color: rgba(15, 23, 42, 0.95);
  color: #fff;
  text-align: left;
  padding: 8px 12px;
  border-radius: 8px;
  width: 260px;
  font-size: 0.75rem;
  line-height: 1.25rem;
  border: 1px solid rgba(255, 255, 255, 0.15);
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.3), 0 4px 6px -4px rgba(0, 0, 0, 0.3);
  z-index: 50;
  opacity: 0;
  transition: opacity 0.2s ease, transform 0.2s ease;
  pointer-events: none;
  font-weight: normal;
}

.tooltip-container:hover .tooltip-text {
  visibility: visible;
  opacity: 1;
  transform: translateX(-50%) translateY(-2px);
}
</style>
```
