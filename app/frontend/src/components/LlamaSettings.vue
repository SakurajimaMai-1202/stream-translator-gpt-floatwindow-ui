<template>
  <div class="llama-settings">
    <!-- 伺服器狀態卡片 -->
    <div class="status-card" :class="{ running: llamaStore.isServerRunning }">
      <div class="status-header">
        <div class="status-indicator">
          <span class="status-dot" :class="{ 
            active: llamaStore.isServerReady, 
            starting: llamaStore.isServerRunning && !llamaStore.isServerReady 
          }"></span>
          <span class="status-text">
            {{ 
              llamaStore.isServerReady ? '伺服器已就緒' : 
              llamaStore.isServerRunning ? '伺服器啟動中...' : 
              '伺服器已停止' 
            }}
          </span>
        </div>
        <button 
          v-if="llamaStore.isServerRunning"
          @click="handleStopServer"
          :disabled="llamaStore.isLoading"
          class="btn-stop"
        >
          🛑 停止伺服器
        </button>
      </div>
      
      <div v-if="llamaStore.isServerRunning" class="status-details">
        <div class="detail-item">
          <span class="label">模型:</span>
          <span class="value">{{ llamaStore.currentModel || 'N/A' }}</span>
        </div>
        <div class="detail-item">
          <span class="label">URL:</span>
          <span class="value">{{ llamaStore.serverStatus.server_url || 'N/A' }}</span>
        </div>
        <div class="detail-item">
          <span class="label">PID:</span>
          <span class="value">{{ llamaStore.serverStatus.pid || 'N/A' }}</span>
        </div>
      </div>
    </div>

    <!-- 訊息提示 -->
    <div v-if="llamaStore.errorMessage" class="alert alert-error">
      ❌ {{ llamaStore.errorMessage }}
    </div>
    <div v-if="llamaStore.successMessage" class="alert alert-success">
      ✅ {{ llamaStore.successMessage }}
    </div>

    <!-- 配置預設管理 (優先級最高) -->
    <div class="section preset-management-section">
      <h3>⚡ 配置預設管理</h3>
      
      <div class="form-group">
        <label>快速切換配置</label>
        <div class="preset-row">
          <select v-model="llamaStore.selectedPreset" @change="applyPreset" class="form-input preset-select">
            <option value="">-- 自訂配置 --</option>
            <optgroup label="系統預設">
              <option v-for="(_, name) in llamaStore.systemPresets" :key="name" :value="name">
                {{ name }}
              </option>
            </optgroup>
            <optgroup label="我的配置" v-if="Object.keys(llamaStore.customPresets).length > 0">
              <option v-for="(_, name) in llamaStore.customPresets" :key="'custom-' + name" :value="'custom:' + name">
                📦 {{ name }}
              </option>
            </optgroup>
          </select>
          <button 
            @click="handleSetDefaultPreset" 
            :disabled="!llamaStore.selectedPreset"
            :class="['btn-set-default', { 'is-default': llamaStore.selectedPreset && llamaStore.selectedPreset === llamaStore.defaultPreset }]"
            :title="llamaStore.selectedPreset === llamaStore.defaultPreset ? '取消預設' : '設為啟動預設'"
          >
            {{ llamaStore.selectedPreset === llamaStore.defaultPreset ? '⭐' : '☆' }}
          </button>
          <button @click="showSaveDialog = true" class="btn-save-preset" title="保存目前配置">
            💾 保存
          </button>
          <button 
            v-if="llamaStore.selectedPreset.startsWith('custom:')"
            @click="handleDeletePreset"
            class="btn-delete-preset"
            title="刪除此配置"
          >
            🗑️
          </button>
        </div>
        <p class="hint">選擇預設配置可快速套用模型和參數,或保存自己的配置。點擊 ⭐ 設為啟動預設。</p>
      </div>
    </div>

    <!-- 當前配置摘要 -->
    <div class="section current-config-summary">
      <h3>🎯 當前配置</h3>
      <div class="config-grid">
        <div class="config-item">
          <span class="config-label">模型</span>
          <span class="config-value">{{ getModelName(llamaStore.selectedModelPath) }}</span>
        </div>
        <div class="config-item">
          <span class="config-label">伺服器</span>
          <span class="config-value">{{ llamaStore.serverConfig.host }}:{{ llamaStore.serverConfig.port }}</span>
        </div>
        <div class="config-item">
          <span class="config-label">GPU 層數</span>
          <span class="config-value">{{ llamaStore.serverConfig.n_gpu_layers }}</span>
        </div>
        <div class="config-item">
          <span class="config-label">上下文</span>
          <span class="config-value">{{ llamaStore.serverConfig.n_ctx }}</span>
        </div>
        <div class="config-item">
          <span class="config-label">溫度</span>
          <span class="config-value">{{ llamaStore.serverConfig.temp }}</span>
        </div>
        <div class="config-item">
          <span class="config-label">執行緒</span>
          <span class="config-value">{{ llamaStore.serverConfig.n_threads }}</span>
        </div>
        <div class="config-item">
          <span class="config-label">併發數</span>
          <span class="config-value">{{ llamaStore.serverConfig.n_parallel }}</span>
        </div>
      </div>
    </div>

    <!-- 模型選擇 -->
    <div class="section">
      <h3>📁 模型管理</h3>
      
      <div class="form-group">
        <label>模型目錄</label>
        <div class="input-with-btn">
          <input 
            v-model="modelDirectory"
            type="text" 
            placeholder="例如: G:\models"
            class="form-input"
          />
          <button @click="handleLoadModels" :disabled="llamaStore.isLoading" class="btn-primary">
            🔄 掃描模型
          </button>
        </div>
        <p class="hint">輸入包含 .gguf 模型的目錄路徑</p>
      </div>

      <div v-if="llamaStore.hasModels" class="model-list">
        <div class="model-list-header">
          <h4>可用模型 ({{ filteredModels.length }} / {{ llamaStore.models.length }})</h4>
          <div class="model-controls">
            <select v-model="modelSeriesFilter" class="series-filter">
              <option value="">所有系列</option>
              <option v-for="series in modelSeries" :key="series" :value="series">
                {{ series }}
              </option>
            </select>
            <button @click="showSeriesManager = true" class="btn-manage-series" title="管理模型系列">
              ⚙️ 管理系列
            </button>
            <input 
              v-model="modelSearchQuery"
              type="text"
              placeholder="🔍 搜尋模型..."
              class="model-search-input"
            />
          </div>
        </div>
        
        <div class="model-grid">
          <div 
            v-for="model in filteredModels" 
            :key="model.path"
            class="model-card"
            :class="{ selected: llamaStore.selectedModelPath === model.path }"
            @click="llamaStore.selectModel(model.path)"
          >
            <div class="model-card-header">
              <div class="model-icon">🤖</div>
              <div class="model-check" v-if="llamaStore.selectedModelPath === model.path">
                ✓
              </div>
            </div>
            <div class="model-card-body">
              <div class="model-name">{{ getModelDisplayName(model.name) }}</div>
              <div class="model-series">{{ getModelSeries(model.name) }}</div>
              <div class="model-meta">
                <span class="model-size">📦 {{ model.size_mb.toFixed(0) }} MB</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else-if="!llamaStore.isLoading" class="empty-state">
        <p>🔍 尚未掃描模型，請輸入模型目錄並點擊「掃描模型」</p>
      </div>
    </div>

    <!-- 伺服器配置 -->
    <div class="section">
      <h3>⚙️ 伺服器參數</h3>
      
      <div class="form-row">
        <div class="form-group">
          <label>主機</label>
          <input 
            v-model="llamaStore.serverConfig.host"
            type="text"
            class="form-input"
          />
        </div>
        <div class="form-group">
          <label>埠號</label>
          <input 
            v-model.number="llamaStore.serverConfig.port"
            type="number"
            class="form-input"
          />
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>上下文長度 (n_ctx)</label>
          <input 
            v-model.number="llamaStore.serverConfig.n_ctx"
            type="number"
            min="512"
            max="32768"
            step="512"
            class="form-input"
          />
          <p class="hint">建議: 2048 - 4096</p>
        </div>
        <div class="form-group">
          <label>執行緒數 (n_threads)</label>
          <input 
            v-model.number="llamaStore.serverConfig.n_threads"
            type="number"
            min="1"
            max="32"
            class="form-input"
          />
          <p class="hint">根據 CPU 核心數調整</p>
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>GPU 層數 (n_gpu_layers)</label>
          <input 
            v-model.number="llamaStore.serverConfig.n_gpu_layers"
            type="number"
            min="0"
            max="100"
            class="form-input"
          />
          <p class="hint">設為 0 則使用 CPU，設為較大值可使用 GPU 加速</p>
        </div>
        <div class="form-group">
          <label>併發數量 (n_parallel)</label>
          <input 
            v-model.number="llamaStore.serverConfig.n_parallel"
            type="number"
            min="1"
            max="32"
            class="form-input"
          />
          <p class="hint">處理多個併發請求的數量，預設為 1</p>
        </div>
      </div>

      <!-- 進階參數（可摺疊） -->
      <div class="collapsible-section">
        <button @click="showAdvanced = !showAdvanced" class="collapse-toggle" type="button">
          {{ showAdvanced ? '▼' : '▶' }} 進階參數
        </button>
        
        <div v-show="showAdvanced" class="advanced-params">
          <h4>🎛️ 生成參數</h4>
          
          <div class="form-row">
            <div class="form-group">
              <label>溫度 (Temperature)</label>
              <input 
                v-model.number="llamaStore.serverConfig.temp"
                type="number"
                min="0"
                max="2"
                step="0.1"
                class="form-input"
              />
              <p class="hint">控制隨機性：0.1 精準，0.8 創意</p>
            </div>
            <div class="form-group">
              <label>Top-P</label>
              <input 
                v-model.number="llamaStore.serverConfig.top_p"
                type="number"
                min="0"
                max="1"
                step="0.05"
                class="form-input"
              />
              <p class="hint">核心採樣機率閾值</p>
            </div>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>Top-K</label>
              <input 
                v-model.number="llamaStore.serverConfig.top_k"
                type="number"
                min="1"
                max="100"
                class="form-input"
              />
              <p class="hint">候選 token 數量</p>
            </div>
            <div class="form-group">
              <label>重複懲罰</label>
              <input 
                v-model.number="llamaStore.serverConfig.repeat_penalty"
                type="number"
                min="1"
                max="2"
                step="0.05"
                class="form-input"
              />
              <p class="hint">避免重複生成</p>
            </div>
          </div>

          <div class="form-group">
            <label>預測長度 (n_predict)</label>
            <input 
              v-model.number="llamaStore.serverConfig.n_predict"
              type="number"
              min="128"
              max="4096"
              step="128"
              class="form-input"
            />
            <p class="hint">單次生成最大長度</p>
          </div>

          <h4>⚡ 性能優化</h4>
          
          <div class="form-group checkbox-group">
            <label>
              <input 
                v-model="llamaStore.serverConfig.flash_attn"
                type="checkbox"
              />
              <span>啟用 Flash Attention（推薦）</span>
            </label>
            <p class="hint">加速推理，需要支援的硬體</p>
          </div>

          <div class="form-group checkbox-group">
            <label>
              <input 
                v-model="llamaStore.serverConfig.no_mmap"
                type="checkbox"
              />
              <span>禁用 mmap（記憶體直接載入）</span>
            </label>
            <p class="hint">可能提升載入速度但占用更多記憶體</p>
          </div>
        </div>
      </div>
    </div>

    <!-- 啟動按鈕 -->
    <div class="action-buttons">
      <button 
        @click="handleStartServer"
        :disabled="!llamaStore.selectedModelPath || llamaStore.isLoading || llamaStore.isServerRunning"
        class="btn-start"
      >
        <span v-if="llamaStore.isLoading">⏳ 啟動中...</span>
        <span v-else>🚀 啟動 Llama 伺服器</span>
      </button>
      
      <button 
        @click="handleTestTranslation"
        :disabled="!llamaStore.isServerReady || llamaStore.isLoading"
        class="btn-test"
      >
        🧪 測試翻譯
      </button>
    </div>

    <!-- 測試翻譯對話框 -->
    <div v-if="showTestDialog" class="modal-overlay" @click.self="showTestDialog = false">
      <div class="modal-content">
        <h3>測試翻譯</h3>
        <div class="form-group">
          <label>輸入文字</label>
          <textarea 
            v-model="testText"
            class="form-textarea"
            rows="3"
            placeholder="輸入要翻譯的文字..."
          ></textarea>
        </div>
        <div class="form-group">
          <label>翻譯結果</label>
          <textarea 
            v-model="testResult"
            class="form-textarea"
            rows="3"
            readonly
            placeholder="翻譯結果將顯示在這裡..."
          ></textarea>
        </div>
        <div class="modal-actions">
          <button @click="executeTest" :disabled="!testText || llamaStore.isLoading" class="btn-primary">
            {{ llamaStore.isLoading ? '翻譯中...' : '執行翻譯' }}
          </button>
          <button @click="showTestDialog = false" class="btn-secondary">關閉</button>
        </div>
      </div>
    </div>

    <!-- 保存配置對話框 -->
    <div v-if="showSaveDialog" class="modal-overlay" @click.self="showSaveDialog = false">
      <div class="modal-content">
        <h3>💾 保存配置預設</h3>
        <div class="form-group">
          <label>配置名稱</label>
          <input 
            v-model="presetName"
            type="text" 
            class="form-input"
            placeholder="例如: 高效能翻譯模式"
            @keyup.enter="handleSavePreset"
            autofocus
          />
        </div>
        
        <div class="preset-summary">
          <h4>將保存以下配置:</h4>
          <ul>
            <li><strong>模型:</strong> {{ getModelName(llamaStore.selectedModelPath) }}</li>
            <li><strong>主機:</strong> {{ llamaStore.serverConfig.host }}:{{ llamaStore.serverConfig.port }}</li>
            <li><strong>GPU 層數:</strong> {{ llamaStore.serverConfig.n_gpu_layers }}</li>
            <li><strong>上下文:</strong> {{ llamaStore.serverConfig.n_ctx }}</li>
            <li><strong>併發數量:</strong> {{ llamaStore.serverConfig.n_parallel }}</li>
            <li><strong>所有伺服器參數</strong></li>
          </ul>
        </div>
        
        <div class="modal-actions">
          <button @click="handleSavePreset" :disabled="!presetName.trim()" class="btn-primary">
            保存
          </button>
          <button @click="showSaveDialog = false; presetName = ''" class="btn-secondary">取消</button>
        </div>
      </div>
    </div>

    <!-- 系列管理對話框 -->
    <div v-if="showSeriesManager" class="modal-overlay" @click.self="showSeriesManager = false">
      <div class="modal-content series-manager">
        <h3>🏷️ 模型系列管理</h3>
        
        <!-- 系列列表 -->
        <div class="series-list">
          <div v-if="llamaStore.customModelSeries.length === 0" class="empty-state">
            <p>目前沒有任何模型系列設定</p>
          </div>
          <div v-for="(series, index) in llamaStore.customModelSeries" 
               :key="index" 
               class="series-item">
            <div class="series-info">
              <strong>{{ series.name }}</strong>
              <span class="series-patterns">
                關鍵字: {{ series.patterns.join(', ') }}
              </span>
            </div>
            <div class="series-actions">
              <button @click="editSeries(index)" title="編輯">✏️</button>
              <button @click="deleteSeries(index)" title="刪除">🗑️</button>
            </div>
          </div>
        </div>
        
        <!-- 新增按鈕 -->
        <button @click="showAddSeriesDialog = true; showSeriesManager = false" class="btn-add-series">
          ➕ 新增系列
        </button>
        
        <div class="modal-actions">
          <button @click="showSeriesManager = false" class="btn-secondary">關閉</button>
        </div>
      </div>
    </div>

    <!-- 新增/編輯系列對話框 -->
    <div v-if="showAddSeriesDialog" class="modal-overlay" @click.self="cancelEditSeries">
      <div class="modal-content">
        <h3>{{ editingSeriesIndex >= 0 ? '✏️ 編輯' : '➕ 新增' }}模型系列</h3>
        
        <div class="form-group">
          <label>系列名稱</label>
          <input 
            v-model="newSeries.name" 
            type="text"
            class="form-input"
            placeholder="例如: Qwen"
            autofocus
          />
        </div>
        
        <div class="form-group">
          <label>匹配關鍵字 (用逗號分隔)</label>
          <input 
            v-model="newSeriesPatterns" 
            type="text"
            class="form-input"
            placeholder="例如: qwen, qwen2, qwen2.5"
          />
          <p class="hint">模型名稱包含任一關鍵字即會分類到此系列 (不區分大小寫)</p>
        </div>
        
        <div class="modal-actions">
          <button @click="saveSeries" class="btn-primary">
            {{ editingSeriesIndex >= 0 ? '更新' : '新增' }}
          </button>
          <button @click="cancelEditSeries" class="btn-secondary">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue';
import { useLlamaStore } from '../stores/llama';

const llamaStore = useLlamaStore();
const modelDirectory = ref('');
const modelSearchQuery = ref('');
const modelSeriesFilter = ref('');
const showTestDialog = ref(false);
const testText = ref('Hello, how are you today?');
const testResult = ref('');
const showAdvanced = ref(false);
// selectedPreset moved to store
// presets moved to store (systemPresets)
const showSaveDialog = ref(false);
const presetName = ref('');

// 系列管理狀態
const showSeriesManager = ref(false);
const showAddSeriesDialog = ref(false);
const editingSeriesIndex = ref(-1);
const newSeries = ref({ name: '', patterns: [] as string[] });
const newSeriesPatterns = ref('');


// 提取模型系列名稱
function getModelSeries(modelName: string): string {
  const lowerName = modelName.toLowerCase();
  
  // 優先檢查自訂系列
  for (const series of llamaStore.customModelSeries) {
    for (const pattern of series.patterns) {
      if (lowerName.includes(pattern.toLowerCase())) {
        return series.name;
      }
    }
  }
  
  return '其他';
}

// 獲取模型顯示名稱 (簡化版)
function getModelDisplayName(fullName: string): string {
  // 移除 .gguf 副檔名
  let name = fullName.replace(/\.gguf$/i, '');
  // 如果名稱太長,截斷並加上省略號
  if (name.length > 40) {
    name = name.substring(0, 37) + '...';
  }
  return name;
}

// 獲取所有模型系列
const modelSeries = computed(() => {
  const series = new Set<string>();
  llamaStore.models.forEach(model => {
    series.add(getModelSeries(model.name));
  });
  return Array.from(series).sort();
});

// 過濾模型列表
const filteredModels = computed(() => {
  let models = llamaStore.models;
  
  // 按系列過濾
  if (modelSeriesFilter.value) {
    models = models.filter(model => 
      getModelSeries(model.name) === modelSeriesFilter.value
    );
  }
  
  // 按搜尋關鍵字過濾
  if (modelSearchQuery.value.trim()) {
    const query = modelSearchQuery.value.toLowerCase();
    models = models.filter(model => 
      model.name.toLowerCase().includes(query)
    );
  }
  
  return models;
});

onMounted(async () => {
  await llamaStore.initialize();
  // Sync local model directory with store
  if (llamaStore.modelDirectory) {
    modelDirectory.value = llamaStore.modelDirectory;
  }
  // loadPresets removed, using store.systemPresets
});



async function applyPreset() {
  if (!llamaStore.selectedPreset) return;
  
  try {
    // 檢查是否是自訂配置
    if (llamaStore.selectedPreset.startsWith('custom:')) {
      const presetName = llamaStore.selectedPreset.substring(7); // 移除 "custom:" 前綴
      const customPreset = llamaStore.customPresets[presetName];
      if (customPreset) {
        console.log('[LlamaSettings] 套用自訂配置:', presetName);
        console.log('[LlamaSettings] 配置內容:', customPreset);
        console.log('[LlamaSettings] 配置中的 model_path:', customPreset.model_path);
        
        // 先更新模型路徑
        if (customPreset.model_path) {
          console.log('[LlamaSettings] 更新模型路徑:', customPreset.model_path);
          llamaStore.selectedModelPath = customPreset.model_path;
        } else {
          console.warn('[LlamaSettings] 配置中沒有 model_path!');
        }
        
        // 再更新伺服器配置
        Object.assign(llamaStore.serverConfig, customPreset);
        
        llamaStore.successMessage = `已套用自訂配置: ${presetName}`;
        setTimeout(() => llamaStore.successMessage = '', 3000);
        
        console.log('[LlamaSettings] 當前模型路徑:', llamaStore.selectedModelPath);
      }
    } else {
      // 系統預設配置
      const preset = llamaStore.systemPresets[llamaStore.selectedPreset];
      if (preset) {
        console.log('[LlamaSettings] 套用系統配置:', llamaStore.selectedPreset, preset);
        
        // 先更新模型路徑
        if (preset.model_path) {
          console.log('[LlamaSettings] 更新模型路徑:', preset.model_path);
          llamaStore.selectedModelPath = preset.model_path;
        }
        
        // 再更新伺服器配置
        Object.assign(llamaStore.serverConfig, preset);
        
        llamaStore.successMessage = `已套用預設配置: ${llamaStore.selectedPreset}`;
        setTimeout(() => llamaStore.successMessage = '', 3000);
        
        console.log('[LlamaSettings] 當前模型路徑:', llamaStore.selectedModelPath);
      }
    }
  } catch (error) {
    console.error('套用配置失敗:', error);
  }
}

async function handleSavePreset() {
  if (!presetName.value.trim()) return;
  
  const savedName = presetName.value.trim(); // 先保存名稱
  try {
    console.log('[LlamaSettings] 保存配置:', savedName);
    console.log('[LlamaSettings] 當前選擇的模型:', llamaStore.selectedModelPath);
    console.log('[LlamaSettings] 伺服器配置:', llamaStore.serverConfig);
    
    await llamaStore.saveCustomPreset(savedName);
    showSaveDialog.value = false;
    presetName.value = '';
    // 切換到新保存的配置（使用本地已保存的名稱）
    llamaStore.selectedPreset = `custom:${savedName}`;
  } catch (error) {
    console.error('保存配置失敗:', error);
  }
}

function handleSetDefaultPreset() {
  if (!llamaStore.selectedPreset) return;
  llamaStore.setDefaultPreset(llamaStore.selectedPreset);
}

async function handleDeletePreset() {
  if (!llamaStore.selectedPreset.startsWith('custom:')) return;
  
  const presetName = llamaStore.selectedPreset.substring(7);
  if (confirm(`確定要刪除配置「${presetName}」嗎？`)) {
    try {
      await llamaStore.deleteCustomPreset(presetName);
      llamaStore.selectedPreset = '';
    } catch (error) {
      console.error('刪除配置失敗:', error);
    }
  }
}

async function handleLoadModels() {
  await llamaStore.loadModels(modelDirectory.value);
}

async function handleStartServer() {
  try {
    await llamaStore.startServer();
  } catch (error) {
    console.error('啟動失敗:', error);
  }
}

async function handleStopServer() {
  if (confirm('確定要停止 Llama 伺服器嗎？')) {
    try {
      await llamaStore.stopServer();
    } catch (error) {
      console.error('停止失敗:', error);
    }
  }
}

function handleTestTranslation() {
  showTestDialog.value = true;
  testResult.value = '';
}

async function executeTest() {
  try {
    testResult.value = await llamaStore.translate(testText.value);
  } catch (error: any) {
    testResult.value = `錯誤: ${error.message}`;
  }
}

// ==================== 系列管理方法 ====================

function editSeries(index: number) {
  editingSeriesIndex.value = index;
  const series = llamaStore.customModelSeries[index];
  newSeries.value = { name: series.name, patterns: [...series.patterns] };
  newSeriesPatterns.value = series.patterns.join(', ');
  showSeriesManager.value = false;
  showAddSeriesDialog.value = true;
}

function saveSeries() {
  const patterns = newSeriesPatterns.value
    .split(',')
    .map(p => p.trim())
    .filter(p => p);
  
  if (!newSeries.value.name.trim()) {
    alert('請輸入系列名稱');
    return;
  }
  
  if (patterns.length === 0) {
    alert('請至少輸入一個匹配關鍵字');
    return;
  }
  
  const series = {
    name: newSeries.value.name.trim(),
    patterns
  };
  if (editingSeriesIndex.value >= 0) {
    llamaStore.updateModelSeries(editingSeriesIndex.value, series);
  } else {
    llamaStore.addModelSeries(series);
  }
  
  showAddSeriesDialog.value = false;
  showSeriesManager.value = true;
}

function deleteSeries(index: number) {
  if (confirm(`確定要刪除系列 "${llamaStore.customModelSeries[index].name}" 嗎?`)) {
    llamaStore.deleteModelSeries(index);
  }
}

function cancelEditSeries() {
  showAddSeriesDialog.value = false;
  showSeriesManager.value = true; // Make sure to return to the series manager
  editingSeriesIndex.value = -1;
  newSeries.value = { name: '', patterns: [] };
  newSeriesPatterns.value = '';
}

function getModelName(path: string): string {
  if (!path) return '未選擇';
  return path.split(/[\\\/]/).pop() || '未知模型';
}

// 監聽狀態,如果正在運行但未就緒,則輪詢
let pollTimer: number | null = null;

watch(() => [llamaStore.isServerRunning, llamaStore.isServerReady], ([running, ready]) => {
  if (running && !ready) {
    if (!pollTimer) {
      pollTimer = window.setInterval(async () => {
        await llamaStore.refreshServerStatus();
        if (llamaStore.isServerReady) {
          if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
          }
        }
      }, 2000);
    }
  } else {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }
}, { immediate: true });

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer);
  }
});
</script>

<style scoped>
.llama-settings {
  padding: 0;
}

.status-card {
  background: linear-gradient(135deg, rgba(37, 99, 235, 0.2) 0%, rgba(79, 70, 229, 0.2) 100%);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  color: white;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
  backdrop-filter: blur(10px);
}

.status-card.running {
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.2) 0%, rgba(5, 150, 105, 0.2) 100%);
  border-color: rgba(16, 185, 129, 0.3);
}

.status-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  animation: pulse 2s infinite;
}

.status-dot.active {
  background: #4caf50;
  box-shadow: 0 0 8px #4caf50;
  animation: none;
}

.status-dot.starting {
  background: #ff9800;
  box-shadow: 0 0 8px #ff9800;
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.status-text {
  font-weight: 600;
  font-size: 1.1rem;
  color: white;
}

.btn-stop {
  background: rgba(220, 38, 38, 0.2);
  border: 1px solid rgba(220, 38, 38, 0.4);
  color: #fca5a5;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.btn-stop:hover:not(:disabled) {
  background: rgba(220, 38, 38, 0.4);
  color: white;
}

.status-details {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.detail-item .label {
  font-size: 0.85rem;
  opacity: 0.7;
  color: white;
}

.detail-item .value {
  font-weight: 600;
  font-family: monospace;
  color: #93c5fd;
}

.alert {
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1rem;
  backdrop-filter: blur(5px);
}

.alert-error {
  background: rgba(239, 68, 68, 0.2);
  color: #fca5a5;
  border: 1px solid rgba(239, 68, 68, 0.3);
}

.alert-success {
  background: rgba(34, 197, 94, 0.2);
  color: #86efac;
  border: 1px solid rgba(34, 197, 94, 0.3);
}

.section {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.section h3 {
  margin: 0 0 1rem 0;
  color: #60a5fa; /* blue-400 */
  font-size: 1.2rem;
  font-weight: 600;
}

.section h4 {
  margin: 1rem 0 0.5rem 0;
  color: #93c5fd; /* blue-300 */
  font-size: 1rem;
}

/* 配置預設管理區塊 */
.preset-management-section {
  background: linear-gradient(135deg, rgba(168, 85, 247, 0.15) 0%, rgba(139, 92, 246, 0.1) 100%);
  border: 2px solid rgba(168, 85, 247, 0.4);
  box-shadow: 0 4px 12px rgba(168, 85, 247, 0.2);
}

.preset-management-section h3 {
  color: #c084fc;
}

/* 當前配置摘要 */
.current-config-summary {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.15) 0%, rgba(147, 197, 253, 0.1) 100%);
  border: 2px solid rgba(59, 130, 246, 0.3);
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  margin-top: 1rem;
}

.config-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.75rem;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.config-label {
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.6);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.config-value {
  font-size: 1rem;
  font-weight: 600;
  color: #60a5fa;
  font-family: monospace;
  word-break: break-all;
}

/* 保存對話框摘要 */
.preset-summary {
  margin: 1rem 0;
  padding: 1rem;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 8px;
}

.preset-summary h4 {
  margin: 0 0 0.75rem 0;
  color: #93c5fd;
  font-size: 0.9rem;
}

.preset-summary ul {
  margin: 0;
  padding-left: 1.5rem;
  color: rgba(255, 255, 255, 0.8);
}

.preset-summary li {
  margin-bottom: 0.5rem;
  line-height: 1.5;
}

.preset-summary strong {
  color: #60a5fa;
}

.form-group {
  margin-bottom: 1rem;
}

.preset-row {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.preset-select {
  flex: 1;
  min-width: 200px;
}

.btn-set-default {
  padding: 0.5rem 0.75rem;
  background: rgba(251, 191, 36, 0.2);
  color: #fbbf24;
  border: 1px solid rgba(251, 191, 36, 0.4);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 1.2rem;
  line-height: 1;
}

.btn-set-default:hover:not(:disabled) {
  background: rgba(251, 191, 36, 0.3);
  border-color: rgba(251, 191, 36, 0.6);
  transform: scale(1.05);
}

.btn-set-default.is-default {
  background: rgba(251, 191, 36, 0.3);
  border-color: rgba(251, 191, 36, 0.6);
  box-shadow: 0 0 8px rgba(251, 191, 36, 0.4);
}

.btn-set-default:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-save-preset, .btn-delete-preset {
  padding: 0.5rem 1rem;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  cursor: pointer;
  font-size: 1.2rem;
  transition: all 0.2s;
  background: rgba(255, 255, 255, 0.1);
  color: white;
}

.btn-save-preset:hover, .btn-delete-preset:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: translateY(-1px);
}

.form-group label {
  display: block;
  margin-bottom: 0.5rem;
  color: rgba(255, 255, 255, 0.7);
  font-weight: 500;
  font-size: 0.9rem;
}

.form-input, .form-textarea {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  font-size: 0.95rem;
  transition: all 0.3s;
  color: white;
  background-color: rgba(255, 255, 255, 0.05);
}

.form-input:focus, .form-textarea:focus {
  outline: none;
  border-color: #60a5fa;
  background-color: rgba(255, 255, 255, 0.1);
}

.form-input::placeholder {
  color: rgba(255, 255, 255, 0.3);
}

.form-input option, .form-input optgroup {
  background-color: #1e293b;
  color: white;
}

.form-textarea {
  resize: vertical;
  font-family: inherit;
}

.input-with-btn {
  display: flex;
  gap: 0.5rem;
}

.input-with-btn .form-input {
  flex: 1;
}

.hint {
  margin: 0.5rem 0 0 0;
  font-size: 0.8rem;
  color: rgba(255, 255, 255, 0.4);
}

.form-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.model-list {
  margin-top: 1.5rem;
}

.model-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1rem;
  flex-wrap: wrap;
}

.model-list-header h4 {
  margin: 0;
  flex-shrink: 0;
}

.model-controls {
  display: flex;
  gap: 0.5rem;
  flex: 1;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.series-filter {
  padding: 0.5rem 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  font-size: 0.9rem;
  color: white;
  background-color: rgba(255, 255, 255, 0.05);
  transition: all 0.3s;
  min-width: 120px;
}

.series-filter:focus {
  outline: none;
  border-color: #60a5fa;
  background-color: rgba(255, 255, 255, 0.1);
}

.series-filter option {
  background-color: #1e293b;
  color: white;
}

.btn-manage-series {
  padding: 0.5rem 0.75rem;
  background: rgba(168, 85, 247, 0.2);
  border: 1px solid rgba(168, 85, 247, 0.4);
  color: #c084fc;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
  font-weight: 600;
  white-space: nowrap;
}

.btn-manage-series:hover {
  background: rgba(168, 85, 247, 0.3);
  border-color: rgba(168, 85, 247, 0.6);
  transform: translateY(-1px);
}

/* 系列管理對話框 */
.series-manager {
  max-width: 600px;
  max-height: 80vh;
  overflow-y: auto;
}

.series-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1rem;
  max-height: 400px;
  overflow-y: auto;
  padding: 0.5rem;
}

.series-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  transition: all 0.2s;
}

.series-item:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
}

.series-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
}

.series-info strong {
  color: #c084fc;
  font-size: 1rem;
}

.series-patterns {
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.6);
}

.series-actions {
  display: flex;
  gap: 0.5rem;
}

.series-actions button {
  padding: 0.5rem;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 1rem;
}

.series-actions button:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: scale(1.1);
}

.btn-add-series {
  width: 100%;
  padding: 0.75rem;
  background: rgba(59, 130, 246, 0.2);
  border: 1px solid rgba(59, 130, 246, 0.4);
  color: #60a5fa;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.3s;
  margin-bottom: 1rem;
}

.btn-add-series:hover {
  background: rgba(59, 130, 246, 0.3);
  border-color: rgba(59, 130, 246, 0.6);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.model-search-input {
  flex: 1;
  max-width: 250px;
  padding: 0.5rem 0.75rem;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 8px;
  font-size: 0.9rem;
  color: white;
  background-color: rgba(255, 255, 255, 0.05);
  transition: all 0.3s;
}

.model-search-input:focus {
  outline: none;
  border-color: #60a5fa;
  background-color: rgba(255, 255, 255, 0.1);
}

.model-search-input::placeholder {
  color: rgba(255, 255, 255, 0.4);
}

/* 卡片式網格布局 */
.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1rem;
  max-height: 500px;
  overflow-y: auto;
  padding: 0.5rem;
  /* Scrollbar styling */
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.2) transparent;
}

.model-grid::-webkit-scrollbar {
  width: 6px;
}

.model-grid::-webkit-scrollbar-thumb {
  background-color: rgba(255,255,255,0.2);
  border-radius: 3px;
}

.model-card {
  background: rgba(255, 255, 255, 0.05);
  border: 2px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  padding: 1rem;
  cursor: pointer;
  transition: all 0.3s;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  position: relative;
  overflow: hidden;
}

.model-card:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(96, 165, 250, 0.5);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(96, 165, 250, 0.2);
}

.model-card.selected {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(37, 99, 235, 0.15) 100%);
  border-color: #60a5fa;
  box-shadow: 0 0 20px rgba(96, 165, 250, 0.3);
}

.model-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.model-icon {
  font-size: 2rem;
  opacity: 0.8;
}

.model-check {
  width: 24px;
  height: 24px;
  background: #10b981;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: bold;
  font-size: 0.9rem;
  box-shadow: 0 2px 8px rgba(16, 185, 129, 0.4);
}

.model-card-body {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.model-name {
  font-weight: 600;
  color: white;
  font-size: 0.9rem;
  line-height: 1.3;
  word-break: break-word;
}

.model-series {
  display: inline-block;
  padding: 0.25rem 0.5rem;
  background: rgba(96, 165, 250, 0.2);
  border: 1px solid rgba(96, 165, 250, 0.3);
  border-radius: 4px;
  color: #93c5fd;
  font-size: 0.75rem;
  font-weight: 500;
  width: fit-content;
}

.model-meta {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.model-size {
  font-size: 0.8rem;
  color: rgba(255, 255, 255, 0.6);
  font-family: monospace;
}

/* 移除舊的 model-items 樣式 */
.model-items {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  max-height: 300px;
  overflow-y: auto;
  padding-right: 0.5rem;
  /* Scrollbar styling */
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,0.2) transparent;
}

.model-items::-webkit-scrollbar {
  width: 6px;
}
.model-items::-webkit-scrollbar-thumb {
  background-color: rgba(255,255,255,0.2);
  border-radius: 3px;
}

.model-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.model-item:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
}

.model-item.selected {
  background: rgba(37, 99, 235, 0.2); /* blue-600/20 */
  border-color: #60a5fa;
}

.model-info {
  flex: 1;
}

.model-name {
  font-weight: 600;
  color: white;
  margin-bottom: 0.25rem;
}

.model-meta {
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.6);
}

.model-check {
  color: #60a5fa;
  font-size: 1.5rem;
  font-weight: bold;
}

.empty-state {
  text-align: center;
  padding: 2rem;
  color: rgba(255, 255, 255, 0.4);
  background: rgba(255, 255, 255, 0.02);
  border-radius: 8px;
  border: 1px dashed rgba(255, 255, 255, 0.1);
}

.collapsible-section {
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  padding-top: 1rem;
  margin-top: 1rem;
}

.collapse-toggle {
  background: none;
  border: none;
  color: #60a5fa;
  font-weight: 600;
  cursor: pointer;
  padding: 0;
  font-size: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.collapse-toggle:hover {
  color: #93c5fd;
}

.advanced-params {
  margin-top: 1rem;
  padding-left: 0.5rem;
}

.checkbox-group label {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  cursor: pointer;
  color: white;
  font-weight: normal;
}

.checkbox-group input[type="checkbox"] {
  width: 1.2rem;
  height: 1.2rem;
  accent-color: #3b82f6;
}

.action-buttons {
  display: flex;
  gap: 1rem;
  margin-top: 2rem;
  flex-wrap: wrap;
}

.btn-primary, .btn-start, .btn-test {
  flex: 1;
  min-width: 200px;
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  font-size: 1rem;
  cursor: pointer;
  transition: all 0.3s;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.btn-primary {
  background: #3b82f6;
  flex: initial;
  min-width: auto;
}
.btn-primary:hover:not(:disabled) {
  background: #2563eb;
}

.btn-start {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
}
.btn-start:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(16, 185, 129, 0.4);
}

.btn-test {
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}
.btn-test:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4);
}

.btn-start:disabled, .btn-test:disabled, .btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
  background: #475569;
}

.btn-secondary {
  padding: 0.75rem 1.5rem;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: white;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  font-weight: 600;
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.15);
}

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  backdrop-filter: blur(5px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 1rem;
}

.modal-content {
  background: #1e293b;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 16px;
  padding: 2rem;
  width: 100%;
  max-width: 500px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5);
}

.modal-content h3 {
  margin: 0 0 1.5rem 0;
  color: white;
  font-size: 1.5rem;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  margin-top: 1.5rem;
}
</style>
