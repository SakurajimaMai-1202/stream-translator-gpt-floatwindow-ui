<template>
  <div class="llama-settings">
    <div class="status-card" :class="{ running: llamaStore.isServerRunning }">
      <div class="status-header">
        <div class="status-indicator">
          <span
            class="status-dot"
            :class="{
              active: llamaStore.isServerReady,
              starting: llamaStore.isServerRunning && !llamaStore.isServerReady
            }"
          ></span>
          <div>
            <div class="status-text">
              {{
                llamaStore.isServerReady
                  ? '伺服器已就緒'
                  : llamaStore.isServerRunning
                    ? '伺服器啟動中...'
                    : '伺服器已停止'
              }}
            </div>
            <p class="status-subtext">
              {{ llamaStore.isServerRunning ? '目前可直接測試翻譯與切換模型觀察效果。' : '先挑模型、調參數，再一鍵啟動本地翻譯服務。' }}
            </p>
          </div>
        </div>
        <div class="status-actions">
          <span class="status-pill" :class="llamaStore.isServerReady ? 'ready' : llamaStore.isServerRunning ? 'booting' : 'idle'">
            {{ llamaStore.isServerReady ? 'Ready' : llamaStore.isServerRunning ? 'Booting' : 'Offline' }}
          </span>
          <button
            v-if="!llamaStore.isServerRunning"
            type="button"
            @click="handleStartServer"
            :disabled="!llamaStore.selectedModelPath || llamaStore.isLoading"
            class="btn-start-quick"
            :title="!llamaStore.selectedModelPath ? '請先在「模型管理」選擇一個模型' : ''"
          >
            <span v-if="llamaStore.isLoading">⏳ 啟動中...</span>
            <span v-else>🚀 啟動伺服器</span>
          </button>
          <button
            v-if="llamaStore.isServerRunning"
            type="button"
            @click="handleStopServer"
            :disabled="llamaStore.isLoading"
            class="btn-stop"
          >
            🛑 停止伺服器
          </button>
        </div>
      </div>

      <div v-if="!llamaStore.isServerRunning" class="status-target">
        <span class="target-label">目標位址</span>
        <span class="target-value">{{ llamaStore.serverConfig.host }}:{{ llamaStore.serverConfig.port }}</span>
        <span v-if="!llamaStore.selectedModelPath" class="target-warn">⚠ 尚未選擇模型</span>
        <span v-else class="target-model">{{ getModelName(llamaStore.selectedModelPath) }}</span>
      </div>

      <div v-if="llamaStore.isServerRunning" class="status-details">
        <div class="detail-item">
          <span class="label">執行中模型</span>
          <span class="value">{{ llamaStore.currentModel || getModelName(llamaStore.selectedModelPath) }}</span>
        </div>
        <div class="detail-item">
          <span class="label">服務位址</span>
          <span class="value">{{ llamaStore.serverStatus.server_url || `${llamaStore.serverConfig.host}:${llamaStore.serverConfig.port}` }}</span>
        </div>
        <div class="detail-item">
          <span class="label">程序 PID</span>
          <span class="value">{{ llamaStore.serverStatus.pid || 'N/A' }}</span>
        </div>
      </div>
    </div>

    <div v-if="llamaStore.errorMessage" class="alert alert-error">❌ {{ llamaStore.errorMessage }}</div>
    <div v-if="llamaStore.successMessage" class="alert alert-success">✅ {{ llamaStore.successMessage }}</div>

    <div class="workspace-grid">
      <section class="panel panel-emphasis">
        <div class="panel-header">
          <div>
            <h3>⚡ 配置工作區</h3>
            <p class="panel-subtitle">把「切換預設 → 微調參數 → 保存自己的版本」。</p>
          </div>
          <span class="sync-badge" :class="presetSyncTone">
            {{ presetSyncText }}
          </span>
        </div>

        <div class="preset-selector-block">
          <label>快速切換配置</label>
          <UiSelect
            v-model="llamaStore.selectedPreset"
            :options="presetOptions"
            placeholder="選擇系統預設或自己的配置"
          />
          <p class="hint">切換後會立即套用到目前編輯中的 Llama 參數，並自動保存到設定檔。</p>
        </div>

        <div class="preset-actions-grid">
          <button
            type="button"
            @click="handleSetDefaultPreset"
            :disabled="!llamaStore.selectedPreset"
            class="action-tile"
            :class="{ active: llamaStore.selectedPreset && llamaStore.selectedPreset === llamaStore.defaultPreset }"
          >
            <span class="action-icon">{{ llamaStore.selectedPreset === llamaStore.defaultPreset ? '⭐' : '☆' }}</span>
            <span>
              <strong>{{ llamaStore.selectedPreset === llamaStore.defaultPreset ? '已設為啟動預設' : '設為啟動預設' }}</strong>
              <small>開啟程式時自動套用這組配置</small>
            </span>
          </button>

          <button type="button" @click="openSaveDialog" class="action-tile primary">
            <span class="action-icon">💾</span>
            <span>
              <strong>保存目前配置</strong>
              <small>{{ isOverwritingPreset ? '將覆蓋同名自訂配置' : '把現在的模型與參數收成你的預設' }}</small>
            </span>
          </button>

          <button
            v-if="llamaStore.selectedPreset.startsWith('custom:')"
            type="button"
            @click="handleDeletePreset"
            class="action-tile danger"
          >
            <span class="action-icon">🗑️</span>
            <span>
              <strong>刪除此自訂配置</strong>
              <small>只會移除你保存的配置，不影響目前頁面內容</small>
            </span>
          </button>
        </div>

        <div class="meta-grid">
          <div class="meta-card">
            <span class="meta-label">目前來源</span>
            <strong>{{ selectedPresetLabel }}</strong>
            <small>{{ selectedPresetSourceText }}</small>
          </div>
          <div class="meta-card">
            <span class="meta-label">啟動預設</span>
            <strong>{{ defaultPresetLabel }}</strong>
            <small>程式啟動後自動載入</small>
          </div>
          <div class="meta-card">
            <span class="meta-label">我的配置</span>
            <strong>{{ customPresetCount }}</strong>
            <small>已保存的自訂組合</small>
          </div>
          <div class="meta-card">
            <span class="meta-label">系統預設</span>
            <strong>{{ systemPresetCount }}</strong>
            <small>內建建議配置</small>
          </div>
        </div>

        <div class="preset-library">
          <div class="library-group">
            <div class="library-title">系統預設</div>
            <div class="pill-row">
              <button
                v-for="name in systemPresetNames"
                :key="`system-${name}`"
                type="button"
                class="pill-button"
                :class="{ active: llamaStore.selectedPreset === name }"
                @click="llamaStore.selectedPreset = name"
              >
                {{ name }}
              </button>
            </div>
          </div>

          <div class="library-group" v-if="customPresetNames.length">
            <div class="library-title">我的配置</div>
            <div class="pill-row">
              <button
                v-for="name in customPresetNames"
                :key="`custom-${name}`"
                type="button"
                class="pill-button custom"
                :class="{ active: llamaStore.selectedPreset === `custom:${name}` }"
                @click="llamaStore.selectedPreset = `custom:${name}`"
              >
                📦 {{ name }}
              </button>
            </div>
          </div>
        </div>
      </section>

      <section class="panel current-config-panel">
        <div class="panel-header">
          <div>
            <h3>🎯 當前配置總覽</h3>
            <p class="panel-subtitle">使用者最常看的資訊先放前面：現在是哪個模型、參數偏哪種風格、是否與預設同步。</p>
          </div>
        </div>

        <div class="hero-config-card">
          <div>
            <span class="hero-label">當前模型</span>
            <div class="hero-title">{{ getModelName(llamaStore.selectedModelPath) }}</div>
            <p class="hero-subtitle">
              {{ activeModelInfo ? `${getModelSeries(activeModelInfo.name)} · ${activeModelInfo.size_mb.toFixed(0)} MB` : '尚未從已掃描清單中選定模型' }}
            </p>
          </div>
          <div class="hero-tags">
            <span class="hero-tag">{{ llamaStore.serverConfig.host }}:{{ llamaStore.serverConfig.port }}</span>
            <span class="hero-tag">GPU {{ llamaStore.serverConfig.n_gpu_layers }}</span>
            <span class="hero-tag">Ctx {{ llamaStore.serverConfig.n_ctx }}</span>
          </div>
        </div>

        <div class="summary-grid">
          <div v-for="item in currentConfigItems" :key="item.label" class="summary-card">
            <span class="summary-label">{{ item.label }}</span>
            <strong class="summary-value">{{ item.value }}</strong>
            <small class="summary-help">{{ item.help }}</small>
          </div>
        </div>

        <div class="info-strip">
          <div>
            <strong>配置狀態：</strong>
            {{ presetSyncText }}
          </div>
          <div>
            <strong>自動保存：</strong>
            參數變更約 1 秒後會同步到設定檔
          </div>
        </div>
      </section>
    </div>

    <section class="panel">
      <div class="panel-header">
        <div>
          <h3>📁 模型管理</h3>
          <p class="panel-subtitle">先掃描模型，再用搜尋 / 系列 / 卡片選取快速鎖定要啟動的 GGUF 模型。</p>
        </div>
      </div>

      <div class="form-group">
        <label>模型目錄</label>
        <div class="input-with-btn">
          <input
            v-model="modelDirectory"
            type="text"
            placeholder="例如: G:\models"
            class="form-input"
          />
          <button type="button" @click="handleLoadModels" :disabled="llamaStore.isLoading" class="btn-primary compact">
            🔄 掃描模型
          </button>
        </div>
        <p class="hint">輸入包含 `.gguf` 模型的目錄路徑。掃描成功後會保留在設定裡，下次不用再找一次。</p>
      </div>

      <div v-if="llamaStore.selectedModelPath" class="selected-model-banner">
        <div>
          <span class="meta-label">已選擇模型</span>
          <strong>{{ getModelName(llamaStore.selectedModelPath) }}</strong>
          <small>{{ llamaStore.selectedModelPath }}</small>
        </div>
        <span class="sync-badge ok">準備可啟動</span>
      </div>

      <div v-if="llamaStore.hasModels" class="model-list">
        <div class="model-list-header">
          <h4>可用模型 ({{ filteredModels.length }} / {{ llamaStore.models.length }})</h4>
          <div class="model-controls">
            <div class="control-block">
              <label class="control-label">模型系列</label>
              <UiSelect v-model="modelSeriesFilter" :options="modelSeriesOptions" placeholder="所有系列" />
            </div>
            <button type="button" @click="showSeriesManager = true" class="btn-manage-series" title="管理模型系列">
              ⚙️ 管理系列
            </button>
            <div class="control-block grow">
              <label class="control-label">搜尋模型</label>
              <input
                v-model="modelSearchQuery"
                type="text"
                placeholder="🔍 輸入模型名稱關鍵字..."
                class="form-input"
              />
            </div>
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
              <div class="model-check" v-if="llamaStore.selectedModelPath === model.path">✓</div>
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
    </section>

    <section class="panel">
      <div class="panel-header">
        <div>
          <h3>⚙️ 參數編輯器</h3>
          <p class="panel-subtitle">常用設定先排前面，搭配快捷建議值，改參數不用像在解鎖 BIOS。</p>
        </div>
        <div class="panel-header-actions">
          <button type="button" class="ghost-button" @click="resetServerTuning">↺ 重設參數</button>
        </div>
      </div>

      <div class="quick-profile-row">
        <button
          v-for="profile in quickProfiles"
          :key="profile.id"
          type="button"
          class="profile-chip"
          @click="applyQuickProfile(profile.id)"
        >
          <span>{{ profile.icon }}</span>
          <span>{{ profile.label }}</span>
        </button>
      </div>

      <div class="parameter-grid">
        <div class="param-card">
          <div class="param-card-header">
            <h4>🧭 基本連線與上下文</h4>
            <p>控制伺服器位址、上下文長度與 CPU 執行緒數。</p>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>主機</label>
              <input v-model="llamaStore.serverConfig.host" type="text" class="form-input" />
            </div>
            <div class="form-group">
              <label>埠號</label>
              <input v-model.number="llamaStore.serverConfig.port" type="number" class="form-input" />
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
              <div class="suggestion-row">
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_ctx', 2048)">2048</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_ctx', 4096)">4096</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_ctx', 8192)">8192</button>
              </div>
              <p class="hint">一般翻譯建議 2048–4096；內容較長可拉高。</p>
            </div>

            <div class="form-group">
              <label>執行緒數 (n_threads)</label>
              <input
                v-model.number="llamaStore.serverConfig.n_threads"
                type="number"
                min="1"
                max="64"
                class="form-input"
              />
              <div class="suggestion-row">
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_threads', 4)">4</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_threads', 8)">8</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_threads', 12)">12</button>
              </div>
              <p class="hint">依 CPU 核心數調整，通常設為實體核心數附近即可。</p>
            </div>
          </div>
        </div>

        <div class="param-card">
          <div class="param-card-header">
            <h4>⚡ 加速與吞吐量</h4>
            <p>決定 GPU 使用程度、單次可處理併發量，以及記憶體載入策略。</p>
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
              <div class="suggestion-row">
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_gpu_layers', 0)">CPU</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_gpu_layers', 33)">33</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_gpu_layers', 99)">99</button>
              </div>
              <p class="hint">0 表示純 CPU；可用 GPU 時通常越高越快，但也越吃顯存。</p>
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
              <div class="suggestion-row">
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_parallel', 1)">1</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_parallel', 2)">2</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_parallel', 4)">4</button>
              </div>
              <p class="hint">只做單一路翻譯可維持 1，多工時再慢慢加。</p>
            </div>
          </div>

          <div class="toggle-stack">
            <label class="toggle-card">
              <input v-model="llamaStore.serverConfig.flash_attn" type="checkbox" />
              <div>
                <strong>啟用 Flash Attention</strong>
                <small>推薦優先開啟，有支援的硬體通常可獲得更好的推理速度。</small>
              </div>
            </label>
            <label class="toggle-card">
              <input v-model="llamaStore.serverConfig.no_mmap" type="checkbox" />
              <div>
                <strong>禁用 mmap</strong>
                <small>某些環境能改善載入穩定性，但會使用更多記憶體。</small>
              </div>
            </label>
          </div>
        </div>

        <div class="param-card full-width">
          <div class="param-card-header">
            <h4>🎛️ 生成參數</h4>
            <p>控制翻譯時的穩定度、採樣範圍與單次輸出長度。</p>
          </div>

          <div class="form-row three-columns">
            <div class="form-group">
              <label>溫度 (temp)</label>
              <input
                v-model.number="llamaStore.serverConfig.temp"
                type="number"
                min="0"
                max="2"
                step="0.1"
                class="form-input"
              />
              <div class="suggestion-row">
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('temp', 0.2)">精準</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('temp', 0.5)">平衡</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('temp', 0.8)">靈活</button>
              </div>
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
              <p class="hint">控制採樣覆蓋率，越低越保守。</p>
            </div>

            <div class="form-group">
              <label>Top-K</label>
              <input
                v-model.number="llamaStore.serverConfig.top_k"
                type="number"
                min="1"
                max="100"
                class="form-input"
              />
              <p class="hint">候選 token 數量，較小通常更穩定。</p>
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
              <p class="hint">避免模型陷入「重複自己」模式。</p>
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
              <div class="suggestion-row">
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_predict', 256)">256</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_predict', 512)">512</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_predict', 1024)">1024</button>
              </div>
            </div>

            <div class="form-group parameter-note">
              <div class="note-card">
                <strong>小建議</strong>
                <ul>
                  <li>翻譯想穩：溫度 0.2–0.5</li>
                  <li>字幕想快：上下文 2048、預測 256–512</li>
                  <li>長文本想完整：上下文 4096+、預測 1024</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <div class="action-buttons">
      <button
        type="button"
        @click="handleTestTranslation"
        :disabled="!llamaStore.isServerReady || llamaStore.isLoading"
        class="btn-test full-width"
      >
        🧪 測試翻譯
      </button>
    </div>

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
            rows="4"
            readonly
            placeholder="翻譯結果將顯示在這裡..."
          ></textarea>
        </div>
        <div class="modal-actions">
          <button type="button" @click="executeTest" :disabled="!testText || llamaStore.isLoading" class="btn-primary compact">
            {{ llamaStore.isLoading ? '翻譯中...' : '執行翻譯' }}
          </button>
          <button type="button" @click="showTestDialog = false" class="btn-secondary">關閉</button>
        </div>
      </div>
    </div>

    <div v-if="showSaveDialog" class="modal-overlay" @click.self="showSaveDialog = false">
      <div class="modal-content">
        <h3>💾 保存配置預設</h3>
        <p class="modal-description">把目前模型、伺服器參數與生成參數一起保存。下次可直接一鍵套用。</p>

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
          <p class="hint">{{ isOverwritingPreset ? '這個名稱已存在，保存後會直接覆蓋。' : '建議用用途或模型命名，未來比較好找。' }}</p>
        </div>

        <div class="preset-summary-card">
          <h4>這次會保存</h4>
          <div class="summary-grid compact-grid">
            <div v-for="item in savePresetSummaryItems" :key="item.label" class="summary-card compact">
              <span class="summary-label">{{ item.label }}</span>
              <strong class="summary-value">{{ item.value }}</strong>
            </div>
          </div>
        </div>

        <div class="modal-actions">
          <button type="button" @click="handleSavePreset" :disabled="!presetName.trim()" class="btn-primary compact">
            {{ isOverwritingPreset ? '覆蓋保存' : '保存' }}
          </button>
          <button type="button" @click="closeSaveDialog" class="btn-secondary">取消</button>
        </div>
      </div>
    </div>

    <div v-if="showSeriesManager" class="modal-overlay" @click.self="showSeriesManager = false">
      <div class="modal-content series-manager">
        <h3>🏷️ 模型系列管理</h3>

        <div class="series-list">
          <div v-if="llamaStore.customModelSeries.length === 0" class="empty-state">
            <p>目前沒有任何模型系列設定</p>
          </div>
          <div v-for="(series, index) in llamaStore.customModelSeries" :key="index" class="series-item">
            <div class="series-info">
              <strong>{{ series.name }}</strong>
              <span class="series-patterns">關鍵字: {{ series.patterns.join(', ') }}</span>
            </div>
            <div class="series-actions">
              <button type="button" @click="editSeries(index)" title="編輯">✏️</button>
              <button type="button" @click="deleteSeries(index)" title="刪除">🗑️</button>
            </div>
          </div>
        </div>

        <button type="button" @click="showAddSeriesDialog = true; showSeriesManager = false" class="btn-add-series">
          ➕ 新增系列
        </button>

        <div class="modal-actions">
          <button type="button" @click="showSeriesManager = false" class="btn-secondary">關閉</button>
        </div>
      </div>
    </div>

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
          <button type="button" @click="saveSeries" class="btn-primary compact">
            {{ editingSeriesIndex >= 0 ? '更新' : '新增' }}
          </button>
          <button type="button" @click="cancelEditSeries" class="btn-secondary">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import UiSelect, { type UiSelectOption } from './UiSelect.vue';
import { useLlamaStore } from '../stores/llama';
import type { ServerConfig } from '../services/llamaApi';

const DEFAULT_TUNING: Required<Pick<ServerConfig, 'n_ctx' | 'n_gpu_layers' | 'n_threads' | 'n_parallel' | 'top_k' | 'top_p' | 'temp' | 'repeat_penalty' | 'n_predict' | 'flash_attn' | 'no_mmap'>> = {
  n_ctx: 2048,
  n_gpu_layers: 0,
  n_threads: 4,
  n_parallel: 1,
  top_k: 40,
  top_p: 0.95,
  temp: 0.8,
  repeat_penalty: 1.1,
  n_predict: 512,
  flash_attn: true,
  no_mmap: false
};

const quickProfiles = [
  {
    id: 'low-latency',
    icon: '⚡',
    label: '低延遲',
    config: { n_ctx: 2048, n_parallel: 1, temp: 0.25, top_p: 0.9, top_k: 20, n_predict: 256 }
  },
  {
    id: 'balanced',
    icon: '⚖️',
    label: '平衡',
    config: { n_ctx: 4096, n_parallel: 1, temp: 0.45, top_p: 0.92, top_k: 40, n_predict: 512 }
  },
  {
    id: 'quality',
    icon: '🎯',
    label: '高品質',
    config: { n_ctx: 8192, n_parallel: 1, temp: 0.65, top_p: 0.95, top_k: 60, n_predict: 1024 }
  }
] as const;

const llamaStore = useLlamaStore();
const modelDirectory = ref('');
const modelSearchQuery = ref('');
const modelSeriesFilter = ref<string | number | null>('');
const showTestDialog = ref(false);
const testText = ref('Hello, how are you today?');
const testResult = ref('');
const showSaveDialog = ref(false);
const presetName = ref('');

const showSeriesManager = ref(false);
const showAddSeriesDialog = ref(false);
const editingSeriesIndex = ref(-1);
const newSeries = ref({ name: '', patterns: [] as string[] });
const newSeriesPatterns = ref('');

function getModelSeries(modelName: string): string {
  const lowerName = modelName.toLowerCase();

  for (const series of llamaStore.customModelSeries) {
    for (const pattern of series.patterns) {
      if (lowerName.includes(pattern.toLowerCase())) {
        return series.name;
      }
    }
  }

  return '其他';
}

function getModelDisplayName(fullName: string): string {
  let name = fullName.replace(/\.gguf$/i, '');
  if (name.length > 40) {
    name = `${name.substring(0, 37)}...`;
  }
  return name;
}

function getModelName(path: string): string {
  if (!path) return '未選擇';
  return path.split(/[\\/]/).pop() || '未知模型';
}

function getPresetConfig(presetKey: string): Partial<ServerConfig> | undefined {
  if (!presetKey) return undefined;
  if (presetKey.startsWith('custom:')) {
    return llamaStore.customPresets[presetKey.substring(7)];
  }
  return llamaStore.systemPresets[presetKey];
}

function isConfigMatch(preset: Partial<ServerConfig>): boolean {
  const keysToCompare: (keyof ServerConfig)[] = [
    'model_path',
    'host',
    'port',
    'n_ctx',
    'n_gpu_layers',
    'n_threads',
    'n_parallel',
    'temp',
    'top_p',
    'top_k',
    'repeat_penalty',
    'n_predict',
    'flash_attn',
    'no_mmap'
  ];

  return keysToCompare.every((key) => {
    const presetValue = preset[key];
    const currentValue = key === 'model_path' ? llamaStore.selectedModelPath : llamaStore.serverConfig[key];
    return presetValue === undefined || presetValue === currentValue;
  });
}

const systemPresetNames = computed(() => Object.keys(llamaStore.systemPresets));
const customPresetNames = computed(() => Object.keys(llamaStore.customPresets));
const systemPresetCount = computed(() => systemPresetNames.value.length);
const customPresetCount = computed(() => customPresetNames.value.length);

const presetOptions = computed<UiSelectOption[]>(() => [
  { value: '', label: '自訂配置（目前手動調整）' },
  ...systemPresetNames.value.map((name) => ({ value: name, label: name, group: '系統預設' })),
  ...customPresetNames.value.map((name) => ({ value: `custom:${name}`, label: `📦 ${name}`, group: '我的配置' }))
]);

const modelSeries = computed(() => {
  const series = new Set<string>();
  llamaStore.models.forEach((model) => series.add(getModelSeries(model.name)));
  return Array.from(series).sort();
});

const modelSeriesOptions = computed<UiSelectOption[]>(() => [
  { value: '', label: '所有系列' },
  ...modelSeries.value.map((series) => ({ value: series, label: series }))
]);

const filteredModels = computed(() => {
  let models = llamaStore.models;

  if (modelSeriesFilter.value) {
    models = models.filter((model) => getModelSeries(model.name) === modelSeriesFilter.value);
  }

  if (modelSearchQuery.value.trim()) {
    const query = modelSearchQuery.value.toLowerCase();
    models = models.filter((model) => model.name.toLowerCase().includes(query));
  }

  return models;
});

const selectedPresetLabel = computed(() => {
  if (!llamaStore.selectedPreset) return '手動調整中';
  return llamaStore.selectedPreset.startsWith('custom:')
    ? llamaStore.selectedPreset.substring(7)
    : llamaStore.selectedPreset;
});

const selectedPresetSourceText = computed(() => {
  if (!llamaStore.selectedPreset) return '目前沒有綁定到任何預設';
  return llamaStore.selectedPreset.startsWith('custom:') ? '使用自訂配置' : '使用系統預設';
});

const defaultPresetLabel = computed(() => {
  if (!llamaStore.defaultPreset) return '未設定';
  return llamaStore.defaultPreset.startsWith('custom:')
    ? llamaStore.defaultPreset.substring(7)
    : llamaStore.defaultPreset;
});

const currentPresetConfig = computed(() => getPresetConfig(llamaStore.selectedPreset));
const isSelectedPresetSynced = computed(() => {
  if (!currentPresetConfig.value) return false;
  return isConfigMatch(currentPresetConfig.value);
});

const presetSyncTone = computed(() => {
  if (!llamaStore.selectedPreset) return 'idle';
  return isSelectedPresetSynced.value ? 'ok' : 'warn';
});

const presetSyncText = computed(() => {
  if (!llamaStore.selectedPreset) return '目前是手動調整配置';
  return isSelectedPresetSynced.value ? '與所選預設完全同步' : '已偏離所選預設，建議另存新版本';
});

const activeModelInfo = computed(() => llamaStore.models.find((model) => model.path === llamaStore.selectedModelPath));

const currentConfigItems = computed(() => [
  {
    label: '預設來源',
    value: selectedPresetLabel.value,
    help: selectedPresetSourceText.value
  },
  {
    label: '推理風格',
    value: `T=${llamaStore.serverConfig.temp} · P=${llamaStore.serverConfig.top_p} · K=${llamaStore.serverConfig.top_k}`,
    help: '越低越穩、越高越靈活'
  },
  {
    label: '輸出長度',
    value: `${llamaStore.serverConfig.n_predict} tokens`,
    help: '單次生成上限'
  },
  {
    label: 'CPU / GPU',
    value: `${llamaStore.serverConfig.n_threads} 執行緒 / ${llamaStore.serverConfig.n_gpu_layers} GPU 層`,
    help: '決定推理速度與資源占用'
  },
  {
    label: '吞吐量',
    value: `${llamaStore.serverConfig.n_parallel} 路併發`,
    help: '多任務時才需要拉高'
  },
  {
    label: '效能模式',
    value: llamaStore.serverConfig.flash_attn ? 'Flash Attention 開啟' : '標準注意力模式',
    help: llamaStore.serverConfig.no_mmap ? '已禁用 mmap' : '使用 mmap 載入模型'
  }
]);

const savePresetSummaryItems = computed(() => [
  { label: '模型', value: getModelName(llamaStore.selectedModelPath) },
  { label: '服務位址', value: `${llamaStore.serverConfig.host}:${llamaStore.serverConfig.port}` },
  { label: '上下文', value: String(llamaStore.serverConfig.n_ctx) },
  { label: 'GPU 層數', value: String(llamaStore.serverConfig.n_gpu_layers) },
  { label: '併發', value: String(llamaStore.serverConfig.n_parallel) },
  { label: '採樣', value: `T=${llamaStore.serverConfig.temp} / P=${llamaStore.serverConfig.top_p}` }
]);

const isOverwritingPreset = computed(() => {
  const name = presetName.value.trim();
  return !!name && !!llamaStore.customPresets[name];
});

function setServerConfigValue<K extends keyof ServerConfig>(key: K, value: NonNullable<ServerConfig[K]>) {
  (llamaStore.serverConfig[key] as ServerConfig[K]) = value as ServerConfig[K];
}

function applyQuickProfile(profileId: string) {
  const profile = quickProfiles.find((item) => item.id === profileId);
  if (!profile) return;
  Object.assign(llamaStore.serverConfig, profile.config);
  llamaStore.successMessage = `已套用快速配置：${profile.label}`;
  window.setTimeout(() => {
    if (llamaStore.successMessage === `已套用快速配置：${profile.label}`) {
      llamaStore.successMessage = '';
    }
  }, 2500);
}

function resetServerTuning() {
  if (!confirm('確定要把 Llama 參數重設回建議預設值嗎？')) return;
  Object.assign(llamaStore.serverConfig, {
    ...DEFAULT_TUNING,
    host: llamaStore.serverConfig.host || '127.0.0.1',
    port: llamaStore.serverConfig.port || 8080,
    model_path: llamaStore.selectedModelPath
  });
  llamaStore.successMessage = '已重設 Llama 參數';
  window.setTimeout(() => {
    if (llamaStore.successMessage === '已重設 Llama 參數') {
      llamaStore.successMessage = '';
    }
  }, 2500);
}

function buildSuggestedPresetName() {
  if (llamaStore.selectedPreset.startsWith('custom:')) {
    return llamaStore.selectedPreset.substring(7);
  }

  const modelName = getModelName(llamaStore.selectedModelPath).replace(/\.gguf$/i, '');
  return modelName && modelName !== '未選擇' ? `${modelName}-自訂` : '新的 Llama 配置';
}

function openSaveDialog() {
  presetName.value = buildSuggestedPresetName();
  showSaveDialog.value = true;
}

function closeSaveDialog() {
  showSaveDialog.value = false;
  presetName.value = '';
}

async function handleSavePreset() {
  if (!presetName.value.trim()) return;

  const savedName = presetName.value.trim();
  try {
    await llamaStore.saveCustomPreset(savedName);
    closeSaveDialog();
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

  const currentPresetName = llamaStore.selectedPreset.substring(7);
  if (!confirm(`確定要刪除配置「${currentPresetName}」嗎？`)) return;

  try {
    await llamaStore.deleteCustomPreset(currentPresetName);
    llamaStore.selectedPreset = '';
  } catch (error) {
    console.error('刪除配置失敗:', error);
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
  if (!confirm('確定要停止 Llama 伺服器嗎？')) return;

  try {
    await llamaStore.stopServer();
  } catch (error) {
    console.error('停止失敗:', error);
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
    .map((pattern) => pattern.trim())
    .filter(Boolean);

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
  editingSeriesIndex.value = -1;
  newSeries.value = { name: '', patterns: [] };
  newSeriesPatterns.value = '';
}

function deleteSeries(index: number) {
  if (confirm(`確定要刪除系列 "${llamaStore.customModelSeries[index].name}" 嗎?`)) {
    llamaStore.deleteModelSeries(index);
  }
}

function cancelEditSeries() {
  showAddSeriesDialog.value = false;
  showSeriesManager.value = true;
  editingSeriesIndex.value = -1;
  newSeries.value = { name: '', patterns: [] };
  newSeriesPatterns.value = '';
}

onMounted(async () => {
  await llamaStore.initialize();
  if (llamaStore.modelDirectory) {
    modelDirectory.value = llamaStore.modelDirectory;
  }
});

let pollTimer: number | null = null;

watch(
  () => [llamaStore.isServerRunning, llamaStore.isServerReady],
  ([running, ready]) => {
    if (running && !ready) {
      if (!pollTimer) {
        pollTimer = window.setInterval(async () => {
          await llamaStore.refreshServerStatus();
          if (llamaStore.isServerReady && pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
          }
        }, 2000);
      }
    } else if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  },
  { immediate: true }
);

onUnmounted(() => {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
});
</script>

<style scoped>
.llama-settings {
  padding: 0;
  color: white;
}

.status-card,
.panel {
  border-radius: 20px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(15, 23, 42, 0.92);
  box-shadow: 0 14px 32px rgba(0, 0, 0, 0.22);
}

.panel-emphasis {
  background: rgba(26, 16, 54, 0.95);
  border-color: rgba(192, 132, 252, 0.28);
}

.current-config-panel {
  background: rgba(10, 34, 50, 0.95);
  border-color: rgba(96, 165, 250, 0.28);
}

.status-card {
  background: rgba(15, 27, 55, 0.95);
  border-color: rgba(59, 130, 246, 0.3);
}

.status-card.running {
  background: rgba(5, 30, 22, 0.95);
  border-color: rgba(16, 185, 129, 0.3);
}

.workspace-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr);
  gap: 1.5rem;
}

.status-header,
.panel-header,
.model-list-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.panel-header h3,
.status-text {
  margin: 0;
  font-size: 1.2rem;
  font-weight: 700;
}

.panel-subtitle,
.status-subtext {
  margin: 0.35rem 0 0;
  color: rgba(255, 255, 255, 0.66);
  line-height: 1.5;
  font-size: 0.92rem;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 0.9rem;
}

.status-actions,
.panel-header-actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.status-dot {
  width: 14px;
  height: 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.24);
  flex-shrink: 0;
}

.status-dot.active {
  background: #4ade80;
  box-shadow: 0 0 14px rgba(74, 222, 128, 0.85);
}

.status-dot.starting {
  background: #f59e0b;
  box-shadow: 0 0 10px rgba(245, 158, 11, 0.75);
  animation: pulse 1s infinite;
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.45;
  }
}

.status-pill,
.sync-badge,
.hero-tag {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.45rem 0.75rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 700;
  border: 1px solid rgba(255, 255, 255, 0.12);
}

.status-pill.ready,
.sync-badge.ok {
  background: rgba(34, 197, 94, 0.18);
  color: #86efac;
  border-color: rgba(34, 197, 94, 0.4);
}

.status-pill.booting,
.sync-badge.warn {
  background: rgba(245, 158, 11, 0.16);
  color: #fcd34d;
  border-color: rgba(245, 158, 11, 0.3);
}

.status-pill.idle,
.sync-badge.idle {
  background: rgba(148, 163, 184, 0.16);
  color: #cbd5e1;
  border-color: rgba(148, 163, 184, 0.3);
}

.btn-stop,
.btn-manage-series,
.ghost-button,
.btn-add-series,
.btn-secondary {
  padding: 0.75rem 1rem;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.08);
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
  font-weight: 600;
}

.btn-stop:hover:not(:disabled),
.btn-manage-series:hover,
.ghost-button:hover,
.btn-add-series:hover,
.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.14);
  transform: translateY(-1px);
}

.btn-stop {
  background: rgba(220, 38, 38, 0.18);
  border-color: rgba(248, 113, 113, 0.26);
  color: #fecaca;
}

.status-details,
.meta-grid,
.summary-grid,
.parameter-grid {
  display: grid;
  gap: 1rem;
}

.status-details,
.meta-grid,
.summary-grid {
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}

.detail-item,
.meta-card,
.summary-card,
.hero-config-card,
.selected-model-banner,
.note-card,
.action-tile,
.toggle-card,
.series-item {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 16px;
}

.detail-item,
.meta-card,
.summary-card {
  padding: 1rem;
}

.label,
.meta-label,
.summary-label,
.hero-label,
.control-label {
  display: block;
  font-size: 0.78rem;
  color: rgba(255, 255, 255, 0.55);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 0.35rem;
}

.value,
.summary-value,
.hero-title,
.meta-card strong {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
  color: #e2e8f0;
  word-break: break-word;
}

.summary-help,
.meta-card small,
.hero-subtitle,
.modal-description,
.info-strip,
.series-patterns {
  color: rgba(255, 255, 255, 0.58);
}

.preset-selector-block,
.form-group {
  margin-top: 1.25rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.55rem;
  color: rgba(255, 255, 255, 0.74);
  font-weight: 600;
}

.preset-actions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.9rem;
  margin-top: 1rem;
}

.action-tile {
  display: flex;
  align-items: flex-start;
  gap: 0.85rem;
  text-align: left;
  padding: 1rem;
  cursor: pointer;
  color: white;
}

.action-tile strong,
.toggle-card strong {
  display: block;
  margin-bottom: 0.25rem;
}

.action-tile small,
.toggle-card small {
  display: block;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.62);
}

.action-tile.primary {
  border-color: rgba(96, 165, 250, 0.25);
  background: rgba(37, 99, 235, 0.16);
}

.action-tile.danger {
  border-color: rgba(248, 113, 113, 0.25);
  background: rgba(127, 29, 29, 0.16);
}

.action-tile.active {
  border-color: rgba(251, 191, 36, 0.4);
  background: rgba(251, 191, 36, 0.16);
}

.action-icon {
  font-size: 1.25rem;
  line-height: 1;
}

.preset-library {
  margin-top: 1.25rem;
  display: grid;
  gap: 0.85rem;
}

.library-title {
  font-size: 0.88rem;
  font-weight: 700;
  color: #d8b4fe;
  margin-bottom: 0.45rem;
}

.pill-row,
.quick-profile-row,
.suggestion-row {
  display: flex;
  gap: 0.55rem;
  flex-wrap: wrap;
}

.pill-button,
.profile-chip,
.suggestion-chip {
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.05);
  color: white;
  border-radius: 999px;
  padding: 0.45rem 0.8rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.pill-button:hover,
.profile-chip:hover,
.suggestion-chip:hover {
  background: rgba(255, 255, 255, 0.12);
  transform: translateY(-1px);
}

.pill-button.active {
  background: rgba(168, 85, 247, 0.22);
  border-color: rgba(192, 132, 252, 0.4);
}

.pill-button.custom {
  color: #f9a8d4;
}

.hero-config-card {
  padding: 1.15rem;
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: flex-start;
}

.hero-title {
  font-size: 1.1rem;
  font-weight: 700;
}

.hero-tags {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.hero-tag {
  background: rgba(96, 165, 250, 0.14);
  color: #bfdbfe;
}

.info-strip {
  margin-top: 1rem;
  display: grid;
  gap: 0.5rem;
  background: rgba(255, 255, 255, 0.04);
  border: 1px dashed rgba(255, 255, 255, 0.14);
  border-radius: 14px;
  padding: 0.9rem 1rem;
  line-height: 1.6;
}

.input-with-btn {
  display: flex;
  gap: 0.75rem;
  align-items: stretch;
}

.control-block {
  min-width: 180px;
}

.control-block.grow {
  flex: 1;
}

.model-controls {
  display: flex;
  gap: 0.75rem;
  align-items: flex-end;
  flex-wrap: wrap;
  flex: 1;
  justify-content: flex-end;
}

.form-input,
.form-textarea {
  width: 100%;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.05);
  color: white;
  padding: 0.8rem 0.95rem;
  font-size: 0.95rem;
  transition: border-color 0.2s ease, background 0.2s ease;
}

.form-input:focus,
.form-textarea:focus {
  outline: none;
  border-color: rgba(96, 165, 250, 0.85);
  background: rgba(255, 255, 255, 0.1);
}

.form-input::placeholder,
.form-textarea::placeholder {
  color: rgba(255, 255, 255, 0.3);
}

.form-textarea {
  resize: vertical;
}

.hint {
  margin: 0.45rem 0 0;
  font-size: 0.82rem;
  color: rgba(255, 255, 255, 0.48);
  line-height: 1.5;
}

.selected-model-banner {
  padding: 1rem 1.1rem;
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
  margin-bottom: 1rem;
}

.selected-model-banner strong,
.selected-model-banner small {
  display: block;
}

.selected-model-banner small {
  color: rgba(255, 255, 255, 0.48);
  margin-top: 0.3rem;
  word-break: break-all;
}

.model-list {
  margin-top: 1rem;
}

.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 1rem;
  max-height: 560px;
  overflow-y: auto;
  padding: 0.35rem;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.25) transparent;
}

.model-card {
  background: rgba(255, 255, 255, 0.05);
  border: 2px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
  padding: 1rem;
  cursor: pointer;
  transition: all 0.25s ease;
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}

.model-card:hover {
  background: rgba(255, 255, 255, 0.09);
  border-color: rgba(96, 165, 250, 0.44);
  transform: translateY(-2px);
}

.model-card.selected {
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(37, 99, 235, 0.15) 100%);
  border-color: #60a5fa;
  box-shadow: 0 0 0 1px rgba(96, 165, 250, 0.2), 0 10px 24px rgba(37, 99, 235, 0.18);
}

.model-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.model-icon {
  font-size: 1.8rem;
}

.model-check {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: #10b981;
  color: white;
  font-weight: 700;
}

.model-card-body {
  display: grid;
  gap: 0.5rem;
}

.model-name {
  font-weight: 700;
  line-height: 1.45;
  word-break: break-word;
}

.model-series {
  width: fit-content;
  padding: 0.3rem 0.55rem;
  border-radius: 999px;
  background: rgba(96, 165, 250, 0.18);
  color: #bfdbfe;
  font-size: 0.78rem;
  font-weight: 600;
}

.model-meta {
  color: rgba(255, 255, 255, 0.62);
  font-size: 0.85rem;
}

.parameter-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  margin-top: 1rem;
}

.param-card {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 18px;
  padding: 1.2rem;
}

.param-card.full-width {
  grid-column: 1 / -1;
}

.param-card-header h4 {
  margin: 0;
  color: #93c5fd;
}

.param-card-header p {
  margin: 0.35rem 0 0.9rem;
  color: rgba(255, 255, 255, 0.56);
  line-height: 1.5;
}

.form-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.form-row.three-columns {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.toggle-stack {
  display: grid;
  gap: 0.85rem;
  margin-top: 0.75rem;
}

.toggle-card {
  display: flex;
  gap: 0.85rem;
  align-items: flex-start;
  padding: 0.95rem 1rem;
  cursor: pointer;
}

.toggle-card input[type='checkbox'] {
  margin-top: 0.2rem;
  width: 1.1rem;
  height: 1.1rem;
  accent-color: #60a5fa;
}

.note-card {
  padding: 1rem;
  height: 100%;
}

.note-card ul {
  margin: 0.6rem 0 0;
  padding-left: 1.2rem;
  color: rgba(255, 255, 255, 0.72);
  line-height: 1.75;
}

.parameter-note {
  display: flex;
}

.empty-state {
  text-align: center;
  padding: 2rem;
  color: rgba(255, 255, 255, 0.44);
  background: rgba(255, 255, 255, 0.03);
  border: 1px dashed rgba(255, 255, 255, 0.14);
  border-radius: 16px;
}

.alert {
  margin-bottom: 1rem;
  padding: 1rem 1.1rem;
  border-radius: 14px;
  border: 1px solid transparent;
}

.alert-error {
  background: rgba(239, 68, 68, 0.18);
  border-color: rgba(248, 113, 113, 0.25);
  color: #fecaca;
}

.alert-success {
  background: rgba(34, 197, 94, 0.18);
  border-color: rgba(74, 222, 128, 0.25);
  color: #bbf7d0;
}

.action-buttons {
  display: flex;
  gap: 1rem;
  margin-top: 1.5rem;
  flex-wrap: wrap;
}

.btn-primary,
.btn-start,
.btn-start-quick,
.btn-test {
  border: none;
  border-radius: 14px;
  padding: 0.95rem 1.4rem;
  font-size: 1rem;
  font-weight: 700;
  color: white;
  cursor: pointer;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
}

.btn-primary.compact {
  min-width: 0;
}

.btn-primary {
  background: #2563eb;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-start-quick {
  padding: 0.55rem 1.1rem;
  font-size: 0.92rem;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3);
}

.btn-start-quick:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 6px 16px rgba(16, 185, 129, 0.45);
}

.status-target {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  margin-top: 0.85rem;
  padding: 0.65rem 0.9rem;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 12px;
  font-size: 0.85rem;
}

.target-label {
  color: rgba(255, 255, 255, 0.5);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.target-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  color: #93c5fd;
  font-weight: 600;
}

.target-warn {
  color: #fcd34d;
  font-size: 0.82rem;
}

.target-model {
  color: rgba(255, 255, 255, 0.68);
  font-size: 0.82rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 260px;
}

.btn-start,
.btn-test {
  flex: 1;
  min-width: 220px;
}

.btn-start {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  box-shadow: 0 8px 20px rgba(16, 185, 129, 0.28);
}

.btn-test {
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
  box-shadow: 0 8px 20px rgba(99, 102, 241, 0.28);
}

.btn-test.full-width {
  min-width: 0;
  width: 100%;
}

.btn-start:hover:not(:disabled),
.btn-test:hover:not(:disabled) {
  transform: translateY(-2px);
}

button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none !important;
  box-shadow: none !important;
}

.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1rem;
  background: rgba(2, 6, 23, 0.88);
}

.modal-content {
  width: 100%;
  max-width: 560px;
  background: #0f172a;
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 20px;
  padding: 1.6rem;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.45);
}

.modal-content h3 {
  margin: 0 0 0.75rem;
  font-size: 1.35rem;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  margin-top: 1.4rem;
}

.preset-summary-card {
  margin-top: 1rem;
  padding: 1rem;
  background: rgba(59, 130, 246, 0.08);
  border-radius: 16px;
  border: 1px solid rgba(96, 165, 250, 0.18);
}

.preset-summary-card h4 {
  margin: 0 0 0.85rem;
  color: #bfdbfe;
}

.summary-grid.compact-grid {
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
}

.summary-card.compact {
  padding: 0.8rem;
}

.series-manager {
  max-width: 620px;
  max-height: 82vh;
  overflow-y: auto;
}

.series-list {
  display: grid;
  gap: 0.75rem;
  margin: 1rem 0;
}

.series-item {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  align-items: center;
  padding: 1rem;
}

.series-info {
  display: grid;
  gap: 0.25rem;
}

.series-info strong {
  color: #d8b4fe;
}

.series-actions {
  display: flex;
  gap: 0.5rem;
}

.series-actions button {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(255, 255, 255, 0.08);
  color: white;
  cursor: pointer;
}

.series-actions button:hover {
  background: rgba(255, 255, 255, 0.14);
}

@media (max-width: 1100px) {
  .workspace-grid,
  .parameter-grid,
  .form-row,
  .form-row.three-columns {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .status-header,
  .panel-header,
  .model-list-header,
  .selected-model-banner,
  .hero-config-card {
    flex-direction: column;
  }

  .input-with-btn,
  .modal-actions {
    flex-direction: column;
  }

  .action-buttons {
    flex-direction: column;
  }

  .btn-start,
  .btn-test {
    width: 100%;
  }
}
</style>
