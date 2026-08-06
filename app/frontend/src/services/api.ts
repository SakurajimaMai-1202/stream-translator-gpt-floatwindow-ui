import axios from 'axios';

const API_BASE = '/api';

const CLIENT_ID_STORAGE_KEY = 'stream-translator-client-id';
let cachedClientId = '';
let cachedConfig: Config | null = null;
let pendingConfigRequest: Promise<Config> | null = null;

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

export interface SubtitleLatencyTrace {
  trace_id?: string | null;
  merged_trace_ids?: string[];
  capture_wait_ms?: number | null;
  speech_to_slice_ms?: number | null;
  audio_duration_ms?: number | null;
  asr_queue_ms?: number | null;
  asr_inference_ms?: number | null;
  asr_realtime_factor?: number | null;
  assembler_wait_ms?: number | null;
  translation_queue_ms?: number | null;
  translation_inference_ms?: number | null;
  delivery_ms?: number | null;
  end_to_end_ms?: number | null;
}

export interface LatencyWindowSnapshot {
  sample_count: number;
  window_size: number;
  max_window_size: number;
  metrics: Record<string, { latest: number; p50: number; p95: number }>;
}

export interface TranslationStatus {
  is_running: boolean;
  url?: string;
}

export interface ServerInfo {
  public_port: number;
  enable_subtitle_sharing: boolean;
  lan_addresses: string[];
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

export interface RuntimeGpuDevice {
  index: number;
  name: string;
  vendor: string;
  backend: string;
  memory_mb: number | null;
  is_integrated: boolean;
  arch_name?: string | null;
  is_supported_by_torch?: boolean | null;
  source: string;
}

export interface RuntimeCapabilities {
  profile: string;
  status: string;
  package_suffix: string;
  default_device_policy: string;
  allow_integrated_gpu: boolean;
  qwen3_default_dtype: string;
  qwen3_offline_models: string[];
  qwen3_asr_model_ids: string[];
  sensevoice_status: string;
  sensevoice_models: string[];
  sensevoice_model_ids: string[];
  sensevoice_note: string;
  fun_asr_status: string;
  fun_asr_models: string[];
  fun_asr_model_ids: string[];
  fun_asr_note: string;
  parakeet_status: string;
  parakeet_models: string[];
  parakeet_model_ids: string[];
  parakeet_note: string;
  faster_whisper_status: string;
  faster_whisper_models: string[];
  faster_whisper_model_ids: string[];
  faster_whisper_gpu_enabled: boolean;
  faster_whisper_cpu_fallback: boolean;
  local_asr_engines: string[];
  remote_asr_engines: string[];
  asr_model_capabilities: AsrModelCapability[];
}

export interface AsrModelCapability {
  model_id: string;
  engine: string;
  language_mode: 'fixed' | 'limited' | 'multilingual';
  supported_languages: string[];
  default_language: string;
  note: string;
}

export interface RuntimeSelection {
  kind: string;
  profile: string;
  policy: string;
  device: RuntimeGpuDevice | null;
  reason: string;
  ignored_devices: RuntimeGpuDevice[];
}

export interface RuntimeStatus {
  profile: string;
  status: string;
  package_suffix: string;
  device_policy: string;
  allow_integrated_gpu: boolean;
  profile_locked: boolean;
  packaged_profile: string | null;
  asr_compute_backend: 'auto' | 'gpu' | 'cpu';
  effective_asr_compute_backend: 'gpu' | 'cpu';
  capabilities: RuntimeCapabilities;
  asr_capabilities: RuntimeCapabilities;
  cpu_asr_runtime: {
    available: boolean;
    path: string;
    python: string;
    is_sidecar: boolean;
  };
  cpu: {
    name: string;
    logical_cores: number | null;
  };
  devices: RuntimeGpuDevice[];
  selection: RuntimeSelection;
}

export const configApi = {
  async getConfig(force = false): Promise<Config> {
    if (!force && cachedConfig) return cachedConfig;
    if (pendingConfigRequest) return pendingConfigRequest;

    pendingConfigRequest = axios.get(`${API_BASE}/config`).then((response) => {
      cachedConfig = response.data.data || response.data;
      return cachedConfig!;
    }).finally(() => {
      pendingConfigRequest = null;
    });
    return pendingConfigRequest;
  },

  async updateConfig(config: Config): Promise<Config> {
    // 使用 PUT 進行完整配置更新
    const response = await axios.put(`${API_BASE}/config`, config);
    cachedConfig = response.data.data || config;
    return cachedConfig!;
  },

  async updateSection(section: string, data: any): Promise<any> {
    const response = await axios.patch(`${API_BASE}/config/${section}`, data);
    const updatedSection = response.data.data ?? data;
    if (cachedConfig) cachedConfig = { ...cachedConfig, [section]: updatedSection };
    return updatedSection;
  },

  async resetConfig(): Promise<Config> {
    const response = await axios.post(`${API_BASE}/config/reset`);
    cachedConfig = response.data.data || response.data;
    return cachedConfig!;
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

  async importConfig(file: File): Promise<Config> {
    const formData = new FormData();
    formData.append('file', file);
    const response = await axios.post(`${API_BASE}/config/import/file`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    });
    cachedConfig = response.data.data;
    return cachedConfig!;
  },

  applySnapshot(config: Config): Config {
    cachedConfig = config;
    return cachedConfig;
  },

  invalidateCache(): void {
    cachedConfig = null;
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

export const runtimeApi = {
  async getStatus(): Promise<RuntimeStatus> {
    const response = await axios.get(`${API_BASE}/runtime/status`);
    return response.data.data || response.data;
  },
  async getCpuAsrSidecarStatus(): Promise<CpuAsrSidecarInstallStatus> {
    const response = await axios.get(`${API_BASE}/runtime/cpu-asr-sidecar`);
    return response.data.data || response.data;
  },
  async installCpuAsrSidecar(): Promise<CpuAsrSidecarInstallStatus> {
    const response = await axios.post(`${API_BASE}/runtime/cpu-asr-sidecar/install`, {});
    return response.data.data || response.data;
  }
};

export interface CpuAsrSidecarInstallStatus {
  status: 'idle' | 'starting' | 'downloading' | 'verifying' | 'installing' | 'completed' | 'error';
  progress: number;
  message: string;
  error: string;
  bytes_downloaded: number;
  bytes_total: number;
  installed: boolean;
  restart_required: boolean;
  version: string;
  asset_name: string;
}

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
  sensevoice_model?: string;       // SenseVoice 模型名稱
  fun_asr_model?: string;          // Fun-ASR Nano 模型名稱
  nemo_asr_model?: string;         // NVIDIA Parakeet / NeMo 模型名稱
  nemo_asr_dtype?: string;         // NVIDIA Parakeet dtype: bfloat16, float16, float32
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

export type ModelEngine = 'qwen3-asr' | 'faster-whisper' | 'sensevoice' | 'fun-asr-nano' | 'parakeet-ctc-ja';
export type ModelComputeBackend = 'gpu' | 'cpu';

export interface StartModelDownloadRequest {
  engine: ModelEngine;
  model_id: string;
  compute_backend: ModelComputeBackend;
}

export interface ModelDownloadTask {
  task_id: string;
  engine: ModelEngine;
  model_id: string;
  compute_backend: ModelComputeBackend;
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
  compute_backend: ModelComputeBackend;
  size_bytes: number;
  cache_path: string;
}

export interface ModelStorageInfo {
  storage_path: string;
  hub_cache_path: string;
  modelscope_cache_path?: string;
  sherpa_onnx_path: string;
  is_default: boolean;
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
  },

  async getStorage(): Promise<{ success: boolean; storage: ModelStorageInfo }> {
    const response = await axios.get(`${API_BASE}/models/storage`);
    return response.data;
  },

  async openStorage(): Promise<{ success: boolean; message: string }> {
    const response = await axios.post(`${API_BASE}/models/storage/open`);
    return response.data;
  },

  async deleteModel(engine: ModelEngine, modelId: string, computeBackend: ModelComputeBackend): Promise<{ success: boolean; message: string }> {
    const response = await axios.delete(`${API_BASE}/models/${engine}/${encodeURIComponent(modelId)}`, {
      params: { compute_backend: computeBackend },
    });
    return response.data;
  }
};
