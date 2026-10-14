<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick, toRaw, defineAsyncComponent } from 'vue';
import GeneralSettingsTab from '../components/settings/GeneralSettingsTab.vue';
import DiagnosticsSettingsTab from '../components/settings/DiagnosticsSettingsTab.vue';
import InputSettingsTab from '../components/settings/InputSettingsTab.vue';
import AudioVadSettingsTab from '../components/settings/AudioVadSettingsTab.vue';
import OutputSettingsTab from '../components/settings/OutputSettingsTab.vue';
import TranscriptionSettingsTab from '../components/settings/TranscriptionSettingsTab.vue';
import ModelManagementSettingsTab from '../components/settings/ModelManagementSettingsTab.vue';
import TranslationSettingsTab from '../components/settings/TranslationSettingsTab.vue';
import TerminologySettingsTab from '../components/settings/TerminologySettingsTab.vue';
import { provideSettingsContext, provideSettingsTabBindings } from '../composables/settings/settingsContext';
import { useRoute } from 'vue-router';
import { resolveTranslationFamily } from '../utils/translationFamily';
import axios from 'axios';
import { useTranslationStore } from '../stores/translation';
import { useModelDownloadStore } from '../stores/modelDownload';
import { useLlamaStore } from '../stores/llama';
import { type UiSelectOption } from '../components/UiSelect.vue';
import { useTranscriptionMutex } from '../composables/useTranscriptionMutex';
import { useAppSyncEvents } from '../composables/useAppSyncEvents';
import { runtimeApi, serverApi, type AppUpdateStatus, type CpuAsrSidecarInstallStatus, type ModelComputeBackend, type ModelEngine } from '../services/api';
import {
  ASR_LANGUAGE_OPTIONS,
  coerceLanguageForModel,
  isModelLanguageCompatible,
  languageOptionsForModel,
} from '../utils/asrCapabilities';

const testingGpt = ref(false);
const testingGemini = ref(false);
const hyMt2HealthChecking = ref(false);
const hyMt2HealthResult = ref('');
const LlamaSettings = defineAsyncComponent(() => import('../components/LlamaSettings.vue'));

const autoSaveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle');
const glossaryImporting = ref(false);
const asrCorrectionsImporting = ref(false);
const settingsReady = ref(false);
const sharingLanAddresses = ref<string[]>([]);
const copiedSharingUrl = ref('');
const appUpdateStatus = ref<AppUpdateStatus | null>(null);
const appUpdateBusy = computed(() => ['starting', 'downloading', 'verifying', 'staging'].includes(appUpdateStatus.value?.status || ''));
let appUpdatePollTimer: ReturnType<typeof setInterval> | null = null;
let autoSaveStatusTimeout: ReturnType<typeof setTimeout> | null = null;
const suspendedAutoSaveSections = new Set<string>();


const route = useRoute();
const store = useTranslationStore();
const modelDownloadStore = useModelDownloadStore();

function stopAppUpdatePolling() {
  if (appUpdatePollTimer) clearInterval(appUpdatePollTimer);
  appUpdatePollTimer = null;
}

async function refreshAppUpdateStatus() {
  appUpdateStatus.value = await runtimeApi.getAppUpdateStatus();
  if (!appUpdateBusy.value) stopAppUpdatePolling();
}

async function checkAppUpdate() {
  try {
    appUpdateStatus.value = await runtimeApi.checkAppUpdate();
  } catch (error: any) {
    appUpdateStatus.value = { ...(appUpdateStatus.value || {} as AppUpdateStatus), status: 'error', error: error?.message || '檢查更新失敗' };
  }
}

async function downloadAppUpdate() {
  try {
    appUpdateStatus.value = await runtimeApi.downloadAppUpdate();
    stopAppUpdatePolling();
    appUpdatePollTimer = setInterval(() => void refreshAppUpdateStatus(), 1000);
  } catch (error: any) {
    appUpdateStatus.value = { ...(appUpdateStatus.value || {} as AppUpdateStatus), status: 'error', error: error?.response?.data?.detail || error?.message || '下載更新失敗' };
  }
}

async function cancelAppUpdate() {
  appUpdateStatus.value = await runtimeApi.cancelAppUpdate();
}

async function applyAppUpdate() {
  try {
    const handoff = await runtimeApi.prepareAppUpdateApply();
    const bridge = (window as any).pyqt;
    if (!bridge?.applyAppUpdate) throw new Error('只有 Windows 桌面版可以套用更新');
    bridge.applyAppUpdate(handoff.plan_path, handoff.updater_path);
  } catch (error: any) {
    appUpdateStatus.value = { ...(appUpdateStatus.value || {} as AppUpdateStatus), status: 'error', error: error?.response?.data?.detail || error?.message || '無法啟動更新器' };
  }
}
const llamaStore = useLlamaStore();


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
const translationModelFamilyOptions: UiSelectOption[] = [
  { value: 'auto', label: '自動判斷' },
  { value: 'hy_mt2', label: 'Hy-MT2 專用翻譯模型' },
  { value: 'index_translate', label: 'Index-Translate 專用翻譯模型' },
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
    max_audio_length: 8.0,
    target_audio_length: 4.0,
    continuous_no_speech_threshold: 0.5,
    disable_dynamic_no_speech_threshold: false,
    prefix_retention_length: 0.25,
    vad_enabled: true,
    vad_threshold: 0.35,
    disable_dynamic_vad_threshold: false,
    vad_every_n_frames: 2,
    vad_backend: 'firered',
    firered_vad_model_path: '',
    slicing_mode: 'omnivad_native',
    omnivad_threshold: 0.35,
    omnivad_max_audio_length: 6.0,
    omnivad_smooth_window_size: 5,
    omnivad_pad_start_frame: 5,
    omnivad_min_speech_frame: 8,
    omnivad_max_speech_frame: 2000,
    omnivad_min_silence_frame: 20
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
    gemini_model: 'gemini-2.5-flash-lite',
    gpt_base_url: 'https://api.openai.com/v1',
    gemini_base_url: 'https://generativelanguage.googleapis.com/v1beta',
    translation_history_size: 0,
    translation_timeout: 10,
    processing_proxy: '',
    use_json_result: false,
    translation_model_family: 'auto',
    translation_output_format: 'auto',
    translation_max_concurrency: 0,
    translation_max_output_tokens: 128,
    hy_mt2_optimizer_enabled: false,
    hy_mt2_context_window: 3,
    hy_mt2_max_context_chars: 1000,
    hy_mt2_max_terms: 10,
    hy_mt2_style: true,
    hy_mt2_style_text: '使用自然、簡潔的台灣繁體中文直播字幕；保留原文語氣，不要補充原文沒有的資訊；只輸出譯文。',
    hy_mt2_preferences: '',
    hy_mt2_debug: false,
    hy_mt2_provider: 'existing',
    hy_mt2_lm_studio_url: 'http://127.0.0.1:1234/v1',
    hy_mt2_lm_studio_model: '',
    hy_mt2_lm_studio_api_key: '',
    hy_mt2_llama_cpp_url: 'http://127.0.0.1:8081/v1',
    hy_mt2_llama_cpp_model: '',
    hy_mt2_llama_cpp_api_key: '',
    hy_mt2_glossary_folder: '',
    hy_mt2_glossary_preset: '',
    index_translate_optimizer_enabled: false,
    index_translate_context_window: 3,
    index_translate_max_context_chars: 1000,
    index_translate_max_terms: 10,
    index_translate_style: true,
    index_translate_style_text: '使用自然、簡潔的台灣繁體中文直播字幕；保留原文語氣，不要補充原文沒有的資訊；只輸出譯文。',
    index_translate_preferences: '',
    index_translate_debug: false,
    index_translate_provider: 'existing',
    index_translate_lm_studio_url: 'http://127.0.0.1:1234/v1',
    index_translate_lm_studio_model: '',
    index_translate_lm_studio_api_key: '',
    index_translate_llama_cpp_url: 'http://127.0.0.1:8081/v1',
    index_translate_llama_cpp_model: '',
    index_translate_llama_cpp_api_key: '',
    index_translate_glossary_folder: '',
    index_translate_glossary_preset: '',
    translation_glossary_scope: null,
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
    glossary_list: [],
    custom_glossary_scopes: []
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
const cookiePlatform = ref('youtube');
const cookieBrowser = ref('chrome');
const cookieBrowserProfile = ref('');
const cookieImporting = ref(false);
const cookieFileInput = ref<HTMLInputElement | null>(null);
const cookieImportResult = ref<{ type: 'success' | 'error'; message: string } | null>(null);
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
watch(cookiePlatform, () => {
  cookieImportResult.value = null;
});

const settingsTabIds = new Set([
  'general',
  'input',
  'output',
  'diagnostics',
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

const activeTranslationFamily = computed(() => resolveTranslationFamily(localConfig.value.translation));
const familySettings = computed(() => activeTranslationFamily.value === 'index_translate' ? 'index_translate' : 'hy_mt2');
const familyLabel = computed(() => activeTranslationFamily.value === 'index_translate' ? 'Index-Translate' : 'HY-MT2');
const previewText = ref('今日はすいちゃんと一緒にゲームをします。');
const previewContext = ref('');
const previewBusy = ref(false);
const previewError = ref('');
const previewResult = ref<any>(null);
function previewValidationStatus(result: any): string {
  const reasons = Array.isArray(result?.validation)
    ? result.validation.map((issue: any) => issue.code).filter(Boolean).join('、') : '';
  if (result?.error) return reasons ? `未通過：${reasons}` : '未完成：翻譯請求失敗';
  if (!String(result?.translation || '').trim()) return reasons ? `未通過：${reasons}` : '未通過：空白譯文';
  return reasons ? `未通過：${reasons}` : '通過';
}
function previewLatencyLabel(value: unknown): string {
  const milliseconds = Number(value);
  return Number.isFinite(milliseconds) && milliseconds >= 0 ? `${Math.round(milliseconds)} ms` : '未取得';
}

async function runTranslationPreview() {
  previewBusy.value = true;
  previewError.value = '';
  previewResult.value = null;
  try {
    const response = await axios.post('/api/translation/preview', {
      text: previewText.value,
      context: previewContext.value.split('\n').filter(Boolean).map(source => ({source, target: ''})),
      config: { translation: toRaw(localConfig.value.translation), terminology: toRaw(localConfig.value.terminology), transcription: {language: localConfig.value.transcription.language} },
    });
    previewResult.value = response.data;
  } catch (e: any) {
    previewError.value = e?.response?.data?.detail || '試譯失敗，請檢查端點與模型 ID。';
  } finally { previewBusy.value = false; }
}

const hyMt2EffectiveBackend = computed(() => {
  const t = localConfig.value.translation;
  const provider = t[familySettings.value + '_provider'];
  if (['lm_studio', 'llama_cpp'].includes(provider)) {
    return `${provider === 'lm_studio' ? 'LM Studio' : 'llama.cpp'} · ${t[familySettings.value + '_' + provider + '_model'] || '尚未填模型 ID'}`;
  }
  const selected = String(t.backend || 'none');
  const custom = (t.custom_models || []).find((m: any) => `custom:${m.name}` === selected);
  return `目前模型 · ${custom?.model_name || t.gpt_model || selected}`;
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
  if (existing) await existing.catch(() => undefined);
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
    } catch (e: any) {
      const detail = e?.response?.data?.detail ?? e?.message ?? String(e);
      console.warn(`[SettingsView] ${section} 自動保存失敗: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`);
      autoSaveStatus.value = 'error';
      throw e;
    } finally {
      sectionSaveInFlight.delete(section);
    }
  })();
  sectionSaveInFlight.set(section, request);
  await request;
}

async function checkHyMt2Backend() {
  hyMt2HealthChecking.value = true;
  hyMt2HealthResult.value = '';
  try {
    const pendingSave = sectionSaveTimers.get('translation');
    if (pendingSave) clearTimeout(pendingSave);
    sectionSaveTimers.delete('translation');
    await saveSectionNow('translation');
    const response = await axios.post('/api/translation/health', {config: {translation: toRaw(localConfig.value.translation), terminology: toRaw(localConfig.value.terminology)}});
    const result = response.data;
    hyMt2HealthResult.value = `已連線 ${result.model}；測試回應「${result.sample}」（${result.latency_ms} ms）`;
  } catch (error: any) {
    hyMt2HealthResult.value = `連線失敗：${error?.response?.data?.detail || error?.message || '未知錯誤'}`;
  } finally {
    hyMt2HealthChecking.value = false;
  }
}

function debouncedAutoSaveSection(section: string) {
  if (suspendedAutoSaveSections.has(section)) return;
  autoSaveStatus.value = 'saving';
  const currentTimer = sectionSaveTimers.get(section);
  if (currentTimer) clearTimeout(currentTimer);
  sectionSaveTimers.set(section, setTimeout(() => {
    sectionSaveTimers.delete(section);
    // saveSectionNow reports the error; background timers have no caller
    // to handle a rejected promise (bulk imports still receive failures).
    void saveSectionNow(section).catch(() => undefined);
  }, 1000));
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
const newTermAliases = ref('');
const newTermScope = ref('all');
const glossaryEntryForm = ref<HTMLElement | null>(null);
const glossaryUserList = ref<HTMLElement | null>(null);
const termSearchQuery = ref('');
const terminologySubTab = ref<'translation' | 'asr'>('translation');
const expandedGlossaryTerm = ref<any | null>(null);
const selectedGlossaryTerms = ref<any[]>([]);
const bulkGlossaryScope = ref('hololive_vtuber');
const removedGlossaryTerm = ref<{ term: any; index: number } | null>(null);
const glossaryListMode = ref<'active' | 'all' | 'global'>('active');
const presetGlossaries = ref<Record<string, Record<string, string>>>({});
const builtinGlossaryScopeOptions = [
  { value: 'all', label: '所有直播' },
  { value: 'general_chat', label: '日文雜談' },
  { value: 'hololive_vtuber', label: 'Hololive／VTuber 雜談' },
  { value: 'cosplay', label: 'Cosplay 雜談' },
];
const customGlossaryScopes = computed<{ value: string; label: string }[]>(() =>
  Array.isArray(localConfig.value.terminology?.custom_glossary_scopes)
    ? localConfig.value.terminology.custom_glossary_scopes.filter((scope: any) =>
      typeof scope?.value === 'string' && scope.value.startsWith('custom_') && typeof scope?.label === 'string')
    : []);
const glossaryScopeOptions = computed(() => [...builtinGlossaryScopeOptions, ...customGlossaryScopes.value]);
const newGlossaryScopeName = ref('');
const editingGlossaryScope = ref('');
const editingGlossaryScopeName = ref('');
const selectedGlossaryPreset = computed(() => String(localConfig.value.translation?.translation_glossary_scope ?? localConfig.value.translation?.hy_mt2_glossary_preset ?? ''));
const selectedGlossaryPresetLabel = computed(() => glossaryScopeOptions.value.find(option => option.value === selectedGlossaryPreset.value)?.label || '不加情境詞表');
const activeUserGlossaryRows = computed<any[]>(() => {
  const rows: any[] = localConfig.value.terminology?.glossary_list || [];
  const globalRows = rows.filter(row => String(row?.scope || 'all') === 'all');
  const scopedRows = rows.filter(row => selectedGlossaryPreset.value && row?.scope === selectedGlossaryPreset.value);
  return [...globalRows, ...scopedRows];
});
const userGlossaryBySource = computed(() => {
  const values = new Map<string, string>();
  if (!localConfig.value.terminology?.use_terminology_glossary) return values;
  const legacy = localConfig.value.terminology?.terminology_glossary || {};
  if (Object.keys(legacy).length > 0) {
    for (const [source, target] of Object.entries(legacy)) values.set(source, String(target));
  } else {
    for (const row of activeUserGlossaryRows.value) {
      if (row.original?.trim() && row.translated?.trim()) values.set(row.original.trim(), row.translated.trim());
    }
  }
  return values;
});
const selectedPresetPreview = computed(() => Object.entries(presetGlossaries.value[selectedGlossaryPreset.value] || {}).map(([source, target]) => ({
  source, target, override: userGlossaryBySource.value.get(source),
})));
const activeGlossaryRows = computed<any[]>(() => {
  const legacy = localConfig.value.terminology?.terminology_glossary || {};
  const userRows = !localConfig.value.terminology?.use_terminology_glossary ? []
    : Object.keys(legacy).length
      ? Object.entries(legacy).map(([original, translated]) => ({ original, translated: String(translated), legacy: true }))
      : [...new Map(activeUserGlossaryRows.value.map(row => [row.original?.trim(), row])).values()];
  const userSources = new Set(userRows.map(row => row.original?.trim()));
  const builtinRows = selectedPresetPreview.value
    .filter(term => !userSources.has(term.source))
    .map(term => ({ original: term.source, translated: term.target, scope: selectedGlossaryPreset.value, builtin: true }));
  return [...userRows, ...builtinRows];
});
const effectiveGlossaryCount = computed(() => {
  const sources = new Set(userGlossaryBySource.value.keys());
  for (const term of selectedPresetPreview.value) sources.add(term.source);
  return sources.size;
});
const newAsrCanonical = ref('');
const newAsrAliases = ref('');
const asrCorrectionSearchQuery = ref('');
const LARGE_LIST_BATCH_SIZE = 100;
const GLOSSARY_PAGE_SIZE = 20;
const glossaryRenderLimit = ref(GLOSSARY_PAGE_SIZE);
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

// 過濾後的術語表
const filteredGlossary = computed(() => {
  const allRows = localConfig.value.terminology?.glossary_list || [];
  const list = glossaryListMode.value === 'active' ? activeGlossaryRows.value
    : glossaryListMode.value === 'global' ? allRows.filter((row: any) => String(row?.scope || 'all') === 'all')
    : allRows;
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
const cpuQwenModels = ['Qwen/Qwen3-ASR-0.6B', 'Qwen/Qwen3-ASR-1.7B'];
const cpuSenseVoiceModels = ['iic/SenseVoiceSmall'];
const cpuFunAsrModels = ['FunAudioLLM/Fun-ASR-Nano-2512'];
const cpuParakeetModels = ['nvidia/parakeet-tdt-0.6b-v3', 'nvidia/parakeet-tdt_ctc-0.6b-ja'];
const cpuQwenDescriptions = {
  'Qwen/Qwen3-ASR-0.6B': 'Sherpa-ONNX 專用 INT8 ONNX bundle；CPU 離線推論，不使用 PyTorch、CUDA dtype 或 4-bit 設定。',
  'Qwen/Qwen3-ASR-1.7B': 'Sherpa-ONNX INT8 1.7B CPU bundle；準確度較高，但下載約 2.4 GB、推論速度與記憶體需求也高於 0.6B。',
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
const cpuAsrOfflineArchive = ref('');
const diagnosticsBusy = ref(false);
const cpuAsrSidecarBusy = computed(() =>
  ['starting', 'downloading', 'verifying', 'installing'].includes(cpuAsrSidecarStatus.value?.status || '')
);
const canInstallCpuAsrSidecar = computed(() =>
  ['cuda', 'rocm'].includes(runtimeStatus.value?.profile || '')
  && !cpuAsrSidecarBusy.value
);
const canCancelCpuAsrSidecar = computed(() =>
  cpuAsrSidecarBusy.value && cpuAsrSidecarStatus.value?.status !== 'installing'
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
      healthy: false, health_error: '',
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
      healthy: false, health_error: '',
      error: error?.response?.data?.detail || error?.message || '無法啟動 sidecar 安裝',
    };
    return;
  }
  stopCpuAsrSidecarPolling();
  cpuAsrSidecarPollTimer = setInterval(() => void refreshCpuAsrSidecarStatus(), 1000);
}

async function cancelCpuAsrSidecarInstall() {
  try {
    cpuAsrSidecarStatus.value = await runtimeApi.cancelCpuAsrSidecarInstall();
  } catch (error: any) {
    cpuAsrSidecarStatus.value = {
      ...(cpuAsrSidecarStatus.value || {
        status: 'error', progress: 0, message: '', installed: false, restart_required: false,
        bytes_downloaded: 0, bytes_total: 0, version: '', asset_name: '', healthy: false, health_error: '',
      }),
      status: 'error', error: error?.response?.data?.detail || error?.message || '無法取消 sidecar 安裝',
    };
  }
}

async function importCpuAsrSidecarOffline() {
  const archive = cpuAsrOfflineArchive.value.trim();
  if (!archive) return;
  try {
    cpuAsrSidecarStatus.value = await runtimeApi.importCpuAsrSidecar(archive);
    if (cpuAsrSidecarStatus.value.installed) await store.loadRuntimeStatus();
  } catch (error: any) {
    cpuAsrSidecarStatus.value = {
      ...(cpuAsrSidecarStatus.value || {
        status: 'error', progress: 0, message: '', installed: false, restart_required: false,
        bytes_downloaded: 0, bytes_total: 0, version: '', asset_name: '', healthy: false, health_error: '',
      }),
      status: 'error', error: error?.response?.data?.detail || error?.message || '離線 Runtime 匯入失敗',
    };
  }
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
  glossaryRenderLimit.value = GLOSSARY_PAGE_SIZE;
});
watch(selectedGlossaryPreset, (preset) => {
  newTermScope.value = preset || 'all';
  glossaryRenderLimit.value = GLOSSARY_PAGE_SIZE;
});
watch(glossaryListMode, () => {
  glossaryRenderLimit.value = GLOSSARY_PAGE_SIZE;
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

function getModelTask(engine: ModelEngine, modelId: string) {
  return modelDownloadStore.getTask(engine, modelId);
}

function canStartDownload(engine: ModelEngine, modelId: string): boolean {
  const task = getModelTask(engine, modelId);
  return !modelDownloadStore.isDownloaded(engine, modelId)
    && task?.status !== 'pending'
    && task?.status !== 'downloading';
}

async function startModelDownload(engine: ModelEngine, modelId: string) {
  await modelDownloadStore.startDownload(engine, modelId);
}

function getModelStatusText(engine: ModelEngine, modelId: string): string {
  if (modelDownloadStore.isDownloaded(engine, modelId)) return '已下載';
  const task = getModelTask(engine, modelId);
  if (!task) return '尚未下載';
  if (task.status === 'pending') return '等待下載';
  if (task.status === 'downloading') return task.message || '下載中';
  if (task.status === 'completed') return '下載完成';
  if (task.status === 'failed') return task.error || task.message || '下載失敗';
  return task.message || task.status;
}

function getModelStatusClass(engine: ModelEngine, modelId: string): string {
  if (modelDownloadStore.isDownloaded(engine, modelId)) return 'text-emerald-300';
  const status = getModelTask(engine, modelId)?.status;
  if (status === 'failed') return 'text-red-300';
  if (status === 'pending' || status === 'downloading') return 'text-blue-300';
  return 'text-white/50';
}

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
    return 'ROCm package/profile is selected. Export the Runtime diagnostics report on an AMD GPU machine and run an ASR sample to confirm HIP execution; package validation alone does not verify inference.';
  }
  return 'ROCm package/profile is selected, but no suitable AMD discrete GPU is selected on this machine. Package validation can still pass; ROCm GPU inference remains unverified until an AMD machine exports diagnostics and passes an ASR sample.';
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
    // Config is a fast, cached YAML read.  Do not keep the whole settings UI
    // behind cold Torch/GPU or llama.cpp probes, which can take many seconds.
    await store.loadConfig();
    await applyStoreConfigToLocalConfig(store.config, false);
  } finally {
    await nextTick();
    settingsReady.value = true;
  }

  const runtimeStatusPromise = store.loadRuntimeStatus();
  void axios.get('/api/config/hy-mt2-glossary-presets').then((response) => {
    presetGlossaries.value = response.data || {};
  }).catch(() => { presetGlossaries.value = {}; });
  void serverApi.getInfo().then((serverInfo) => {
    if (serverInfo?.lan_addresses) sharingLanAddresses.value = serverInfo.lan_addresses;
  }).catch(() => null);
  void refreshAppUpdateStatus().catch(() => null);
  void (async () => {
    await llamaStore.loadConfig();
    await llamaStore.refreshServerStatus();
  })();

  // 從 URL 參數設定 tab
  syncActiveTabFromRoute();

  if (activeTab.value === 'model_management') {
    await runtimeStatusPromise;
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
      if (isApplyingRemoteConfig.value || suspendedAutoSaveSections.has(section)) return;
      debouncedAutoSaveSection(section);
    }, { deep: true, flush: 'post' });
  }

  watch(runtimeCapabilities, () => {
    if (isApplyingRemoteConfig.value) return;
    coerceAsrSettingsForRuntime();
  }, { flush: 'post' });

  watch(
    [
      () => localConfig.value.audio_slicing_vad.slicing_mode,
      () => localConfig.value.audio_slicing_vad.vad_backend,
      () => localConfig.value.audio_slicing_vad.vad_enabled,
    ],
    () => {
      if (isApplyingRemoteConfig.value) return;
      const vad = localConfig.value.audio_slicing_vad;
      if (vad.slicing_mode !== 'omnivad_native') return;
      vad.vad_backend = 'firered';
      vad.vad_enabled = true;
    },
    { flush: 'sync' },
  );

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
  stopAppUpdatePolling();
});

async function applyModelStoragePath() {
  await store.saveConfig(localConfig.value);
  await modelDownloadStore.refreshAll();
}

async function deleteDownloadedModel(engine: ModelEngine, modelId: string, computeBackend: ModelComputeBackend) {
  if (!confirm(`確定要刪除模型「${modelId}」嗎？之後使用時需要重新下載。`)) return;
  await modelDownloadStore.deleteModel(engine, modelId, computeBackend);
}

async function resetToDefault() {
  if (confirm('確定要重置為後端預設值嗎？此操作無法復原。')) {
    await store.resetConfig();
    await applyStoreConfigToLocalConfig(store.config, true);
  }
}

// 術語表操作
function addGlossaryScope() {
  const label = newGlossaryScopeName.value.trim();
  if (!label) return;
  if (glossaryScopeOptions.value.some(scope => scope.label.toLocaleLowerCase() === label.toLocaleLowerCase())) {
    store.statusMessage = '已有同名情境，請換一個名稱';
    return;
  }
  const value = `custom_${crypto.randomUUID()}`;
  if (!Array.isArray(localConfig.value.terminology.custom_glossary_scopes)) {
    localConfig.value.terminology.custom_glossary_scopes = [];
  }
  localConfig.value.terminology.custom_glossary_scopes.push({ value, label });
  localConfig.value.translation.translation_glossary_scope = value;
  newGlossaryScopeName.value = '';
  store.statusMessage = `已建立「${label}」，儲存設定後可在翻譯時使用`;
}

function renameGlossaryScope(scope: { value: string; label: string }) {
  const label = editingGlossaryScopeName.value.trim();
  if (!label) return;
  if (glossaryScopeOptions.value.some(other => other.value !== scope.value && other.label.toLocaleLowerCase() === label.toLocaleLowerCase())) {
    store.statusMessage = '已有同名情境，請換一個名稱';
    return;
  }
  scope.label = label;
  editingGlossaryScope.value = '';
}

function removeGlossaryScope(scope: { value: string; label: string }) {
  const count = (localConfig.value.terminology.glossary_list || []).filter((term: any) => term.scope === scope.value).length;
  if (count) {
    store.statusMessage = `「${scope.label}」還有 ${count} 筆詞條，請先將詞條移到其他情境`;
    glossaryListMode.value = 'all';
    return;
  }
  localConfig.value.terminology.custom_glossary_scopes = customGlossaryScopes.value.filter(item => item.value !== scope.value);
  if (selectedGlossaryPreset.value === scope.value) localConfig.value.translation.translation_glossary_scope = '';
  if (newTermScope.value === scope.value) newTermScope.value = 'all';
  if (bulkGlossaryScope.value === scope.value) bulkGlossaryScope.value = 'all';
  editingGlossaryScope.value = '';
}

function addTerm() {
  if (!newTermOriginal.value.trim() || !newTermTranslated.value.trim()) return;
  if (!localConfig.value.terminology.glossary_list) {
    localConfig.value.terminology.glossary_list = [];
  }
  const original = newTermOriginal.value.trim();
  if (localConfig.value.terminology.glossary_list.some((term: any) =>
    term.original?.trim() === original && String(term.scope || 'all') === newTermScope.value)) {
    store.statusMessage = `「${original}」已在此情境存在；請直接編輯下方詞條`;
    glossaryListMode.value = 'all';
    termSearchQuery.value = original;
    return;
  }
  const created = {
    original,
    translated: newTermTranslated.value.trim(),
    aliases: newTermAliases.value.split(',').map(s => s.trim()).filter(Boolean),
    scope: newTermScope.value,
  };
  localConfig.value.terminology.glossary_list.push(created);
  expandedGlossaryTerm.value = created;
  termSearchQuery.value = original;
  if (newTermScope.value !== 'all' && newTermScope.value !== selectedGlossaryPreset.value) glossaryListMode.value = 'all';
  newTermOriginal.value = '';
  newTermTranslated.value = '';
  newTermAliases.value = '';
}

function removeTerm(index: number) {
  localConfig.value.terminology.glossary_list.splice(index, 1);
}

function removeTermEntry(term: any) {
  const list = localConfig.value.terminology.glossary_list || [];
  const index = list.indexOf(term);
  if (index < 0) return;
  removedGlossaryTerm.value = { term: structuredClone(toRaw(term)), index };
  removeTerm(index);
  selectedGlossaryTerms.value = selectedGlossaryTerms.value.filter(item => item !== term);
  if (expandedGlossaryTerm.value === term) expandedGlossaryTerm.value = null;
}

function undoRemovedGlossaryTerm() {
  const removed = removedGlossaryTerm.value;
  if (!removed) return;
  localConfig.value.terminology.glossary_list.splice(removed.index, 0, removed.term);
  removedGlossaryTerm.value = null;
}

function toggleGlossarySelection(term: any, checked: boolean) {
  selectedGlossaryTerms.value = checked
    ? [...selectedGlossaryTerms.value.filter(item => item !== term), term]
    : selectedGlossaryTerms.value.filter(item => item !== term);
}

function selectVisibleGlossaryTerms() {
  selectedGlossaryTerms.value = [...new Set([...selectedGlossaryTerms.value, ...visibleGlossary.value.filter((term: any) => !term.builtin && !term.legacy)])];
}

function applySelectedGlossaryScope() {
  const rows = localConfig.value.terminology.glossary_list || [];
  let changed = 0;
  let conflicts = 0;
  for (const term of selectedGlossaryTerms.value) {
    if (!rows.includes(term) || String(term.scope || 'all') === bulkGlossaryScope.value) continue;
    const duplicate = rows.some((other: any) => other !== term
      && other.original?.trim() === term.original?.trim()
      && String(other.scope || 'all') === bulkGlossaryScope.value);
    if (duplicate) { conflicts += 1; continue; }
    term.scope = bulkGlossaryScope.value;
    changed += 1;
  }
  selectedGlossaryTerms.value = [];
  store.statusMessage = `已調整 ${changed} 筆詞條${conflicts ? `；${conflicts} 筆因同情境已有相同原詞而略過` : ''}`;
}

function setTermScope(term: any, value: string | number | null) {
  const scope = String(value || 'all');
  const duplicate = (localConfig.value.terminology.glossary_list || []).some((other: any) =>
    other !== term && other.original?.trim() === term.original?.trim() && String(other.scope || 'all') === scope);
  if (duplicate) {
    store.statusMessage = `「${term.original}」在此情境已有譯法；請先處理重複詞條`;
    return;
  }
  term.scope = scope;
}

function setTermAliases(term: any, event: Event) {
  term.aliases = (event.target as HTMLInputElement).value.split(/[,，]/).map(value => value.trim()).filter(Boolean);
}

function customizePresetTerm(source: string, target: string, hasOverride: boolean) {
  if (hasOverride) {
    glossaryListMode.value = 'active';
    termSearchQuery.value = source;
    expandedGlossaryTerm.value = Object.keys(localConfig.value.terminology?.terminology_glossary || {}).length
      ? null : activeUserGlossaryRows.value.find(row => row.original?.trim() === source) || null;
    void nextTick(() => glossaryUserList.value?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
    return;
  }
  newTermOriginal.value = source;
  newTermTranslated.value = target;
  newTermAliases.value = '';
  newTermScope.value = selectedGlossaryPreset.value || 'all';
  void nextTick(() => glossaryEntryForm.value?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
}

/**
 * Parse the two-column files accepted by the settings page.
 *
 * The old implementation used `split(',')`, which made an exported glossary
 * unusable as soon as a term contained a comma, a quote, or a line break.  A
 * small RFC-4180 compatible parser keeps this dependency-free and also accepts
 * tab-separated text exported by spreadsheet applications.
 */
function parseDelimitedRows(text: string): string[][] {
  const source = text.replace(/^\uFEFF/, '');
  const firstLine = source.split(/\r?\n/, 1)[0] || '';
  const delimiterCounts = { ',': 0, '\t': 0, '，': 0 } as Record<string, number>;
  let delimiterQuoted = false;
  for (let index = 0; index < firstLine.length; index += 1) {
    const character = firstLine[index];
    if (character === '"') {
      if (firstLine[index + 1] === '"') index += 1;
      else delimiterQuoted = !delimiterQuoted;
    } else if (!delimiterQuoted && character in delimiterCounts) {
      delimiterCounts[character] += 1;
    }
  }
  const delimiter = (Object.entries(delimiterCounts)
    .sort((left, right) => right[1] - left[1])[0]?.[1] || 0) > 0
    ? Object.entries(delimiterCounts).sort((left, right) => right[1] - left[1])[0][0]
    : ',';
  const rows: string[][] = [];
  let row: string[] = [];
  let field = '';
  let quoted = false;

  const pushRow = () => {
    // Keep quoted whitespace intact, but ignore the incidental whitespace
    // around unquoted values that is common in hand-written CSV files.
    row.push(field);
    if (row.some(value => value.trim())) rows.push(row);
    row = [];
    field = '';
  };

  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (quoted) {
      if (character === '"') {
        if (source[index + 1] === '"') {
          field += '"';
          index += 1;
        } else {
          quoted = false;
        }
      } else {
        field += character;
      }
    } else if (character === '"' && field.trim() === '') {
      // Permit the common `  "quoted value"` spelling while avoiding the
      // incidental spaces becoming part of the parsed value.
      field = '';
      quoted = true;
    } else if (character === delimiter) {
      row.push(field.trim());
      field = '';
    } else if (character === '\n') {
      pushRow();
    } else if (character === '\r') {
      if (source[index + 1] === '\n') index += 1;
      pushRow();
    } else {
      field += character;
    }
  }
  if (field.length > 0 || row.length > 0) pushRow();
  return rows;
}

function isGlossaryHeader(row: string[]): boolean {
  const original = (row[0] || '').trim().toLowerCase();
  const translated = (row[1] || '').trim().toLowerCase();
  return ['original', 'source', '原文', '來源'].includes(original)
    && ['translated', 'translation', 'target', '翻譯', '譯文'].includes(translated);
}

function isAsrCorrectionHeader(row: string[]): boolean {
  const canonical = (row[0] || '').trim().toLowerCase();
  return ['canonical', 'standard', 'name', '標準', '標準名稱', '正確名稱'].includes(canonical);
}

function csvField(value: unknown): string {
  const text = String(value ?? '');
  return /[",\r\n\t]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function glossaryExportRows(): string[][] {
  const terminology = localConfig.value.terminology || {};
  const rows: string[][] = [];
  const seen = new Set<string>();
  const add = (original: unknown, translated: unknown, scope: unknown = 'all', aliases: unknown = []) => {
    const source = String(original ?? '').trim();
    const target = String(translated ?? '').trim();
    const termScope = String(scope || 'all');
    if (!source || !target) return;
    const key = `${source}\u0000${termScope}`;
    if (seen.has(key)) return;
    seen.add(key);
    const aliasList = Array.isArray(aliases) ? aliases : String(aliases || '').split(/[,，]/);
    rows.push([source, target, termScope, aliasList.map(value => String(value).trim()).filter(Boolean).join(', ')]);
  };

  if (terminology.terminology_glossary && typeof terminology.terminology_glossary === 'object') {
    for (const [original, translated] of Object.entries(terminology.terminology_glossary)) {
      add(original, translated);
    }
  }
  if (Array.isArray(terminology.glossary_list)) {
    for (const term of terminology.glossary_list) add(term?.original, term?.translated, term?.scope, term?.aliases);
  }
  // Older configurations used `glossary` as either a JSON object or a small
  // delimited text block. Include it as well so export always means *all*.
  if (typeof terminology.glossary === 'string' && terminology.glossary.trim()) {
    const legacy = terminology.glossary.trim();
    try {
      const parsed = JSON.parse(legacy);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        for (const [original, translated] of Object.entries(parsed)) add(original, translated);
      }
    } catch {
      for (const row of parseDelimitedRows(legacy)) {
        if (row.length >= 2 && !isGlossaryHeader(row)) add(row[0], row[1]);
      }
    }
  }
  const scopeRows = customGlossaryScopes.value.map(scope => ['#context', scope.value, scope.label, '']);
  return rows.length || scopeRows.length ? [...scopeRows, ['original', 'translated', 'scope', 'aliases'], ...rows] : [];
}

function asrCorrectionExportRows(): string[][] {
  const rawRules = localConfig.value.transcription?.asr_correction_rules;
  let rules: any[] = Array.isArray(rawRules) ? rawRules : [];
  if (typeof rawRules === 'string' && rawRules.trim()) {
    try {
      const parsed = JSON.parse(rawRules);
      if (Array.isArray(parsed)) rules = parsed;
      else if (parsed && typeof parsed === 'object') {
        rules = Object.entries(parsed).map(([canonical, aliases]) => ({ canonical, aliases }));
      }
    } catch {
      rules = parseDelimitedRows(rawRules).map(row => ({ canonical: row[0], aliases: row.slice(1) }));
    }
  }

  const rows: string[][] = [];
  const seen = new Set<string>();
  for (const rule of rules) {
    const canonical = String(rule?.canonical ?? rule?.original ?? '').trim();
    const aliases = Array.isArray(rule?.aliases)
      ? rule.aliases
      : String(rule?.aliases ?? '').split(/[,，\t\r\n]/);
    const values = [canonical, ...aliases.map((value: unknown) => String(value ?? '').trim())]
      .filter((value, index, all) => value && (index === 0 || value !== canonical) && all.indexOf(value) === index);
    if (values.length < 2) continue;
    const key = values.join('\u0000');
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push(values);
  }
  return rows;
}

async function downloadCsv(filename: string, rows: string[][], label: string): Promise<boolean> {
  if (rows.length === 0) {
    store.statusMessage = `沒有可匯出的${label}`;
    return false;
  }
  // UTF-8 BOM makes Traditional Chinese display correctly in Excel on
  // Windows.  CRLF is also the format Excel expects for a CSV file.
  const csv = `\uFEFF${rows.map(row => row.map(csvField).join(',')).join('\r\n')}\r\n`;
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });

  // Chromium supports a real Save As dialog in normal browser builds. Use it
  // when available; this also works around WebView builds that ignore a
  // synthetic download click.
  const saveFilePicker = (window as any).showSaveFilePicker;
  if (typeof saveFilePicker === 'function') {
    try {
      const handle = await saveFilePicker({
        suggestedName: filename,
        types: [{ description: 'CSV 檔案', accept: { 'text/csv': ['.csv'] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      store.statusMessage = `已匯出 ${label} CSV`;
      return true;
    } catch (error: any) {
      // User cancellation is not an error. Other picker failures fall back to
      // the standard anchor download below.
      if (error?.name === 'AbortError') return false;
      console.warn('[SettingsView] Save As CSV 失敗，改用瀏覽器下載:', error);
    }
  }

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  // Keep the anchor and object URL alive long enough for Qt WebEngine and
  // Chromium download handlers to receive the click.
  window.setTimeout(() => {
    anchor.remove();
    URL.revokeObjectURL(url);
  }, 10_000);
  store.statusMessage = `已匯出 ${label} CSV`;
  return true;
}

function importGlossary() {
  if (glossaryImporting.value) return;
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.txt,.csv';
  input.onchange = async (e: any) => {
    const file = e.target.files[0];
    if (!file) return;
    glossaryImporting.value = true;
    try {
      const rows = parseDelimitedRows(await file.text());
      const importedScopes = rows.filter(row => row[0]?.trim() === '#context').map(row => ({
        value: row[1]?.trim() || '', label: row[2]?.trim() || '',
      }));
      const existingScopeIds = new Set(glossaryScopeOptions.value.map(option => option.value));
      const importedIds = new Set<string>();
      const importedNames = new Set<string>();
      for (const scope of importedScopes) {
        const normalizedName = scope.label.toLocaleLowerCase();
        if (!/^custom_[0-9a-f-]{36}$/i.test(scope.value) || !scope.label || scope.label.length > 40 || importedIds.has(scope.value) || importedNames.has(normalizedName)) {
          throw new Error('CSV 中的自訂情境資料無效或重複');
        }
        const existing = glossaryScopeOptions.value.find(item => item.value === scope.value);
        if (existing && existing.label !== scope.label) throw new Error(`情境 ID 衝突：${scope.value}`);
        if (!existing && glossaryScopeOptions.value.some(item => item.label.toLocaleLowerCase() === normalizedName)) {
          throw new Error(`已有同名情境：${scope.label}`);
        }
        importedIds.add(scope.value);
        importedNames.add(normalizedName);
      }
      const allowedScopes = new Set([...existingScopeIds, ...importedIds]);
      const newTerms: any[] = rows
        .filter(row => row.length >= 2 && row[0]?.trim() !== '#context' && !isGlossaryHeader(row))
        .map(row => {
          const scope = (row[2] || 'all').trim();
          if (!allowedScopes.has(scope)) throw new Error(`未知適用情境：${scope}`);
          return {
            original: row[0].trim(), translated: row[1].trim(), scope,
            ...(row.length >= 4 ? { aliases: row[3].split(/[,，]/).map(value => value.trim()).filter(Boolean) } : {}),
          };
        })
        .filter(term => term.original && term.translated);
      let mergedCount = localConfig.value.terminology.glossary_list?.length || 0;
      await saveBulkImport('terminology', () => {
        const currentScopes = Array.isArray(localConfig.value.terminology.custom_glossary_scopes)
          ? localConfig.value.terminology.custom_glossary_scopes : [];
        localConfig.value.terminology.custom_glossary_scopes = [
          ...currentScopes, ...importedScopes.filter(scope => !existingScopeIds.has(scope.value)),
        ];
        const merged = mergeGlossaryTerms(localConfig.value.terminology.glossary_list || [], newTerms);
        mergedCount = merged.length;
        localConfig.value.terminology.glossary_list = merged;
      });
      store.statusMessage = `詞語表匯入完成：讀取 ${newTerms.length} 筆，合併後共 ${mergedCount} 筆`;
    } catch (error: any) {
      store.errorMessage = `詞語表匯入失敗：${error?.message || '未知錯誤'}`;
    } finally {
      glossaryImporting.value = false;
    }
  };
  input.click();
}

function exportGlossary() {
  void downloadCsv('glossary.csv', glossaryExportRows(), '術語');
}

async function saveBulkImport(section: 'terminology' | 'transcription', applyImport: () => void) {
  const pendingTimer = sectionSaveTimers.get(section);
  if (pendingTimer) clearTimeout(pendingTimer);
  sectionSaveTimers.delete(section);
  suspendedAutoSaveSections.add(section);
  try {
    applyImport();
    // Deep watchers use flush: 'post'. Keep the section suspended until those
    // callbacks have observed the single bulk replacement.
    await nextTick();
  } finally {
    suspendedAutoSaveSections.delete(section);
  }
  await saveSectionNow(section);
}

function mergeGlossaryTerms(existing: any[], imported: any[]): any[] {
  const merged = new Map<string, any>();
  for (const term of [...existing, ...imported]) {
    const original = String(term?.original || '').trim();
    const translated = String(term?.translated || '').trim();
    const scope = String(term?.scope || 'all');
    if (original && translated) {
      const key = `${original}\u0000${scope}`;
      merged.set(key, { ...(merged.get(key) || {}), ...term, original, translated, scope });
    }
  }
  return [...merged.values()];
}

function mergeAsrCorrectionRules(existing: any[], imported: any[]): any[] {
  const merged = new Map<string, Set<string>>();
  for (const rule of [...existing, ...imported]) {
    const canonical = String(rule?.canonical || '').trim();
    if (!canonical) continue;
    const aliases = merged.get(canonical) || new Set<string>();
    for (const value of rule?.aliases || []) {
      const alias = String(value || '').trim();
      if (alias && alias !== canonical) aliases.add(alias);
    }
    if (aliases.size > 0) merged.set(canonical, aliases);
  }
  return [...merged.entries()].map(([canonical, aliases]) => ({ canonical, aliases: [...aliases] }));
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
  if (asrCorrectionsImporting.value) return;
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.txt,.csv';
  input.onchange = async (event: any) => {
    const file = event.target.files[0];
    if (!file) return;
    asrCorrectionsImporting.value = true;
    try {
      const imported = parseDelimitedRows(await file.text())
        .filter(row => row.length >= 2 && !isAsrCorrectionHeader(row))
        .map(row => {
          const canonical = row[0].trim();
          const aliases = row.slice(1)
            .map(value => value.trim())
            .filter((value, index, values) => value && value !== canonical && values.indexOf(value) === index);
          return { canonical, aliases };
        })
        .filter(rule => rule.canonical && rule.aliases.length > 0);
      let mergedCount = localConfig.value.transcription.asr_correction_rules?.length || 0;
      await saveBulkImport('transcription', () => {
        const merged = mergeAsrCorrectionRules(
          localConfig.value.transcription.asr_correction_rules || [],
          imported,
        );
        mergedCount = merged.length;
        localConfig.value.transcription.asr_correction_rules = merged;
      });
      store.statusMessage = `ASR 校正表匯入完成：讀取 ${imported.length} 筆，合併後共 ${mergedCount} 筆`;
    } catch (error: any) {
      store.errorMessage = `ASR 校正表匯入失敗：${error?.message || '未知錯誤'}`;
    } finally {
      asrCorrectionsImporting.value = false;
    }
  };
  input.click();
}

function exportAsrCorrections() {
  void downloadCsv('asr-name-corrections.csv', asrCorrectionExportRows(), 'ASR 修正規則');
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
      section: 'transcription',
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
provideSettingsContext({ localConfig, sharingLanAddresses, copiedSharingUrl, appUpdateStatus, appUpdateBusy, checkAppUpdate, downloadAppUpdate, cancelAppUpdate, applyAppUpdate, testingGpt, testingGemini, testConnection, diagnosticsBusy, cookiePlatform, cookieBrowser, cookieBrowserProfile, cookieImporting, cookieFileInput, cookieImportResult });
provideSettingsTabBindings({ GLOSSARY_PAGE_SIZE, LARGE_LIST_BATCH_SIZE, activeTab, activeTranslationFamily, addAsrCorrection, addGlossaryScope, addTerm, applyModelStoragePath, applySelectedGlossaryScope, asrComputeBackendLocked, asrComputeBackendOptions, asrCorrectionRenderLimit, asrCorrectionSearchQuery, asrCorrectionsImporting, bulkGlossaryScope, canCancelCpuAsrSidecar, canInstallCpuAsrSidecar, canStartDownload, canUseFasterWhisper, canUseFasterWhisperSimul, canUseFunAsr, canUseOpenAiAsr, canUseParakeet, canUseQwen3Asr, canUseSenseVoice, canUseSimulStreaming, cancelCpuAsrSidecarInstall, checkHyMt2Backend, cpuAsrOfflineArchive, cpuAsrRuntimeAvailable, cpuAsrSidecarBusy, cpuAsrSidecarStatus, cpuFunAsrDescriptions, cpuFunAsrModels, cpuParakeetDescriptions, cpuParakeetModels, cpuQwenDescriptions, cpuQwenModels, cpuSenseVoiceDescriptions, cpuSenseVoiceModels, customGlossaryScopes, customizePresetTerm, deleteCustomModel, deleteDownloadedModel, editingGlossaryScope, editingGlossaryScopeName, effectiveAsrComputeBackend, effectiveAsrRuntimeLabel, effectiveGlossaryCount, expandedGlossaryTerm, exportAsrCorrections, exportGlossary, familyLabel, familySettings, fasterWhisperModelList, filteredAsrCorrections, filteredGlossary, funAsrModelList, funAsrModelOptions, getModelStatusClass, getModelStatusText, getModelTask, glossaryEntryForm, glossaryImporting, glossaryListMode, glossaryRenderLimit, glossaryScopeOptions, glossaryUserList, gpuFasterWhisperModels, gpuFunAsrModels, gpuParakeetModels, gpuQwenModels, gpuSenseVoiceModels, hyMt2EffectiveBackend, hyMt2HealthChecking, hyMt2HealthResult, ignoredRuntimeDevices, importAsrCorrections, importCpuAsrSidecarOffline, importGlossary, installCpuAsrSidecar, isAsrEngineSelected, isSherpaOnnxMode, isTranscriptionLanguageLocked, localConfig, managedDownloadedModels, modelDownloadStore, modelManagementBackend, newAsrAliases, newAsrCanonical, newGlossaryScopeName, newTermAliases, newTermOriginal, newTermScope, newTermTranslated, openCustomModelDialog, packageProfileLabel, parakeetDecodingOptions, parakeetModelList, parakeetModelOptions, previewBusy, previewContext, previewError, previewLatencyLabel, previewResult, previewText, previewValidationStatus, qwen3AsrModelOptions, qwen3DtypeOptions, qwenModelList, removeAsrCorrection, removeGlossaryScope, removeTermEntry, removedGlossaryTerm, renameGlossaryScope, runTranslationPreview, runtimeCapabilities, runtimeDeviceLine, runtimeDevicePolicyOptions, runtimeDiagnosticNotice, runtimeSelection, runtimeStatus, runtimeStatusLabel, selectAsrEngine, selectVisibleGlossaryTerms, selectedGlossaryPresetLabel, selectedGlossaryTerms, selectedPresetPreview, selectedRuntimeDevice, senseVoiceModelList, senseVoiceModelOptions, setTermAliases, setTermScope, startModelDownload, store, targetLanguageOptions, termSearchQuery, terminologySubTab, testConnection, testOpenAiAsrConnection, testingGemini, testingGpt, toggleGlossarySelection, transcriptionLanguageOptions, translationBackendOptions, translationModelFamilyOptions, translationOutputFormatOptions, undoRemovedGlossaryTerm, userGlossaryBySource, visibleAsrCorrections, visibleGlossary, whisperModelSelectOptions });
</script>

<template>
  <div class="commercial-page commercial-settings p-4 sm:p-5 max-w-7xl mx-auto">
    <!-- Header -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between mb-5 gap-3 border-b border-white/5 pb-2.5">
      <div>
        <div class="flex items-center gap-3">
          <h1 class="text-base font-bold text-white tracking-wide">系統設定</h1>
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
              {{ store.errorMessage ? '狀態未同步' : '尚未變更' }}
            </span>
          </div>
        </div>
      </div>

      <!-- Import/Export & Reset Buttons -->
      <div class="flex flex-wrap gap-2">
        <button @click="handleImportClick" class="bg-blue-600/85 hover:bg-blue-600 text-white font-semibold py-1.5 px-3 rounded-lg transition text-xs flex items-center gap-1.5 shadow-sm">
          匯入設定
        </button>
        <button @click="handleExportClick" class="bg-emerald-600/85 hover:bg-emerald-600 text-white font-semibold py-1.5 px-3 rounded-lg transition text-xs flex items-center gap-1.5 shadow-sm">
          匯出設定
        </button>
        <button @click="resetToDefault" class="bg-yellow-600/20 hover:bg-yellow-600/30 text-yellow-300 border border-yellow-500/20 font-semibold py-1.5 px-3 rounded-lg transition text-xs flex items-center gap-1.5">
          重置預設值
        </button>
      </div>
    </div>

    <!-- 隱藏的檔案輸入框 -->
    <input type="file" ref="fileInput" accept=".yaml,.yml" class="hidden" @change="handleFileChange" />

    <!-- Error/Status Messages -->
    <div v-if="store.errorMessage" class="mb-4 p-3 bg-red-950/80 border border-red-500/30 text-red-200 rounded-xl flex justify-between items-center text-xs">
      <span>{{ store.errorMessage }}</span>
      <button @click="store.clearError()" class="hover:text-white font-bold text-lg leading-none p-1">✕</button>
    </div>

    <div v-if="store.statusMessage" class="mb-4 p-3 bg-green-950/80 border border-green-500/30 text-green-200 rounded-xl flex justify-between items-center text-xs">
      <span>{{ store.statusMessage }}</span>
      <button @click="store.clearStatus()" class="hover:text-white font-bold text-lg leading-none p-1">✕</button>
    </div>

    <!-- Content Container (Card Layout) -->
    <!-- 長捲動內容不使用 backdrop-filter：Qt WebEngine/Chromium 在 Windows
         重新合成大型毛玻璃 layer 時可能短暫露出底層視窗。 -->
    <div v-if="!settingsReady" class="commercial-panel min-h-[550px] p-6 sm:p-8" aria-busy="true">
      <div class="animate-pulse space-y-6">
        <div class="h-7 w-40 rounded bg-white/10"></div>
        <div class="h-4 w-72 max-w-full rounded bg-white/5"></div>
        <div class="h-12 rounded-xl bg-white/5"></div>
        <div class="h-36 rounded-xl bg-white/5"></div>
      </div>
      <p class="mt-6 text-sm text-white/45">正在讀取設定…</p>
    </div>
    <div v-else class="commercial-panel min-h-[550px] p-6 sm:p-8">
          <!-- General Settings -->
          <GeneralSettingsTab v-if="activeTab === 'general'" />

          <DiagnosticsSettingsTab v-if="activeTab === 'diagnostics'" />

          <!-- Input Settings -->
          <InputSettingsTab v-if="activeTab === 'input'" />

          <!-- Audio Slicing & VAD Settings -->
          <AudioVadSettingsTab v-if="activeTab === 'audio_vad'" />

          <!-- Transcription Settings -->
          <TranscriptionSettingsTab v-if="activeTab === 'transcription'" />

          <!-- Model Management Settings -->
          <ModelManagementSettingsTab v-if="activeTab === 'model_management'" />

          <!-- Translation Settings -->
          <TranslationSettingsTab v-if="activeTab === 'translation'" />

          <!-- Llama Settings -->
          <div v-if="activeTab === 'llama'" class="settings-paint-section">
            <LlamaSettings />
          </div>

          <!-- Terminology Settings -->
          <TerminologySettingsTab v-if="activeTab === 'terminology'" />

          <!-- Output & Notification Settings -->
          <OutputSettingsTab v-if="activeTab === 'output'" />
        </div>



    <!-- Custom Model Dialog -->
    <div v-if="showCustomModelDialog" class="fixed inset-0 bg-black/80 flex items-center justify-center z-50">
      <div class="bg-gray-900 rounded-2xl border border-white/20 shadow-2xl p-6 w-full max-w-md mx-4" role="dialog" aria-modal="true" aria-labelledby="custom-model-dialog-title">
        <h3 id="custom-model-dialog-title" class="text-xl font-bold text-white mb-4">{{ editingModelIndex >= 0 ? '編輯' : '新增' }}自訂模型</h3>

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

<style scoped src="../components/settings/settings-shared.css"></style>
