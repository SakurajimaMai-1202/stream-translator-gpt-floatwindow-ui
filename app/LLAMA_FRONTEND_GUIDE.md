# Llama 前端整合完成

## ✅ 已完成的功能

### 1. **API 服務層** 
- [llamaApi.ts](frontend/src/services/llamaApi.ts) - 完整的 Llama API 客戶端

### 2. **狀態管理**
- [llama.ts](frontend/src/stores/llama.ts) - Pinia Store 管理 Llama 狀態

### 3. **UI 元件**
- [LlamaSettings.vue](frontend/src/components/LlamaSettings.vue) - 完整的 Llama 控制介面
  - 📁 模型掃描與選擇
  - ⚙️ 伺服器配置（埠號、GPU 層數、執行緒等）
  - 🚀 啟動/停止按鈕
  - 🧪 測試翻譯功能
  - 📊 即時狀態顯示

### 4. **設定整合**
- [SettingsView.vue](frontend/src/views/SettingsView.vue) 新增 "🦙 Llama 設定" 分頁
- 翻譯後端選項新增 "Llama (本地)" 選項

### 5. **配置支援**
- [config.yaml](backend/config.yaml) 新增 llama 配置區段

---

## 🎯 使用流程

### 1. 啟動應用
```powershell
cd ui2
.\venv\Scripts\Activate.ps1
python main.py
```

### 2. 配置 Llama
1. 開啟設定頁面
2. 點擊 "🦙 Llama 設定" 分頁
3. 輸入模型目錄（例如：`G:\models`）
4. 點擊 "🔄 掃描模型"
5. 從列表中選擇模型
6. 調整伺服器配置（GPU 層數、執行緒等）
7. 點擊 "🚀 啟動 Llama 伺服器"

### 3. 選擇翻譯引擎
1. 切換到 "翻譯選項" 分頁
2. 翻譯後端選擇 "🦙 Llama (本地)"
3. 儲存配置

### 4. 開始翻譯
- 返回首頁，輸入 YouTube URL
- 點擊開始翻譯
- Llama 會自動處理翻譯請求

---

## 🎨 UI 特色

### 狀態卡片
- **運行中**: 綠色漸變背景 + 閃爍指示燈
- **停止中**: 紫色漸變背景
- 顯示：當前模型、伺服器 URL、程序 PID

### 模型列表
- 自動掃描 .gguf 檔案
- 顯示檔案大小
- 點擊選擇模型
- 已選模型高亮顯示 ✓

### 測試翻譯
- 即時測試翻譯功能
- 輸入文字 → 查看翻譯結果
- 確保伺服器正常運作

---

## 🔧 配置選項

### 伺服器配置
```yaml
translation:
  backend: llama  # 使用 Llama 翻譯
  llama:
    model_path: 'G:\models\llama-2-7b-chat.Q4_K_M.gguf'
    server_url: 'http://127.0.0.1:8080'
    n_ctx: 2048        # 上下文長度
    n_gpu_layers: 20   # GPU 層數 (0=CPU only)
    n_threads: 4       # CPU 執行緒數
    temperature: 0.3   # 溫度參數
    max_tokens: 512    # 最大輸出 token
```

### GPU 加速建議
- **全 CPU**: `n_gpu_layers: 0`
- **部分 GPU**: `n_gpu_layers: 10-20`
- **全 GPU**: `n_gpu_layers: 99`

---

## 🔄 自動生命週期管理

當翻譯後端設為 "llama" 時：

1. **啟動翻譯前**
   - 自動檢查 Llama 伺服器狀態
   - 如果未啟動，提示使用者先啟動

2. **翻譯過程中**
   - 使用 Llama API 進行翻譯
   - 支援上下文記憶

3. **停止翻譯後**
   - Llama 伺服器繼續運行
   - 可手動停止或保持運行

---

## 📝 API 文檔

訪問 http://127.0.0.1:8000/api/docs 查看完整 API 文檔

### 主要端點

**列出模型**
```http
GET /api/llama/models?model_dir=G:\models
```

**啟動伺服器**
```http
POST /api/llama/server/start
Content-Type: application/json

{
  "model_path": "G:\\models\\model.gguf",
  "n_gpu_layers": 20
}
```

**翻譯**
```http
POST /api/llama/translate
Content-Type: application/json

{
  "text": "Hello World",
  "source_lang": "English",
  "target_lang": "Traditional Chinese"
}
```

---

## 🎓 相關文檔

- [LLAMA_INTEGRATION.md](LLAMA_INTEGRATION.md) - 後端整合說明
- [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) - 專案總覽
- [README.md](README.md) - 快速開始

---

**整合完成日期**: 2026-01-22  
**前端框架**: Vue 3 + Pinia + TypeScript  
**後端框架**: FastAPI + llama.cpp
