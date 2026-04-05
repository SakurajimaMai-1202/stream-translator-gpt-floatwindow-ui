# Stream Translator FloatWindow

<p align="center">
  <strong>即時語音辨識 × 翻譯 × 浮動字幕</strong><br>
  基於 <a href="https://github.com/ionic-bond/stream-translator-gpt">stream-translator-gpt</a> 的桌面 GUI 前端
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10--3.12-blue" alt="Python">
  <img src="https://img.shields.io/badge/CUDA-12.4-green" alt="CUDA">
  <img src="https://img.shields.io/badge/platform-Windows-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/license-GPLv3-orange" alt="License">
</p>

---

## 簡介

Stream Translator FloatWindow 將即時語音辨識與翻譯整合進一個可操作的 GUI 應用程式，支援多種音源輸入與辨識 / 翻譯後端。核心亮點包括：

- 可置頂的**浮動字幕視窗**，支援字體、顏色、透明度等自訂
- 區網**字幕分享**端口，讓其他裝置也能同步看到字幕
- 內建**模型下載管理**介面，一鍵取得 Qwen3-ASR / faster-whisper 模型

> **⚠️ 本專案需要 NVIDIA CUDA GPU，不提供 CPU 模式。**
> ** 建議至Release 下載可攜式執行包
---

## 功能一覽

| 類別 | 說明 |
|------|------|
| **音源** | YouTube / Twitch / Bilibili / X 直播 URL、麥克風、系統播放音訊（WASAPI Loopback）、本地音檔 |
| **語音辨識 (ASR)** | Qwen3-ASR（0.6B / 1.7B）、faster-whisper（tiny → large-v3-turbo）、OpenAI Whisper API |
| **翻譯** | OpenAI GPT、Google Gemini、本地 LLM（llama.cpp / Ollama，OpenAI 相容 API） |
| **智慧提示詞** | 根據轉錄內容動態調整翻譯 prompt，提升翻譯品質 |
| **術語表** | 使用者自定義術語對照，改善專業詞彙翻譯 |
| **浮動字幕** | 獨立置頂視窗，可自訂字體大小、粗細、顏色、位置、透明度 |
| **字幕分享** | 內建公開端口（預設 8765），區網內其他裝置可瀏覽即時字幕 |
| **字幕輸出** | SRT / TXT / ASS 檔案匯出 |
| **VAD** | 整合 Silero VAD，自動切割有效語音、降低無效轉錄 |
| **模型管理** | 內建 Qwen3-ASR / faster-whisper 模型下載與管理介面 |

---

## 專案結構

```
stream-translator-gpt-floatwindow-ui/
├── app/                            # 主應用程式
│   ├── main.py                     # 入口（PyQt6 WebView 容器）
│   ├── windows.py                  # 視窗管理（Home / Settings / FloatingSubtitle）
│   ├── services.py                 # FastAPI 後端 + 前端靜態檔服務
│   ├── backend/
│   │   ├── api/                    # REST API 路由（config / translation / llama / models）
│   │   ├── core/                   # 翻譯管理、Llama 管理、設定管理、模型下載、系統檢查
│   │   └── models/                 # 資料模型
│   ├── frontend/                   # Vue 3 + Tailwind CSS + TypeScript
│   │   └── src/views/              # HomeView / SettingsView / FloatingSubtitleView / ...
│   ├── config.example.yaml         # 設定範本
│   ├── requirements.txt            # 執行用 Python 相依套件
│   └── requirements_full.txt       # 打包用完整相依套件
├── stream-translator-gpt/          # 核心轉錄翻譯引擎（fork，已針對本專案修改）
│   └── stream_translator_gpt/      # 主模組
├── README.md
└── USER_GUIDE.md                   # 詳細使用說明
```

## 必要外部檔案放置示意

> **重點先講：** `llama/` 與 `ffmpeg-8.1-essentials_build/` 都要放在**專案根目錄**，也就是和 `app/` **同一層**。

| 項目 | 來源 | 要放哪裡 |
|------|------|----------|
| `llama/` | [llama.cpp Releases](https://github.com/ggerganov/llama.cpp/releases) | 放在專案根目錄，與 `app/` 同層 |
| `ffmpeg/` | [ffmpeg.org](https://ffmpeg.org/download.html) | 放在專案根目錄，與 `app/` 同層 |
| Qwen3-ASR 模型權重 | 首次啟動自動下載 | 不需要手動擺放 |

### 資料夾擺放範例

```text
floatwindow/
├── app/
├── llama/
├── ffmpeg/
├── stream-translator-gpt/
├── README.md
└── USER_GUIDE.md
```

如果 `llama/` 或 `ffmpeg/` 被放到別的磁碟、別的子資料夾，或塞到 `app/` 裡面，程式通常就會開始進入「找不到你，但我很努力」模式。

---

## 系統需求

| 項目 | 要求 |
|------|------|
| 作業系統 | Windows 10 / 11（64-bit） |
| GPU | NVIDIA CUDA 相容顯示卡 |
| NVIDIA Driver | ≥ 528（支援 CUDA 12） |
| CUDA Toolkit | 12.4以上（建議） |
| Python | 3.10 – 3.12 |
| Node.js | ≥ 18（僅前端建構需要） |

---

## 快速開始

### 1. 先確認資料夾位置

請先確認：

- `app/`
- `llama/`
- `ffmpeg/`

這三者位於同一層。

### 2. 安裝 Python 相依套件

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1

# 安裝 CUDA 版 PyTorch（必須先於其他套件）
pip install torch --extra-index-url https://download.pytorch.org/whl/cu124

# 安裝主應用所有 Python 相依套件
pip install -r app/requirements.txt
```

> 若要使用 Qwen3-ASR 4-bit NF4 量化，可另外安裝 `bitsandbytes`。

### 3. 複製設定並啟動

```powershell
copy app\config.example.yaml app\config.yaml
cd app
python main.py
```

編輯 `app/config.yaml`，至少填入翻譯後端設定後即可啟動。

PyQt6 視窗會自動開啟主介面。

> **打包發佈版**請改用 `app/requirements_full.txt`，其中額外包含 PyInstaller。

---

## 相依套件說明

### pip 可安裝的部分

| 檔案 | 用途 |
|------|------|
| `app/requirements.txt` | 主應用執行用：GUI / FastAPI / 核心引擎 / Qwen3-ASR 依賴鏈 |
| `app/requirements_full.txt` | 打包機用完整清單（含 PyInstaller） |
| `stream-translator-gpt/requirements.txt` | 核心引擎依賴（由 `app/requirements.txt` 自動引用） |

### 需要手動安裝的外部元件

| 項目 | 說明 |
|------|------|
| **CUDA 版 PyTorch** | 必須依 CUDA 版本選擇正確安裝來源，無法寫死在 requirements.txt |
| **CUDA Toolkit / cuDNN / NVIDIA Driver** | 系統層依賴，非 Python 套件 |
| **ffmpeg** | 音訊轉碼處理；加入 PATH，或將 `ffmpeg-8.1-essentials_build/` 放在專案根目錄，與 `app/` 同層 |
| **Node.js / npm** | 僅前端建構時需要 |
| **llama-server.exe / DLL** | 使用本地 LLM 時才需要；請放入專案根目錄下的 `llama/` 資料夾，與 `app/` 同層 |

---

## 語音辨識 (ASR) 後端

| 後端 | 模型 | 說明 |
|------|------|------|
| **Qwen3-ASR** | 0.6B / 1.7B | 中日英辨識效果優異；支援 4-bit 量化；首次使用自動下載 |
| **faster-whisper** | tiny → large-v3-turbo | 輕量快速，多語言支援 |
| **OpenAI Whisper API** | whisper-1 | 雲端辨識，需 API Key，無需本地 GPU |

所有本地 ASR 後端均需 NVIDIA CUDA GPU。

---

## ASR 模型對應顯卡建議

> 參數量來源：HuggingFace 模型頁；VRAM 來源：faster-whisper 官方 benchmark（RTX 3070 Ti，CUDA 12.4）& 模型權重估算。
> Qwen3-ASR 名稱中的 0.6B / 1.7B 為語言模型部分；含音訊編碼器後實際載入參數量分別約 **0.9B** 與 **2B**。

| ASR 模型 | 參數量 / 權重大小 | 建議 VRAM | 建議顯卡（起跳） | 使用定位 |
|------|------|------|------|------|
| faster-whisper（tiny / base / small） | 39M–244M / < 0.5 GB | 2–4 GB | GTX 1060 6GB 以上 | 超輕量，延遲最低 |
| faster-whisper（medium / large-v3-turbo） | 769M–809M / 1.5–1.6 GB fp16 | 3–5 GB | GTX 1070 8GB / RTX 3060 | 速度與品質均衡 |
| faster-whisper（large-v3） | 1.55B / ~3 GB fp16 | 4–6 GB | RTX 3060 12GB / RTX 4060 8GB | Whisper 品質最高 |
| Qwen3-ASR-0.6B（bf16/fp16） | 0.9B / ~1.8 GB | 4–5 GB | RTX 3060 12GB / RTX 4060 8GB | 主力入門推薦 |
| Qwen3-ASR-1.7B（bf16/fp16） | 2B / ~4 GB | 6–8 GB | RTX 3060 12GB / RTX 4070 12GB | 品質優先 |
| Qwen3-ASR-1.7B（4-bit NF4） | 2B / ~1 GB（量化後） | 3–5 GB | GTX 1070 8GB / RTX 3060 | 低 VRAM，高品質 |

### 顯卡檔位建議

- **最低可用**：GTX 1070 8GB（faster-whisper 全系列 / Qwen3-ASR 4-bit 均可）
- **甜蜜點**：RTX 3060 12GB / RTX 4060 8GB（覆蓋所有 ASR 模型）
- **高階穩定**：RTX 4070 12GB 或以上（ASR + 本地 LLM 同機共跑更順）

請注意看VRAM大小即可 目前純ASR其實8GB就能跑,若真的要連LLM翻譯一起跑建議是16G比較適合 上面只是參考建議
目前測試過主要在用的為qwen3-asr-1.7b-4bit+gemma-4-E4B 目前效果挺不錯的 也很快 

---

## 翻譯模型建議（sakura / hymt 1.5 / gemma 4）

| 翻譯模型 | 建議定位 | 推薦搭配 ASR | 備註 |
|------|------|------|------|
| sakura 模型 | 日中翻譯品質優先 | Qwen3-ASR-1.7B / 0.6B | 術語與語氣通常較穩 |
| hymt 1.5 | 低延遲與可讀性平衡 | Qwen3-ASR-0.6B / faster-whisper medium | 適合即時直播場景 |
| gemma 4 | 泛用備援 / 多語場景 | faster-whisper large-v3-turbo / Qwen3-ASR-0.6B | 泛用性高，建議先做領域測試 |

### 推薦組合

- **低延遲優先**：Qwen3-ASR-0.6B + hymt 1.5
- **品質優先**：Qwen3-ASR-1.7B + sakura 模型
- **泛用多語**：faster-whisper large-v3-turbo + gemma 4
- **私心推薦**: Qwen3-ASR-1.7B（4-bit NF4）+ gemma 4（E4B）
---

## 翻譯後端

| 後端 | Base URL 範例 | 說明 |
|------|--------------|------|
| OpenAI GPT | `https://api.openai.com/v1` | 需 API Key |
| Google Gemini | （留空使用預設） | 需 API Key |
| 本地 LLM (llama.cpp) | `http://127.0.0.1:8080/v1` | 需另外自行準備 `llama/` 目錄 |
| 本地 LLM (Ollama) | `http://127.0.0.1:11434/v1` | 需本機已有可用服務 |

若要使用本地 LLM，請記得把所需的 `llama/` 資料夾放在專案根目錄下，與 `app/` 同一層，讓應用程式能正確找到執行檔與相關 DLL。

---

## 常見問題

<details>
<summary><strong>有沒有 CPU 模式？</strong></summary>

本專案不提供 CPU 模式。即時語音辨識與翻譯的資源消耗和延遲在 CPU 上過高，不符合「即時字幕翻譯」的使用目標。
</details>

<details>
<summary><strong>為什麼 requirements.txt 沒把 PyTorch / CUDA 一起裝好？</strong></summary>

PyTorch 必須依照你的 CUDA 版本選擇對應安裝來源（`cu118`、`cu121`、`cu124` 等），無法在 requirements.txt 中硬寫死。CUDA Toolkit、cuDNN、NVIDIA Driver 則是系統層依賴，不屬於 Python 套件。
</details>

<details>
<summary><strong>ffmpeg 未偵測到</strong></summary>

啟動後首頁若出現黃色警告，表示 ffmpeg 不在 PATH。將 ffmpeg 加入系統 PATH，或將解壓縮後的資料夾放在專案同層目錄並命名為 `ffmpeg-8.1-essentials_build/`。
</details>

<details>
<summary><strong>llama 功能為什麼無法使用？</strong></summary>

`llama-server.exe` 與相關 DLL 不隨此倉庫提供。請從 [llama.cpp Releases](https://github.com/ggerganov/llama.cpp/releases) 下載對應 CUDA 版本的 binary，並放入專案根目錄下的 `llama/` 目錄，與 `app/` 同層。
</details>

<details>
<summary><strong>模型載入卡住</strong></summary>

首次使用 Qwen3-ASR / faster-whisper 模型會自動從 HuggingFace 下載（約 1–4 GB），請確認網路暢通並耐心等待。
</details>

<details>
<summary><strong>翻譯沒有回應</strong></summary>

確認 LLM 服務已啟動，並在 Settings → Translation → LLM Base URL 填寫正確的位址。
</details>

<details>
<summary><strong>YouTube 無法讀取音訊</strong></summary>

部分影片需要登入憑證。在 Settings → Input → Cookies 填入你的 `cookies.txt` 路徑。
</details>

---

另行有提供打包完成的版本避免冗長的安裝依賴流程


---

更完整的操作說明與設定選項，請參閱 [USER_GUIDE.md](USER_GUIDE.md)。
