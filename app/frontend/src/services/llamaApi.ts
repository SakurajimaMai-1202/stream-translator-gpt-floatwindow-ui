/**
 * Llama.cpp API 服務
 * 提供 Llama 模型管理和推論功能
 */
import axios from 'axios';

const API_BASE = '/api/llama';

export interface ModelInfo {
  name: string;
  path: string;
  size_mb: number;
  modified_time: string;
}

export interface ServerConfig {
  model_path: string;
  host?: string;
  port?: number;
  n_ctx?: number;
  n_gpu_layers?: number;
  n_threads?: number;
  n_parallel?: number;
  server_exe?: string;

  // 進階生成參數
  top_k?: number;
  top_p?: number;
  temp?: number;
  repeat_penalty?: number;
  n_predict?: number;

  // 進階性能參數
  flash_attn?: boolean;
  no_mmap?: boolean;
}

export interface ServerStatus {
  is_running: boolean;
  is_ready: boolean;
  server_url: string | null;
  current_model: string | null;
  last_error?: string | null;
  pid: number | null;
  resources: Record<string, any>;
  performance: Record<string, any>;
  runtime: { installed: boolean; path: string; version: string; download_url: string };
}

export interface InferenceRequest {
  prompt: string;
  max_tokens?: number;
  temperature?: number;
  top_p?: number;
  stop?: string[];
}

export interface TranslateRequest {
  text: string;
  source_lang?: string;
  target_lang?: string;
  context?: string;
}

export interface TranslateResponse {
  original: string;
  translated: string;
  model: string;
}

export interface RuntimeVariant {
  id: string;
  label: string;
  backend: string;
  runtime_version: string;
  recommended: boolean;
  installable: boolean;
  compatibility_error: string;
  installed?: boolean;
  installed_latest?: boolean;
  size: number;
  assets: Array<{
    name: string;
    url: string;
    size: number;
    digest: string;
    role: 'runtime' | 'dependency';
  }>;
}

export interface RuntimeReleaseInfo {
  source: 'github';
  tag: string;
  published_at: string | null;
  installed_tag?: string;
  installed_variant?: string;
  is_latest?: boolean;
  recommended_variant?: string;
  recommendation_reason?: string;
  detected_gpus?: Array<{
    name: string;
    vendor: string;
    backend: string;
    memory_mb: number | null;
    is_integrated: boolean;
  }>;
  variants: RuntimeVariant[];
}

export interface RuntimeInstallStatus {
  state: 'idle' | 'resolving' | 'downloading' | 'verifying' | 'staging' | 'activating' | 'completed' | 'error';
  message: string;
  progress: number;
  job_id: string;
  variant: string;
  tag: string;
  installed_path: string;
  previous_runtime: string;
  error: string;
  files: Array<{
    name: string;
    role: 'runtime' | 'dependency';
    state: 'pending' | 'downloading' | 'verifying' | 'completed' | 'error';
    progress: number;
    downloaded_bytes: number;
    total_bytes: number;
    sha256: string;
    error: string;
  }> | null;
}

export const llamaApi = {
  async getRuntimeReleases(): Promise<RuntimeReleaseInfo> {
    const response = await axios.get(`${API_BASE}/runtime/releases`);
    return response.data;
  },

  async installRuntime(variant: string): Promise<{ success: boolean; message: string; job_id: string }> {
    const response = await axios.post(`${API_BASE}/runtime/install`, { variant });
    return response.data;
  },

  async getRuntimeInstallStatus(): Promise<RuntimeInstallStatus> {
    const response = await axios.get(`${API_BASE}/runtime/install/status`);
    return response.data;
  },
  /**
   * 列出可用的 GGUF 模型
   */
  async listModels(modelDir?: string): Promise<ModelInfo[]> {
    const params = modelDir ? { model_dir: modelDir } : {};
    const response = await axios.get(`${API_BASE}/models`, { params });
    return response.data;
  },

  /**
   * 啟動 Llama 伺服器
   */
  async startServer(config: ServerConfig): Promise<any> {
    const response = await axios.post(`${API_BASE}/server/start`, config);
    return response.data;
  },

  /**
   * 停止 Llama 伺服器
   */
  async stopServer(): Promise<any> {
    const response = await axios.post(`${API_BASE}/server/stop`);
    return response.data;
  },

  /**
   * 獲取伺服器狀態
   */
  async getServerStatus(): Promise<ServerStatus> {
    const response = await axios.get(`${API_BASE}/server/status`);
    return response.data;
  },

  /**
   * 執行推論
   */
  async inference(request: InferenceRequest): Promise<any> {
    const response = await axios.post(`${API_BASE}/inference`, request);
    return response.data;
  },

  /**
   * 翻譯文字
   */
  async translate(request: TranslateRequest): Promise<TranslateResponse> {
    const response = await axios.post(`${API_BASE}/translate`, request);
    return response.data;
  },

  /**
   * 健康檢查
   */
  async healthCheck(): Promise<any> {
    const response = await axios.get(`${API_BASE}/health`);
    return response.data;
  },

  /**
   * 獲取預設配置列表
   */
  async getPresets(): Promise<Record<string, any>> {
    const response = await axios.get(`${API_BASE}/presets`);
    return response.data.presets;
  },

  /**
   * 獲取特定預設配置
   */
  async getPreset(presetName: string): Promise<any> {
    const response = await axios.get(`${API_BASE}/presets/${encodeURIComponent(presetName)}`);
    return response.data;
  },

  /**
   * 獲取自訂配置列表
   */
  async getCustomPresets(): Promise<Record<string, any>> {
    const response = await axios.get(`${API_BASE}/presets/custom`);
    return response.data;
  },

  /**
   * 保存自訂配置
   */
  async saveCustomPreset(name: string, config: ServerConfig): Promise<any> {
    const response = await axios.post(`${API_BASE}/presets/custom/${encodeURIComponent(name)}`, config);
    return response.data;
  },

  /**
   * 刪除自訂配置
   */
  async deleteCustomPreset(name: string): Promise<any> {
    const response = await axios.delete(`${API_BASE}/presets/custom/${encodeURIComponent(name)}`);
    return response.data;
  }
};
