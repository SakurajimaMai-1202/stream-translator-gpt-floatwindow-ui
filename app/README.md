# Stream Translator — 使用者教學 README

> 即時擷取 YouTube 直播 / 本地音頻，透過 **Qwen3-ASR** 語音辨識 + **本地 LLM** 翻譯，即時顯示雙語浮動字幕。

> ✅ 目前專案統一以 **UI2** 為唯一 GUI 入口。請優先使用根目錄 `快速啟動_UI2.bat`。
>
> ⚠️ 本文件含少量歷史流程說明（例如分離式手動啟動），主要供開發/除錯參考。

---

## 目錄

1. [功能簡介](#1-功能簡介)
2. [系統需求](#2-系統需求)
3. [取得程式](#3-取得程式)
4. [設定本地 LLM（必要）](#4-設定本地-llm必要)
5. [首次啟動](#5-首次啟動)
6. [操作介面說明](#6-操作介面說明)
7. [常用設定調整](#7-常用設定調整)
8. [浮動字幕視窗](#8-浮動字幕視窗)
9. [打包成 EXE](#9-打包成-exe)
10. [常見問題](#10-常見問題)

---

## 1. 功能簡介

| 功能 | 說明 |
|------|------|
| 語音辨識 | 預設使用 **Qwen3-ASR 1.7B**（本地推理，免費、離線） |
| 翻譯 | 預設使用**本地 LLM**（相容 OpenAI API，例如 llama.cpp server） |
| 輸入來源 | YouTube 直播 URL、本地麥克風、系統音頻（loopback）、影片檔案 |
| 字幕輸出 | 浮動置頂視窗、SRT 檔案、TXT 檔案 |
| 介面 | Vue 3 網頁介面，內嵌 PyQt6 視窗，支援淺色/深色主題 |

---

## 2. 系統需求

| 項目 | 最低需求 |
|------|----------|
| 作業系統 | Windows 10 / 11（64-bit） |
| Python | 3.10 或以上（原始碼執行時需要） |
| Node.js | 18 或以上（開發模式需要） |
| RAM | 建議 8 GB 以上（Qwen3-ASR 1.7B 約佔 4 GB） |
| 磁碟空間 | 約 3 GB（模型 + 程式） |
| GPU | 可選，有 CUDA GPU 可顯著加速 ASR |

---

## 3. 取得程式

### 方式 A：使用打包好的 EXE（推薦一般使用者）

1. 從 [Releases](../../releases) 下載最新 `Stream Translator.zip`。
2. 解壓縮到任意資料夾。
3. 跳至 [第 4 節](#4-設定本地-llm必要) 繼續設定。

### 方式 B：從原始碼執行

```powershell
# 1. 進入 ui2 目錄
cd ui2

# 2. 建立並啟動 Python 虛擬環境
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. 安裝 Python 相依套件
pip install -r requirements.txt

# 4. 安裝前端相依套件
cd frontend
npm install
cd ..

# 5. 複製設定檔
copy config.example.yaml config.yaml

# 6. 啟動（開發模式）
python main.py
```

---

## 4. 設定本地 LLM（必要）

程式預設使用本地 LLM API（`http://127.0.0.1:8080`）進行翻譯。  
**啟動程式前，請先確認本地 LLM 已在背景執行。**

### 推薦方案：llama.cpp server

1. 前往本專案 `llama.cpp` 目錄，或從 [llama.cpp Releases](https://github.com/ggerganov/llama.cpp/releases) 下載 `llama-server.exe`。
2. 準備翻譯用 GGUF 模型（建議 4B 以上，例如 `Qwen2.5-7B-Instruct-Q4_K_M.gguf`）。
3. 啟動伺服器：

```powershell
.\llama-server.exe -m "你的模型路徑.gguf" --port 8080 --ctx-size 4096
```

4. 確認瀏覽器可開啟 `http://127.0.0.1:8080` 看到 llama.cpp 頁面即成功。

> **提示**：如果你的 LLM API 不在 `127.0.0.1:8080`，請在設定頁修改 **Translation > LLM Base URL**。

---

## 5. 首次啟動

### EXE 版本

1. 開啟解壓縮後的資料夾。
2. 雙擊 `Stream Translator.exe`。
3. 第一次啟動時，程式會自動下載 **Qwen3-ASR 1.7B** 模型（約 1.6 GB），需要等待幾分鐘。
4. 載入完成後，主介面會自動出現。

### 原始碼版本

```powershell
cd ui2
.\venv\Scripts\Activate.ps1
python main.py
```

---

## 6. 操作介面說明

### Home（首頁）

| 區域 | 功能 |
|------|------|
| 輸入來源 | 選擇 YouTube URL、麥克風、系統音頻或本地檔案 |
| URL 欄位 | 輸入 YouTube 直播或影片網址 |
| 目標語言 | 選擇翻譯輸出語言（預設：繁體中文） |
| 啟動 / 停止 | 開始或結束即時翻譯 |
| 字幕區 | 即時顯示原文與譯文 |

#### 快速開始翻譯 YouTube 直播

1. 在 URL 欄位貼上直播網址，例如：
   ```
   https://www.youtube.com/watch?v=xxxxxxxxx
   ```
2. 確認目標語言為「Traditional Chinese」（繁體中文）。
3. 點擊「**Start**」。
4. 等待 ASR 模型載入（第一次約 1–2 分鐘），之後字幕會開始出現。

---

### Settings（設定）

點擊右上角齒輪圖示進入設定頁，共有四個分頁：

#### General（一般）
- **Log Level**：日誌詳細程度
- **Cookies**：YouTube 需要登入時使用（貼上 `cookies.txt` 路徑）

#### Transcription（轉錄）
- **Backend**：語音辨識引擎，預設 `Qwen3-ASR`
- **Qwen3-ASR Model**：預設 `Qwen/Qwen3-ASR-1.7B`（可換成 `Qwen/Qwen3-ASR-7B`）
- **Source Language**：來源語言，例如 `ja`（日語）、`en`（英語）、`zh`（中文）

#### Translation（翻譯）
- **Backend**：翻譯引擎，預設 `custom:localllm`（本地 LLM）
- **LLM Base URL**：本地 LLM API 位址，預設 `http://127.0.0.1:8080`
- **Target Language**：翻譯目標語言
- **Translation Prompt**：自訂翻譯提示詞

#### Output（輸出）
- **Output Directory**：字幕檔儲存位置
- **Output SRT**：是否輸出 SRT 字幕檔
- **Max History**：畫面顯示的最多字幕條數

---

## 7. 常用設定調整

### 更換 LLM API 位址

如果你的 LLM 不在預設的 `127.0.0.1:8080`：

1. 進入 **Settings > Translation**。
2. 修改 **LLM Base URL** 為你的實際位址，例如 `http://127.0.0.1:11434`（Ollama）。
3. 修改 **LLM Model Name** 為你的模型名稱。
4. 點擊「Save」。

### 使用 Ollama 作為翻譯後端

1. 安裝並啟動 [Ollama](https://ollama.com/)。
2. 拉取翻譯模型，例如：
   ```bash
   ollama pull qwen2.5:7b
   ```
3. 在設定中：
   - **LLM Base URL**：`http://127.0.0.1:11434/v1`
   - **LLM Model Name**：`qwen2.5:7b`

### 更換 ASR 為更大的 Qwen3-ASR 7B

若辨識精度不足，可換成 7B 版本（約佔 8 GB RAM）：

1. 進入 **Settings > Transcription**。
2. 將 **Qwen3-ASR Model** 改為 `Qwen/Qwen3-ASR-7B`。
3. 儲存設定，重新啟動翻譯。

### 重置所有設定

點擊設定頁右上角「**Reset to Default**」，所有設定會回到初始預設（Qwen3-ASR 1.7B + local LLM）。

---

## 8. 浮動字幕視窗

1. 點擊主介面右上角的「**字幕**」按鈕（或浮動字幕圖示）。
2. 浮動字幕視窗置頂顯示，可拖曳到螢幕任意位置。
3. 在 **Settings > Subtitle** 可調整：

| 設定項 | 說明 |
|--------|------|
| Font Size | 字幕字體大小（預設 24px） |
| Text Color | 原文字體顏色（預設青色 `#55ffff`） |
| Translated Color | 譯文字體顏色（預設黃色 `#FFDD00`） |
| Background Opacity | 背景透明度（0 = 全透明，100 = 不透明） |
| Show Original | 是否顯示原文 |
| Show Translated | 是否顯示譯文 |
| Position | 字幕位置（top / bottom） |

---

## 9. 打包成 EXE

詳細步驟請參考 [打包使用說明.md](打包使用說明.md)。

簡短流程：

```powershell
cd ui2
.\build_exe.ps1
# 輸出位置：ui2/dist/Stream Translator.zip
```

---

## 10. 常見問題

### Q：啟動後一直顯示「Loading model...」怎麼辦？

首次啟動需要從 HuggingFace 下載 Qwen3-ASR 1.7B 模型（約 1.6 GB）。  
請確認網路連線，並耐心等待下載完成。  
若網路受限，可手動下載後放到 HuggingFace 預設快取目錄（`~/.cache/huggingface/`）。

### Q：字幕出現亂碼怎麼辦？

1. 確認 **Settings > Transcription > Source Language** 設定正確（例如日文直播設為 `ja`）。
2. 確認 **Settings > Translation > Translation Prompt** 有指明目標語言。

### Q：翻譯失敗（出現錯誤訊息）怎麼辦？

1. 確認本地 LLM 伺服器正在執行，且可在瀏覽器打開 `http://127.0.0.1:8080`。
2. 確認 **Settings > Translation > LLM Base URL** 位址正確。
3. 查看 `ui2/ui2.log` 取得詳細錯誤資訊。

### Q：如何翻譯成英文以外的語言？

1. 進入 **Settings > Translation**。
2. 修改 **Target Language**，例如 `Traditional Chinese`（繁體中文）、`Japanese`（日文）。
3. 同步修改 **Translation Prompt** 末尾的語言名稱，例如 `Translate the following text to Traditional Chinese`。

### Q：YouTube 因為版權無法擷取音頻怎麼辦？

部分地區封鎖的直播需要提供 `cookies.txt`：

1. 使用瀏覽器擴充功能（例如 `Get cookies.txt LOCALLY`）匯出 YouTube cookies。
2. 在 **Settings > General > Cookies** 填入 `cookies.txt` 的完整路徑。

---

## 授權

本專案採用 [MIT License](LICENSE)。  
語音辨識模型 Qwen3-ASR 請參閱 [Qwen 授權條款](https://huggingface.co/Qwen/Qwen3-ASR-1.7B)。

## ✨ 特色

- 🎨 **現代化介面**: 使用 Vue 3 + Tailwind CSS 打造的美觀 UI
- 🚀 **高效能架構**: FastAPI 非同步後端 + SSE 即時字幕推送
- 🖥️ **原生體驗**: PyQt6 WebView 提供跨平台原生視窗
- 🔄 **熱重載開發**: Vite 開發伺服器支援即時預覽
- 🎯 **浮動字幕**: 可自訂樣式的置頂字幕視窗
- 🤖 **Llama 整合**: 支援本地 Llama 模型進行翻譯
- 📝 **完整配置**: 豐富的設定選項,支援匯入匯出

## 📸 螢幕截圖

<!-- TODO: 新增螢幕截圖 -->

## 📋 專案架構

```
ui2/
├── backend/           # FastAPI 後端
│   ├── api/          # API 路由
│   ├── core/         # 核心邏輯 (ConfigManager, Translator)
│   ├── models/       # Pydantic 資料模型
│   └── config/       # 配置設定
├── frontend/         # Vue 3 前端
│   └── src/
│       ├── views/    # 頁面元件
│       ├── stores/   # Pinia 狀態管理
│       ├── services/ # API 通訊服務
│       └── router/   # 路由設定
└── start_dev.ps1     # 開發環境啟動腳本
```

## 🚀 快速開始

### 前置需求

- Python 3.10+
- Node.js 18+
- [stream-translator-gpt](https://github.com/fortypercnt/stream-translator-gpt) (核心翻譯引擎)

### 安裝 stream-translator-gpt

```bash
pip install stream-translator-gpt
```

或從源碼安裝:
```bash
git clone https://github.com/fortypercnt/stream-translator-gpt.git
cd stream-translator-gpt
pip install -e .
```

### 首次安裝

```powershell
# 1. 建立 Python 虛擬環境
cd ui2
python -m venv venv

# 2. 啟動虛擬環境
.\venv\Scripts\Activate.ps1

# 3. 安裝 Python 依賴
pip install -r requirements.txt

# 4. 安裝前端依賴
cd frontend
npm install
cd ..

# 5. 建立配置檔案
cp config.example.yaml config.yaml
# 編輯 config.yaml 填入您的 API keys 和設定
```

### 配置設定

編輯 `config.yaml` 設定您的參數:

```yaml
general:
  openai_api_key: YOUR_API_KEY  # 如使用 OpenAI
  
translation:
  backend: gpt  # 或 custom (使用 Llama)
  target_language: Traditional Chinese
  
llama:  # 如使用本地 Llama 模型
  model_path: /path/to/your/model.gguf
  n_gpu_layers: 0  # GPU 加速層數
```

詳細配置說明請參考 `config.example.yaml`。


### 方式 1: 使用整合啟動器（推薦）

```powershell
# 在 ui2/ 目錄下，啟動虛擬環境後執行
.\venv\Scripts\Activate.ps1
python main.py              # 開發模式
python main.py --prod       # 生產模式（需先構建）
```

### 方式 2: 使用快速啟動腳本

```powershell
# 自動檢查依賴並啟動
.\run.ps1
```

### 方式 3: 手動啟動（分離模式）

```powershell
# 終端 1: 啟動後端
cd backend
python main.py

# 終端 2: 啟動前端
cd frontend
npm run dev
```

## 訪問應用

- **前端應用**: http://localhost:5173
- **後端 API**: http://127.0.0.1:8000
- **API 文件**: http://127.0.0.1:8000/api/docs

## 功能介面

### 1. Home (首頁)
- URL 輸入與翻譯控制
- 即時狀態顯示
- 最近字幕預覽

### 2. Settings (設定)
- 一般設定 (語言、歷史記錄等)
- 轉錄選項 (Whisper 模型、裝置等)
- 翻譯選項 (GPT 模型、API 設定等)
- 輸出選項 (格式、目錄等)

### 3. Floating Subtitle (浮動字幕)
- 即時字幕顯示
- 可自訂字體大小、顏色、位置
- 透明背景支援

## 技術棧

### 後端
- FastAPI (非同步 Web 框架)
- asyncio (非同步 I/O)
- Server-Sent Events (SSE，即時字幕推送)

### 前端
- Vue 3 (Composition API)
- Vite (建構工具)
- Pinia (狀態管理)
- Vue Router (路由)
- Tailwind CSS (樣式)
- Axios (HTTP 客戶端)

## API 規範

### REST Endpoints

- `GET /api/config` - 獲取配置
- `PATCH /api/config/{section}` - 更新配置區段
- `POST /api/config/reset` - 重置配置
- `POST /api/translation/start` - 啟動翻譯
- `DELETE /api/translation/stop/{task_id}` - 停止翻譯

### SSE Endpoint

- `GET /api/translation/stream/{task_id}` - 即時字幕串流

## 事件格式

```typescript
// 字幕事件
{
  type: 'subtitle',
  data: {
    original: string,
    translated: string
  }
}

// 狀態事件
{
  type: 'status',
  data: {
    message: string
  }
}

// 錯誤事件
{
  type: 'error',
  data: {
    message: string
  }
}
```

## 開發注意事項

- 後端使用絕對導入（而非相對導入）
- 前端透過 Vite proxy 連接後端 API
- SSE 連接需要處理重連邏輯
- 字幕視窗可在獨立視窗開啟

## 構建生產版本

```powershell
# 構建前端並整合至後端
.\build.ps1

# 啟動生產版本
python main.py --prod
```

## 架構說明

### 整合啟動器 (main.py)

整合啟動器自動管理後端和前端的生命週期：

1. **開發模式** (`python main.py`)：
   - 自動啟動 FastAPI 後端 (Port 8000)
   - 自動啟動 Vite 開發伺服器 (Port 5173)
   - 啟動 PyQt6 主視窗（載入 Vite 開發伺服器）

2. **生產模式** (`python main.py --prod`)：
   - 啟動 FastAPI 後端（包含靜態檔案服務）
   - 啟動 PyQt6 主視窗（載入後端靜態檔案）

### PyQt6 視窗

- **HomeWindow**: 主控制介面
- **SettingsWindow**: 設定介面
- **FloatingSubtitleWindow**: 浮動字幕視窗（無邊框、置頂、可拖曳）

## 故障排除

### Port 已被佔用

如果看到 "Port 8000 已被佔用" 錯誤：

```powershell
# 找出佔用 Port 的程序
netstat -ano | findstr :8000

# 結束該程序
taskkill /PID <PID> /F
```

### 前端依賴問題

```powershell
cd frontend
rm -r node_modules
npm install
```

### Python 依賴問題

```powershell
.\venv\Scripts\Activate.ps1
pip install --upgrade -r requirements.txt
```

### ffmpeg 不可用（首頁黃色警告）

UI2 會在首頁啟動時自動檢查 ffmpeg，若不可用會顯示黃色警告列。

可用以下方式快速確認：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/system/check
```

若 `ffmpeg.available` 為 `false`，請依序檢查：

1. 是否可直接執行 `ffmpeg -version`
2. 專案根目錄是否存在 `ffmpeg-8.1-essentials_build\ffmpeg-8.1-essentials_build\bin\ffmpeg.exe`
3. 打包版本是否存在 `ffmpeg\bin\ffmpeg.exe`

修復後重新啟動 UI2 即可。

---

## 🙏 致謝

本專案基於 [stream-translator-gpt](https://github.com/fortypercnt/stream-translator-gpt) 開發,感謝原作者 [fortypercnt](https://github.com/fortypercnt) 提供優秀的核心翻譯引擎。

UI2 專案專注於提供現代化的圖形介面,讓使用者能更方便地使用 stream-translator-gpt 的強大功能。

## 📄 授權

本專案採用 [MIT License](LICENSE) 授權。

## 🤝 貢獻

歡迎提交 Issue 和 Pull Request!

### 開發指南

1. Fork 本專案
2. 建立功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交變更 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 開啟 Pull Request

## 📞 聯絡

如有問題或建議,歡迎開啟 [Issue](https://github.com/YOUR_USERNAME/YOUR_REPO/issues)。

---

**⭐ 如果這個專案對您有幫助,請給個星星支持一下!**
