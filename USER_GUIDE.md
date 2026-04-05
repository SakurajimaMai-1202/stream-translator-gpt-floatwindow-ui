# Stream Translator FloatWindow — 設定選項參考

> 本文件為 Settings 各區塊選項的詳細說明。  
> 功能介紹、快速開始、常見問題請見 [README.md](README.md)。

---

## Settings 完整選項參考

### General（一般）

| 選項 | 說明 |
|------|------|
| OpenAI API Key | GPT 翻譯後端的 API 金鑰 |
| Google API Key | Gemini 翻譯後端的 API 金鑰 |
| Log Level | 日誌詳細程度（DEBUG / INFO / WARNING / ERROR） |

### Input（輸入）

| 選項 | 說明 |
|------|------|
| Source Type | 直播平台類型（youtube / twitch / bilibili / x） |
| Format | yt-dlp 音訊格式（預設 `ba/wa*`） |
| Cookies | `cookies.txt` 路徑（需要登入的頻道使用） |
| Proxy | 下載代理設定 |
| Timeout | 連線逾時秒數 |
| Device Recording Interval | 裝置錄音間隔（秒） |

### Audio Slicing & VAD（音訊切割）

| 選項 | 說明 |
|------|------|
| Min / Max Audio Length | 送入 ASR 的最短 / 最長片段長度（秒） |
| Chunk Gap Threshold | 靜音切割門檻 |
| VAD Enabled | 啟用 Silero VAD 靜音偵測 |
| VAD Threshold | 語音偵測靈敏度（0~1，越高越嚴格） |
| Realtime Processing | 啟用即時模式（低延遲，準確度稍低） |

### Transcription（語音辨識）

| 選項 | 說明 |
|------|------|
| 後端選擇 | faster-whisper / Qwen3-ASR / OpenAI API |
| Whisper Model | tiny / base / small / medium / large-v2 / large-v3 / large-v3-turbo |
| Qwen3-ASR Model | 1.7B（推薦）或 0.6B（更快） |
| Qwen3 Dtype | bfloat16（推薦）/ float16 / float32 |
| Qwen3 4-bit | 4-bit NF4 量化（需 `bitsandbytes`） |
| Language | 辨識語言（auto / ja / en / zh / ko） |
| Initial Prompt | Whisper 初始提示詞 |
| Whisper Filters | emoji_filter / repetition_filter |
| Simul Streaming | 同步串流模式（邊辨識邊輸出） |

### Translation（翻譯）

| 選項 | 說明 |
|------|------|
| Backend | gpt / gemini |
| Target Language | 目標語言（繁中 / 簡中 / 日 / 英 / 韓） |
| GPT Model | 模型名稱（本地 LLM 填對應名稱） |
| LLM Base URL | OpenAI 相容 API 地址 |
| Translation Prompt | 自訂翻譯提示詞 |
| Smart Prompt | 智慧提示詞（動態調整） |
| Translation History Size | 翻譯上下文歷史數量 |
| Translation Timeout | API 逾時秒數 |

### Terminology（術語表）

| 選項 | 說明 |
|------|------|
| Use Terminology Glossary | 啟用術語對照表 |
| Glossary | 術語對照（格式：`原文=譯文`，每行一條） |

### Output（輸出）

| 選項 | 說明 |
|------|------|
| Output Dir | 字幕輸出目錄 |
| Output SRT / TXT / ASS | 輸出格式 |
| Max History | 介面最大字幕歷史條數 |

### Server（伺服器）

| 選項 | 說明 |
|------|------|
| Public Port | 字幕分享端口（預設 8765） |
| Enable Subtitle Sharing | 啟用區網字幕分享 |

### Llama Settings（本地 LLM）

| 選項 | 說明 |
|------|------|
| Model Path | `.gguf` 模型檔案路徑 |
| Host / Port | 監聽地址（預設 127.0.0.1:8080） |
| Context Length | 上下文視窗長度 |
| GPU Layers | 載入至 GPU 的層數 |
| Threads | CPU 輔助執行緒數 |
| Server Executable | llama-server.exe 路徑（留空自動尋找） |

---

設定儲存於 `app/config.yaml`，範本請參考 `app/config.example.yaml`。


