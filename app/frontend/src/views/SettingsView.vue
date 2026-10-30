<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue';
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
import { useTranscriptionSettings } from '../composables/settings/useTranscriptionSettings';
import { useTerminologySettings, normalizeTermAliases } from '../composables/settings/useTerminologySettings';
import { useTranslationSettings } from '../composables/settings/useTranslationSettings';
import { useAsrModelManagement } from '../composables/settings/useAsrModelManagement';
import { useRoute } from 'vue-router';

import axios from 'axios';
import { queuePendingSave, takePendingSaves } from '../composables/settings/pendingSaves';
import { validateAudioSlicing } from '../composables/settings/audioSlicingValidation';
import { useTranslationStore } from '../stores/translation';
import { useModelDownloadStore } from '../stores/modelDownload';
import { useLlamaStore } from '../stores/llama';

import { useTranscriptionMutex } from '../composables/useTranscriptionMutex';
import { useStatusSync } from '../composables/useStatusSync';
import { useAppSyncEvents } from '../composables/useAppSyncEvents';
import { runtimeApi, serverApi, type AppUpdateStatus } from '../services/api';
import { coerceLanguageForModel,  } from '../utils/asrCapabilities';

const testingGpt = ref(false);
const testingGemini = ref(false);

const saveStatus = ref<'idle' | 'saving' | 'saved'>('idle');
const settingsReady = ref(false);
const sharingLanAddresses = ref<string[]>([]);
const copiedSharingUrl = ref('');
const appUpdateStatus = ref<AppUpdateStatus | null>(null);
const appUpdateBusy = computed(() => ['starting', 'downloading', 'verifying', 'staging'].includes(appUpdateStatus.value?.status || ''));
let autoSaveStatusTimeout: ReturnType<typeof setTimeout> | null = null;
const suspendedAutoSaveSections = new Set<string>();


const route = useRoute();
const store = useTranslationStore();
const modelDownloadStore = useModelDownloadStore();

const appUpdateSync = useStatusSync('app_update.status', async () => ({ data: await runtimeApi.getAppUpdateStatus() }), (payload) => {
  appUpdateStatus.value = payload.data;
});

async function refreshAppUpdateStatus() {
  appUpdateStatus.value = await runtimeApi.getAppUpdateStatus();
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
    void appUpdateSync.refetch();
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


const localConfig = ref<any>({
  general: {
    log_level: 'INFO'
  },
  server: {
    public_port: 8765,
    enable_subtitle_sharing: true,
    allow_lan_admin: false,
    lan_admin_password: ''
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
    family_optimizer_auto: true,
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
    use_terminology_glossary: true,
    translation_glossary_audit_enabled: false,
    glossary: '',
    glossary_list: [],
    custom_glossary_scopes: [],
    active_categories: [],
    builtin_disabled: [],
    ignored_alias_suggestions: [],
    schema_version: 2,
    glossary_to_asr_prompt: false
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

// Each config section saves independently so a small UI edit does not traverse,
// serialize, replace, and re-render the complete configuration tree.
const sectionSaveTimers = new Map<string, ReturnType<typeof setTimeout>>();
const sectionSaveInFlight = new Map<string, Promise<void>>();
const transcriptionSettings = useTranscriptionSettings(localConfig, store);
const terminologySettings = useTerminologySettings(localConfig, store, saveBulkImport);
const translationSettings = useTranslationSettings(localConfig, sectionSaveTimers, saveSectionNow);
const asrModelManagement = useAsrModelManagement(localConfig, store, modelDownloadStore, transcriptionSettings);
const { runtimeCapabilities, selectedSettingsAsrModelId, coerceAsrSettingsForRuntime } = transcriptionSettings;
const { presetCategories, presetLoadError } = terminologySettings;
const { stopCpuAsrSidecarPolling, refreshCpuAsrSidecarStatus } = asrModelManagement;


const pendingRetrySections = ref(new Set<string>());
const failedSections = ref(new Set<string>());
const deferredSections = new Set<string>();
let replacingConfig = 0;
const localEdits = new Set<string>();
const replacementEdits = new Map<string, any>();
const handedOffSections = new Set<string>();
const healthySaveFailures = new Map<string, number>();
let lastValidAudio: Record<string, unknown> | null = null;
const audioServerValidationMessage = ref('');
const audioValidationMessage = computed(() => audioServerValidationMessage.value
  || validateAudioSlicing(localConfig.value.audio_slicing_vad));
const audioInvalidChanges = computed(() => audioServerValidationMessage.value
  || (audioValidationMessage.value
    && !sameEntries(localConfig.value.audio_slicing_vad, store.config.audio_slicing_vad)));
const autoSaveStatus = computed(() => audioInvalidChanges.value ? 'invalid'
  : pendingRetrySections.value.size ? 'retry'
  : failedSections.value.size ? 'error' : saveStatus.value);
let retryTimer: ReturnType<typeof setTimeout> | null = null;
let retryPolling = false;
let disposed = false;

function scheduleRetry() {
  if (!pendingRetrySections.value.size || disposed || replacingConfig) {
    if (retryTimer) clearTimeout(retryTimer);
    retryTimer = null;
    return;
  }
  if (retryTimer || retryPolling) return;
  retryTimer = setTimeout(async () => {
    retryTimer = null;
    retryPolling = true;
    try {
      const health = await axios.get('/api/health', { timeout: 3000 });
      if (health.data?.status !== 'ok') return;
      for (const section of [...pendingRetrySections.value]) {
        if (disposed || replacingConfig) break;
        if (pendingRetrySections.value.has(section)) await saveSectionNow(section).catch(() => undefined);
      }
    } catch {
      // Keep pending sections until the backend is reachable again.
    } finally {
      retryPolling = false;
      scheduleRetry();
    }
  }, 3000);
}

watch(() => localConfig.value.audio_slicing_vad, () => {
  audioServerValidationMessage.value = '';
}, { deep: true, flush: 'sync' });

function markAutoSaveCompleted() {
  saveStatus.value = 'saved';
  if (autoSaveStatusTimeout) clearTimeout(autoSaveStatusTimeout);
  autoSaveStatusTimeout = setTimeout(() => {
    saveStatus.value = 'idle';
  }, 3000);
}

async function saveSectionNow(section: string): Promise<void> {
  if (replacingConfig) throw new Error('Configuration replacement in progress');
  const existing = sectionSaveInFlight.get(section);
  if (existing) {
    await existing.catch(() => undefined);
    return saveSectionNow(section);
  }
  if (disposed) return;
  if (section === 'audio_slicing_vad' && audioValidationMessage.value && !lastValidAudio) {
    pendingRetrySections.value.delete(section);
    saveStatus.value = 'idle';
    scheduleRetry();
    throw new Error(audioValidationMessage.value);
  }
  saveStatus.value = 'saving';
  let saved = false;
  let sectionSnapshot: any;
  const request = (async () => {
    try {
      // Config is plain JSON. A JSON round trip also unwraps reactive proxies
      // nested in replaced arrays (e.g. a new glossary_list), which
      // structuredClone(toRaw()) rejects with DataCloneError.
      sectionSnapshot = JSON.parse(JSON.stringify(section === 'audio_slicing_vad' && audioValidationMessage.value
        ? lastValidAudio : localConfig.value[section] ?? {}));
      if (section === 'terminology') {
        for (const term of sectionSnapshot.glossary_list || []) term.aliases = normalizeTermAliases(term.aliases);
      }
      const runtimeChanged = section === 'runtime'
        && !configsEqual(store.config.runtime, sectionSnapshot);
      const asrComputeChanged = section === 'transcription'
        && store.config.transcription?.asr_compute_backend !== sectionSnapshot.asr_compute_backend;
      if (section === 'audio_slicing_vad' && !audioValidationMessage.value) {
        lastValidAudio = sectionSnapshot;
      }
      await store.saveConfigSection(section, sectionSnapshot);
      saved = true;
      if (section === 'audio_slicing_vad' && lastValidAudio && sameEntries(lastValidAudio, sectionSnapshot)) {
        lastValidAudio = null;
      }
      if (configsEqual(localConfig.value[section], sectionSnapshot)) localEdits.delete(section);
      failedSections.value.delete(section);
      healthySaveFailures.delete(section);
      pendingRetrySections.value.delete(section);
      scheduleRetry();
      if (runtimeChanged || asrComputeChanged) await store.loadRuntimeStatus();
      if (!disposed) markAutoSaveCompleted();
    } catch (e: any) {
      const detail = e?.response?.data?.detail ?? e?.message ?? String(e);
      const status = e?.response?.status;
      let retryLimitReached = false;
      if (!e?.response || status >= 500) {
        try {
          const health = await axios.get('/api/health', { timeout: 3000 });
          if (health.data?.status === 'ok' && configsEqual(
            section === 'audio_slicing_vad' && audioValidationMessage.value ? lastValidAudio : localConfig.value[section], sectionSnapshot)) {
            const failures = (healthySaveFailures.get(section) || 0) + 1;
            healthySaveFailures.set(section, failures);
            retryLimitReached = failures >= 3;
            if (failures === 3) console.warn(`[SettingsView] ${section} 自動保存連續失敗 3 次，停止重試`);
          }
        } catch { /* An unreachable backend does not count toward the limit. */ }
      } else if (e?.response) {
        healthySaveFailures.delete(section);
        console.warn(`[SettingsView] ${section} 自動保存失敗: ${typeof detail === 'string' ? detail : JSON.stringify(detail)}`);
      }
      if (status === 422 && section === 'audio_slicing_vad') {
        if (lastValidAudio && sameEntries(lastValidAudio, sectionSnapshot)) lastValidAudio = null;
        if (configsEqual(localConfig.value[section], sectionSnapshot)) {
          audioServerValidationMessage.value = String(detail);
        }
        pendingRetrySections.value.delete(section);
        store.clearError();
      } else {
        if ((!e?.response || status >= 500) && !retryLimitReached) pendingRetrySections.value.add(section);
        else {
          pendingRetrySections.value.delete(section);
          failedSections.value.add(section);
          if (section === 'audio_slicing_vad' && lastValidAudio && sameEntries(lastValidAudio, sectionSnapshot)) {
            lastValidAudio = null;
          }
        }
      }
      if (disposed && !handedOffSections.has(section) && pendingRetrySections.value.has(section)) {
        handoffSection(section);
      }
      scheduleRetry();
      throw e;
    } finally {
      sectionSaveInFlight.delete(section);
      if (saved && !disposed && !replacingConfig && deferredSections.has(section)
        && !pendingRetrySections.value.has(section) && !sectionSaveTimers.has(section)) {
        suspendedAutoSaveSections.add(section);
        const wasApplyingRemoteConfig = isApplyingRemoteConfig.value;
        isApplyingRemoteConfig.value = true;
        try {
          applyConfigSection(section, store.config[section]);
          await nextTick();
        } finally {
          isApplyingRemoteConfig.value = wasApplyingRemoteConfig;
          suspendedAutoSaveSections.delete(section);
        }
      }
    }
  })();
  sectionSaveInFlight.set(section, request);
  await request;
}

function debouncedAutoSaveSection(section: string) {
  healthySaveFailures.delete(section);
  if (suspendedAutoSaveSections.has(section)) return;
  localEdits.add(section);
  if (replacingConfig) {
    replacementEdits.set(section, JSON.parse(JSON.stringify(localConfig.value[section])));
    return;
  }
  if (section === 'audio_slicing_vad' && audioValidationMessage.value) {
    const pendingTimer = sectionSaveTimers.get(section);
    if (pendingTimer) clearTimeout(pendingTimer);
    sectionSaveTimers.delete(section);
    if (!sectionSaveInFlight.has(section) && !pendingRetrySections.value.has(section)) saveStatus.value = 'idle';
    return;
  }
  if (autoSaveStatusTimeout) clearTimeout(autoSaveStatusTimeout);
  const currentTimer = sectionSaveTimers.get(section);
  if (currentTimer) clearTimeout(currentTimer);
  sectionSaveTimers.delete(section);
  saveStatus.value = 'saving';
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
// 自訂模型
const showCustomModelDialog = ref(false);
const editingModelIndex = ref(-1);
const customModelForm = ref({
  name: '',
  base_url: '',
  api_key: '',
  model_name: ''
});

// 互斥邏輯: 轉錄引擎互斥規則
const diagnosticsBusy = ref(false);
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

// Local sections are merged over defaults, so their key order differs from the server's.
function sameEntries(left: Record<string, unknown> = {}, right: Record<string, unknown> = {}): boolean {
  const sorted = (section: Record<string, unknown>) => JSON.stringify(Object.keys(section).sort().map(key => [key, section[key]]));
  return sorted(left) === sorted(right);
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
  if (!replacingConfig && (pendingRetrySections.value.has(section) || sectionSaveTimers.has(section)
    || sectionSaveInFlight.has(section))) {
    deferredSections.add(section);
    return;
  }
  if (!replacingConfig && settingsReady.value && section === 'audio_slicing_vad'
    && localEdits.has(section) && audioInvalidChanges.value) {
    deferredSections.add(section);
    return;
  }
  localEdits.delete(section);
  deferredSections.delete(section);
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

    if (!deferredSections.has('translation') && loadedConfig.translation?.custom_models) {
      if (!configsEqual(localConfig.value.translation.custom_models, loadedConfig.translation.custom_models)) {
        localConfig.value.translation.custom_models = loadedConfig.translation.custom_models;
      }
    } else if (!deferredSections.has('translation') && loadedConfig.custom_models) {
      if (!configsEqual(localConfig.value.translation.custom_models, loadedConfig.custom_models)) {
        localConfig.value.translation.custom_models = loadedConfig.custom_models;
      }
    }

    for (const term of localConfig.value.terminology.glossary_list || []) {
      term.aliases = normalizeTermAliases(term.aliases);
      term.scope = term.scope || 'all';
      term.translated = String(term.translated || '');
    }
    coerceAsrSettingsForRuntime();

  } finally {
    await nextTick();
    isApplyingRemoteConfig.value = false;
  }
  if (syncLlama) {
    await llamaStore.loadConfig();
    await llamaStore.refreshServerStatus();
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
  onConfigReset: async (payload) => replaceSettings(async () => {
    if (payload.config) store.applyConfigSnapshot(payload.config);
    else await store.loadConfig(true);
    await store.loadRuntimeStatus();
    await applyStoreConfigToLocalConfig(store.config, true);
  }),
  onConfigImported: async (payload) => replaceSettings(async () => {
    if (payload.config) store.applyConfigSnapshot(payload.config);
    else await store.loadConfig(true);
    await store.loadRuntimeStatus();
    await applyStoreConfigToLocalConfig(store.config, true);
  }),
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

watch(activeTab, async (tab, previousTab) => {
  if (previousTab === 'audio_vad' && audioInvalidChanges.value) {
    if (sectionSaveInFlight.has('audio_slicing_vad')) deferredSections.add('audio_slicing_vad');
    if (!lastValidAudio) localEdits.delete('audio_slicing_vad');
    if (!sectionSaveInFlight.has('audio_slicing_vad') && !pendingRetrySections.value.has('audio_slicing_vad')) {
      saveStatus.value = 'idle';
    }
    suspendedAutoSaveSections.add('audio_slicing_vad');
    localConfig.value.audio_slicing_vad = JSON.parse(JSON.stringify(lastValidAudio ?? store.config.audio_slicing_vad));
    audioServerValidationMessage.value = '';
    await nextTick();
    suspendedAutoSaveSections.delete('audio_slicing_vad');
    scheduleRetry();
  }
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
  const queued = await takePendingSaves();
  try {
    // Config is a fast, cached YAML read.  Do not keep the whole settings UI
    // behind cold Torch/GPU or llama.cpp probes, which can take many seconds.
    await store.loadConfig();
    await applyStoreConfigToLocalConfig(store.config, false);
  } finally {
    for (const [section, entry] of queued) {
      if (disposed) {
        queuePendingSave(section, entry.snapshot, entry.failures);
        continue;
      }
      localConfig.value[section] = entry.snapshot;
      if (section === 'audio_slicing_vad') lastValidAudio = JSON.parse(JSON.stringify(entry.snapshot));
      localEdits.add(section);
      pendingRetrySections.value.add(section);
      healthySaveFailures.set(section, entry.failures);
    }
    scheduleRetry();
    await nextTick();
    settingsReady.value = true;
  }

  if (disposed) return;
  const runtimeStatusPromise = store.loadRuntimeStatus();
  void axios.get('/api/config/hy-mt2-glossary-presets').then((response) => {
    if (!Array.isArray(response.data?.categories)) throw new Error('Invalid glossary categories');
    presetCategories.value = response.data.categories;
    presetLoadError.value = false;
  }).catch(() => { presetCategories.value = []; presetLoadError.value = true; });
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

function handoffSection(section: string, immediate = false) {
  const snapshot = section === 'audio_slicing_vad' && audioValidationMessage.value
    ? lastValidAudio : localConfig.value[section];
  if (!snapshot) return;
  handedOffSections.add(section);
  queuePendingSave(section, snapshot, healthySaveFailures.get(section) || 0, immediate, sectionSaveInFlight.get(section));
}

onUnmounted(() => {
  disposed = true;
  if (!replacingConfig) {
    for (const section of new Set([...sectionSaveTimers.keys(), ...sectionSaveInFlight.keys()])) handoffSection(section, true);
    for (const section of pendingRetrySections.value) {
      if (!handedOffSections.has(section)) handoffSection(section);
    }
  }
  if (retryTimer) clearTimeout(retryTimer);
  if (autoSaveStatusTimeout) clearTimeout(autoSaveStatusTimeout);
  for (const timer of sectionSaveTimers.values()) clearTimeout(timer);
  sectionSaveTimers.clear();
  modelDownloadStore.stopPolling();
  stopCpuAsrSidecarPolling();
});

async function replaceSettings(apply: () => Promise<void>) {
  replacingConfig++;
  const timerSections = new Set(sectionSaveTimers.keys());
  const pendingSections = new Set(pendingRetrySections.value);
  const failed = new Set(failedSections.value);
  const deferred = new Set(deferredSections);
  const edited = new Set(localEdits);
  const snapshots = new Map<string, any>(Object.keys(localConfig.value)
    .map(section => [section, JSON.parse(JSON.stringify(localConfig.value[section]))]));
  for (const timer of sectionSaveTimers.values()) clearTimeout(timer);
  scheduleRetry();
  const queued = await takePendingSaves();
  const clearPending = () => {
    for (const timer of sectionSaveTimers.values()) clearTimeout(timer);
    sectionSaveTimers.clear();
    pendingRetrySections.value.clear();
    healthySaveFailures.clear();
    failedSections.value.clear();
    deferredSections.clear();
    lastValidAudio = null;
    audioServerValidationMessage.value = '';
    if (autoSaveStatusTimeout) clearTimeout(autoSaveStatusTimeout);
    saveStatus.value = 'idle';
    scheduleRetry();
  };
  try {
    await Promise.allSettled([...sectionSaveInFlight.values()]);
    await apply();
    await applyStoreConfigToLocalConfig(store.config);
    clearPending();
    replacementEdits.clear();
  } catch (error) {
    for (const [section, snapshot] of replacementEdits) snapshots.set(section, snapshot);
    isApplyingRemoteConfig.value = true;
    for (const [section, snapshot] of snapshots) localConfig.value[section] = snapshot;
    sectionSaveTimers.clear();
    for (const section of [...timerSections, ...pendingSections, ...replacementEdits.keys()]) {
      pendingRetrySections.value.add(section);
      localEdits.add(section);
    }
    for (const section of edited) localEdits.add(section);
    for (const section of failed) failedSections.value.add(section);
    for (const section of deferred) deferredSections.add(section);
    for (const [section, entry] of queued) {
      if (!edited.has(section) && !replacementEdits.has(section)) localConfig.value[section] = entry.snapshot;
      pendingRetrySections.value.add(section);
      localEdits.add(section);
      healthySaveFailures.set(section, entry.failures);
    }
    await nextTick();
    isApplyingRemoteConfig.value = false;
    replacementEdits.clear();
    throw error;
  } finally {
    replacingConfig--;
    if (disposed) {
      for (const section of pendingRetrySections.value) handoffSection(section);
    }
    scheduleRetry();
  }
}

async function resetToDefault() {
  if (confirm('確定要重置為後端預設值嗎？此操作無法復原。')) {
    await replaceSettings(async () => {
      await store.resetConfig();
      await applyStoreConfigToLocalConfig(store.config, true);
    });
  }
}

// 術語表操作
async function saveBulkImport(section: 'terminology' | 'transcription', applyImport: () => void) {
  const pendingTimer = sectionSaveTimers.get(section);
  if (pendingTimer) clearTimeout(pendingTimer);
  sectionSaveTimers.delete(section);
  suspendedAutoSaveSections.add(section);
  try {
    healthySaveFailures.delete(section);
    applyImport();
    // Deep watchers use flush: 'post'. Keep the section suspended until those
    // callbacks have observed the single bulk replacement.
    await nextTick();
  } finally {
    suspendedAutoSaveSections.delete(section);
  }
  await saveSectionNow(section);
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
    await replaceSettings(async () => {
      await store.importConfig(file);
      await store.loadRuntimeStatus();
      await applyStoreConfigToLocalConfig(store.config, true);
    });
  } catch (error) {
    console.error('匯入失敗:', error);
  }

  // 清空輸入框以允許再次選擇同一檔案
  input.value = '';
}
provideSettingsContext({ localConfig, audioValidationMessage, sharingLanAddresses, copiedSharingUrl, appUpdateStatus, appUpdateBusy, checkAppUpdate, downloadAppUpdate, cancelAppUpdate, applyAppUpdate, testingGpt, testingGemini, testConnection, diagnosticsBusy, cookiePlatform, cookieBrowser, cookieBrowserProfile, cookieImporting, cookieFileInput, cookieImportResult });
provideSettingsTabBindings({ ...transcriptionSettings, ...terminologySettings, ...translationSettings, ...asrModelManagement, activeTab, deleteCustomModel, localConfig, modelDownloadStore, openCustomModelDialog, store, testConnection, testOpenAiAsrConnection, testingGemini, testingGpt });
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
            <span v-if="autoSaveStatus === 'invalid'" class="text-rose-400 font-semibold text-[10px]">⚠️ 未儲存</span>
            <span v-else-if="autoSaveStatus === 'retry'" class="text-rose-400 font-semibold text-[10px]">⚠️ 儲存失敗，連線恢復後會自動重試</span>
            <span v-else-if="autoSaveStatus === 'saving'" class="text-blue-300 flex items-center gap-1 text-[10px] font-semibold">
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
