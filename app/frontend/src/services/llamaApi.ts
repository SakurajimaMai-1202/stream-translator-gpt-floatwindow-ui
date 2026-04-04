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
  pid: number | null;
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

export const llamaApi = {
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
