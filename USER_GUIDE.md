# Stream Translator FloatWindow — 使用說明

> 版本：2026-04-04  
> 入口：`cd app` → `python main.py`

---

## 0. 安裝前先理解：哪些會自動裝、哪些不會

### 0.1 Python 套件清單

| 檔案 | 用途 |
|------|------|
| `app/requirements.txt` | 主應用執行用；包含 GUI / API / 核心引擎 / Qwen3-ASR Python 依賴 |
| `app/requirements_full.txt` | 打包機用完整清單；額外包含 PyInstaller |
| `stream-translator-gpt/requirements.txt` | 核心引擎依賴 |
| `stream-translator-gpt/requirements_webui.txt` | 上游舊 WebUI 額外依賴；本專案主流程通常不需要 |

### 0.2 一定要另外準備的外部元件

| 項目 | 說明 |
|------|------|
| **PyTorch** | 要先手動安裝 CUDA 版 |
| **CUDA / cuDNN / NVIDIA Driver** | 原始碼模式必備；不是 pip 套件 |
| **ffmpeg** | 提供音訊轉碼與處理；需在 PATH 或放在專案根目錄，與 `app/` 同層 |
| **Node.js / npm** | 用來建構 `app/frontend/` |
| **llama-server.exe / DLL** | 只有要使用本地 LLM 時才需要；需放在專案根目錄下的 `llama/` |

### 0.3 必要外部檔案放置示意

> **重點先講：** `llama/` 與 `ffmpeg-8.1-essentials_build/` 都要放在**專案根目錄**，也就是和 `app/` **同一層**。

| 項目 | 來源 | 要放哪裡 |
|------|------|----------|
| `llama/` | [llama.cpp Releases](https://github.com/ggerganov/llama.cpp/releases) | 放在專案根目錄，與 `app/` 同層 |
| `ffmpeg-8.1-essentials_build/` | [ffmpeg.org](https://ffmpeg.org/download.html) | 放在專案根目錄，與 `app/` 同層 |
| Qwen3-ASR 模型權重 | 首次啟動自動下載 | 不需要手動擺放 |

### 0.4 資料夾擺放範例

```text
floatwindow/
├── app/
├── llama/
├── ffmpeg-8.1-essentials_build/
├── stream-translator-gpt/
├── README.md
└── USER_GUIDE.md
```

如果 `llama/` 或 `ffmpeg-8.1-essentials_build/` 被放到別的磁碟、別的子資料夾，或塞到 `app/` 裡面，程式就很容易找不到它們。

### 0.5 建議安裝順序（原始碼模式）

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1

# 先安裝 CUDA 版 PyTorch
pip install torch --extra-index-url https://download.pytorch.org/whl/cu124

pip install -r app/requirements.txt

# 若要啟用 Qwen3-ASR 4-bit NF4 量化（可選）
# pip install bitsandbytes
```

> 如果你是使用我**另外打包好的發佈版**，其中可能已經包含 torch / CUDA DLL / ffmpeg / runtime；那種情況就不必照原始碼安裝流程全部重做。

> **重要：本專案文件不提供 CPU 模式。**  
> 雖然部分元件理論上可在 CPU 執行，但 Qwen3-ASR、faster-whisper 與本地 LLM 在 CPU 上的資源消耗與延遲都太高，不符合本專案的實際使用目標。

---

## 1. 系統概覽

Stream Translator FloatWindow 是一套即時語音轉錄與翻譯工具，主要流程：

```
音訊來源 → VAD 切割 → ASR 語音辨識 → LLM 翻譯 → 字幕顯示 / 輸出
```

**支援的音訊來源：**
- YouTube / Twitch / Bilibili / X (Twitter) 直播 URL
- 麥克風輸入
- 系統播放音訊（WASAPI Loopback，捕獲電腦正在播放的聲音）
- 本地音訊 / 影片檔案

---

## 2. 介面頁面說明

### 2.1 Home（首頁）

主要操作頁面，包含：

| 區域 | 說明 |
|------|------|
| **音訊來源** | 下拉選擇：URL / 麥克風 / 系統音訊 / 本地檔案 |
| **URL 輸入** | 貼上直播網址（選 URL 時顯示） |
| **裝置選擇** | 選擇麥克風或音訊輸出裝置（選裝置時顯示） |
| **Start / Stop** | 開始或停止轉錄翻譯任務 |
| **字幕區** | 即時顯示原文與翻譯結果 |
| **字幕分享** | 啟用後可在區網其他裝置以瀏覽器開啟 `http://[本機IP]:8765` 查看即時字幕 |
| **ffmpeg 警告** | 若 ffmpeg 未安裝會顯示黃色警告列 |

**快速使用流程：**

```
1. 選擇音訊來源
2. 貼上網址 或 選擇裝置
3. 點 Start
4. 等待模型載入（首次需下載模型）
5. 字幕開始顯示
```

---

### 2.2 Settings（設定頁）

#### General（一般）

| 選項 | 說明 |
|------|------|
| OpenAI API Key | GPT 翻譯後端的 API 金鑰 |
| Google API Key | Gemini 翻譯後端的 API 金鑰 |
| Log Level | 日誌詳細程度（DEBUG / INFO / WARNING / ERROR） |

#### Input（輸入）

| 選項 | 說明 |
|------|------|
| Source Type | 直播平台類型（youtube / twitch / bilibili / x） |
| Format | yt-dlp 音訊格式（預設 `ba/wa*`） |
| Cookies | `cookies.txt` 路徑（需要登入的頻道使用） |
| Proxy | 下載代理設定 |
| Timeout | 連線逾時秒數 |
| Device Recording Interval | 裝置錄音間隔（秒） |

#### Audio Slicing & VAD（音訊切割）

| 選項 | 說明 |
|------|------|
| Min / Max Audio Length | 送入 ASR 的最短 / 最長片段長度（秒） |
| Chunk Gap Threshold | 靜音切割門檻 |
| VAD Enabled | 啟用 Silero VAD 靜音偵測 |
| VAD Threshold | 語音偵測靈敏度（0~1，越高越嚴格） |
| Realtime Processing | 啟用即時模式（低延遲，準確度稍低） |

#### Transcription（語音辨識）

| 選項 | 說明 |
|------|------|
| **後端選擇** | 三選一：faster-whisper、Qwen3-ASR、OpenAI API |
| Whisper Model | tiny / base / small / medium / large-v2 / large-v3 / large-v3-turbo |
| Qwen3-ASR Model | Qwen3-ASR-1.7B（推薦）或 0.6B（更快） |
| Qwen3 Dtype | bfloat16（推薦）/ float16 / float32 |
| Qwen3 4-bit | 啟用 4-bit NF4 量化（可降低 VRAM 用量，需額外安裝 `bitsandbytes`） |
| Language | 辨識語言（auto / ja / en / zh / ko） |
| Initial Prompt | Whisper 初始提示詞，可提升特定詞彙識別率 |
| Whisper Filters | 過濾器：emoji_filter、repetition_filter |
| Simul Streaming | 啟用同步串流模式（邊辨識邊輸出） |

#### Translation（翻譯）

| 選項 | 說明 |
|------|------|
| Backend | gpt / gemini |
| Target Language | 翻譯目標語言（繁體中文 / 簡體中文 / 日文 / 英文 / 韓文） |
| GPT Model | 模型名稱（如 `gpt-4o-mini`，本地 LLM 填對應名稱） |
| LLM Base URL | OpenAI 相容 API 地址（本地：`http://127.0.0.1:8080/v1`） |
| Translation Prompt | 自訂翻譯指令提示詞 |
| Smart Prompt | 啟用智慧提示詞（根據內容動態調整，提升翻譯品質） |
| Translation History Size | 翻譯上下文歷史數量（0 = 不使用上下文） |
| Translation Timeout | 翻譯 API 逾時秒數 |
| Use JSON Result | 要求翻譯結果以 JSON 格式返回 |
| Custom Models | 自訂模型清單 |

#### Terminology（術語表）

| 選項 | 說明 |
|------|------|
| Use Terminology Glossary | 啟用術語對照表 |
| Glossary | 手動輸入術語對照（格式：`原文=譯文`，每行一條） |

術語表會自動整合進翻譯提示詞，提升特定詞彙（如人名、專有名詞）的翻譯準確度。

#### Output（輸出）

| 選項 | 說明 |
|------|------|
| Output Dir | 字幕輸出目錄 |
| Output SRT | 輸出 `.srt` 字幕檔 |
| Output TXT | 輸出純文字字幕 |
| Output ASS | 輸出 ASS 格式字幕 |
| Max History | 介面顯示的最大字幕歷史條數 |

#### Server（伺服器）

| 選項 | 說明 |
|------|------|
| Public Port | 字幕分享端口（預設 8765） |
| Enable Subtitle Sharing | 啟用區網字幕分享 |

#### Llama Settings（本地 LLM 設定）

| 選項 | 說明 |
|------|------|
| Model Path | `.gguf` 模型檔案路徑 |
| Host / Port | llama-server 監聽地址（預設 127.0.0.1:8080） |
| Context Length | 上下文視窗長度 |
| GPU Layers | 載入至 GPU 的層數（建議大於 0；本專案以 GPU 模式為主） |
| Threads | CPU 輔助執行緒數 |
| Server Executable | llama-server.exe 路徑（留空自動尋找） |

---

### 2.3 Floating Subtitle（浮動字幕）

獨立置頂視窗，適合全螢幕監看時使用。

| 設定 | 說明 |
|------|------|
| 字體大小 / 粗細 | 調整文字大小與粗細 |
| 原文顏色 | 原始語言字幕顏色（預設白色） |
| 譯文顏色 | 翻譯結果字幕顏色（預設黃色） |
| 背景顏色 / 透明度 | 字幕背景顏色與透明度 |
| 位置 | 顯示在視窗上方或下方 |
| 顯示原文 / 譯文 | 分別切換是否顯示 |
| 顯示時間碼 | 是否在字幕旁顯示時間資訊 |
| 最大顯示條數 | 同時顯示的字幕行數 |
| 自動捲動 | 字幕自動滾動至最新 |

---

### 2.4 Desktop Subtitle / Mobile Subtitle

- **Desktop Subtitle**：嵌入主視窗的字幕顯示區塊
- **Mobile Subtitle**：針對行動裝置瀏覽器優化的字幕頁面（透過字幕分享功能存取）

---

### 2.5 ASR 顯卡與翻譯模型建議

#### ASR 模型對應顯卡

| ASR 模型 | 建議 VRAM | 建議顯卡（起跳） | 使用定位 |
|------|------|------|------|
| faster-whisper（tiny / base / small） | 6–8 GB | RTX 3060 12GB / RTX 4060 8GB | 低延遲入門 |
| faster-whisper（medium / large-v3-turbo） | 8–12 GB | RTX 3060 12GB / RTX 4070 12GB | 平衡速度與品質 |
| Qwen3-ASR-0.6B（bf16/fp16） | 8–12 GB | RTX 3060 12GB / RTX 4070 12GB | 主力入門推薦 |
| Qwen3-ASR-1.7B（bf16/fp16） | 12–16 GB | RTX 4070 12GB / RTX 4070 Ti Super 16GB | 品質優先 |
| Qwen3-ASR-1.7B（4-bit） | 8–12 GB | RTX 3060 12GB / RTX 4070 12GB | 降低 VRAM 需求 |

#### 翻譯模型建議（sakura / hymt 1.5 / gemma 4）

| 翻譯模型 | 建議定位 | 推薦搭配 ASR | 備註 |
|------|------|------|------|
| sakura 模型 | 日中翻譯品質優先 | Qwen3-ASR-1.7B / 0.6B | 術語與語氣通常較穩 |
| hymt 1.5 | 低延遲與可讀性平衡 | Qwen3-ASR-0.6B / faster-whisper medium | 適合即時直播場景 |
| gemma 4 | 泛用備援 / 多語場景 | faster-whisper large-v3-turbo / Qwen3-ASR-0.6B | 泛用性高，建議先做領域測試 |

#### 三種常用組合

1. **低延遲優先**：Qwen3-ASR-0.6B + hymt 1.5
2. **品質優先**：Qwen3-ASR-1.7B + sakura 模型
3. **泛用多語**：faster-whisper large-v3-turbo + gemma 4

---

## 3. 常見工作流程

### 流程 A：YouTube 直播即時翻譯

1. 啟動本地 LLM 或確認 API Key 已設定
2. 在 Settings > Transcription 選擇 ASR 後端
3. 在 Settings > Translation 填入翻譯後端與目標語言
4. 回到 Home，選 URL，貼上直播網址
5. 點 Start，等待模型載入後字幕開始顯示

### 流程 B：擷取電腦播放音訊（Loopback）

1. 在 Home 選擇「系統音訊」
2. 選擇對應的音訊輸出裝置
3. 設定辨識語言與目標語言
4. 點 Start
5. 開啟浮動字幕視窗並置頂

### 流程 C：本地 LLM 離線翻譯

1. 準備 `.gguf` 格式模型（如 `Orion-Qwen3.5-2B-SFT-v2603-v1-Q4_K_M.gguf`）
2. 在 Settings > Llama Settings 設定模型路徑與 GPU Layers
3. 點「啟動 Llama Server」
4. 在 Settings > Translation 將 LLM Base URL 填入 `http://127.0.0.1:8080/v1`
5. 正常啟動翻譯任務

---

## 4. 常見問題

<details>
<summary><strong>`requirements.txt` 是不是已經把所有東西都準備好？</strong></summary>

不是。它只會處理 **Python 套件**。像 CUDA、cuDNN、NVIDIA Driver、ffmpeg、Node.js、llama-server 都需要另外準備。
</details>

<details>
<summary><strong>Qwen3-ASR 為什麼特別容易卡在環境？</strong></summary>

因為它除了 Python 套件外，還會受 CUDA 環境、VRAM 大小、是否啟用 4-bit 量化影響。請先確認 `torch.cuda.is_available()` 為 `True`。
</details>

<details>
<summary><strong>為什麼文件不提供 CPU 模式？</strong></summary>

因為 CPU 模式太吃資源、延遲太高，無論是 Qwen3-ASR、faster-whisper，還是本地 LLM，實際體驗都不符合本專案需求，所以文件統一以 CUDA GPU 為準。
</details>

<details>
<summary><strong>ffmpeg 警告怎麼處理？</strong></summary>

將 ffmpeg.exe 加入系統 PATH，或將 `ffmpeg-8.1-essentials_build/` 放在專案根目錄，與 `app/` 同層。
</details>

<details>
<summary><strong>Qwen3-ASR 模型下載很慢？</strong></summary>

首次使用會自動從 HuggingFace 下載（1.7B 約 3.5 GB）。可設定 `HF_ENDPOINT` 環境變數使用鏡像站，或先手動下載放到 HuggingFace cache 目錄。
</details>

<details>
<summary><strong>翻譯沒有回應？</strong></summary>

確認 LLM 服務已啟動，且 Base URL 正確。可在瀏覽器開啟 `http://127.0.0.1:8080/v1/models` 確認 llama-server 是否正常回應。
</details>

<details>
<summary><strong>llama 資料夾要放哪裡？</strong></summary>

請放在專案根目錄下的 `llama/`，也就是和 `app/` 同一層，不要放進 `app/` 裡，也不要散落到其他子資料夾。
</details>

<details>
<summary><strong>YouTube 讀取失敗？</strong></summary>

部分影片或頻道需要提供 cookies。在瀏覽器安裝「Get cookies.txt LOCALLY」擴充套件匯出 `cookies.txt`，再到 Settings > Input > Cookies 填入路徑。
</details>

<details>
<summary><strong>辨識結果有大量重複文字？</strong></summary>

可在 Settings > Transcription > Whisper Filters 確認 `repetition_filter` 已啟用。Qwen3-ASR 通常不需要此過濾器。
</details>

<details>
<summary><strong>字幕分享無法存取？</strong></summary>

確認防火牆允許 Public Port（預設 8765）的連入連線。區網內其他裝置可用 `http://[本機IP]:8765` 存取；若要在非區網內使用，則需要額外進行端口轉發或使用 VPN。
</details>

<details>
<summary><strong>目前這個專案對 Python 版本有沒有建議？</strong></summary>

有。打包腳本目前明確以 **Python 3.10–3.12** 為建議範圍。你現在工作區雖然是 Python 3.13，也許能跑，但如果要打包或追求最穩定，建議改用 3.10–3.12。
</details>

---

## 5. 設定檔說明

設定儲存於 `app/config.yaml`。範本請參考 `app/config.example.yaml`。

設定分為以下區塊：

| 區塊 | 內容 |
|------|------|
| `general` | API Key、日誌層級 |
| `server` | 公開端口、字幕分享 |
| `input` | 音源類型、格式、cookies、代理 |
| `audio_slicing_vad` | 音訊切割與 VAD 參數 |
| `transcription` | ASR 後端與模型設定 |
| `translation` | 翻譯後端、模型、提示詞 |
| `terminology` | 術語表 |
| `output` | 輸出目錄與格式 |


