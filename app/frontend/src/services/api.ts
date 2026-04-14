import axios from 'axios';

const API_BASE = '/api';

const CLIENT_ID_STORAGE_KEY = 'stream-translator-client-id';
let cachedClientId = '';

export function getClientId(): string {
  if (cachedClientId) {
    return cachedClientId;
  }

  try {
    const existing = window.sessionStorage.getItem(CLIENT_ID_STORAGE_KEY);
    if (existing) {
      cachedClientId = existing;
      return cachedClientId;
    }

    cachedClientId = `client-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    window.sessionStorage.setItem(CLIENT_ID_STORAGE_KEY, cachedClientId);
    return cachedClientId;
  } catch {
    cachedClientId = `client-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    return cachedClientId;
  }
}

axios.interceptors.request.use((config) => {
  config.headers = config.headers || {};
  config.headers['X-Client-Id'] = getClientId();
  return config;
});

export interface Config {
  [key: string]: any;
}

export interface TranslationStatus {
  is_running: boolean;
  url?: string;
}

export interface ServerInfo {
  public_port: number;
  enable_subtitle_sharing: boolean;
}

export interface FfmpegCheckResult {
  available: boolean;
  path: string | null;
  version: string | null;
  checked_at: number;
}

export interface SystemCheckResponse {
  ffmpeg: FfmpegCheckResult;
}

export const configApi = {
  async getConfig(): Promise<Config> {
    const response = await axios.get(`${API_BASE}/config`);
    // 後端返回 {success: true, data: {...}}
    return response.data.data || response.data;
  },

  async updateConfig(config: Config): Promise<void> {
    // 使用 PUT 進行完整配置更新
    await axios.put(`${API_BASE}/config`, config);
  },

  async updateSection(section: string, data: any): Promise<void> {
    await axios.patch(`${API_BASE}/config/${section}`, data);
  },

  async resetConfig(): Promise<void> {
    await axios.post(`${API_BASE}/config/reset`);
  },

  async exportConfig(): Promise<void> {
    const response = await axios.get(`${API_BASE}/config/export`, {
      responseType: 'blob'
    });
    // 下載檔案
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', 'config.yaml');
    document.body.appendChild(link);
    link.click();
    link.remove();
  },

  async importConfig(file: File): Promise<void> {
    const formData = new FormData();
    formData.append('file', file);
    await axios.post(`${API_BASE}/config/import/file`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
  }
};

export const serverApi = {
  async getInfo(): Promise<ServerInfo> {
    const response = await axios.get(`${API_BASE}/server/info`);
    return response.data;
  }
};

export const syncApi = {
  createEventSource(): EventSource {
    return new EventSource(`${API_BASE}/sync/events?client_id=${encodeURIComponent(getClientId())}`);
  }
};

export const systemApi = {
  async checkDependencies(): Promise<SystemCheckResponse> {
    const response = await axios.get(`${API_BASE}/system/check`);
    return response.data;
  }
};

export type AudioSource = 'url' | 'file' | 'microphone' | 'system_audio';

export interface AudioDevice {
  index: number;
  name: string;
  sample_rate: number;
  is_default?: boolean;
}

export interface DeviceListResponse {
  success: boolean;
  devices: {
    microphones: AudioDevice[];
    system_audio: AudioDevice[];
  };
}

export interface StartTranslationRequest {
  audio_source?: AudioSource;
  url?: string;
  device_index?: number;
  model?: string;
  backend?: string;
  transcription_engine?: string;  // 轉錄引擎: faster-whisper/qwen3-asr/openai-api/...
  qwen3_asr_model?: string;       // Qwen3-ASR 模型名稱
  qwen3_flash_attention?: boolean;// Qwen3-ASR Flash Attention
  qwen3_dtype?: string;           // Qwen3-ASR 模型精度: bfloat16, float16, float32
  input_language?: string;  // 🔧 新增: Whisper 輸入語言
  target_language?: string;
  gpt_model?: string;
  translation_backend?: string;   // 翻譯後端: gpt/gemini/custom:ModelName
  translation_enabled?: boolean;  // 🔧 新增: 翻譯開關
  override_config?: any;
}

export interface StartResponse {
  success: boolean;
  task_id: string;
  sse_url: string;
  message: string;
}

export type ModelEngine = 'qwen3-asr' | 'faster-whisper';

export interface StartModelDownloadRequest {
  engine: ModelEngine;
  model_id: string;
}

export interface ModelDownloadTask {
  task_id: string;
  engine: ModelEngine;
  model_id: string;
  status: 'pending' | 'downloading' | 'completed' | 'failed';
  progress: number;
  message: string;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface DownloadedModelInfo {
  engine: ModelEngine;
  model_id: string;
  repo_id: string;
  size_bytes: number;
  cache_path: string;
}

export const translationApi = {
  async start(request: StartTranslationRequest): Promise<StartResponse> {
    const response = await axios.post(`${API_BASE}/translation/start`, request);
    return response.data;
  },

  async getDevices(): Promise<DeviceListResponse> {
    const response = await axios.get(`${API_BASE}/translation/devices`);
    return response.data;
  },

  async stop(taskId?: string): Promise<void> {
    if (taskId) {
      await axios.delete(`${API_BASE}/translation/stop/${taskId}`);
    } else {
      // 停止所有任務
      const status = await this.getStatus();
      if (status.tasks && status.tasks.length > 0) {
        await Promise.all(status.tasks.map((t: any) =>
          axios.delete(`${API_BASE}/translation/stop/${t.task_id}`)
        ));
      }
    }
  },

  async getStatus(): Promise<{ success: boolean; active_tasks: number; tasks: any[] }> {
    const response = await axios.get(`${API_BASE}/translation/status`);
    return response.data;
  },

  createEventSource(taskId: string): EventSource {
    return new EventSource(`${API_BASE}/translation/stream/${taskId}`);
  }
};

export const modelApi = {
  async startDownload(request: StartModelDownloadRequest): Promise<{ success: boolean; task_id: string; message: string }> {
    const response = await axios.post(`${API_BASE}/models/download`, request);
    return response.data;
  },

  async getTasks(): Promise<{ success: boolean; tasks: ModelDownloadTask[] }> {
    const response = await axios.get(`${API_BASE}/models/tasks`);
    return response.data;
  },

  async getTask(taskId: string): Promise<ModelDownloadTask> {
    const response = await axios.get(`${API_BASE}/models/tasks/${taskId}`);
    return response.data;
  },

  async getDownloadedModels(): Promise<{ success: boolean; models: DownloadedModelInfo[] }> {
    const response = await axios.get(`${API_BASE}/models/list`);
    return response.data;
  }
};
