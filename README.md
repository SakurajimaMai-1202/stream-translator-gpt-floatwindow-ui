# Stream Translator FloatWindow

<p align="center">
  <strong>即時語音辨識 × 翻譯 × 浮動字幕</strong><br>
  基於 <a href="https://github.com/ionic-bond/stream-translator-gpt">stream-translator-gpt</a> 的桌面 GUI 前端
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10--3.12-blue" alt="Python">
  <img src="https://img.shields.io/badge/CUDA-12.4-green" alt="CUDA">
  <img src="https://img.shields.io/badge/platform-Windows-lightgrey" alt="Platform">
</p>

<img width="2381" height="1058" alt="PixPin_2026-04-05_20-48-45" src="https://github.com/user-attachments/assets/0a663535-dd94-40a6-8444-3c00844bc563" />

> **⚠️ 本專案需要 NVIDIA CUDA GPU，不提供 CPU 模式。**
>

---

## 功能一覽

| 類別 | 說明 |
|------|------|
| **音源** | YouTube / Twitch / Bilibili / X 直播 URL、麥克風、系統播放音訊（WASAPI Loopback）、本地音檔 |
| **語音辨識 (ASR)** | Qwen3-ASR（0.6B / 1.7B）、faster-whisper（tiny → large-v3-turbo）、OpenAI Whisper API |
| **翻譯** | OpenAI GPT、Google Gemini、本地 LLM（llama.cpp / Ollama） |
| **浮動字幕** | 獨立置頂視窗，可自訂字體、顏色、透明度 |
| **字幕分享** | 區網內其他裝置可用瀏覽器即時查看字幕（預設 port 8765） |
| **字幕輸出** | SRT / TXT / ASS 檔案匯出 |
| **智慧提示詞** | 根據轉錄內容動態調整翻譯 prompt |
| **術語表** | 自定義術語對照，改善專業詞彙翻譯 |
| **模型管理** | 內建 Qwen3-ASR / faster-whisper 模型下載介面 |

---

## 快速開始

### 使用打包版（推薦）

1. 從 [release]([https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/releases) 下載壓縮包
2. 解壓後直接執行 `Stream Translator.exe`

### 從原始碼執行

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1

# 先安裝 CUDA 版 PyTorch
pip install torch --extra-index-url https://download.pytorch.org/whl/cu124

# 安裝依賴
pip install -r app/requirements.txt

# 啟動
copy app\config.example.yaml app\config.yaml
cd app
python main.py
```

> 使用本地 LLM 需另備 `llama/`（[llama.cpp Releases](https://github.com/ggerganov/llama.cpp/releases)）；  
> ffmpeg 需加入 PATH 或將 `ffmpeg-8.1-essentials_build/` 放在專案根目錄。  
> 兩者都要和 `app/` 放在**同一層**。

---

## 介面與使用方式

程式的處理流程：

```
音訊來源 → VAD 切割 → ASR 語音辨識 → LLM 翻譯 → 字幕顯示 / 輸出
```

### Home（首頁）

首頁是主要操作頁面：

1. **選擇音訊來源** — URL / 麥克風 / 系統音訊 / 本地檔案
2. **填入網址或選裝置** — 依來源類型顯示對應輸入
3. **點 Start** — 等待模型載入後字幕開始顯示
4. **字幕區** — 即時顯示原文與翻譯結果
5. **字幕分享** — 啟用後區網裝置可用 `http://[本機IP]:8765` 看字幕

### Settings（設定頁）

設定內容多，建議按優先順序調整：

| 優先度 | 區塊 | 用途 |
|------|------|------|
| ★★★ | **Input** | 音訊來源類型、URL cookies、裝置選擇 |
| ★★★ | **Transcription** | ASR 後端（Qwen3-ASR / faster-whisper / OpenAI）、模型、語言 |
| ★★★ | **Translation** | 翻譯後端（GPT / Gemini / 本地 LLM）、目標語言、Base URL |
| ★★ | Audio Slicing & VAD | 語音切割長度、VAD 靈敏度 |
| ★★ | Output | 字幕輸出目錄與格式（SRT/TXT/ASS） |
| ★★ | Server | 字幕分享端口 |
| ★ | General | API Key、Log Level |
| ★ | Terminology | 術語對照表 |
| ★ | Llama Settings | 本地 LLM 模型路徑、GPU Layers、上下文長度 |

**第一次使用只要設好 Input / Transcription / Translation 三區就能跑。**

### Floating Subtitle（浮動字幕）

獨立置頂視窗，適合全螢幕時使用。可自訂：

- 字體大小 / 粗細、原文顏色（預設白）、譯文顏色（預設黃）
- 背景透明度、顯示位置、最大顯示條數
- 可分別開關原文 / 譯文顯示

### 字幕分享

啟用後，區網內其他裝置（手機、平板）可用瀏覽器打開 `http://[本機IP]:8765` 即時查看字幕。有桌面版與行動版兩種檢視頁面。

---

## 常見工作流程

### YouTube / Twitch /X 直播翻譯

1. Settings 設好 ASR 與翻譯後端
2. Home → 選 URL → 貼上直播網址 → Start

### 擷取電腦播放音訊

1. Home → 選「系統音訊」→ 選擇輸出裝置 → Start
2. 適合用於遊戲、影片等非直播場景

### 本地 LLM 離線翻譯

1. Settings → Llama Settings → 設定 `.gguf` 模型路徑與 GPU Layers → 啟動 Llama Server
2. Settings → Translation → Base URL 填 `http://127.0.0.1:8080/v1`
3. 正常啟動翻譯

---

## 翻譯後端

| 後端 | Base URL | 說明 |
|------|----------|------|
| OpenAI GPT | `https://api.openai.com/v1` | 需 API Key |
| Google Gemini | （留空） | 需 API Key |
| llama.cpp | `http://127.0.0.1:8080/v1` | 本地，需自備 `llama/` |
| Ollama | `http://127.0.0.1:11434/v1` | 本地，需已有服務 |

---

## ASR 與顯卡建議

| ASR 模型 | 權重大小 | 建議 VRAM | 使用定位 |
|------|------|------|------|
| faster-whisper tiny/base/small | < 0.5 GB | 2–4 GB | 超輕量，延遲最低 |
| faster-whisper medium/large-v3-turbo | 1.5–1.6 GB | 3–5 GB | 速度與品質均衡 |
| faster-whisper large-v3 | ~3 GB | 4–6 GB | Whisper 品質最高 |
| Qwen3-ASR-0.6B | ~1.8 GB | 4–5 GB | 主力入門推薦 |
| Qwen3-ASR-1.7B | ~4 GB | 6–8 GB | 品質優先 |
| Qwen3-ASR-1.7B 4-bit | ~1 GB | 3–5 GB | 低 VRAM 高品質 |

純 ASR 大約 8GB VRAM 就夠；若要同時跑本地 LLM 翻譯，建議 16GB 以上。

## 翻譯模型推薦組合

| 組合 | ASR | 翻譯模型 | 定位 |
|------|-----|----------|------|
| 低延遲 | Qwen3-ASR-0.6B | hymt 1.5 | 即時直播 |
| 品質優先 | Qwen3-ASR-1.7B | sakura | 日中翻譯 |
| 泛用多語 | faster-whisper large-v3-turbo | gemma 4 | 多語場景 |
| **私心推薦** | Qwen3-ASR-1.7B 4-bit | gemma 4 E4B | 快又好 |

---

## 常見問題

<details>
<summary><strong>有沒有 CPU 模式？</strong></summary>
本專案不提供。即時語音辨識＋翻譯在 CPU 上延遲過高，不符合使用目標。
</details>

<details>
<summary><strong>ffmpeg 未偵測到</strong></summary>
將 ffmpeg 加入系統 PATH，或將 <code>ffmpeg-8.1-essentials_build/</code> 放在專案根目錄（與 <code>app/</code> 同層）。
</details>

<details>
<summary><strong>模型載入很慢 / 卡住</strong></summary>
首次使用會自動從 HuggingFace 下載（1–4 GB），請確認網路暢通。可設定 <code>HF_ENDPOINT</code> 環境變數使用鏡像站。
</details>

<details>
<summary><strong>翻譯沒有回應</strong></summary>
確認 LLM 服務已啟動，且 Base URL 正確。可在瀏覽器開 <code>http://127.0.0.1:8080/v1/models</code> 確認。
</details>

<details>
<summary><strong>YouTube 讀取失敗</strong></summary>
部分影片需要 cookies。用瀏覽器擴充套件匯出 <code>cookies.txt</code>，在 Settings → Input → Cookies 填入路徑。
</details>

<details>
<summary><strong>辨識結果大量重複</strong></summary>
在 Settings → Transcription → Whisper Filters 確認 <code>repetition_filter</code> 已啟用。Qwen3-ASR 通常不需要。
</details>

<details>
<summary><strong>字幕分享無法存取</strong></summary>
確認防火牆允許 port 8765 連入。區網裝置用 <code>http://[本機IP]:8765</code> 存取。
</details>

<details>
<summary><strong>llama 功能無法使用</strong></summary>
<code>llama-server.exe</code> 不隨倉庫提供。請從 <a href="https://github.com/ggerganov/llama.cpp/releases">llama.cpp Releases</a> 下載，放入專案根目錄下的 <code>llama/</code>。
</details>

<details>
<summary><strong>為什麼 requirements.txt 沒一起裝 PyTorch？</strong></summary>
PyTorch 必須依 CUDA 版本選擇安裝來源（cu118/cu121/cu124），無法寫死。CUDA Toolkit / Driver 則是系統層依賴。
</details>

---

<details>
<summary><h2>開發者資訊</h2></summary>

### 專案結構

```
stream-translator-gpt-floatwindow-ui/
├── app/
│   ├── main.py                     # 入口（PyQt6 WebView 容器）
│   ├── windows.py                  # 視窗管理
│   ├── services.py                 # FastAPI 後端 + 靜態檔服務
│   ├── backend/                    # REST API / 核心邏輯 / 資料模型
│   ├── frontend/                   # Vue 3 + Tailwind CSS + TypeScript
│   ├── config.example.yaml         # 設定範本
│   ├── requirements.txt            # 執行用依賴
│   └── requirements_full.txt       # 打包用依賴（含 PyInstaller）
├── stream-translator-gpt/          # 核心轉錄翻譯引擎（fork）
└── README.md
```

### 系統需求

| 項目 | 要求 |
|------|------|
| OS | Windows 10/11 64-bit |
| GPU | NVIDIA CUDA 相容顯卡，Driver ≥ 528 |
| CUDA | 12.4+（建議） |
| Python | 3.10–3.12 |
| Node.js | ≥ 18（僅前端建構需要） |

### 外部檔案放置

`llama/` 與 `ffmpeg-8.1-essentials_build/` 都放在**專案根目錄**（與 `app/` 同層）。

```text
floatwindow/
├── app/
├── llama/
├── ffmpeg-8.1-essentials_build/
└── stream-translator-gpt/
```

</details>
