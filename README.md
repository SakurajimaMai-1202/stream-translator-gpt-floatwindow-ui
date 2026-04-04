# Stream Translator FloatWindow

> 基於 [stream-translator-gpt](https://github.com/ionic-bond/stream-translator-gpt) 開發的桌面圖形介面與浮動字幕前端。  
> 將即時語音辨識與翻譯流程整合進一個可操作的 GUI，並提供可置頂的浮動字幕視窗。

## 功能特色

- **多音源支援**：YouTube / Twitch / Bilibili / X 直播 URL、麥克風、系統播放音訊（WASAPI Loopback）、本地音訊檔案
- **語音辨識（ASR）**：支援 Qwen3-ASR（0.6B / 1.7B，本地 NVIDIA CUDA GPU 推理）、faster-whisper、OpenAI Whisper API
- **即時翻譯**：支援 GPT / Gemini / 本地 LLM（llama.cpp / Ollama，OpenAI 相容 API）
- **智慧提示詞**：自動根據轉錄內容動態調整翻譯提示，提升翻譯品質
- **術語表**：可自定義術語對照，提升專業詞彙識別率
- **浮動字幕視窗**：獨立置頂視窗，可自訂字體、顏色、位置、透明度
- **字幕分享**：內建公開端口（Port 8765），可在區網內其他裝置瀏覽即時字幕
- **字幕輸出**：可輸出 SRT / TXT / ASS 字幕檔
- **VAD 靜音偵測**：整合 Silero VAD，自動切割有效語音片段，降低無效轉錄
- **模型下載管理**：內建 Qwen3-ASR / faster-whisper 模型下載介面

---

## 相依套件與外部元件，一次講清楚

這個專案的依賴分成 **Python 套件** 與 **外部元件** 兩類，`requirements.txt` 只能處理前者。

### Python 套件清單

| 檔案 | 用途 | 目前狀態 |
|------|------|----------|
| `app/requirements.txt` | **主應用執行用**；包含 GUI / FastAPI / `stream-translator-gpt` 核心依賴 / Qwen3-ASR Python 依賴鏈 | **已補齊** |
| `app/requirements_full.txt` | **打包機用完整清單**；額外含 PyInstaller 與完整 ASR 依賴 | **已補齊** |
| `stream-translator-gpt/requirements.txt` | 核心 CLI / 引擎依賴 | 保留原核心用途 |
| `stream-translator-gpt/requirements_webui.txt` | 上游舊版 Gradio WebUI 額外依賴 | **本專案主流程不用** |

### `requirements.txt` 不會自動安裝的東西

| 項目 | 是否由 pip 處理 | 說明 |
|------|------------------|------|
| **PyTorch** | 否（需手動安裝 CUDA 版） | 因為 PyTorch 必須依 CUDA 版本選對安裝來源，不能硬寫死在 `requirements.txt` |
| **CUDA Toolkit / cuDNN / NVIDIA Driver** | 否 | 這些是系統層依賴，不是 Python 套件 |
| **ffmpeg.exe** | 否 | 需自行加入 PATH，或放在 `ffmpeg-8.1-essentials_build/` |
| **Node.js / npm** | 否 | 只用於建構 `app/frontend/` |
| **llama-server.exe / llama DLL** | 否 | 這是外部二進位，需自行放到 `llama/` |

### CUDA / GPU 這件事

- **本專案原始碼模式以 NVIDIA CUDA GPU 為必要條件**
- 不提供 CPU 模式安裝指引，原因是 Qwen3-ASR / faster-whisper / 本地 LLM 在 CPU 上過於吃資源、延遲過高，實務上不適合作為本專案的預設使用方式
- 原始碼模式至少需要：
	1. NVIDIA Driver
	2. 對應 CUDA 環境（本專案目前文件以 **CUDA 12.4** 為主）
	3. 手動安裝 CUDA 版 PyTorch
- 如果你要跑 **Qwen3-ASR 4-bit 量化**，還要另外安裝 `bitsandbytes`
- 如果你是用我另外打包好的版本，CUDA DLL / torch / runtime 可能已隨包攜帶；**原始碼模式不會自動幫你準備這些**

### 目前實際驗證結論

- 目前工作區 `.venv` **已安裝到足以執行本專案的主要 Python 套件**（包含 `torch`、`qwen-asr`、`transformers`、`accelerate`、`faster-whisper`、`openai-whisper`）
- 但目前環境是 **Python 3.13.12**，而 `app/build_exe.ps1` 的打包流程仍以 **Python 3.10–3.12** 為建議與主要支援範圍
- `stream-translator-gpt/requirements_webui.txt` 對應的是上游舊 WebUI；它不是 `app/` 主流程必要條件，**不建議拿它當這個專案的安裝入口**

---

## 專案結構

```
stream-translator-gpt-floatwindow-ui/
├── app/                        # 主應用（PyQt6 + FastAPI + Vue 3）
│   ├── backend/                # FastAPI 後端
│   │   ├── api/                # REST API 路由
│   │   ├── core/               # 翻譯、Llama 管理、設定管理等核心邏輯
│   │   └── models/             # 資料模型
│   ├── frontend/               # Vue 3 前端（含 Tailwind CSS）
│   │   └── src/views/          # 頁面：Home、Settings、浮動字幕、桌面字幕
│   ├── main.py                 # 應用主入口（PyQt6 WebView 容器）
│   ├── config.example.yaml     # 設定範本
│   └── requirements.txt        # Python 相依套件
├── stream-translator-gpt/      # 核心轉錄翻譯引擎（已針對本專案修改）
│   └── stream_translator_gpt/  # 主要模組
├── README.md                   # 本文件
└── USER_GUIDE.md               # 詳細使用說明
```

> **不含於此倉庫，需另外取得：**
> - `llama/`：llama-server 執行檔與 CUDA 函式庫（從 [llama.cpp Releases](https://github.com/ggerganov/llama.cpp/releases) 下載）
> - `ffmpeg-8.1-essentials_build/`：ffmpeg 執行檔（從 [ffmpeg.org](https://ffmpeg.org/download.html) 下載，或加入系統 PATH）
> - Qwen3-ASR 模型：首次啟動時自動從 HuggingFace 下載

---

## 快速開始（Windows）

### 1. 安裝相依套件

```powershell
# 建立虛擬環境（建議）
python -m venv .venv
.venv\Scripts\Activate.ps1

# 先安裝 CUDA 版 PyTorch
pip install torch --extra-index-url https://download.pytorch.org/whl/cu124

# 安裝應用與核心 Python 套件
pip install -r app/requirements.txt

# 若要啟用 Qwen3-ASR 4-bit NF4 量化（可選）
# pip install bitsandbytes

# 安裝前端套件並建構
cd app/frontend
npm install
npm run build
cd ../..
```

> 若你是要**打包發佈版**，請改用 `app/requirements_full.txt`。

### 2. 設定

複製設定範本：

```powershell
copy app\config.example.yaml app\config.yaml
```

用文字編輯器開啟 `app/config.yaml` 填入必要設定（至少設定翻譯後端）。

### 3. 啟動

```powershell
cd app
python main.py
```

瀏覽器或 PyQt6 視窗會自動開啟主介面。

---

## 翻譯後端設定

| 後端 | 說明 | Base URL 範例 |
|------|------|--------------|
| `gpt` | OpenAI GPT API | `https://api.openai.com/v1` |
| `gemini` | Google Gemini API | （留空使用預設） |
| `gpt`（本地） | llama.cpp / Ollama | `http://127.0.0.1:8080/v1` |

本地 LLM 啟動方式：

```powershell
# llama.cpp
llama\llama-server.exe -m 模型路徑.gguf --port 8080

# Ollama
ollama serve
```

---

## 語音辨識後端

| 後端 | 需求 | 說明 |
|------|------|------|
| faster-whisper | NVIDIA CUDA GPU | 輕量，支援多種模型尺寸（tiny → large-v3-turbo） |
| Qwen3-ASR | NVIDIA CUDA GPU | 中日英文效果優異，支援 0.6B / 1.7B，可 4-bit 量化 |
| OpenAI Whisper API | API Key | 雲端辨識，無需本地 GPU |

---

## 常見問題

**為什麼 `requirements.txt` 沒把 CUDA 一起裝好？**  
因為 CUDA、cuDNN、NVIDIA Driver、CUDA 版 PyTorch 都不是一般 `pip install -r requirements.txt` 能安全統一處理的內容，尤其 PyTorch 必須依你的硬體與 CUDA 版本選對安裝來源。

**有沒有 CPU 模式？**  
理論上部分元件可以在 CPU 上執行，但**本專案不把 CPU 模式列為支援工作流**。原因是整體資源消耗與延遲都過高，實務上不符合這個專案「即時字幕翻譯」的目標。

**ffmpeg 未偵測到**  
啟動後首頁若顯示黃色警告，表示 ffmpeg 不在 PATH。  
解法：將 ffmpeg 加入 PATH，或將解壓縮後的資料夾放在專案同層目錄命名為 `ffmpeg-8.1-essentials_build/`。

**llama 功能為什麼不能直接用？**  
因為 `llama-server.exe` 與其 DLL 沒有放進倉庫。若要使用本地 LLM，需自行準備 `llama/` 目錄或使用你另外打包好的版本。

**模型載入中卡住**  
首次使用 Qwen3-ASR 會自動從 HuggingFace 下載（約 1-4 GB），需等待網路傳輸完成。

**翻譯沒有回應**  
確認 LLM 服務已啟動，且 Settings > Translation > LLM Base URL 填寫正確。

**YouTube 無法讀取音訊**  
部分影片需要登入憑證，在 Settings > Input > Cookies 填入 `cookies.txt` 路徑。

---

詳細功能說明與設定選項，請參閱 [USER_GUIDE.md](USER_GUIDE.md)。
