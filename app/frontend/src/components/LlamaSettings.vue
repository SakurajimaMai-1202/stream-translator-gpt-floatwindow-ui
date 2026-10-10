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
            <h2 class="page-title">本地翻譯</h2>
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
              {{ llamaStore.isServerRunning ? '模型在本機執行，設定變更會自動保存。' : '選擇模型與顯卡，啟動後即可測試翻譯。' }}
            </p>
          </div>
        </div>
        <div class="status-actions">
          <button
            v-if="!llamaStore.isServerRunning"
            type="button"
            @click="handleStartServer"
            :disabled="!llamaStore.selectedModelPath || llamaStore.isLoading"
            class="btn-start-quick"
            :title="!llamaStore.selectedModelPath ? '請先在「模型管理」選擇一個模型' : ''"
          >
            <span v-if="llamaStore.isLoading">啟動中…</span>
            <span v-else>啟動伺服器</span>
          </button>
          <button
            v-if="llamaStore.isServerRunning"
            type="button"
            @click="handleApplyAndRestart"
            :disabled="!llamaStore.selectedModelPath || llamaStore.isLoading"
            class="btn-start-quick"
          >
            套用並重啟
          </button>
          <button
            v-if="llamaStore.isServerRunning"
            type="button"
            @click="handleStopServer"
            :disabled="llamaStore.isLoading"
            class="btn-stop"
          >
            停止伺服器
          </button>
        </div>
      </div>

      <div class="quick-model-picker">
        <div class="quick-model-label">
          <span>翻譯模型</span>
          <small v-if="llamaStore.currentModel">執行中：{{ llamaStore.currentModel }}</small>
        </div>
        <div class="quick-model-controls">
          <UiSelect
            :model-value="llamaStore.selectedModelPath"
            :options="quickModelOptions"
            searchable
            search-placeholder="搜尋 GGUF 模型…"
            placeholder="請先到模型管理掃描 GGUF"
            button-class="quick-model-select"
            @update:model-value="handleQuickModelSelect"
          />
          <button type="button" class="favorite-model-button" :disabled="!llamaStore.selectedModelPath" @click="llamaStore.toggleFavoriteModel(llamaStore.selectedModelPath)"
            :title="isSelectedModelFavorite ? '取消收藏' : '收藏此模型'">{{ isSelectedModelFavorite ? '★' : '☆' }}</button>
          <button type="button" class="ghost-button" @click="router.push('/llm-models')">管理模型</button>
        </div>
        <p v-if="hasPendingRuntimeChanges" class="quick-model-pending">已選擇新的模型或參數；目前服務不受影響，按「套用並重啟」後生效。</p>
      </div>

    <section class="panel">
      <div class="panel-header">
        <div><h3>翻譯模型顯卡</h3><p class="hint">自動選擇單張獨顯；GPU 層數為 0 時使用 CPU。AMD 與 Intel 預設推薦 Vulkan。</p></div>
        <button type="button" class="btn-secondary compact" :disabled="gpuDevicesLoading || llamaStore.isServerRunning || runtimeInstallBusy" @click="refreshGpuDevices">{{ gpuDevicesLoading ? '偵測中…' : '重新偵測顯卡' }}</button>
      </div>
      <label>下次啟動使用顯卡</label>
      <UiSelect
        :model-value="llamaStore.serverConfig.gpu_device || 'auto'"
        @update:model-value="llamaStore.serverConfig.gpu_device = String($event ?? 'auto')"
        :options="gpuDeviceOptions"
        aria-label="使用顯卡"
        :disabled="llamaStore.isServerRunning || gpuDevicesLoading || runtimeInstallBusy"
      />
      <label class="hint"><input aria-label="允許選擇內顯" v-model="llamaStore.serverConfig.allow_integrated_gpu" type="checkbox" :disabled="llamaStore.isServerRunning || gpuDevicesLoading || runtimeInstallBusy" /> 允許選擇內顯（預設排除）</label>
      <p v-if="gpuDevicesError" class="alert alert-error" role="alert">{{ gpuDevicesError }}</p>
      <p v-if="gpuSelectionNotice" class="hint" role="status">{{ gpuSelectionNotice }}</p>
      <p v-else-if="gpuDevicesLoaded && !eligibleGpuDevices.length" class="hint">目前 Runtime 未偵測到可選顯卡。GPU 層數為 0 可使用 CPU。</p>
      <p class="hint" role="status">實際使用：{{ actualGpuLabel }}</p>
    </section>


      <div class="common-settings"><div class="form-group">
              <label>GPU 卸載層數</label>
              <input
                aria-label="GPU 層數" v-model.number="llamaStore.serverConfig.n_gpu_layers"
                type="number"
                min="0"
                class="form-input"
              />
              <div class="suggestion-row">
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_gpu_layers', 0)">CPU</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_gpu_layers', 33)">33</button>
                <button type="button" class="suggestion-chip" @click="setServerConfigValue('n_gpu_layers', 99)">99</button>
              </div>
              <p class="hint">0 表示純 CPU；可用 GPU 時通常越高越快，但也越吃顯存。</p>
            </div><div class="form-group">
              <label>上下文長度</label>
              <input
                aria-label="上下文長度" v-model.number="llamaStore.serverConfig.n_ctx"
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
            </div><div class="form-group">
              <label>CPU 執行緒</label>
              <input
                aria-label="執行緒數" v-model.number="llamaStore.serverConfig.n_threads"
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
            </div><div class="form-group">
              <label>同時請求數</label>
              <input
                aria-label="併發數量" v-model.number="llamaStore.serverConfig.n_parallel"
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
            </div></div>
      <div v-if="!llamaStore.isServerRunning" class="status-target">
        <span class="target-label">目標位址</span>
        <span class="target-value">{{ llamaStore.serverConfig.host }}:{{ llamaStore.serverConfig.port }}</span>
        <span v-if="!llamaStore.selectedModelPath" class="target-warn">尚未選擇模型</span>
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

      <details class="inline-test-workspace" open>
        <summary>測試翻譯</summary>
        <div class="inline-test-heading">
          <div>
            <strong>啟動與測試</strong>
            <p>{{ llamaStore.isServerReady ? '服務已就緒，可直接驗證目前模型的翻譯效果。' : '選好模型後可在這裡啟動並立即測試。' }}</p>
          </div>
          <span v-if="hasPendingRuntimeChanges" class="sync-badge warn">參數尚未套用至執行中服務</span>
        </div>
        <textarea aria-label="試譯文字" v-model="testText" class="form-textarea" rows="3" placeholder="輸入要測試翻譯的文字…"></textarea>
        <div class="inline-test-actions">
          <button type="button" @click="executePrimaryTest" :disabled="!testText.trim() || !llamaStore.selectedModelPath || isTesting || llamaStore.isLoading" class="btn-test">
            {{ primaryTestButtonLabel }}
          </button>
          <span v-if="llamaStore.serverStatus.performance?.latency_ms" class="test-performance">
            {{ llamaStore.serverStatus.performance.latency_ms }} ms · {{ llamaStore.serverStatus.performance.tokens_predicted || 0 }} tokens · {{ llamaStore.serverStatus.performance.tokens_per_second || 0 }} tok/s
          </span>
        </div>
        <div class="inline-test-result">
          <span>翻譯結果</span>
          <p v-if="testResult">{{ testResult }}</p>
          <p v-else class="empty-result">尚未執行測試</p>
        </div>
      </details>
    </div>

    <section class="resource-strip" aria-label="即時資源" v-if="llamaStore.isServerRunning">
      <span>CPU <strong>{{ llamaStore.serverStatus.resources?.cpu_percent ?? '—' }}%</strong></span>
      <span>RAM <strong>{{ llamaStore.serverStatus.resources?.ram_used_gb ?? '—' }} / {{ llamaStore.serverStatus.resources?.ram_total_gb ?? '—' }} GB</strong></span>
      <span>程序 RAM <strong>{{ llamaStore.serverStatus.resources?.process_ram_mb ?? '—' }} MB</strong></span>
      <span>生成速度 <strong>{{ llamaStore.serverStatus.performance?.tokens_per_second ?? '—' }} tok/s</strong></span>
      <span v-if="llamaStore.serverStatus.gpu_selection?.confirmed">GPU 卸載 <strong>{{ llamaStore.serverStatus.gpu_selection.offloaded_layers ?? '—' }} 層</strong></span>
    </section>
    <details class="panel runtime-management">
      <summary>執行環境 <small>{{ llamaStore.serverStatus.runtime?.version || "llama.cpp" }}</small></summary>
        <p class="runtime-version">{{ llamaStore.serverStatus.runtime?.version || '讀取中…' }}</p>
        <p class="hint break-path">{{ llamaStore.serverStatus.runtime?.path || '尚未找到 llama-server' }}</p>
        <span v-if="llamaStore.serverStatus.runtime?.source === 'custom'" class="runtime-current-badge">自訂位置</span>
        <label class="hint" for="custom-llama-runtime">自訂 Runtime 資料夾或 llama-server.exe（留空使用程式管理版本）</label>
        <input id="custom-llama-runtime" v-model="llamaStore.serverConfig.server_exe" type="text" class="form-input" placeholder="例如 D:\\llama.cpp" :disabled="llamaStore.isServerRunning" />
        <button type="button" class="btn-secondary compact" :disabled="llamaStore.isServerRunning || runtimePathBusy" @click="applyCustomRuntime">
          {{ runtimePathBusy ? '驗證中…' : '驗證並套用' }}
        </button>
        <span v-if="runtimeReleaseLoading && !runtimeRelease" class="runtime-current-badge checking">正在核對官方最新版…</span>
        <span v-else-if="runtimeRelease?.is_latest" class="runtime-current-badge">✓ 已是最新版本 {{ runtimeRelease.tag }}</span>
        <button v-else type="button" @click="openRuntimeInstaller" class="btn-start-quick runtime-download">在此下載／更新 Runtime</button>
        <a :href="llamaStore.serverStatus.runtime?.download_url || 'https://github.com/ggml-org/llama.cpp/releases/latest'" target="_blank" rel="noopener" class="runtime-official-link">查看官方 Release</a>

    </details>
    <section v-if="showRuntimeInstaller" class="panel runtime-installer">
      <div class="panel-header">
        <div><h3>下載 llama.cpp Runtime</h3><p class="panel-subtitle">來源為官方 GitHub Release，並依目前 Runtime Profile 標示推薦的 Windows x64 套件。</p></div>
        <button type="button" class="btn-secondary compact" @click="showRuntimeInstaller = false">關閉</button>
      </div>
      <div v-if="runtimeReleaseLoading" class="runtime-install-message">正在讀取官方最新版…</div>
      <div v-else-if="runtimeReleaseError" class="alert alert-error">{{ runtimeReleaseError }}</div>
      <template v-else-if="runtimeRelease">
        <div class="runtime-release-meta">
          <span>來源：<strong>{{ runtimeRelease.source === 'github' ? 'GitHub 官方 Release' : runtimeRelease.source }}</strong></span>
          <span>最新版：<strong>{{ runtimeRelease.tag }}</strong></span>
          <span v-if="runtimeRelease.installed_tag">目前安裝：<strong>{{ runtimeRelease.installed_tag }}<template v-if="runtimeRelease.installed_variant"> / {{ runtimeRelease.installed_variant }}</template></strong></span>
        </div>
        <div v-if="runtimeRelease.is_latest" class="alert alert-success">已安裝官方最新版本，無需重複下載。</div>
        <div v-if="runtimeInstallNotice" class="alert alert-success">{{ runtimeInstallNotice }}</div>
        <div v-if="runtimeRelease.detected_gpus?.length" class="runtime-hardware-summary">
          <span v-for="gpu in runtimeRelease.detected_gpus" :key="`${gpu.name}-${gpu.backend}`">
            {{ gpu.name }}<small>{{ gpu.is_integrated ? '內顯' : '獨立 GPU' }}<template v-if="gpu.memory_mb"> · {{ Math.round(gpu.memory_mb / 1024) }} GB</template></small>
          </span>
        </div>
        <p v-if="runtimeRelease.recommendation_reason" class="runtime-recommendation">{{ runtimeRelease.recommendation_reason }}</p>
        <div class="runtime-variant-grid">
          <label v-for="variant in runtimeRelease.variants" :key="variant.id" :class="['runtime-variant', selectedRuntimeVariant === variant.id && 'selected', !variant.installable && 'disabled']">
            <input v-model="selectedRuntimeVariant" type="radio" :value="variant.id" :disabled="!variant.installable" />
            <span class="runtime-variant-content">
              <span class="runtime-variant-title"><strong>{{ variant.label }}</strong><span v-if="variant.recommended" class="recommended-badge">依偵測硬體推薦</span><span v-if="variant.installed_latest" class="recommended-badge">已安裝最新版</span></span>
              <small>{{ formatRuntimeBytes(variant.size) }} · {{ variant.assets.length }} 個官方檔案<template v-if="variant.runtime_version"> · {{ variant.backend === 'cuda' ? 'CUDA' : variant.backend === 'hip' ? 'ROCm' : variant.backend.toUpperCase() }} {{ variant.runtime_version }}</template></small>
              <span class="runtime-asset-list">
                <small v-for="asset in variant.assets" :key="asset.name"><b>{{ asset.role === 'dependency' ? 'CUDA-RT' : 'llama.cpp' }}</b>{{ asset.name }}</small>
              </span>
              <small v-if="variant.compatibility_error" class="runtime-error">{{ variant.compatibility_error }}</small>
            </span>
          </label>
        </div>
        <div v-if="runtimeInstallStatus && runtimeInstallStatus.state !== 'idle'" class="runtime-progress-wrap">
          <div class="runtime-progress"><span :style="{ width: `${Math.round(runtimeInstallStatus.progress * 100)}%` }"></span></div>
          <p>{{ runtimeInstallStatus.message }} <span v-if="runtimeInstallStatus.progress">{{ Math.round(runtimeInstallStatus.progress * 100) }}%</span><small class="runtime-state-badge">{{ runtimeStateLabel(runtimeInstallStatus.state) }}</small></p>
          <div v-if="runtimeInstallStatus.files?.length" class="runtime-file-progress-list">
            <div v-for="file in runtimeInstallStatus.files" :key="file.name" class="runtime-file-progress-item">
              <div class="runtime-file-progress-head">
                <span><b>{{ file.role === 'dependency' ? 'CUDA-RT' : 'llama.cpp' }}</b>{{ file.name }}</span>
                <small>{{ runtimeStateLabel(file.state) }} · {{ formatRuntimeBytes(file.downloaded_bytes) }} / {{ formatRuntimeBytes(file.total_bytes) }}</small>
              </div>
              <div class="runtime-progress file"><span :class="{ error: file.state === 'error' }" :style="{ width: `${Math.round(file.progress * 100)}%` }"></span></div>
              <small v-if="file.error" class="runtime-error">{{ file.error }}</small>
            </div>
          </div>
          <p v-if="runtimeInstallStatus.fallback_reason" class="runtime-recommendation">{{ runtimeInstallStatus.fallback_reason }}</p>
          <p v-if="runtimeInstallStatus.error" class="runtime-error">{{ runtimeInstallStatus.error }}</p>
        </div>
        <button type="button" class="btn-start-quick" :disabled="!selectedRuntimeOption?.installable || runtimeInstallBusy || llamaStore.isServerRunning || runtimeRelease.is_latest" @click="installSelectedRuntime">{{ runtimeInstallBusy ? '下載安裝中…' : runtimeRelease.is_latest ? '目前已是最新版本' : '下載並安裝選取版本' }}</button>
        <p v-if="llamaStore.isServerRunning" class="hint warn-text">請先停止 llama.cpp 伺服器，才能更換 Runtime。</p>
        <p class="hint">安裝後會保留現有 Runtime，模型與執行參數不會被刪除。</p>
      </template>
    </section>

    <div v-if="llamaStore.errorMessage" class="alert alert-error">{{ llamaStore.errorMessage }}</div>
    <div v-if="llamaStore.successMessage" class="alert alert-success">{{ llamaStore.successMessage }}</div>

    <details class="panel preset-management">
      <summary>配置預設 <small>{{ selectedPresetLabel }}</small></summary>
      <p class="hint">{{ presetSyncText }} · 啟動預設：{{ defaultPresetLabel }}</p>
      <div class="preset-selector-block">
        <label>套用配置</label>
        <UiSelect v-model="llamaStore.selectedPreset" :options="presetOptions" placeholder="選擇系統預設或自己的配置" aria-label="套用配置" />
        <p class="hint">套用至目前編輯的設定；執行中的服務需重啟後生效。</p>
      </div>
      <div class="status-actions preset-actions">
        <button type="button" @click="handleSetDefaultPreset" :disabled="!llamaStore.selectedPreset" class="btn-secondary">{{ llamaStore.selectedPreset === llamaStore.defaultPreset ? '已設為啟動預設' : '設為啟動預設' }}</button>
        <button type="button" @click="openSaveDialog" class="btn-secondary">保存目前配置</button>
        <button v-if="llamaStore.selectedPreset.startsWith('custom:')" type="button" @click="handleDeletePreset" class="btn-stop">刪除自訂配置</button>
      </div>
    </details>
    <details class="panel advanced-settings">
      <summary>進階執行設定 <small>連線、效能與生成參數</small></summary>
      <div class="panel-header">
        <div>
          <h3>執行參數</h3>
          <p class="panel-subtitle">設定會自動保存；服務執行中，重啟後才會套用。</p>
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

          <span>{{ profile.label }}</span>
        </button>
      </div>

      <div class="parameter-grid">
        <div class="param-card">
          <div class="param-card-header">
            <h4>連線與上下文</h4>
            <p>設定本機服務的監聽位址與埠號。</p>
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>主機</label>
              <input aria-label="主機" v-model="llamaStore.serverConfig.host" type="text" class="form-input" />
            </div>
            <div class="form-group">
              <label>埠號</label>
              <input aria-label="埠號" v-model.number="llamaStore.serverConfig.port" type="number" class="form-input" />
            </div>
          </div>


        </div>

        <div class="param-card">
          <div class="param-card-header">
            <h4>效能與記憶體</h4>
            <p>設定注意力加速與模型載入策略。</p>
          </div>



          <div class="toggle-stack">
            <label :class="['toggle-card', { 'is-disabled': isHyMtModel }]">
              <div>
                <strong>Flash Attention [on|off|auto]</strong>
                <small v-if="isHyMtModel">Hy-MT／Hy-MT2 不相容，已自動關閉。</small>
                <small v-else>預設 auto，由 llama.cpp 根據模型與硬體自行判斷。</small>
              </div>
              <UiSelect :model-value="llamaStore.serverConfig.flash_attn || 'auto'" @update:model-value="llamaStore.serverConfig.flash_attn = $event as 'auto' | 'on' | 'off'" :options="[{ value: 'auto', label: '自動' }, { value: 'on', label: '開啟' }, { value: 'off', label: '關閉' }]" :disabled="isHyMtModel" aria-label="Flash Attention" />
            </label>
            <label :class="['toggle-card', { 'is-disabled': isHyMtModel }]">
              <input aria-label="禁用 mmap" v-model="llamaStore.serverConfig.no_mmap" type="checkbox" :disabled="isHyMtModel" />
              <div>
                <strong>禁用 mmap</strong>
                <small v-if="isHyMtModel">Hy-MT／Hy-MT2 必須停用 mmap，已自動套用。</small>
                <small v-else>某些環境能改善載入穩定性，但會使用更多記憶體。</small>
              </div>
            </label>
          </div>
        </div>

        <div class="param-card full-width">
          <div class="param-card-header">
            <h4>生成參數</h4>
            <p>控制翻譯時的穩定度、採樣範圍與單次輸出長度。</p>
          </div>

          <div class="form-row three-columns">
            <div class="form-group">
              <label>溫度 (temp)</label>
              <input
                aria-label="溫度" v-model.number="llamaStore.serverConfig.temp"
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
                aria-label="Top-P" v-model.number="llamaStore.serverConfig.top_p"
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
                aria-label="Top-K" v-model.number="llamaStore.serverConfig.top_k"
                type="number"
                min="0"
                max="100"
                class="form-input"
              />
              <p class="hint">候選 token 數量；0 表示停用 Top-K。</p>
            </div>

            <div class="form-group">
              <label>重複懲罰</label>
              <input
                aria-label="重複懲罰" v-model.number="llamaStore.serverConfig.repeat_penalty"
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
                aria-label="預測長度" v-model.number="llamaStore.serverConfig.n_predict"
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
    </details>

    <div v-if="showSaveDialog" class="modal-overlay" @click.self="showSaveDialog = false">
      <div class="modal-content" role="dialog" aria-modal="true" aria-labelledby="save-preset-title">
        <h3 id="save-preset-title">保存配置預設</h3>
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
      <div class="modal-content series-manager" role="dialog" aria-modal="true" aria-labelledby="series-manager-title">
        <h3 id="series-manager-title">模型系列管理</h3>

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
      <div class="modal-content" role="dialog" aria-modal="true" aria-labelledby="edit-series-title">
        <h3 id="edit-series-title">{{ editingSeriesIndex >= 0 ? '編輯' : '新增' }}模型系列</h3>

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
import { useRouter } from 'vue-router';
import UiSelect, { type UiSelectOption } from './UiSelect.vue';
import { useLlamaStore } from '../stores/llama';
import { llamaApi, type RuntimeInstallStatus, type RuntimeReleaseInfo, type RuntimeDevice, type ServerConfig } from '../services/llamaApi';

const showRuntimeInstaller = ref(false);
const runtimeReleaseLoading = ref(false);
const runtimeReleaseError = ref('');
const runtimeRelease = ref<RuntimeReleaseInfo | null>(null);
const selectedRuntimeVariant = ref('');
const runtimeInstallStatus = ref<RuntimeInstallStatus | null>(null);
const runtimeInstallNotice = ref('');
const runtimePathBusy = ref(false);
const gpuDevices = ref<RuntimeDevice[]>([]);
const gpuDevicesLoading = ref(false);
const gpuDevicesLoaded = ref(false);
const gpuDevicesError = ref('');
const gpuSelectionNotice = ref('');
let gpuRequestGeneration = 0;
let gpuSettingsInitialized = false;
const eligibleGpuDevices = computed(() => gpuDevices.value.filter(device => device.eligible && (!device.is_integrated || llamaStore.serverConfig.allow_integrated_gpu)));
const unlistedGpuSelection = computed(() => llamaStore.serverConfig.gpu_device && llamaStore.serverConfig.gpu_device !== 'auto' && !eligibleGpuDevices.value.some(device => device.id === llamaStore.serverConfig.gpu_device));
const gpuDeviceOptions = computed<UiSelectOption[]>(() => [
  { value: 'auto', label: '自動選擇獨顯' },
  ...(unlistedGpuSelection.value ? [{
    value: llamaStore.serverConfig.gpu_device || '',
    label: `已儲存的顯卡：${llamaStore.serverConfig.gpu_device}（目前無法選用）`,
    disabled: true,
  }] : []),
  ...eligibleGpuDevices.value.map(device => ({
    value: device.id,
    label: `${device.name} · ${device.id}${device.memory_mb ? ` · ${(device.memory_mb / 1024).toFixed(1)} GB` : ''}${device.is_integrated ? ' · 內顯' : ''}`,
  })),
]);
const actualGpuLabel = computed(() => {
  const selection = llamaStore.serverStatus.gpu_selection;
  if (!llamaStore.isServerRunning) return '尚未啟動模型';
  if (selection?.mode === 'cpu') return 'CPU';
  if (selection?.confirmed && selection.selected_device) return selection.selected_device.name;
  if (selection?.selected_device) return `已指定 ${selection.selected_device.name}，等待確認 GPU 卸載`;
  return '實際使用裝置尚未確認';
});

async function refreshGpuDevices() {
  const generation = ++gpuRequestGeneration;
  gpuDevicesLoading.value = true;
  gpuDevicesLoaded.value = false;
  gpuDevicesError.value = '';
  gpuDevices.value = [];
  try {
    const result = await llamaApi.getRuntimeDevices(llamaStore.serverConfig.server_exe || '', llamaStore.serverConfig.allow_integrated_gpu === true);
    if (generation !== gpuRequestGeneration) return;
    gpuDevices.value = result.devices;
    gpuDevicesError.value = result.error || '';
    gpuDevicesLoaded.value = !result.error;
    if (!result.error && unlistedGpuSelection.value) {
      gpuDevicesError.value = `已儲存的顯卡 ${llamaStore.serverConfig.gpu_device} 目前無法選用。請明確選擇另一張顯卡或自動選擇後再啟動。`;
    } else if (!result.error && llamaStore.serverConfig.gpu_device_name) {
      const selected = eligibleGpuDevices.value.find(device => device.id === llamaStore.serverConfig.gpu_device);
      if (selected && selected.name !== llamaStore.serverConfig.gpu_device_name) gpuDevicesError.value = `顯卡編號已變更：原本為 ${llamaStore.serverConfig.gpu_device_name}，目前為 ${selected.name}。請重新選擇顯卡後再啟動。`;
    }
  } catch (error: any) {
    if (generation === gpuRequestGeneration) gpuDevicesError.value = error.response?.data?.detail || error.message || '顯卡偵測失敗';
  } finally {
    if (generation === gpuRequestGeneration) gpuDevicesLoading.value = false;
  }
}
let runtimeCompletionNotifiedJobId = '';
let runtimeInstallPollTimer: number | null = null;

const runtimeInstallBusy = computed(() => ['resolving', 'downloading', 'verifying', 'staging', 'activating'].includes(runtimeInstallStatus.value?.state || ''));
const selectedRuntimeOption = computed(() => runtimeRelease.value?.variants.find(item => item.id === selectedRuntimeVariant.value));

function isHyMtModelPath(modelPath: string): boolean {
  const compactName = (modelPath.split(/[\\/]/).pop() || '').toLowerCase().replace(/[-_]/g, '');
  return compactName.includes('hymt');
}

const isHyMtModel = computed(() => isHyMtModelPath(llamaStore.selectedModelPath));

function formatRuntimeBytes(bytes: number) {
  if (!bytes) return '0 MB';
  return `${(bytes / 1024 / 1024).toFixed(0)} MB`;
}

function runtimeStateLabel(state: string) {
  return ({
    idle: '待命', resolving: '解析版本', pending: '等待下載', downloading: '下載中',
    verifying: '驗證中', staging: '準備安裝', activating: '切換版本', completed: '完成', error: '失敗',
  } as Record<string, string>)[state] || state;
}

async function applyCustomRuntime() {
  runtimePathBusy.value = true;
  runtimeReleaseError.value = '';
  runtimeInstallNotice.value = '';
  try {
    const value = String(llamaStore.serverConfig.server_exe || '').trim();
    if (value) {
      const result = await llamaApi.validateRuntime(value);
      llamaStore.serverConfig.server_exe = result.path;
      runtimeInstallNotice.value = `自訂 Runtime 驗證通過：${result.version}`;
    } else {
      runtimeInstallNotice.value = '已切回程式管理的 llama.cpp Runtime。';
    }
    await llamaStore.saveConfig();
    await llamaStore.refreshServerStatus();
  } catch (error: any) {
    runtimeReleaseError.value = error.response?.data?.detail || error.message || 'Runtime 驗證失敗';
  } finally {
    runtimePathBusy.value = false;
  }
}

async function openRuntimeInstaller() {
  showRuntimeInstaller.value = true;
  await refreshRuntimeRelease(false);
  try {
    runtimeInstallStatus.value = await llamaApi.getRuntimeInstallStatus();
    if (runtimeInstallBusy.value) startRuntimeInstallPolling();
  } catch (error: any) {
    runtimeReleaseError.value = error.response?.data?.detail || error.message;
  }
}

async function refreshRuntimeRelease(silent = true) {
  runtimeReleaseLoading.value = true;
  if (!silent) runtimeReleaseError.value = '';
  runtimeInstallNotice.value = '';
  try {
    runtimeRelease.value = await llamaApi.getRuntimeReleases();
    selectedRuntimeVariant.value = runtimeRelease.value.variants.find(item => item.recommended && item.installable)?.id
      || runtimeRelease.value.variants.find(item => item.installable)?.id || '';
  } catch (error: any) {
    if (!silent) runtimeReleaseError.value = error.response?.data?.detail || error.message;
  } finally {
    runtimeReleaseLoading.value = false;
  }
}

function stopRuntimeInstallPolling() {
  if (runtimeInstallPollTimer) window.clearInterval(runtimeInstallPollTimer);
  runtimeInstallPollTimer = null;
}

function startRuntimeInstallPolling() {
  stopRuntimeInstallPolling();
  runtimeInstallPollTimer = window.setInterval(() => void pollRuntimeInstallStatus(), 1000);
}

async function pollRuntimeInstallStatus() {
  runtimeInstallStatus.value = await llamaApi.getRuntimeInstallStatus();
  if (['completed', 'error'].includes(runtimeInstallStatus.value.state)) {
    stopRuntimeInstallPolling();
    if (runtimeInstallStatus.value.state === 'completed') {
      await llamaStore.refreshServerStatus();
      runtimeRelease.value = await llamaApi.getRuntimeReleases();
      if (runtimeCompletionNotifiedJobId !== runtimeInstallStatus.value.job_id) {
        runtimeCompletionNotifiedJobId = runtimeInstallStatus.value.job_id;
        runtimeInstallNotice.value = `llama.cpp Runtime ${runtimeInstallStatus.value.tag} 已下載、驗證並安裝完成。`;
      }
    }
  }
}

async function installSelectedRuntime() {
  if (!selectedRuntimeOption.value?.installable || llamaStore.isServerRunning || runtimeRelease.value?.is_latest) return;
  if (!confirm('要下載並安裝選取的 llama.cpp Runtime 嗎？模型與現有 Runtime 會保留。')) return;
  try {
    runtimeInstallNotice.value = '';
    await llamaApi.installRuntime(selectedRuntimeVariant.value);
    await pollRuntimeInstallStatus();
    startRuntimeInstallPolling();
  } catch (error: any) {
    runtimeReleaseError.value = error.response?.data?.detail || error.message;
  }
}

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
  flash_attn: 'auto',
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
const router = useRouter();
const modelDirectory = ref('');


const testText = ref('Hello, how are you today?');
const testResult = ref('');
const isTesting = ref(false);
const appliedRuntimeFingerprint = ref('');
const showSaveDialog = ref(false);
const presetName = ref('');

const showSeriesManager = ref(false);
const showAddSeriesDialog = ref(false);
const editingSeriesIndex = ref(-1);
const newSeries = ref({ name: '', patterns: [] as string[] });
const newSeriesPatterns = ref('');





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
    'no_mmap',
    'gpu_device',
    'gpu_device_name',
    'allow_integrated_gpu'
  ];

  return keysToCompare.every((key) => {
    const presetValue = preset[key];
    const currentValue = key === 'model_path' ? llamaStore.selectedModelPath : llamaStore.serverConfig[key];
    return presetValue === undefined || presetValue === currentValue;
  });
}

const systemPresetNames = computed(() => Object.keys(llamaStore.systemPresets));
const customPresetNames = computed(() => Object.keys(llamaStore.customPresets));


const presetOptions = computed<UiSelectOption[]>(() => [
  { value: '', label: '自訂配置（目前手動調整）' },
  ...systemPresetNames.value.map((name) => ({ value: name, label: name, group: '系統預設' })),
  ...customPresetNames.value.map((name) => ({ value: `custom:${name}`, label: `📦 ${name}`, group: '我的配置' }))
]);


const selectedPresetLabel = computed(() => {
  if (!llamaStore.selectedPreset) return '手動調整中';
  return llamaStore.selectedPreset.startsWith('custom:')
    ? llamaStore.selectedPreset.substring(7)
    : llamaStore.selectedPreset;
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


const presetSyncText = computed(() => {
  if (!llamaStore.selectedPreset) return '目前是手動調整配置';
  return isSelectedPresetSynced.value ? '與所選預設完全同步' : '已偏離所選預設，建議另存新版本';
});

const runtimeFingerprint = computed(() => JSON.stringify({ ...llamaStore.serverConfig, model_path: llamaStore.selectedModelPath }));
const hasPendingRuntimeChanges = computed(() => llamaStore.isServerRunning
  && Boolean(appliedRuntimeFingerprint.value)
  && runtimeFingerprint.value !== appliedRuntimeFingerprint.value);
const primaryTestButtonLabel = computed(() => {
  if (isTesting.value) return '測試中…';
  if (!llamaStore.isServerReady) return '🚀 啟動並測試';
  if (hasPendingRuntimeChanges.value) return '套用、重啟並測試';
  return '🧪 測試翻譯';
});
const isSelectedModelFavorite = computed(() => llamaStore.favoriteModelPaths.includes(llamaStore.selectedModelPath));
const quickModelOptions = computed<UiSelectOption[]>(() => {
  const byPath = new Map(llamaStore.models.map(model => [model.path, model]));
  const format = (path: string, status = '') => {
    const model = byPath.get(path);
    const name = model?.name || getModelName(path);
    const size = model ? ` · ${model.size_mb.toFixed(0)} MB` : '';
    return { value: path, label: `${status}${name}${size}` };
  };
  const favorites = llamaStore.favoriteModelPaths.filter(path => byPath.has(path));
  const recent = llamaStore.recentModelPaths.filter(path => byPath.has(path) && !favorites.includes(path));
  const used = new Set([...favorites, ...recent]);
  const options: UiSelectOption[] = [
    ...favorites.map(path => ({ ...format(path, '★ '), group: '收藏模型' })),
    ...recent.map(path => ({ ...format(path, '最近 · '), group: '最近使用' })),
    ...llamaStore.models.filter(model => !used.has(model.path)).map(model => ({ ...format(model.path), group: '全部模型' })),
  ];
  if (llamaStore.selectedModelPath && !byPath.has(llamaStore.selectedModelPath)) {
    options.unshift({ ...format(llamaStore.selectedModelPath, '✓ '), group: '目前選擇' });
  }
  return options;
});

function handleQuickModelSelect(value: string | number | null) {
  if (typeof value === 'string' && value) llamaStore.selectModel(value);
}



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
    port: llamaStore.serverConfig.port || 8081,
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



async function handleStartServer() {
  try {
    await llamaStore.startServer();
    appliedRuntimeFingerprint.value = runtimeFingerprint.value;
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
  gpuSettingsInitialized = true;
  void refreshGpuDevices();
  void refreshRuntimeRelease(true);
  if (llamaStore.isServerRunning) appliedRuntimeFingerprint.value = runtimeFingerprint.value;
  if (llamaStore.modelDirectory) {
    modelDirectory.value = llamaStore.modelDirectory;
  }
});

let pollTimer: number | null = null;

watch(() => [llamaStore.serverConfig.server_exe, llamaStore.serverStatus.runtime?.path, llamaStore.serverStatus.runtime?.version], () => {
  ++gpuRequestGeneration;
  gpuDevices.value = [];
  gpuDevicesLoaded.value = false;
  gpuDevicesLoading.value = false;
  gpuDevicesError.value = '';
  if (gpuSettingsInitialized && !llamaStore.isServerRunning) {
    if (llamaStore.serverConfig.gpu_device !== 'auto') gpuSelectionNotice.value = 'Runtime 已變更，顯卡選擇已重設為自動。請重新偵測並確認顯卡。';
    llamaStore.serverConfig.gpu_device = 'auto';
  }
});
watch(() => llamaStore.serverConfig.gpu_device, () => {
  if (gpuSettingsInitialized) {
    llamaStore.serverConfig.gpu_device_name = llamaStore.serverConfig.gpu_device === 'auto' ? '' : (eligibleGpuDevices.value.find(device => device.id === llamaStore.serverConfig.gpu_device)?.name || llamaStore.serverConfig.gpu_device_name || '');
  }
  if (gpuDevicesLoaded.value && !unlistedGpuSelection.value) gpuDevicesError.value = '';
});
watch(() => llamaStore.serverConfig.allow_integrated_gpu, () => {
  if (!llamaStore.isServerRunning) void refreshGpuDevices();
});

watch(
  isHyMtModel,
  (hyMtSelected) => {
    if (!hyMtSelected) return;
    llamaStore.serverConfig.flash_attn = 'off';
    llamaStore.serverConfig.no_mmap = true;
  },
  { immediate: true }
);

watch(
  () => llamaStore.isServerRunning,
  (running) => {
    if (running) {
      if (!pollTimer) {
        pollTimer = window.setInterval(async () => {
          await llamaStore.refreshServerStatus();
        }, 4000);
      }
    } else if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  },
  { immediate: true }
);

onUnmounted(() => {
  stopRuntimeInstallPolling();
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
});

async function handleApplyAndRestart() {
  if (!confirm('將停止目前服務，套用模型與參數後重新啟動。是否繼續？')) return;
  try {
    await llamaStore.applyAndRestart();
    appliedRuntimeFingerprint.value = runtimeFingerprint.value;
  } catch (error) {
    console.error('套用並重啟失敗:', error);
  }
}

async function executePrimaryTest() {
  if (!testText.value.trim()) return;
  isTesting.value = true;
  testResult.value = '';
  try {
    if (!llamaStore.isServerReady) {
      await llamaStore.startServer();
      appliedRuntimeFingerprint.value = runtimeFingerprint.value;
    } else if (hasPendingRuntimeChanges.value) {
      await llamaStore.applyAndRestart();
      appliedRuntimeFingerprint.value = runtimeFingerprint.value;
    }
    await executeTest();
    await llamaStore.refreshServerStatus();
  } finally {
    isTesting.value = false;
  }
}
</script>

<style scoped>
.llama-settings { color:var(--fw-text); font-family:system-ui,-apple-system,"Segoe UI",sans-serif; font-size:.9375rem; line-height:1.5; }
.status-card,.panel { background:var(--fw-surface); border:1px solid var(--fw-border); border-radius:16px; padding:1.25rem; margin-bottom:1rem; }
.status-card { padding:1.5rem; } .status-card .panel { background:transparent; border:0; border-top:1px solid var(--fw-border); border-radius:0; padding:1.25rem 0 0; margin:1.25rem 0; }
.page-title { margin:0 0 .3rem;font-size:1.5rem;line-height:1.2;letter-spacing:-.025em;font-weight:650; }
h3,h4 { margin:0;font-size:1rem;font-weight:600;letter-spacing:-.01em; } p { margin:.45rem 0; }
.status-header,.panel-header,.status-indicator,.status-actions,.quick-model-controls,.inline-test-actions,.input-with-btn,.modal-actions { display:flex;align-items:center;gap:.75rem; }
.status-header,.panel-header { justify-content:space-between;align-items:flex-start; } .status-actions { flex-wrap:wrap; } .status-indicator { align-items:flex-start; }
.status-text { font-size:.875rem;color:var(--fw-text-secondary); } .status-dot { width:8px;height:8px;border-radius:50%;background:#8290a4;margin-top:.5rem;flex-shrink:0; } .status-dot.active { background:#5bd9a3; } .status-dot.starting { background:#e7b867; }
.status-subtext,.hint,.panel-subtitle,.param-card-header p,.modal-description,.toggle-card small { font-size:.8125rem;line-height:1.55;color:var(--fw-text-secondary); }
.common-settings { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem;border-top:1px solid var(--fw-border);padding-top:.25rem; }
.quick-model-picker { margin-top:1.5rem; } .quick-model-label { display:flex;justify-content:space-between;gap:.5rem;margin-bottom:.5rem;font-weight:600; } .quick-model-label small { color:var(--fw-text-secondary);font-weight:400; } .quick-model-controls > :first-child { flex:1;min-width:0; }
button { font:inherit;font-weight:600;min-height:44px;padding:.6rem 1rem;border-radius:10px;border:1px solid #ffffff1c;background:#ffffff09;color:var(--fw-text);cursor:pointer;touch-action:manipulation;transition:background 120ms ease,transform 100ms ease; } button:hover:not(:disabled) { background:#ffffff13; } button:active:not(:disabled) { transform:scale(.98);background:#ffffff20; } button:disabled { opacity:.45;cursor:not-allowed; }
.btn-start-quick,.btn-primary { background:var(--fw-primary);border-color:var(--fw-primary);color:white; } .btn-start-quick:hover:not(:disabled),.btn-primary:hover:not(:disabled) { background:#4488ee; } .btn-stop { color:#f4b6bb; } .favorite-model-button { padding:.5rem .75rem;font-size:1.25rem; } .btn-test { background:var(--fw-primary-soft);border-color:#598cc066; }
button:focus-visible,input:focus-visible,textarea:focus-visible,summary:focus-visible { outline:2px solid var(--fw-primary);outline-offset:3px; }
.form-input,.form-textarea,.form-select { box-sizing:border-box;width:100%;min-height:44px;padding:.65rem .8rem;border-radius:10px;border:1px solid #ffffff26;background:var(--fw-surface-subtle);color:var(--fw-text);font:inherit; } .form-textarea { resize:vertical; } .form-input::placeholder,.form-textarea::placeholder { color:var(--fw-text-muted); }
label { display:block;font-weight:500;margin-bottom:.45rem; } input[type=checkbox] { width:18px;height:18px;accent-color:var(--fw-primary);vertical-align:middle; } label.hint { display:flex;align-items:center;gap:.5rem;min-height:44px; }
.status-target,.status-details { display:flex;gap:1.5rem;flex-wrap:wrap;font-size:.8125rem;margin-top:1rem;color:var(--fw-text-secondary); } .target-model { display:none; } .label { display:block;color:#94a3b8;font-size:.75rem; } .value,.target-value { color:#dbe5f2;overflow-wrap:anywhere; } .target-warn { color:#e7b867; }
.inline-test-workspace { margin-top:1.25rem;border-top:1px solid var(--fw-border);padding-top:.65rem; } summary { min-height:44px;cursor:pointer;font-weight:600;line-height:1.5;display:list-item;align-content:center; } summary small { font-weight:400;color:var(--fw-text-secondary);margin-left:.75rem;font-size:.8125rem; } details[open] > summary { margin-bottom:.75rem; }
.inline-test-heading { display:none; } .inline-test-actions { justify-content:space-between;margin-top:.75rem;flex-wrap:wrap; } .test-performance { color:var(--fw-text-secondary);font-size:.75rem; } .inline-test-result { margin-top:.9rem;padding:.85rem 1rem;border-radius:10px;background:var(--fw-surface-subtle); } .inline-test-result > span { font-size:.75rem;color:var(--fw-text-secondary); } .empty-result { color:var(--fw-text-muted); }
.quick-model-pending { color:#e7b867;font-size:.8125rem; } .resource-strip { display:flex;flex-wrap:wrap;gap:.75rem 1.5rem;padding:.25rem .5rem 1.25rem;font-size:.75rem;color:var(--fw-text-secondary); } .resource-strip strong { color:#dbe5f2;font-weight:500; }
.runtime-version { font-weight:600; } .break-path { overflow-wrap:anywhere; } .runtime-current-badge,.runtime-official-link { display:block;font-size:.8125rem;margin-top:.65rem;color:#9abff6; } .runtime-download { margin-top:.75rem; } .runtime-management .form-input { margin:.5rem 0; }
.preset-selector-block { margin-top:1rem; } .preset-actions { margin-top:1rem; } .parameter-grid { display:grid;grid-template-columns:1fr 1fr;gap:1.25rem;margin-top:1.25rem; } .param-card { min-width:0;border-top:1px solid var(--fw-border);padding-top:1rem; } .full-width { grid-column:1/-1; } .form-row { display:grid;grid-template-columns:1fr 1fr;gap:1rem; } .three-columns { grid-template-columns:repeat(3,1fr); } .form-group { margin-top:1rem; } .suggestion-row,.quick-profile-row { display:flex;flex-wrap:wrap;gap:.5rem;margin-top:.5rem; } .suggestion-chip { font-size:.75rem;padding:.35rem .65rem; } .toggle-stack { display:grid;gap:.75rem;margin-top:1rem; } .toggle-card { display:flex;align-items:center;justify-content:space-between;gap:.75rem;padding:.75rem 0; } .toggle-card strong,.toggle-card small { display:block; } .toggle-card.is-disabled { opacity:.7; } .toggle-card > :last-child { min-width:0; } .note-card { font-size:.8125rem;color:var(--fw-text-secondary); } .note-card ul { padding-left:1.25rem; }
.runtime-release-meta,.runtime-hardware-summary { display:flex;flex-wrap:wrap;gap:1rem;font-size:.8125rem;margin:1rem 0; } .runtime-hardware-summary small { display:block;color:var(--fw-text-secondary); } .runtime-recommendation { color:var(--fw-text-secondary);font-size:.8125rem; } .runtime-variant-grid { display:grid;grid-template-columns:1fr 1fr;gap:.75rem;margin:1rem 0; } .runtime-variant { display:flex;gap:.6rem;border:1px solid #ffffff1c;border-radius:10px;padding:1rem;cursor:pointer; } .runtime-variant.selected { background:var(--fw-primary-soft);border-color:var(--fw-primary); } .runtime-variant.disabled { opacity:.5; } .runtime-variant-content,.runtime-asset-list { display:grid;gap:.4rem;min-width:0;overflow-wrap:anywhere; } .runtime-variant-content small { color:var(--fw-text-secondary); } .recommended-badge { color:#97bdf1;font-size:.7rem;margin-left:.5rem; } .runtime-progress { height:6px;border-radius:5px;overflow:hidden;background:var(--fw-border);margin:.75rem 0; } .runtime-progress span { display:block;height:100%;background:var(--fw-primary); } .runtime-file-progress-head { display:flex;justify-content:space-between;gap:.75rem;font-size:.75rem;overflow-wrap:anywhere; } .runtime-error,.warn-text { color:#e7b867; } .runtime-state-badge { margin-left:.5rem; } .runtime-asset-list b,.runtime-file-progress-head b { margin-right:.5rem; }
.alert { padding:.75rem 1rem;margin:.75rem 0;border-radius:10px;font-size:.875rem; } .alert-error { color:#f4b6bb;background:#dc354515; } .alert-success { color:#9bddb9;background:#32b77812; }
.modal-overlay { position:fixed;inset:0;z-index:1000;background:#060b13cc;backdrop-filter:blur(6px);display:flex;align-items:center;justify-content:center;padding:1rem; } .modal-content { width:100%;max-width:560px;max-height:85vh;overflow:auto;background:var(--fw-surface-raised);border:1px solid #ffffff20;border-radius:18px;padding:1.5rem;box-shadow:0 24px 80px #0008; } .modal-actions { justify-content:flex-end;margin-top:1.25rem; } .summary-grid { display:grid;grid-template-columns:repeat(3,1fr);gap:.75rem;margin-top:.75rem; } .summary-label { display:block;font-size:.75rem;color:var(--fw-text-secondary); } .summary-value { overflow-wrap:anywhere; } .series-item { display:flex;justify-content:space-between;gap:.75rem;margin:1rem 0; }.series-info { display:grid; }.series-patterns { font-size:.8125rem;color:var(--fw-text-secondary); }.series-actions { display:flex;gap:.5rem; }
@media(max-width:960px) { .common-settings { grid-template-columns:1fr 1fr; } .parameter-grid { grid-template-columns:1fr; } .three-columns { grid-template-columns:1fr 1fr; } }
@media(max-width:720px) { .common-settings { grid-template-columns:1fr; } .status-card { padding:1rem; }.status-header,.panel-header { flex-direction:column; }.status-actions { width:100%; }.quick-model-controls { flex-wrap:wrap; }.quick-model-controls > :first-child { flex-basis:calc(100% - 60px); }.quick-model-label { flex-direction:column; }.form-row,.three-columns,.runtime-variant-grid { grid-template-columns:1fr; }.inline-test-actions { align-items:stretch;flex-direction:column; }.runtime-file-progress-head { flex-direction:column; } summary small { display:block;margin-left:0; }.summary-grid { grid-template-columns:1fr 1fr; } }
@media(prefers-reduced-motion:reduce) { button { transition:none; }button:active:not(:disabled) { transform:none; } }
@media(prefers-reduced-transparency:reduce) { .modal-overlay { background:#060b13;backdrop-filter:none; } }
@media(prefers-contrast:more) { .panel,.status-card { border-color:#8b9bb5; }.hint,.status-subtext { color:#d2dbea; } }
</style>
