# Llama.cpp 整合指南

> ⚠️ 目前專案已統一以 **UI2** 作為唯一 GUI 入口。`llama/launcher-ui` 僅保留歷史程式碼，不再建議使用。

## 📦 已完成的整合

### 1. 核心模組

#### `backend/api/llama.py`
完整的 Llama.cpp REST API，包含：
- ✅ 模型列表查詢 (`GET /api/llama/models`)
- ✅ 伺服器啟動 (`POST /api/llama/server/start`)
- ✅ 伺服器停止 (`POST /api/llama/server/stop`)
- ✅ 伺服器狀態查詢 (`GET /api/llama/server/status`)
- ✅ 通用推論 (`POST /api/llama/inference`)
- ✅ 翻譯功能 (`POST /api/llama/translate`)
- ✅ 健康檢查 (`GET /api/llama/health`)

#### `backend/core/llama_manager.py`
Llama.cpp 管理器，提供：
- ✅ 伺服器生命週期管理
- ✅ 模型載入與切換
- ✅ 非同步翻譯介面
- ✅ 通用推論介面
- ✅ 健康檢查機制

#### `backend/core/llm_translator.py`
統一的 LLM 翻譯介面，支援：
- ✅ GPT 翻譯
- ✅ Gemini 翻譯
- ✅ Llama 翻譯
- ✅ 翻譯歷史管理
- ✅ 工廠模式建立

---

## 🚀 使用方式

### 方式 1: 透過 UI2 使用（推薦）

#### 1.1 啟動 UI2 後端
```powershell
cd ui2
.\venv\Scripts\Activate.ps1
python main.py
```

#### 1.2 使用 API

**列出可用模型：**
```bash
curl http://127.0.0.1:8000/api/llama/models?model_dir=G:\models
```

**啟動 Llama 伺服器：**
```bash
curl -X POST http://127.0.0.1:8000/api/llama/server/start \
  -H "Content-Type: application/json" \
  -d '{
    "model_path": "G:\\models\\llama-2-7b-chat.Q4_K_M.gguf",
    "host": "127.0.0.1",
    "port": 8080,
    "n_ctx": 2048,
    "n_gpu_layers": 0,
    "n_threads": 4
  }'
```

**翻譯文字：**
```bash
curl -X POST http://127.0.0.1:8000/api/llama/translate \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello, how are you?",
    "source_lang": "English",
    "target_lang": "Traditional Chinese"
  }'
```

**停止伺服器：**
```bash
curl -X POST http://127.0.0.1:8000/api/llama/server/stop
```

---

### 方式 2: 在程式碼中直接使用

```python
from backend.core.llama_manager import llama_manager
from backend.core.llm_translator import create_translator, TranslationEngine

# 方式 A: 直接使用 llama_manager
llama_manager.start_server(
    model_path="path/to/model.gguf",
    port=8080,
    n_gpu_layers=20  # 使用 GPU
)

translated = await llama_manager.translate(
    text="Hello World",
    source_lang="English",
    target_lang="Traditional Chinese"
)

# 方式 B: 使用統一翻譯器介面
config = {
    "use_llama": True,
    "llama_model": "llama-2-7b-chat"
}
translator = create_translator(config)
result = await translator.translate(
    text="Hello World",
    source_lang="English",
    target_lang="Traditional Chinese"
)
```

---

## 🔧 配置範例

### config.yaml 新增配置

```yaml
translation:
  # 選擇翻譯引擎: gpt, gemini, llama
  engine: llama
  
  # Llama 配置
  llama:
    model_path: "G:\\models\\llama-2-7b-chat.Q4_K_M.gguf"
    server_port: 8080
    n_ctx: 2048
    n_gpu_layers: 20  # 根據你的 GPU 調整
    n_threads: 4
    temperature: 0.3
    max_tokens: 512
  
  # GPT 配置（保留作為備用）
  gpt:
    model: "gpt-3.5-turbo"
    api_key: "your-api-key"
  
  # Gemini 配置（保留作為備用）
  gemini:
    model: "gemini-pro"
    api_key: "your-api-key"
```

---

## 📊 架構圖

```
┌─────────────────────────────────────────────────────────┐
│                      前端應用層                           │
├──────────────────────┬──────────────────────────────────┤
│             UI2 (PyQt6 + Vue)                           │
└──────────────────────┬───────────────────────────────────┘
                       │ HTTP REST API
           ┌──────────▼───────────┐
           │   FastAPI Backend    │
           │  (Port 8000)         │
           └──────────┬───────────┘
                      │
      ┌───────────────┼───────────────┐
      │               │               │
┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
│   GPT     │  │  Gemini   │  │   Llama   │
│ Translator│  │Translator │  │ Manager   │
└───────────┘  └───────────┘  └─────┬─────┘
                                     │
                              ┌──────▼──────┐
                              │ llama-server│
                              │ (Port 8080) │
                              └─────────────┘
```

---

## 🎯 優點總結

### ✅ 統一介面
- UI2 直接整合 Llama 控制能力（模型、啟停、翻譯）
- 單一入口降低學習與維護成本

### ✅ 靈活部署
- 可以獨立使用 UI2（不需要 Electron）
- 可透過 API 供其他程式呼叫

### ✅ 易於擴展
- 新增翻譯引擎只需實作介面
- 支援多種模型切換
- 配置檔統一管理

### ✅ 高效能
- llama.cpp 使用 C++ 實作，速度快
- 支援 GPU 加速
- 本地執行，無需網路

---

## 📝 下一步建議

### 1. 前端整合
在 UI2 的前端 (Vue) 中新增 Llama 控制介面：

```typescript
// frontend/src/services/llamaApi.ts
export const llamaApi = {
  async listModels(modelDir?: string) {
    const params = modelDir ? `?model_dir=${modelDir}` : '';
    const response = await fetch(`/api/llama/models${params}`);
    return response.json();
  },
  
  async startServer(config: ServerConfig) {
    const response = await fetch('/api/llama/server/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config)
    });
    return response.json();
  },
  
  async translate(text: string, sourceLang: string, targetLang: string) {
    const response = await fetch('/api/llama/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, source_lang: sourceLang, target_lang: targetLang })
    });
    return response.json();
  }
};
```

### 2. 設定頁面擴展
在 [SettingsView.vue](cci:1://file:///g:/youtube-live-translator/floatwindow/ui2/frontend/src/views/SettingsView.vue:0:0-0:0) 中新增 "Llama 設定" 分頁：
- 模型選擇器
- GPU 層數調整
- 伺服器啟動/停止按鈕
- 狀態監控

### 3. 效能監控
新增 API 監控伺服器資源使用：
```python
@router.get("/llama/stats")
async def get_stats():
    # 回傳 CPU、記憶體、GPU 使用率
    pass
```

---

## 🐛 故障排除

### 問題 1: llama-server.exe 找不到
**解決方案**：在配置中指定完整路徑
```python
config = {
    "server_exe": "G:\\youtube-live-translator\\floatwindow\\llama\\llama-server.exe"
}
```

### 問題 2: 模型載入失敗
**檢查**：
- 模型檔案是否存在
- 檔案格式是否為 `.gguf`
- 記憶體是否足夠

### 問題 3: 翻譯速度慢
**優化**：
- 啟用 GPU (`n_gpu_layers > 0`)
- 減少 `n_ctx` 長度
- 使用量化模型 (Q4_K_M)

---

## 📚 相關文件

- [llama.cpp 官方文檔](https://github.com/ggerganov/llama.cpp)
- [FastAPI 文檔](https://fastapi.tiangolo.com/)
- [UI2 README](README.md)
- [PROJECT_SUMMARY](PROJECT_SUMMARY.md)

---

**整合完成日期**: 2026-01-22  
**版本**: v1.0.0
