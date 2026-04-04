<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, watch, nextTick } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useTranslationStore } from '../stores/translation';
import { useModelDownloadStore } from '../stores/modelDownload';
import LlamaSettings from '../components/LlamaSettings.vue';
import UiSelect, { type UiSelectOption } from '../components/UiSelect.vue';
import { useTranscriptionMutex } from '../composables/useTranscriptionMutex';

const router = useRouter();
const route = useRoute();
const store = useTranslationStore();
const modelDownloadStore = useModelDownloadStore();

const qwenModels = ['Qwen/Qwen3-ASR-0.6B', 'Qwen/Qwen3-ASR-1.7B'];
const fasterWhisperModels = ['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3', 'large-v3-turbo'];

const logLevelOptions: UiSelectOption[] = [
  { value: 'DEBUG', label: 'DEBUG' },
  { value: 'INFO', label: 'INFO' },
  { value: 'WARNING', label: 'WARNING' },
  { value: 'ERROR', label: 'ERROR' },
];
const sourceTypeOptions: UiSelectOption[] = [
  { value: 'youtube', label: 'YouTube' },
  { value: 'twitch', label: 'Twitch' },
  { value: 'bilibili', label: 'Bilibili' },
  { value: 'x', label: 'X (Twitter)' },
];
const whisperModelSelectOptions: UiSelectOption[] = fasterWhisperModels.map(m => ({ value: m, label: m }));
const qwen3AsrModelOptions: UiSelectOption[] = [
  { value: 'Qwen/Qwen3-ASR-1.7B', label: 'Qwen3-ASR-1.7B (推薦)' },
  { value: 'Qwen/Qwen3-ASR-0.6B', label: 'Qwen3-ASR-0.6B (更快)' },
];
const qwen3DtypeOptions: UiSelectOption[] = [
  { value: 'bfloat16', label: 'bfloat16 (推薦)' },
  { value: 'float16', label: 'float16' },
  { value: 'float32', label: 'float32' },
];
const transcriptionLanguageOptions: UiSelectOption[] = [
  { value: 'auto', label: '自動偵測' },
  { value: 'ja', label: '日文' },
  { value: 'en', label: '英文' },
  { value: 'zh', label: '中文' },
  { value: 'ko', label: '韓文' },
];
const targetLanguageOptions: UiSelectOption[] = [
  { value: 'Traditional Chinese', label: '繁體中文' },
  { value: 'Simplified Chinese', label: '簡體中文' },
  { value: 'Japanese', label: '日文' },
  { value: 'English', label: '英文' },
  { value: 'Korean', label: '韓文' },
];

const localConfig = ref<any>({
  general: {
    openai_api_key: '',
    google_api_key: '',
    log_level: 'INFO'
  },
  server: {
    public_port: 8765,
    enable_subtitle_sharing: true
  },
  input: {
    url: '',
    source_type: 'youtube',
    format: 'ba/wa*',
    cookies: '',
    proxy: '',
    timeout: 30,
    device_recording_interval: 0.5
  },
  audio_slicing_vad: {
    min_audio_length: 3.0,
    max_audio_length: 30.0,
    chunk_gap_threshold: 0.5,
    vad_enabled: true,
    vad_threshold: 0.5,
    vad_neg_threshold: 0.35,
    vad_min_speech_duration_ms: 250,
    vad_min_silence_duration_ms: 100,
    vad_window_size_samples: 512,
    vad_speech_pad_ms: 30,
    vad_every_n_frames: 2,
    realtime_processing: false
  },
  transcription: {
    model: 'base',
    language: 'auto',
    transcription_initial_prompt: '',
    disable_transcription_context: false,
    use_faster_whisper: false,
    use_simul_streaming: false,
    use_openai_transcription_api: false,
    use_qwen3_asr: false,
    qwen3_asr_model: 'Qwen/Qwen3-ASR-1.7B',
    qwen3_dtype: 'bfloat16',
    qwen3_load_in_4bit: false,
    openai_transcription_model: 'whisper-1',
    whisper_filters: ['emoji_filter', 'repetition_filter']
  },
  translation: {
    backend: 'gpt',
    target_language: 'Traditional Chinese',
    gpt_model: 'gpt-4o-mini',
    gemini_model: 'gemini-2.0-flash-exp',
    gpt_base_url: '',
    gemini_base_url: '',
    api_key: '',
    translation_history_size: 0,
    translation_timeout: 10,
    processing_proxy: '',
    use_json_result: false,
    use_smart_prompt: true,
    smart_prompt_enabled: true,
    translation_prompt: '',
    custom_models: []
  },
  terminology: {
    use_terminology_glossary: false,  // 🔧 新增: 術語表啟用開關
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
const activeTab = ref('general');

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

// 自動保存 debounce timer
let _settingsAutoSaveTimer: ReturnType<typeof setTimeout> | null = null;

function debouncedAutoSave() {
  if (_settingsAutoSaveTimer !== null) clearTimeout(_settingsAutoSaveTimer);
  _settingsAutoSaveTimer = setTimeout(async () => {
    _settingsAutoSaveTimer = null;
    try {
      await store.saveConfig(localConfig.value);
    } catch (e) {
      console.warn('[SettingsView] 自動保存失敗:', e);
    }
  }, 1000);
}

// 術語表
const newTermOriginal = ref('');
const newTermTranslated = ref('');
const termSearchQuery = ref('');

// 自訂模型
const showCustomModelDialog = ref(false);
const editingModelIndex = ref(-1);
const customModelForm = ref({
  name: '',
  base_url: '',
  api_key: '',
  model_name: ''
});

const tabs = [
  { id: 'general', name: '一般設定', icon: '⚙️' },
  { id: 'input', name: '輸入選項', icon: '📥' },
  { id: 'audio_vad', name: '音訊切片/VAD', icon: '🔊' },
  { id: 'transcription', name: '轉錄選項', icon: '🎤' },
  { id: 'model_management', name: '模型管理', icon: '📦' },
  { id: 'translation', name: '翻譯選項', icon: '🌐' },
  { id: 'llama', name: 'Llama 設定', icon: '🦙' },
  { id: 'terminology', name: '術語表', icon: '📖' },
  { id: 'output', name: '輸出與通知', icon: '📤' }
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

// 互斥邏輯: 轉錄引擎互斥規則
useTranscriptionMutex(() => localConfig.value.transcription);

onMounted(async () => {
  await store.loadConfig();
  // 深度複製並確保所有區段存在
  const config = store.config || {};
  
  // 合併配置，保留預設值
  const mergeConfig = (defaults: any, loaded: any) => {
    const result = { ...defaults };
    for (const key of Object.keys(result)) {
      if (loaded && loaded[key] !== undefined) {
        if (typeof result[key] === 'object' && !Array.isArray(result[key])) {
          result[key] = { ...result[key], ...loaded[key] };
        } else {
          result[key] = loaded[key];
        }
      }
    }
    return result;
  };
  
  localConfig.value.general = mergeConfig(localConfig.value.general, config.general);
  localConfig.value.server = mergeConfig(localConfig.value.server, config.server);
  localConfig.value.input = mergeConfig(localConfig.value.input, config.input);
  localConfig.value.audio_slicing_vad = mergeConfig(localConfig.value.audio_slicing_vad, config.audio_slicing_vad);
  localConfig.value.transcription = mergeConfig(localConfig.value.transcription, config.transcription);
  localConfig.value.translation = mergeConfig(localConfig.value.translation, config.translation);
  localConfig.value.terminology = mergeConfig(localConfig.value.terminology, config.terminology);
  localConfig.value.output = mergeConfig(localConfig.value.output, config.output);
  localConfig.value.output_notification = mergeConfig(localConfig.value.output_notification, config.output_notification);
  
  // Handle custom_models in translation section
  if (config.translation?.custom_models) {
      localConfig.value.translation.custom_models = config.translation.custom_models;
  } else if (config.custom_models) {
      // Backward compatibility: migrate from root
      localConfig.value.translation.custom_models = config.custom_models;
  }
  
  localConfig.value.ui = mergeConfig(localConfig.value.ui, config.ui);
  
  // 從 URL 參數設定 tab
  if (route.query.tab) {
    activeTab.value = route.query.tab as string;
  }

  await modelDownloadStore.refreshAll();
  if (modelDownloadStore.activeTasks.length > 0) {
    modelDownloadStore.startPolling();
  }

  // 初始化完成後，延後建立深度 watch 避免初始化誤觸發自動保存
  await nextTick();
  watch(localConfig, () => debouncedAutoSave(), { deep: true });
});

onUnmounted(() => {
  if (_settingsAutoSaveTimer !== null) {
    clearTimeout(_settingsAutoSaveTimer);
    _settingsAutoSaveTimer = null;
  }
  modelDownloadStore.stopPolling();
});

function getModelTask(engine: 'qwen3-asr' | 'faster-whisper', modelId: string) {
  return modelDownloadStore.getTask(engine, modelId);
}

function getModelStatusText(engine: 'qwen3-asr' | 'faster-whisper', modelId: string) {
  if (modelDownloadStore.isDownloaded(engine, modelId)) return '已下載';
  const task = getModelTask(engine, modelId);
  if (!task) return '未下載';
  if (task.status === 'failed') return '下載失敗';
  if (task.status === 'completed') return '已下載';
  if (task.status === 'downloading') return `下載中 ${(task.progress * 100).toFixed(0)}%`;
  return '準備中';
}

function getModelStatusClass(engine: 'qwen3-asr' | 'faster-whisper', modelId: string) {
  if (modelDownloadStore.isDownloaded(engine, modelId)) return 'text-green-300';
  const task = getModelTask(engine, modelId);
  if (!task) return 'text-white/50';
  if (task.status === 'failed') return 'text-red-300';
  if (task.status === 'completed') return 'text-green-300';
  return 'text-blue-300';
}

function canStartDownload(engine: 'qwen3-asr' | 'faster-whisper', modelId: string) {
  if (modelDownloadStore.isDownloaded(engine, modelId)) return false;
  const task = getModelTask(engine, modelId);
  return !task || (task.status !== 'pending' && task.status !== 'downloading');
}

async function startModelDownload(engine: 'qwen3-asr' | 'faster-whisper', modelId: string) {
  await modelDownloadStore.startDownload(engine, modelId);
}

async function handleSave() {
  isSaving.value = true;
  try {
    await store.saveConfig(localConfig.value);
  } finally {
    isSaving.value = false;
  }
}

function handleCancel() {
  router.push('/');
}

function resetToDefault() {
  if (confirm('確定要重置為預設值嗎？此操作無法復原。')) {
    // 重置為預設值
    localConfig.value = {
      general: { openai_api_key: '', google_api_key: '', log_level: 'INFO' },
      server: { public_port: 8765, enable_subtitle_sharing: true },
      input: { url: '', source_type: 'youtube', format: 'ba/wa*', cookies: '', proxy: '', timeout: 30 },
      audio_slicing_vad: { min_audio_length: 3.0, max_audio_length: 30.0, chunk_gap_threshold: 0.5, vad_enabled: true, vad_threshold: 0.5, vad_neg_threshold: 0.35, vad_min_speech_duration_ms: 250, vad_min_silence_duration_ms: 100, vad_window_size_samples: 512, vad_speech_pad_ms: 30 },
      transcription: { model: 'base', language: 'auto', transcription_initial_prompt: '', disable_transcription_context: false, use_faster_whisper: false, use_simul_streaming: false, use_openai_transcription_api: false, use_qwen3_asr: false, qwen3_asr_model: 'Qwen/Qwen3-ASR-1.7B', qwen3_dtype: 'bfloat16', qwen3_load_in_4bit: false, openai_transcription_model: 'whisper-1', whisper_filters: ['emoji_filter', 'repetition_filter'] },
      translation: { backend: 'gpt', target_language: 'Traditional Chinese', llm_model: 'gpt-4o-mini', api_base: '', api_key: '', temperature: 0.3, top_p: 1.0, max_tokens: 2048, use_smart_prompt: true, translation_prompt: '', custom_models: [] },
      terminology: { use_terminology_glossary: false, glossary: '', glossary_list: [] },
      output: { output_dir: './output', output_srt: true, output_txt: false, output_ass: false, max_history: 20 },
      output_notification: { discord_enabled: false, discord_webhook_url: '', telegram_enabled: false, telegram_bot_token: '', telegram_chat_id: '', output_file_path: '' },
      ui: { theme: 'dark' }
    };
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
function toggleFilter(filterName: string, checked: boolean) {
  if (!localConfig.value.transcription.whisper_filters) {
    localConfig.value.transcription.whisper_filters = [];
  }
  
  const filters = localConfig.value.transcription.whisper_filters;
  const index = filters.indexOf(filterName);
  
  if (checked && index === -1) {
    filters.push(filterName);
  } else if (!checked && index !== -1) {
    filters.splice(index, 1);
  }
}

// 匯入匯出設定
const fileInput = ref<HTMLInputElement | null>(null);

function handleImportClick() {
  fileInput.value?.click();
}

function handleExportClick() {
  store.exportConfig();
}

async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  if (!input.files || input.files.length === 0) return;
  
  const file = input.files[0];
  try {
    await store.importConfig(file);
    // 重新載入頁面配置以反映更改
    await store.loadConfig();
    router.go(0); // 簡單刷新頁面確保所有狀態更新
  } catch (error) {
    console.error('匯入失敗:', error);
  }
  
  // 清空輸入框以允許再次選擇同一檔案
  input.value = '';
}
</script>

<template>
  <div class="min-h-screen bg-gradient-to-br from-slate-900 via-cyan-900 to-slate-900 p-6">
    <div class="max-w-7xl mx-auto">
      <!-- Header -->
      <div class="flex items-center justify-between mb-6">
        <div>
          <h1 class="text-3xl font-bold text-white mb-1">⚙️ 設定</h1>
          <p class="text-blue-300">配置翻譯引擎參數</p>
        </div>
        <div class="flex gap-4">
          <button @click="handleImportClick" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded-lg transition text-sm flex items-center gap-2">
            📥 匯入設定
          </button>
          <button @click="handleExportClick" class="bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded-lg transition text-sm flex items-center gap-2">
            📤 匯出設定
          </button>
          <button @click="handleCancel" class="bg-white/10 hover:bg-white/20 text-white font-bold py-2 px-6 rounded-lg transition border border-white/20">
            ← 返回
          </button>
        </div>
      </div>
      
      <!-- 隱藏的檔案輸入框 -->
      <input type="file" ref="fileInput" accept=".yaml,.yml" class="hidden" @change="handleFileChange" />

      <!-- Error/Status Messages -->
      <div v-if="store.errorMessage" class="mb-4 p-4 bg-red-500/30 backdrop-blur-xl border border-red-500/50 text-red-200 rounded-xl flex justify-between items-center">
        <span>{{ store.errorMessage }}</span>
        <button @click="store.clearError()" class="hover:text-white font-bold text-xl">✕</button>
      </div>

      <div v-if="store.statusMessage" class="mb-4 p-4 bg-green-500/30 backdrop-blur-xl border border-green-500/50 text-green-200 rounded-xl flex justify-between items-center">
        <span>{{ store.statusMessage }}</span>
        <button @click="store.clearStatus()" class="hover:text-white font-bold text-xl">✕</button>
      </div>

      <!-- Tabs -->
      <div class="bg-slate-900/90 rounded-2xl border border-white/20 shadow-2xl overflow-hidden">
        <div class="flex border-b border-white/10 bg-black/20 overflow-x-auto">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            @click="activeTab = tab.id"
            :class="[
              'flex-shrink-0 py-3 px-5 font-semibold text-center transition-all whitespace-nowrap',
              activeTab === tab.id
                ? 'bg-blue-600/50 text-white border-b-2 border-blue-400'
                : 'text-white/60 hover:bg-white/10 hover:text-white'
            ]"
          >
            <span class="mr-2">{{ tab.icon }}</span>
            {{ tab.name }}
          </button>
        </div>

        <!-- Tab Content -->
        <div class="p-6">
          <!-- General Settings -->
          <div v-show="activeTab === 'general'" class="space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">一般設定</h2>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label class="block text-white/70 font-semibold mb-2">OpenAI API Key</label>
                <input v-model="localConfig.general.openai_api_key" type="password" placeholder="sk-..."
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                <p class="text-white/40 text-sm mt-1">用於 GPT 翻譯</p>
              </div>

              <div>
                <label class="block text-white/70 font-semibold mb-2">Google API Key (Gemini)</label>
                <input v-model="localConfig.general.google_api_key" type="password" placeholder="AIza..."
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                <p class="text-white/40 text-sm mt-1">用於 Gemini 翻譯</p>
              </div>

              <div>
                <label class="block text-white/70 font-semibold mb-2">日誌等級</label>
                <UiSelect v-model="localConfig.general.log_level" :options="logLevelOptions" />
              </div>

              <div class="md:col-span-2 bg-white/5 rounded-lg p-4 border border-white/10">
                <label class="flex items-center justify-between cursor-pointer">
                  <div>
                    <div class="text-white font-semibold">字幕分享功能</div>
                    <p class="text-white/50 text-sm mt-1">控制是否允許外部透過 /desktop、/mobile 與公開 API 存取字幕</p>
                  </div>
                  <input v-model="localConfig.server.enable_subtitle_sharing" type="checkbox" class="w-5 h-5 accent-emerald-500" />
                </label>
              </div>
            </div>
          </div>

          <!-- Input Settings -->
          <div v-show="activeTab === 'input'" class="space-y-6">
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

              <div class="md:col-span-2">
                <label class="block text-white/70 font-semibold mb-2">Cookies 檔案路徑</label>
                <input v-model="localConfig.input.cookies" type="text" placeholder="./youtubecookies.txt"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                <p class="text-white/40 text-sm mt-1">用於存取需要登入的直播</p>
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
                <label class="block text-white/70 font-semibold mb-2">設備錄音間隔（秒）</label>
                <input v-model.number="localConfig.input.device_recording_interval" type="number" step="0.1" min="0.1" max="1.0" placeholder="0.5"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                <p class="text-white/40 text-sm mt-1">僅用於設備/Loopback 模式。間隔越短延遲越低但 CPU 越高，建議 0.5（預設）</p>
              </div>
            </div>
          </div>

          <!-- Audio Slicing & VAD Settings -->
          <div v-show="activeTab === 'audio_vad'" class="space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">音訊切片 & VAD 設定</h2>
            
            <!-- 音訊切片 -->
            <div class="bg-white/5 rounded-xl p-4 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">🔊 音訊切片</h3>
              <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label class="block text-white/70 text-sm mb-1">最小音訊長度 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.min_audio_length" type="number" step="0.1"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">最大音訊長度 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.max_audio_length" type="number" step="0.1"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">片段間隙閾值 (秒)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.chunk_gap_threshold" type="number" step="0.1"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>
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
                  <label class="block text-white/70 text-sm mb-1">語音閾值</label>
                  <input v-model.number="localConfig.audio_slicing_vad.vad_threshold" type="number" step="0.05" min="0" max="1"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-white/30 text-xs mt-1">0.0 ~ 1.0, 預設 0.5</p>
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">負向閾值</label>
                  <input v-model.number="localConfig.audio_slicing_vad.vad_neg_threshold" type="number" step="0.05" min="0" max="1"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-white/30 text-xs mt-1">0.0 ~ 1.0, 預設 0.35</p>
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">最短語音持續 (ms)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.vad_min_speech_duration_ms" type="number"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">最短靜音持續 (ms)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.vad_min_silence_duration_ms" type="number"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">視窗大小 (samples)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.vad_window_size_samples" type="number"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>
                <div>
                  <label class="block text-white/70 text-sm mb-1">語音填充 (ms)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.vad_speech_pad_ms" type="number"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>
              </div>
            </div>

            <!-- CPU 優化設定（非直播音源） -->
            <div class="bg-white/5 rounded-xl p-4 border border-white/10">
              <h3 class="text-lg font-semibold text-yellow-300 mb-1">⚡ 非直播 CPU 優化</h3>
              <p class="text-white/50 text-xs mb-4">適用於本地檔案或非直播 URL，直播音源無需調整</p>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label class="block text-white/70 text-sm mb-1">VAD 跳幀頻率 (每 N 幀呼叫一次)</label>
                  <input v-model.number="localConfig.audio_slicing_vad.vad_every_n_frames" type="number" min="1" max="10" step="1"
                    class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-white/30 text-xs mt-1">1 = 每幀都呼叫（無優化），2 = 約減少 50% CPU，3 = 約減少 67% CPU</p>
                </div>
                <div class="flex flex-col justify-center">
                  <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition">
                    <input v-model="localConfig.audio_slicing_vad.realtime_processing" type="checkbox" class="w-5 h-5 accent-yellow-400 mt-0.5" />
                    <div>
                      <span class="text-white font-medium">實時節流模式</span>
                      <p class="text-white/50 text-sm mt-1">音頻讀取速度限制為實時速度，CPU 降至最低但處理時間等同音頻時長</p>
                    </div>
                  </label>
                </div>
              </div>
            </div>
          </div>

          <!-- Transcription Settings -->
          <div v-show="activeTab === 'transcription'" class="space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">轉錄選項</h2>
            
            <!-- Whisper 引擎模式選擇 (移到最上面) -->
            <div class="bg-white/5 rounded-xl p-4 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">🎯 轉錄引擎</h3>
              <p class="text-white/60 text-sm mb-4">
                💡 提示:可同時選擇 Faster-Whisper + SimulStreaming,將使用 Faster-Whisper 作為編碼器的 SimulStreaming
              </p>
              <div class="space-y-3">
                <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition">
                  <input v-model="localConfig.transcription.use_faster_whisper" type="checkbox" class="w-5 h-5 accent-blue-500 mt-0.5" />
                  <div class="flex-1">
                    <span class="text-white font-medium">使用 Faster-Whisper</span>
                    <p class="text-white/50 text-sm mt-1">
                      使用優化過的 Faster-Whisper 引擎,提升轉錄速度。
                      <br />✨ 與 SimulStreaming 組合:作為編碼器提供更高效能
                    </p>
                  </div>
                </label>

                <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition">
                  <input v-model="localConfig.transcription.use_simul_streaming" type="checkbox" class="w-5 h-5 accent-blue-500 mt-0.5" />
                  <div class="flex-1">
                    <span class="text-white font-medium">使用 SimulStreaming</span>
                    <p class="text-white/50 text-sm mt-1">
                      使用 SimulStreaming 進行即時串流轉錄,降低延遲。
                      <br />✨ 與 Faster-Whisper 組合:使用 Faster-Whisper 作為編碼器
                    </p>
                  </div>
                </label>

                <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition">
                  <input v-model="localConfig.transcription.use_openai_transcription_api" type="checkbox" class="w-5 h-5 accent-blue-500 mt-0.5" />
                  <div class="flex-1">
                    <span class="text-white font-medium">使用 OpenAI Transcription API</span>
                    <p class="text-white/50 text-sm mt-1">
                      使用 OpenAI 官方雲端轉錄 API,無需本地模型但需要 API 額度。
                      <br />⚠️ 此選項與上述兩項互斥
                    </p>
                  </div>
                </label>

                <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition">
                  <input v-model="localConfig.transcription.use_qwen3_asr" type="checkbox" class="w-5 h-5 accent-blue-500 mt-0.5" />
                  <div class="flex-1">
                    <span class="text-white font-medium">使用 Qwen3-ASR</span>
                    <p class="text-white/50 text-sm mt-1">
                      使用阿里巴巴 Qwen3-ASR 模型進行語音轉錄,支援多語言,準確度高。
                      <br />⚠️ 需要 GPU 支援,此選項與上述選項互斥
                      <br />📦 需要安裝: pip install qwen-asr
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
                <UiSelect v-if="!localConfig.transcription.use_qwen3_asr && !localConfig.transcription.use_openai_transcription_api"
                  v-model="localConfig.transcription.model"
                  :options="whisperModelSelectOptions" />
                <!-- OpenAI 模型選擇 -->
                <input v-else-if="localConfig.transcription.use_openai_transcription_api" 
                  v-model="localConfig.transcription.openai_transcription_model" 
                  type="text" 
                  placeholder="whisper-1"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                <!-- Qwen3-ASR 模型選擇 (下拉選單) -->
                <UiSelect v-else-if="localConfig.transcription.use_qwen3_asr"
                  v-model="localConfig.transcription.qwen3_asr_model"
                  :options="qwen3AsrModelOptions" />
                <div v-if="localConfig.transcription.use_qwen3_asr" class="mt-4 grid grid-cols-1 gap-4">
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">模型精度</label>
                    <UiSelect v-model="localConfig.transcription.qwen3_dtype" :options="qwen3DtypeOptions" />
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
                          <br/>📦 需要安裝: pip install bitsandbytes
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
                <UiSelect v-model="localConfig.transcription.language" :options="transcriptionLanguageOptions" />
              </div>

              <div class="md:col-span-2" v-if="!localConfig.transcription.use_qwen3_asr">
                <label class="block text-white/70 font-semibold mb-2">轉錄提示詞</label>
                <textarea v-model="localConfig.transcription.transcription_initial_prompt" placeholder="提示詞1, 提示詞2, ..." rows="3"
                  class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400"></textarea>
                <p class="text-white/40 text-sm mt-1">通用的轉錄固定提示詞/術語表。格式:"提示詞1, 提示詞2, ..."。此文本將始終包含在傳遞給模型的提示詞中。</p>
              </div>
              <div class="md:col-span-2" v-else>
                <p class="text-yellow-400 text-sm">⚠️ Qwen3-ASR 不支援自訂提示詞</p>
              </div>
            </div>

            <!-- Whisper 濾鏡 -->
            <div class="mt-6 pt-6 border-t border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">🔍 Whisper 結果濾鏡</h3>
              <p class="text-white/60 text-sm mb-4">選擇要應用於 Whisper 轉錄結果的濾鏡</p>
              <div class="space-y-3">
                <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition">
                  <input 
                    type="checkbox" 
                    :checked="localConfig.transcription.whisper_filters?.includes('emoji_filter')"
                    @change="toggleFilter('emoji_filter', ($event.target as HTMLInputElement).checked)"
                    class="w-5 h-5 accent-blue-500 mt-0.5" 
                  />
                  <div class="flex-1">
                    <span class="text-white font-medium">Emoji 濾鏡</span>
                    <p class="text-white/50 text-sm mt-1">過濾轉錄結果中的 emoji 表情符號</p>
                  </div>
                </label>

                <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition">
                  <input 
                    type="checkbox" 
                    :checked="localConfig.transcription.whisper_filters?.includes('repetition_filter')"
                    @change="toggleFilter('repetition_filter', ($event.target as HTMLInputElement).checked)"
                    class="w-5 h-5 accent-blue-500 mt-0.5" 
                  />
                  <div class="flex-1">
                    <span class="text-white font-medium">重複濾鏡</span>
                    <p class="text-white/50 text-sm mt-1">過濾重複出現的文字內容</p>
                  </div>
                </label>

                <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition">
                  <input 
                    type="checkbox" 
                    :checked="localConfig.transcription.whisper_filters?.includes('japanese_stream_filter')"
                    @change="toggleFilter('japanese_stream_filter', ($event.target as HTMLInputElement).checked)"
                    class="w-5 h-5 accent-blue-500 mt-0.5" 
                  />
                  <div class="flex-1">
                    <span class="text-white font-medium">日文直播濾鏡</span>
                    <p class="text-white/50 text-sm mt-1">針對日文直播內容的特殊濾鏡處理</p>
                  </div>
                </label>
              </div>
            </div>

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
          <div v-show="activeTab === 'model_management'" class="space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">模型管理</h2>

            <div class="bg-cyan-500/10 rounded-xl p-4 border border-cyan-500/20">
              <p class="text-cyan-200 text-sm">
                📦 在這裡可預先下載 ASR 模型，避免首次啟動轉錄時等待。
              </p>
              <p class="text-white/50 text-xs mt-2">
                模型快取目前沿用 HuggingFace 預設路徑。
              </p>
            </div>

            <div v-if="modelDownloadStore.errorMessage" class="p-3 rounded-lg border border-red-500/40 bg-red-500/20 text-red-200 text-sm">
              {{ modelDownloadStore.errorMessage }}
            </div>
            <div v-if="modelDownloadStore.successMessage" class="p-3 rounded-lg border border-green-500/40 bg-green-500/20 text-green-200 text-sm">
              {{ modelDownloadStore.successMessage }}
            </div>

            <div class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">Qwen3-ASR 模型</h3>
              <div class="space-y-3">
                <div v-for="modelId in qwenModels" :key="`qwen-${modelId}`" class="p-4 rounded-lg bg-white/5 border border-white/10">
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

            <div class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">Faster-Whisper 模型</h3>
              <div class="space-y-3">
                <div v-for="modelId in fasterWhisperModels" :key="`fw-${modelId}`" class="p-4 rounded-lg bg-white/5 border border-white/10">
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

              <div v-if="modelDownloadStore.downloadedModels.length === 0" class="text-white/50 text-sm">
                尚無已下載模型
              </div>
              <div v-else class="space-y-2">
                <div v-for="item in modelDownloadStore.downloadedModels" :key="`${item.engine}-${item.repo_id}`" class="p-3 rounded-lg bg-black/20 border border-white/10">
                  <div class="flex items-center justify-between gap-4">
                    <div>
                      <div class="text-white font-medium">{{ item.model_id }}</div>
                      <div class="text-xs text-white/50 mt-1">{{ item.engine }} · {{ item.repo_id }}</div>
                    </div>
                    <div class="text-sm text-white/70">{{ modelDownloadStore.formatSize(item.size_bytes) }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Translation Settings -->
          <div v-show="activeTab === 'translation'" class="space-y-6">
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
                    <input v-model="localConfig.translation.api_key" type="password" placeholder="覆蓋一般設定的 API Key"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-green-400" />
                    <p class="text-white/40 text-xs mt-1">留空則使用一般設定</p>
                  </div>

                  <div class="md:col-span-2">
                    <label class="block text-white/70 font-semibold mb-2">API Base URL <span class="text-white/40 text-xs">(選填)</span></label>
                    <input v-model="localConfig.translation.gpt_base_url" type="text" placeholder="https://api.openai.com/v1"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-green-400" />
                    <p class="text-white/40 text-xs mt-1">自訂 GPT API 端點，留空使用預設</p>
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
                    <input v-model="localConfig.translation.api_key" type="password" placeholder="覆蓋一般設定的 API Key"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                    <p class="text-white/40 text-xs mt-1">留空則使用一般設定</p>
                  </div>

                  <div class="md:col-span-2">
                    <label class="block text-white/70 font-semibold mb-2">API Base URL <span class="text-white/40 text-xs">(選填)</span></label>
                    <input v-model="localConfig.translation.gemini_base_url" type="text" placeholder="留空使用預設 Gemini 端點"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                    <p class="text-white/40 text-xs mt-1">自訂 Gemini API 端點</p>
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
                  <label class="block text-white/70 font-semibold mb-2">歷史訊息數量</label>
                  <input v-model.number="localConfig.translation.translation_history_size" type="number" min="0" max="20"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-white/40 text-xs mt-1">0 = 並行翻譯, >0 = 串行翻譯 (包含上下文)</p>
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2">翻譯超時 (秒)</label>
                  <input v-model.number="localConfig.translation.translation_timeout" type="number" min="5" max="60"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-white/40 text-xs mt-1">超過此時間將放棄該句翻譯</p>
                </div>

                <div class="md:col-span-2">
                  <label class="block text-white/70 font-semibold mb-2">處理代理伺服器 <span class="text-white/40 text-xs">(選填)</span></label>
                  <input v-model="localConfig.translation.processing_proxy" type="text" placeholder="http://127.0.0.1:7890"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                  <p class="text-white/40 text-xs mt-1">為 Whisper/GPT API 使用代理（Gemini 目前不支援）</p>
                </div>

                <div class="md:col-span-2">
                  <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition">
                    <input v-model="localConfig.translation.use_json_result" type="checkbox" class="w-5 h-5 accent-blue-500 mt-0.5" />
                    <div class="flex-1">
                      <span class="text-white font-medium">使用 JSON 結果格式</span>
                      <p class="text-white/50 text-sm mt-1">針對某些本地部署的模型，在 LLM 翻譯中使用 JSON 結果格式</p>
                    </div>
                  </label>
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
          <div v-show="activeTab === 'llama'" class="space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">🦙 Llama 設定</h2>
            <div class="bg-gradient-to-br from-yellow-500/10 to-orange-500/10 rounded-xl p-5 border border-yellow-500/20 mb-4">
              <p class="text-yellow-200 mb-2">💡 使用本地 llama.cpp 進行翻譯</p>
              <p class="text-white/60 text-sm">無需網路連線，支援 GPU 加速，保護資料隱私</p>
            </div>
            <LlamaSettings />
          </div>

          <!-- Terminology Settings -->
          <div v-show="activeTab === 'terminology'" class="space-y-6">
            <h2 class="text-xl font-bold text-white mb-4">術語表</h2>
            
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
              <div v-for="(term, idx) in filteredGlossary" :key="idx"
                class="flex items-center justify-between p-3 bg-white/5 rounded-lg border border-white/10">
                <div class="flex-1 grid grid-cols-2 gap-4">
                  <span class="text-white">{{ term.original }}</span>
                  <span class="text-yellow-300">→ {{ term.translated }}</span>
                </div>
                <button @click="removeTerm(idx)" class="text-red-400 hover:text-red-300 ml-4">✕</button>
              </div>
              <div v-if="filteredGlossary.length === 0" class="text-white/40 text-center py-8">
                {{ (localConfig.terminology?.glossary_list?.length || 0) === 0 ? '尚未新增術語' : '無符合搜尋的術語' }}
              </div>
            </div>

            <div class="text-white/40 text-sm mt-4">
              共 {{ localConfig.terminology?.glossary_list?.length || 0 }} 個術語
            </div>
          </div>

          <!-- Output & Notification Settings -->
          <div v-show="activeTab === 'output'" class="space-y-6">
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

        <!-- Action Buttons -->
        <div class="border-t border-white/10 bg-white/5 px-6 py-4 flex justify-between items-center">
          <button @click="resetToDefault" class="bg-yellow-600 hover:bg-yellow-700 text-white font-bold py-2 px-6 rounded-lg transition">
            🔄 重置為預設值
          </button>

          <div class="flex gap-4">
            <button @click="handleCancel" class="bg-white/10 hover:bg-white/20 text-white font-bold py-2 px-6 rounded-lg transition border border-white/20">
              取消
            </button>

            <button @click="handleSave" :disabled="isSaving" class="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:from-gray-500 disabled:to-gray-600 text-white font-bold py-2 px-8 rounded-lg transition shadow-lg shadow-blue-500/30">
              {{ isSaving ? '儲存中...' : '💾 儲存設定' }}
            </button>
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
```
