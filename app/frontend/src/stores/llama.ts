/**
 * Llama Store
 * 管理 Llama 伺服器狀態和配置
 */
import { defineStore } from 'pinia';
import { ref, computed, watch } from 'vue';
import { llamaApi, type ModelInfo, type ServerConfig, type ServerStatus } from '../services/llamaApi';
import { configApi } from '../services/api';

// 模型系列介面
export interface ModelSeries {
  name: string;           // 系列名稱
  patterns: string[];     // 匹配關鍵字列表
  color?: string;         // 可選的顯示顏色
  icon?: string;          // 可選的圖標
}

export const useLlamaStore = defineStore('llama', () => {
  // State
  const models = ref<ModelInfo[]>([]);
  const serverStatus = ref<ServerStatus>({
    is_running: false,
    is_ready: false,
    server_url: null,
    current_model: null,
    pid: null
  });
  const selectedModelPath = ref<string>('');
  const modelDirectory = ref<string>('');
  const isLoading = ref(false);
  const errorMessage = ref('');
  const successMessage = ref('');
  const customPresets = ref<Record<string, Partial<ServerConfig>>>({});
  const systemPresets = ref<Record<string, Partial<ServerConfig>>>({}); // 系統預設配置

  const defaultModelSeries: ModelSeries[] = [
    { name: 'Qwen', patterns: ['qwen'] },
    { name: 'Llama', patterns: ['llama'] },
    { name: 'Mistral', patterns: ['mistral'] },
    { name: 'Gemma', patterns: ['gemma'] },
    { name: 'Phi', patterns: ['phi'] },
    { name: 'Orion', patterns: ['orion'] },
    { name: 'HYMT', patterns: ['hymt'] },
    { name: 'Yi', patterns: ['yi'] },
    { name: 'Baichuan', patterns: ['baichuan'] },
    { name: 'ChatGLM', patterns: ['chatglm'] },
  ];
  const customModelSeries = ref<ModelSeries[]>([...defaultModelSeries]);  // 自訂模型系列

  // Server Config
  const serverConfig = ref<ServerConfig>({
    model_path: '',
    host: '127.0.0.1',
    port: 8080,
    n_ctx: 2048,
    n_gpu_layers: 0,
    n_threads: 4,
    n_parallel: 1,
    // 進階生成參數
    top_k: 40,
    top_p: 0.95,
    temp: 0.8,
    repeat_penalty: 1.1,
    n_predict: 512,
    // 進階性能參數
    flash_attn: true,
    no_mmap: false
  });

  // Computed
  const isServerRunning = computed(() => serverStatus.value.is_running);
  const isServerReady = computed(() => serverStatus.value.is_ready);
  const currentModel = computed(() => serverStatus.value.current_model);
  const hasModels = computed(() => models.value.length > 0);

  // Actions
  async function loadModels(directory?: string) {
    isLoading.value = true;
    errorMessage.value = '';
    try {
      const dir = directory || modelDirectory.value;
      models.value = await llamaApi.listModels(dir);
      if (dir) {
        modelDirectory.value = dir;
        if (!isInitializing.value) {
          saveConfig(); // 只在非初始化時保存目錄設定
        }
      }
      successMessage.value = `找到 ${models.value.length} 個模型`;
      setTimeout(() => successMessage.value = '', 2000);
    } catch (error: any) {
      errorMessage.value = `載入模型列表失敗: ${error.message}`;
      models.value = [];
    } finally {
      isLoading.value = false;
    }
  }

  async function refreshServerStatus() {
    try {
      serverStatus.value = await llamaApi.getServerStatus();
    } catch (error: any) {
      console.error('獲取伺服器狀態失敗:', error);
    }
  }

  async function startServer(config?: ServerConfig) {
    isLoading.value = true;
    errorMessage.value = '';
    try {
      const finalConfig = config || {
        ...serverConfig.value,
        model_path: selectedModelPath.value
      };

      if (!finalConfig.model_path) {
        throw new Error('請選擇模型');
      }

      const result = await llamaApi.startServer(finalConfig);

      // 輪詢檢查伺服器是否就緒
      let retries = 0;
      const maxRetries = 60; // 等待 60 秒

      while (retries < maxRetries) {
        await refreshServerStatus();
        if (serverStatus.value.is_ready) {
          break;
        }
        await new Promise(resolve => setTimeout(resolve, 1000));
        retries++;
      }

      if (!serverStatus.value.is_ready) {
        throw new Error('伺服器啟動超時，請檢查日誌');
      }

      successMessage.value = `伺服器已啟動 (PID: ${result.pid})`;
      setTimeout(() => successMessage.value = '', 3000);

      return result;
    } catch (error: any) {
      const msg = error.response?.data?.detail || error.message;
      errorMessage.value = `啟動伺服器失敗: ${msg}`;
      // 如果啟動失敗，嘗試停止可能殘留的進程
      try { await stopServer(); } catch (e) { }
      throw error;
    } finally {
      isLoading.value = false;
    }
  }

  async function stopServer() {
    isLoading.value = true;
    errorMessage.value = '';
    try {
      await llamaApi.stopServer();
      await refreshServerStatus();

      successMessage.value = '伺服器已停止';
      setTimeout(() => successMessage.value = '', 2000);
    } catch (error: any) {
      errorMessage.value = `停止伺服器失敗: ${error.message}`;
      throw error;
    } finally {
      isLoading.value = false;
    }
  }

  async function translate(
    text: string,
    sourceLang: string = 'English',
    targetLang: string = 'Traditional Chinese',
    context?: string
  ): Promise<string> {
    if (!serverStatus.value.is_ready) {
      throw new Error('Llama 伺服器尚未就緒');
    }

    try {
      const result = await llamaApi.translate({
        text,
        source_lang: sourceLang,
        target_lang: targetLang,
        context
      });
      return result.translated;
    } catch (error: any) {
      errorMessage.value = `翻譯失敗: ${error.message}`;
      throw error;
    }
  }

  function selectModel(modelPath: string) {
    selectedModelPath.value = modelPath;
    serverConfig.value.model_path = modelPath;
    saveConfig(); // 保存設定
  }

  function updateServerConfig(config: Partial<ServerConfig>) {
    serverConfig.value = { ...serverConfig.value, ...config };
    saveConfig(); // 保存設定
  }

  function clearMessages() {
    errorMessage.value = '';
    successMessage.value = '';
  }

  const selectedPreset = ref<string>(''); // Add selectedPreset state
  const defaultPreset = ref<string>(''); // Default preset to load on startup

  // ... (existing code)

  // 載入配置
  async function loadConfig() {
    isApplyingRemoteConfig.value = true;
    try {
      const config = await configApi.getConfig();
      if (config.llama) {
        // 更新伺服器配置
        const llamaConfig = config.llama;
        serverConfig.value = {
          model_path: llamaConfig.model_path || '',
          host: llamaConfig.host || '127.0.0.1',
          port: llamaConfig.port || 8080,
          n_ctx: llamaConfig.n_ctx || 2048,
          n_gpu_layers: llamaConfig.n_gpu_layers || 0,
          n_threads: llamaConfig.n_threads || 4,
          n_parallel: llamaConfig.n_parallel || 1,
          top_k: llamaConfig.top_k || 40,
          top_p: llamaConfig.top_p || 0.95,
          temp: llamaConfig.temp || 0.8,
          repeat_penalty: llamaConfig.repeat_penalty || 1.1,
          n_predict: llamaConfig.n_predict || 512,
          flash_attn: llamaConfig.flash_attn !== false,
          no_mmap: llamaConfig.no_mmap || false
        };

        // 更新模型路徑和目錄
        if (llamaConfig.model_path) {
          selectedModelPath.value = llamaConfig.model_path;
        }
        if (llamaConfig.model_dir) {
          modelDirectory.value = llamaConfig.model_dir;
        }

        // 載入自訂配置 (Critical: Load here to prevent data loss on auto-save)
        if (llamaConfig.custom_presets) {
          customPresets.value = llamaConfig.custom_presets;
        }

        // 載入選擇的預設配置 (Persistence for selected preset)
        if (llamaConfig.selected_preset) {
          selectedPreset.value = llamaConfig.selected_preset;
        }

        // 載入自訂模型系列
        if (llamaConfig.custom_model_series !== undefined) {
          customModelSeries.value = llamaConfig.custom_model_series;
        }

        // 載入預設啟動配置
        if (llamaConfig.default_preset) {
          defaultPreset.value = llamaConfig.default_preset;
        }
      }
    } catch (error: any) {
      console.error('載入 Llama 配置失敗:', error);
    } finally {
      isApplyingRemoteConfig.value = false;
    }
  }

  // 保存配置
  async function saveConfig() {
    try {
      const llamaConfig = {
        model_dir: modelDirectory.value,
        model_path: selectedModelPath.value,
        selected_preset: selectedPreset.value, // Save selected preset
        default_preset: defaultPreset.value,   // Save default preset
        host: serverConfig.value.host,
        port: serverConfig.value.port,
        n_ctx: serverConfig.value.n_ctx,
        n_gpu_layers: serverConfig.value.n_gpu_layers,
        n_threads: serverConfig.value.n_threads,
        n_parallel: serverConfig.value.n_parallel,
        top_k: serverConfig.value.top_k,
        top_p: serverConfig.value.top_p,
        temp: serverConfig.value.temp,
        repeat_penalty: serverConfig.value.repeat_penalty,
        n_predict: serverConfig.value.n_predict,
        flash_attn: serverConfig.value.flash_attn,
        no_mmap: serverConfig.value.no_mmap,
        custom_presets: customPresets.value, // Critical: Include custom presets!
        custom_model_series: customModelSeries.value // Save custom model series
      };

      await configApi.updateSection('llama', llamaConfig);
    } catch (error: any) {
      console.error('保存 Llama 配置失敗:', error);
    }
  }

  // 載入自訂配置列表
  async function loadCustomPresets() {
    try {
      customPresets.value = await llamaApi.getCustomPresets();
    } catch (error: any) {
      console.error('載入自訂配置失敗:', error);
      const msg = error.response?.data?.detail || error.message || '未知錯誤';
      // 不要打斷初始化流程，只記錄錯誤
      console.error(`詳細錯誤: ${msg}`);
    }
  }

  // 載入系統預設配置
  async function loadSystemPresets() {
    try {
      systemPresets.value = await llamaApi.getPresets();
    } catch (error: any) {
      console.error('載入系統配置失敗:', error);
    }
  }

  // 保存自訂配置
  async function saveCustomPreset(name: string) {
    try {
      console.log('[LlamaStore] === 開始保存配置 ===');
      console.log('[LlamaStore] 配置名稱:', name);
      console.log('[LlamaStore] selectedModelPath:', selectedModelPath.value);
      console.log('[LlamaStore] serverConfig:', serverConfig.value);

      // 包含模型路徑和伺服器配置
      const presetConfig = {
        ...serverConfig.value,
        model_path: selectedModelPath.value  // 綁定當前選擇的模型
      };

      console.log('[LlamaStore] 準備保存的配置:', presetConfig);
      console.log('[LlamaStore] 配置中的 model_path:', presetConfig.model_path);

      await llamaApi.saveCustomPreset(name, presetConfig);
      await loadCustomPresets();

      console.log('[LlamaStore] 保存後重新載入的配置:', customPresets.value[name]);

      successMessage.value = `配置已保存: ${name}`;
      setTimeout(() => successMessage.value = '', 2000);
    } catch (error: any) {
      console.error('[LlamaStore] 保存配置失敗:', error);
      errorMessage.value = `保存配置失敗: ${error.message}`;
      throw error;
    }
  }

  // 刪除自訂配置
  async function deleteCustomPreset(name: string) {
    try {
      await llamaApi.deleteCustomPreset(name);
      await loadCustomPresets();
      successMessage.value = `配置已刪除: ${name}`;
      setTimeout(() => successMessage.value = '', 2000);
    } catch (error: any) {
      errorMessage.value = `刪除配置失敗: ${error.message}`;
      throw error;
    }
  }

  // 設定預設啟動配置
  function setDefaultPreset(name: string) {
    if (defaultPreset.value === name) {
      // 如果已經是預設，則取消預設
      defaultPreset.value = '';
    } else {
      defaultPreset.value = name;
    }
    saveConfig();
  }

  // 載入指定的配置預設
  function loadPreset(presetName: string) {
    if (!presetName) return;

    let preset: Partial<ServerConfig> | undefined;

    if (presetName.startsWith('custom:')) {
      const realName = presetName.substring(7);
      preset = customPresets.value[realName];
    } else {
      preset = systemPresets.value[presetName];
    }

    if (!preset) {
      console.warn(`找不到配置: ${presetName}`);
      return;
    }

    // 載入伺服器配置
    serverConfig.value = {
      ...serverConfig.value,
      ...preset
    };

    // 載入模型路徑
    if (preset.model_path) {
      selectedModelPath.value = preset.model_path;
      serverConfig.value.model_path = preset.model_path;
    }

    successMessage.value = `已載入配置: ${presetName}`;
    setTimeout(() => successMessage.value = '', 2000);
  }

  // 檢查配置是否匹配
  function isConfigMatch(preset: Partial<ServerConfig>): boolean {
    // 比較關鍵參數
    const keysToCompare: (keyof ServerConfig)[] = [
      'model_path', 'n_ctx', 'n_gpu_layers', 'n_threads', 'n_parallel',
      'temp', 'top_p', 'top_k', 'repeat_penalty', 'n_predict',
      'flash_attn', 'no_mmap'
    ];

    for (const key of keysToCompare) {
      const presetValue = preset[key];
      const currentValue = serverConfig.value[key];

      // 如果預設中有這個值,則必須匹配
      if (presetValue !== undefined && presetValue !== currentValue) {
        return false;
      }
    }

    return true;
  }

  // 自動匹配當前配置到預設配置
  function autoMatchPreset() {
    console.log('[autoMatchPreset] 開始自動匹配');
    console.log('[autoMatchPreset] customPresets 數量:', Object.keys(customPresets.value).length);

    // 先檢查自訂配置
    for (const [name, preset] of Object.entries(customPresets.value)) {
      console.log(`[autoMatchPreset] 檢查配置: ${name}`);
      if (isConfigMatch(preset)) {
        selectedPreset.value = `custom:${name}`;
        console.log(`✅ 自動匹配到自訂配置: ${name}`);
        return;
      }
    }

    // 再檢查系統配置
    for (const [name, preset] of Object.entries(systemPresets.value)) {
      if (isConfigMatch(preset)) {
        selectedPreset.value = name;
        console.log(`✅ 自動匹配到系統配置: ${name}`);
        return;
      }
    }

    // 如果沒有匹配的自訂配置,保持為空字串(表示自訂配置)
    console.log('ℹ️ 當前配置為自訂配置');
  }

  // ==================== 模型系列管理 ====================

  // 新增模型系列
  function addModelSeries(series: ModelSeries) {
    customModelSeries.value.push(series);
    saveConfig();
    successMessage.value = `已新增系列: ${series.name}`;
    setTimeout(() => successMessage.value = '', 2000);
  }

  // 更新模型系列
  function updateModelSeries(index: number, series: ModelSeries) {
    if (index >= 0 && index < customModelSeries.value.length) {
      customModelSeries.value[index] = series;
      saveConfig();
      successMessage.value = `已更新系列: ${series.name}`;
      setTimeout(() => successMessage.value = '', 2000);
    }
  }

  // 刪除模型系列
  function deleteModelSeries(index: number) {
    if (index >= 0 && index < customModelSeries.value.length) {
      const name = customModelSeries.value[index].name;
      customModelSeries.value.splice(index, 1);
      saveConfig();
      successMessage.value = `已刪除系列: ${name}`;
      setTimeout(() => successMessage.value = '', 2000);
    }
  }

  // 初始化旗標：初始化期間暫停自動儲存和 watch 觸發
  const isInitializing = ref(true);
  // 遠端配置套用旗標：避免 loadConfig 套用後又被 watcher 當成本地修改回存
  const isApplyingRemoteConfig = ref(false);

  // Watch for preset changes（只在非初始化時才響應）
  watch(selectedPreset, (newPreset, oldPreset) => {
    if (isInitializing.value || isApplyingRemoteConfig.value) return; // 初始化/遠端套用期間不處理
    if (newPreset && newPreset !== oldPreset) {
      loadPreset(newPreset);
      // 儲存選擇的 preset 到配置
      saveConfig();
    }
  });

  // Watch for changes and auto-save（只在非初始化時才自動儲存）
  let saveTimer: any = null;
  watch([serverConfig], () => {
    if (isInitializing.value || isApplyingRemoteConfig.value) return; // 初始化/遠端套用期間不儲存
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(() => {
      saveConfig();
    }, 1000); // 1秒後自動保存
  }, { deep: true });

  // Initialize
  async function initialize() {
    isInitializing.value = true; // 開始初始化，暫停 watch
    try {
      await loadConfig(); // 先從後端 YAML 讀取配置
      await loadSystemPresets(); // 載入系統預設配置
      // 注意：不再呼叫 loadCustomPresets()，因為 loadConfig() 已從 YAML 中讀取 custom_presets
      // loadCustomPresets() 會從舊的 API 端點取得資料，可能覆蓋 YAML 中的資料
      await refreshServerStatus();

      // 根據已載入的配置設定 selectedPreset（不觸發 watch）
      const savedSelectedPreset = selectedPreset.value; // loadConfig 已設定

      // 優先使用 defaultPreset
      if (defaultPreset.value) {
        console.log(`[Initialize] 使用預設啟動配置: ${defaultPreset.value}`);
        // 直接套用配置，不透過 watch（避免競態條件）
        selectedPreset.value = defaultPreset.value;
        loadPreset(defaultPreset.value);
      } else if (savedSelectedPreset) {
        // 恢復上次選擇的配置，但不重新套用（已在 loadConfig 中恢復）
        console.log(`[Initialize] 恢復上次配置: ${savedSelectedPreset}`);
        selectedPreset.value = savedSelectedPreset;
      } else {
        // 如果沒有任何保存配置，嘗試自動匹配
        autoMatchPreset();
      }

      // 如果有保存的模型目錄,嘗試載入模型列表
      if (modelDirectory.value) {
        await loadModels(modelDirectory.value);
      }
    } finally {
      isInitializing.value = false; // 初始化完成，恢復 watch
    }
  }

  return {
    // State
    models,
    serverStatus,
    selectedModelPath,
    modelDirectory,
    isLoading,
    errorMessage,
    successMessage,
    serverConfig,
    customPresets,
    systemPresets,
    customModelSeries,

    // Computed
    isServerRunning,
    isServerReady,
    currentModel,
    hasModels,
    selectedPreset,
    defaultPreset, // Export defaultPreset

    // Actions
    loadModels,
    refreshServerStatus,
    startServer,
    stopServer,
    translate,
    selectModel,
    updateServerConfig,
    clearMessages,
    loadConfig,
    saveConfig,
    loadCustomPresets,
    saveCustomPreset,
    deleteCustomPreset,
    addModelSeries,
    updateModelSeries,
    deleteModelSeries,
    initialize,
    setDefaultPreset // Export setDefaultPreset
  };
});
