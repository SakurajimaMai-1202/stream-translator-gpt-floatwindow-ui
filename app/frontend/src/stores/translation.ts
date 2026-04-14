import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { translationApi, configApi, type Config, type AudioSource } from '../services/api';

export interface HomeInputState {
  urlInput: string;
  audioSource: AudioSource;
  selectedDeviceIndex: number | null;
  selectedTranscriptionEngine: string;
  selectedWhisperModel: string;
  selectedQwen3AsrModel: string;
  selectedInputLanguage: string;
  selectedOutputLanguage: string;
  selectedBackend: string;
  translationEnabled: boolean;
}

export interface SubtitleLine {
  id: string;
  original: string;
  translated: string;
  timestamp: number; // 前端接收時間
  backend_timestamp?: string; // 後端傳來的字串時間戳 (00:00:01 -> 00:00:03)
}

export const useTranslationStore = defineStore('translation', () => {
  // State
  const isRunning = ref(false);
  const currentUrl = ref('');
  const currentTaskId = ref('');
  const subtitles = ref<SubtitleLine[]>([]);
  const config = ref<Config>({
    general: {},
    server: {},
    input: {},
    audio_slicing_vad: {},
    transcription: {},
    translation: {},
    terminology: {},
    output: {},
    output_notification: {},
    ui: {}
  });
  const errorMessage = ref('');
  const statusMessage = ref('');

  // 首頁輸入狀態持久化（避免從設定頁返回時被覆蓋）
  const isConfigInitialized = ref(false);
  const homeInputState = ref<HomeInputState>({
    urlInput: '',
    audioSource: 'url',
    selectedDeviceIndex: null,
    selectedTranscriptionEngine: 'faster-whisper',
    selectedWhisperModel: 'base',
    selectedQwen3AsrModel: 'Qwen/Qwen3-ASR-1.7B',
    selectedInputLanguage: 'auto',
    selectedOutputLanguage: 'Traditional Chinese',
    selectedBackend: 'gpt',
    translationEnabled: true
  });

  let eventSource: EventSource | null = null;
  let connectedTaskId = '';
  let broadcastChannel: BroadcastChannel | null = null;

  // 初始化 BroadcastChannel
  try {
    broadcastChannel = new BroadcastChannel('subtitle-updates');
  } catch (error) {
    console.error('BroadcastChannel 初始化失敗:', error);
  }

  // Computed
  const latestSubtitle = computed(() => {
    return subtitles.value.length > 0
      ? subtitles.value[subtitles.value.length - 1]
      : null;
  });

  // Actions
  async function loadConfig() {
    try {
      config.value = await configApi.getConfig();
    } catch (error: any) {
      errorMessage.value = `載入配置失敗: ${error.message}`;
    }
  }

  async function saveConfig(newConfig: Config) {
    try {
      await configApi.updateConfig(newConfig);
      config.value = newConfig;
      statusMessage.value = '配置已儲存';
      setTimeout(() => statusMessage.value = '', 3000);
    } catch (error: any) {
      errorMessage.value = `儲存配置失敗: ${error.message}`;
    }
  }

  async function exportConfig() {
    try {
      await configApi.exportConfig();
      statusMessage.value = '設定已匯出';
      setTimeout(() => statusMessage.value = '', 3000);
    } catch (error: any) {
      errorMessage.value = `匯出設定失敗: ${error.message}`;
      console.error(error);
    }
  }

  async function importConfig(file: File) {
    try {
      await configApi.importConfig(file);
      await loadConfig(); // 重新載入設定
      statusMessage.value = '設定已匯入';
      setTimeout(() => statusMessage.value = '', 3000);
    } catch (error: any) {
      errorMessage.value = `匯入設定失敗: ${error.message}`;
      console.error(error);
      throw error;
    }
  }

  async function startTranslation(url: string) {
    try {
      const response = await translationApi.start({
        audio_source: 'url',
        url: url,
        model: config.value.transcription?.model,
        backend: config.value.transcription?.backend,
        target_language: config.value.translation?.target_language,
        gpt_model: config.value.translation?.gpt_model
      });
      currentUrl.value = url;
      currentTaskId.value = response.task_id;
      isRunning.value = true;
      subtitles.value = [];
      errorMessage.value = '';

      // 連接 SSE
      connectEventSource(response.task_id);
    } catch (error: any) {
      errorMessage.value = `啟動失敗: ${error.message}`;
      isRunning.value = false;
    }
  }

  async function stopTranslation() {
    try {
      if (currentTaskId.value) {
        await translationApi.stop(currentTaskId.value);
      }
    } catch (error: any) {
      // 即使 API 調用失敗(例如任務已經停止),也要重置本地狀態
      console.warn('停止翻譯 API 調用失敗:', error.message);
      // 只有在非 404 錯誤時才顯示錯誤訊息
      if (!error.message.includes('404')) {
        errorMessage.value = `停止失敗: ${error.message}`;
      }
    } finally {
      // 無論 API 調用成功與否,都要重置本地狀態
      disconnectEventSource();
      isRunning.value = false;
      currentUrl.value = '';
      currentTaskId.value = '';
    }
  }

  async function syncRunningState() {
    try {
      const status = await translationApi.getStatus();
      const runningTask = status.tasks?.find((task: any) => task.is_running) || null;

      if (runningTask) {
        isRunning.value = true;
        currentTaskId.value = runningTask.task_id || '';
        currentUrl.value = runningTask.url || currentUrl.value;

        if (currentTaskId.value && connectedTaskId !== currentTaskId.value) {
          connectEventSource(currentTaskId.value);
        }
      } else {
        isRunning.value = false;
        currentUrl.value = '';
        currentTaskId.value = '';
        if (connectedTaskId) {
          disconnectEventSource();
        }
      }
    } catch (error: any) {
      console.warn('[TranslationStore] 同步執行狀態失敗:', error?.message || error);
    }
  }

  function connectEventSource(taskId: string) {
    if (connectedTaskId === taskId && eventSource) {
      return;
    }

    if (eventSource) {
      console.log('[SSE] Closing existing EventSource');
      eventSource.close();
    }

    console.log('[SSE] Creating EventSource for task:', taskId);
    eventSource = translationApi.createEventSource(taskId);
    connectedTaskId = taskId;
    console.log('[SSE] EventSource created, readyState:', eventSource.readyState);

    eventSource.onopen = () => {
      console.log('[SSE] Connection opened successfully');
    };

    eventSource.addEventListener('subtitle', (event: MessageEvent) => {
      try {
        console.log('[SSE] Received subtitle event:', event.data);
        const data = JSON.parse(event.data);
        console.log('[SSE] Parsed subtitle data:', data);
        const backendTs = data.timestamp || '';

        // 如果有後端 timestamp，先尋找是否已存在該筆
        let existingIdx = -1;
        if (backendTs) {
          existingIdx = subtitles.value.findIndex(
            (s: any) => s.backend_timestamp === backendTs
          );
        }

        if (existingIdx !== -1) {
          // 直接更新該筆（原文或翻譯擴充）
          (subtitles.value[existingIdx] as any).original = data.original || '';
          (subtitles.value[existingIdx] as any).translated = data.translated || '';
          // 觸發 Vue reactive 更新：重新賍予同一個
          const updated = { ...subtitles.value[existingIdx] };
          subtitles.value.splice(existingIdx, 1, updated);
          console.log('[Store] Updated existing subtitle:', backendTs);
          // 也廣播給其他視窗
          if (broadcastChannel) {
            broadcastChannel.postMessage(updated);
          }
        } else {
          const newSubtitle: SubtitleLine = {
            id: `${Date.now()}-${Math.random()}`,
            original: data.original || '',
            translated: data.translated || '',
            timestamp: Date.now(),
            backend_timestamp: backendTs
          };
          subtitles.value.push(newSubtitle);
          console.log('[Store] Added new subtitle to store, total:', subtitles.value.length);
          // 廣播給其他視窗
          if (broadcastChannel) {
            console.log('[BroadcastChannel] Posting subtitle:', newSubtitle);
            broadcastChannel.postMessage(newSubtitle);
          }
        }

        // 保持最多 100 筆字幕
        if (subtitles.value.length > 100) {
          subtitles.value.shift();
        }
      } catch (err) {
        console.error('解析字幕事件失敗:', err);
      }
    });

    eventSource.addEventListener('status', (event: MessageEvent) => {
      try {
        console.log('[SSE] Received status event:', event.data);
        const data = JSON.parse(event.data);
        statusMessage.value = data.message || '';
      } catch (err) {
        console.error('解析狀態事件失敗:', err);
      }
    });

    eventSource.addEventListener('error', (event: MessageEvent) => {
      try {
        const data = JSON.parse(event.data);
        errorMessage.value = data.message || '未知錯誤';
      } catch (err) {
        errorMessage.value = 'SSE 連接錯誤';
      }
    });

    eventSource.onerror = (error) => {
      console.error('[SSE] EventSource error:', error);
      console.error('[SSE] EventSource readyState:', eventSource?.readyState);
      disconnectEventSource();
      if (isRunning.value) {
        errorMessage.value = 'SSE 連接中斷';
        isRunning.value = false;
      }
    };
  }

  function disconnectEventSource() {
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    connectedTaskId = '';
  }

  function clearError() {
    errorMessage.value = '';
  }

  function clearStatus() {
    statusMessage.value = '';
  }

  function saveHomeInput(state: HomeInputState) {
    homeInputState.value = { ...state };
  }

  return {
    // State
    isRunning,
    currentUrl,
    currentTaskId,
    subtitles,
    config,
    errorMessage,
    statusMessage,
    isConfigInitialized,
    homeInputState,

    // Computed
    latestSubtitle,

    // Actions
    loadConfig,
    saveConfig,
    exportConfig,
    importConfig,
    startTranslation,
    stopTranslation,
    syncRunningState,
    connectEventSource,
    disconnectEventSource,
    clearError,
    clearStatus,
    saveHomeInput
  };
});
