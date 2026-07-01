<div align="center">
  <h1>Stream Translator FloatWindow</h1>
  <p>Windows 即時語音辨識、翻譯與浮動字幕工具</p>
</div>

<p align="center">
  <a href="https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/releases/latest">下載最新版</a>
  ·
  <a href="#快速開始">快速開始</a>
  ·
  <a href="#常見問題">常見問題</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/GPU-NVIDIA%20CUDA-green" alt="NVIDIA CUDA">
  <img src="https://img.shields.io/badge/python-3.10--3.12-blue" alt="Python">
</p>

<img width="2381" height="1058" alt="Stream Translator FloatWindow screenshot" src="https://github.com/user-attachments/assets/0a663535-dd94-40a6-8444-3c00844bc563" />
<img width="1487" height="955" alt="PixPin_2026-06-09_22-08-51" src="https://github.com/user-attachments/assets/ff88ea18-a40c-4f40-918a-0191e2635e91" />




Stream Translator FloatWindow 是一個給 Windows 使用的即時字幕翻譯工具。它可以讀取直播 URL、麥克風、電腦播放音訊或本地音檔，經過 ASR 語音辨識後交給 GPT、Gemini 或本地 LLM 翻譯，最後顯示在桌面浮動字幕視窗，也可以在區網內分享給手機或平板觀看。

本專案基於 [stream-translator-gpt](https://github.com/ionic-bond/stream-translator-gpt) 擴充桌面 GUI、浮動字幕、模型管理與字幕分享功能。若需要串聯手機端，也可搭配 [SubtitleOverlay](https://github.com/W-Nana/SubtitleOverlay)。

> 本專案需要 Windows 10/11 與 NVIDIA CUDA GPU。不提供 CPU-only 模式。

---

## 適合用途

- 看 YouTube、Twitch、Bilibili、X 等直播時即時翻譯字幕
- 擷取遊戲、播放器、會議或瀏覽器的系統音訊並轉成字幕
- 使用麥克風做即時語音辨識與翻譯
- 用浮動視窗在全螢幕遊戲或影片上方顯示字幕
- 在同一個區網內讓手機、平板或另一台電腦觀看字幕頁面
- 使用本地 LLM 做較私密或離線的翻譯流程

---

## 下載

### 一般使用者推薦

建議從 GitHub Release 依照硬體下載對應的 v1.3.2 完整包，合併分割檔後解壓執行：

- GitHub Release：<https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/releases/latest>

完整包資訊：

| 版本 | GitHub Release 檔案 | 適用情境 |
|------|------|------|
| CUDA | `StreamTranslator-win64-CUDA-Full.zip.part01` ~ `.part03` | NVIDIA CUDA 正式版 |
| CPU | `StreamTranslator-win64-CPU-Full.zip.part01` ~ `.part03` | CPU 相容版 |
| ROCm Experimental | `StreamTranslator-win64-ROCm-Experimental-Full.zip.part01` ~ `.part02` | AMD ROCm/HIP 實驗版 |
| App Update | `StreamTranslator-*-App-Update.zip` | 僅適合同 profile 完整包覆蓋更新 |
| SHA256 | `SHA256SUMS-v1.3.2.txt` | 驗證下載與合併後檔案完整性 |

GitHub Release 因為單檔容量限制，Full package 以分割包提供。

請不要下載 GitHub 自動產生的 `Source code (zip)` 當作執行版；那只是原始碼，不能直接雙擊啟動。

### GitHub 分割包

如果從 GitHub Release 下載，請把以下檔案放在同一個資料夾：

- CUDA Full package（NVIDIA CUDA 正式版）：
  - `StreamTranslator-win64-CUDA-Full.zip.part01`
  - `StreamTranslator-win64-CUDA-Full.zip.part02`
  - `StreamTranslator-win64-CUDA-Full.zip.part03`

- CPU Full package（無 GPU / 相容版）：
  - `StreamTranslator-win64-CPU-Full.zip.part01`
  - `StreamTranslator-win64-CPU-Full.zip.part02`
  - `StreamTranslator-win64-CPU-Full.zip.part03`

- ROCm Experimental Full package（AMD ROCm/HIP 實驗版）：
  - `StreamTranslator-win64-ROCm-Experimental-Full.zip.part01`
  - `StreamTranslator-win64-ROCm-Experimental-Full.zip.part02`

- 建議一起下載：
  - `merge-full-package.bat`
  - `SHA256SUMS-v1.3.2.txt`
  - `RELEASE_NOTES_v1.3.2_zh-TW.md`

合併分割包後會得到對應的 Full zip：

- `StreamTranslator-win64-CUDA-Full.zip`
- `StreamTranslator-win64-CPU-Full.zip`
- `StreamTranslator-win64-ROCm-Experimental-Full.zip`

最簡單的方式：把 `merge-full-package.bat` 和同一組 `.part*` 檔案放在同一個資料夾，雙擊執行即可自動合併。

PowerShell 合併範例（以 CUDA 版為例）：

```powershell
$output = [IO.File]::Create(".\StreamTranslator-win64-CUDA-Full.zip")
try {
  Get-ChildItem ".\StreamTranslator-win64-CUDA-Full.zip.part*" | Sort-Object Name | ForEach-Object {
    $input = [IO.File]::OpenRead($_.FullName)
    try { $input.CopyTo($output) } finally { $input.Dispose() }
  }
} finally {
  $output.Dispose()
}
```

也可以使用 7-Zip 或其他支援分割檔的工具，從 `.part01` 開始合併/解壓。合併後請依照 `SHA256SUMS-v1.3.2.txt` 驗證檔案完整性。

如果只是從同 profile 舊版更新，可以下載對應的 App Update：

- `StreamTranslator-CUDA-App-Update.zip`
- `StreamTranslator-CPU-App-Update.zip`
- `StreamTranslator-ROCm-Experimental-App-Update.zip`

App Update 只能覆蓋同 profile 完整包；不要用 CUDA App Update 覆蓋 CPU 或 ROCm 完整包。

---

## 快速開始

### 使用打包版

1. 從 GitHub Release 依硬體下載 CUDA / CPU / ROCm Experimental 其中一組 Full package 分割包，合併後解壓。
2. 解壓到一個不要含特殊符號的資料夾，例如 `D:\Apps\StreamTranslator`。
3. 執行 `Stream Translator.exe`。
4. 在首頁選擇音源。預設會使用 URL 串流模式。
5. 選擇輸入語言、目標語言、ASR 模型與翻譯後端。
6. 按下「啟動即時轉譯」。

第一次使用 Qwen3-ASR 或 faster-whisper 時，模型可能需要下載或載入，等待時間會比較長。

### 最少要設定什麼

| 設定 | 建議 |
|------|------|
| 音源 | 直播網址選 URL；遊戲或影片選系統音訊；真人講話選麥克風 |
| ASR | 多語混用先用 `Qwen/Qwen3-ASR-1.7B`；日文場景可選 JA fine-tune |
| 翻譯 | 有 API Key 可用 GPT/Gemini；要本地離線可用 llama.cpp 或 LM Studio |
| 目標語言 | 例如繁體中文、英文、日文 |

---

## 功能

| 類別 | 說明 |
|------|------|
| 音源輸入 | URL 直播、本地音檔、麥克風、系統音訊 WASAPI Loopback |
| 語音辨識 | Qwen3-ASR、Qwen3-ASR JA fine-tune、faster-whisper、OpenAI Whisper API |
| 語音切片 | Silero VAD、FireRed VAD， |
| 翻譯後端 | OpenAI GPT、Google Gemini、本地 OpenAI-compatible LLM |
| 浮動字幕 | 置頂字幕視窗，可調字體、顏色、透明度、顯示行數 |
| 字幕分享 | 內建網頁字幕服務，區網裝置可用瀏覽器觀看 |
| 字幕輸出 | 支援 SRT、TXT、ASS 輸出 |
| 術語表 | 自訂詞彙對照，改善角色名、專有名詞與固定譯法 |
| 模型管理 | 在介面內下載、檢查與切換 ASR 模型 |

---

## 模型與硬體建議

如果不想研究太多，先照這樣選：

| 情境 | 建議 |
|------|------|
| 多語言混用 | ASR 用 `Qwen/Qwen3-ASR-1.7B` |
| 日文內容為主 | ASR 可改用 `neosophie/Qwen3-ASR-1.7B-JA` |
| 12GB 顯卡想跑本地翻譯 | `Qwen3-ASR-1.7B + Hy-MT2-7B Q4_K_M` 或 `Gemma 4 E4B Q4` |
| 12GB 顯卡想長時間穩定直播 | `Qwen3-ASR-1.7B + Hy-MT2-1.8B Q4_K_M` |
| 不想佔本地顯存 | ASR 跑本地，翻譯用 GPT / Gemini API |

實際顯存會受到 context 長度、KV cache、GPU offload、llama.cpp / LM Studio / Ollama 設定影響。下面的表格是選型方向，不是絕對值。

### 顯卡組合

| 顯卡 | 推薦組合 | 評價 | 適合情境 |
|------|----------|------|----------|
| 6GB | Qwen3-ASR-0.6B 或 faster-whisper small + API 翻譯 | 穩 | 入門、低延遲 |
| 8GB | Qwen3-ASR-0.6B + Hy-MT2-1.8B Q4_K_M | 很穩 | 本地翻譯入門 |
| 12GB 穩定 | Qwen3-ASR-1.7B + Hy-MT2-1.8B Q4_K_M | 很穩 | 長時間直播、多語字幕 |
| 12GB 品質 | Qwen3-ASR-1.7B + Hy-MT2-7B Q4_K_M | 可用但偏緊 | 多語翻譯品質優先 |
| 12GB 泛用 | Qwen3-ASR-1.7B + Gemma 4 E4B Q4 | 可用但偏緊 | 泛用翻譯、速度與品質平衡 |
| 12GB 日文 | Qwen3-ASR-1.7B / JA fine-tune + Sakura 7B IQ4_XS | 可用 | 日文、Galgame、輕小說語氣 |
| 16GB+ 日文品質 | Qwen3-ASR-1.7B + Sakura 14B IQ4 / Q4 | 推薦 | 日中品質優先 |
| 16GB+ 多語品質 | Qwen3-ASR-1.7B + Hy-MT2-7B Q6_K | 推薦 | 多語翻譯品質優先 |

12GB 顯卡的甜蜜點是 **Qwen3-ASR-1.7B + 4B～7B Q4 翻譯模型**。Hy-MT2-7B Q4_K_M 和 Gemma 4 E4B Q4 值得優先嘗試；如果重視穩定和長時間運行，Hy-MT2-1.8B Q4_K_M 會更保守。

### ASR 選擇

| ASR | 適合情境 |
|-----|----------|
| `Qwen/Qwen3-ASR-1.7B` | 預設推薦，多語混用、品質優先 |
| `neosophie/Qwen3-ASR-1.7B-JA` | 日文內容為主，可作為可選模型 |
| `grider-transwithai/parakeet-ctc-1.1b-ja` | CUDA 版日文 CTC experimental；預設 bfloat16，實測穩態顯存約 4GB，載入峰值略高 |
| Qwen3-ASR-0.6B | 顯存較小、低延遲、保守配置 |
| faster-whisper large-v3-turbo | Whisper 系列穩定性、泛用多語 |
| OpenAI Whisper API | 不想在本機跑 ASR，或想節省顯存 |

### 本地翻譯模型

| 系列 | 推薦模型 | 特性 |
|------|----------|------|
| Hy-MT2 | Hy-MT2-1.8B / 7B Q4 | 翻譯專用，多語場景表現穩 |
| Gemma | Gemma 4 E4B Q4 | 泛用能力好，翻譯與一般文字處理平衡 |
| Sakura | Sakura 7B / 14B IQ4 或 Q4 | 日文到中文、Galgame、輕小說語氣較合適 |

Sakura 系列很適合日文翻譯，但多數 Sakura 模型採非商用授權，公開發布或商業使用前請先確認授權。

### 翻譯後端

| 後端 | Base URL | 適合情境 |
|------|----------|----------|
| OpenAI GPT | `https://api.openai.com/v1` | 品質穩、設定簡單，需要 API Key |
| Google Gemini | 留空或依設定頁提示 | 成本與速度彈性，需要 API Key |
| llama.cpp | `http://127.0.0.1:8080/v1` | 本地離線翻譯 |
| LM Studio | `http://127.0.0.1:1234/v1` | 本地模型管理較方便 |

---

## 常見工作流程

### 翻譯直播 URL

1. 首頁選擇 `URL 串流`。
2. 貼上 YouTube、Twitch、Bilibili 或 X 直播網址,只要可以兼容yt-dlp基本上都可以。
3. 選擇 ASR 與目標語言。
4. 啟動即時轉譯。

部分 YouTube 影片或直播需要 cookies，請在設定頁的輸入選項填入 `cookies.txt`。

### 擷取電腦播放音訊

1. 首頁選擇 `系統音訊`。
2. 選擇目前播放聲音的輸出裝置。
3. 啟動轉譯。

這個模式適合遊戲、播放器、會議或任何不能直接提供直播 URL 的場景。

### 使用本地 LLM 翻譯

1. 準備 llama.cpp、LM Studio 或 Ollama。
2. 啟動本地 LLM server。
3. 在設定頁把翻譯後端設為 OpenAI-compatible API。
4. 填入對應 Base URL，例如 `http://127.0.0.1:8080/v1`。
5. 回到首頁啟動轉譯。

### 分享字幕到手機

1. 啟用字幕分享服務。
2. 確認防火牆允許 port `8765`。
3. 手機連到同一個 Wi-Fi。
4. 用瀏覽器打開 `http://[本機IP]:8765`或是使用[SubtitleOverlay](https://github.com/W-Nana/SubtitleOverlay)


---

## 介面說明

### 首頁

首頁是日常使用的主要畫面：

- 選擇音源：URL、本地檔案、麥克風、系統音訊
- 選擇輸入語言與目標語言
- 切換是否翻譯
- 展開進階設定，調整 ASR 引擎與模型
- 開啟字幕視窗或字幕分享服務

處理流程如下：

```text
音訊來源 -> VAD 切割 -> ASR 語音辨識 -> LLM 翻譯 -> 字幕顯示 / 檔案輸出
```

### 浮動字幕

浮動字幕視窗可以置頂顯示在遊戲、影片或直播上方，支援：

- 原文與譯文分別顯示
- 字體大小、粗細、顏色調整
- 背景透明度與視窗位置調整
- 最大顯示行數限制

### 字幕分享

字幕分享服務會在本機啟動網頁服務。區網內其他裝置可用瀏覽器開啟桌面版或行動版字幕頁，預設 port 是 `8765`。

---

## 常見問題

<details>
<summary><strong>有沒有 CPU 模式？</strong></summary>

沒有。本專案目標是即時語音辨識與翻譯，CPU-only 延遲太高，不符合使用目標。

</details>

<details>
<summary><strong>為什麼第一次啟動很久？</strong></summary>

第一次使用模型時可能需要下載或載入權重。Qwen3-ASR 與 faster-whisper 模型大小從數百 MB 到數 GB 不等，請確認網路和磁碟空間足夠。

</details>

<details>
<summary><strong>YouTube 或直播網址讀不到怎麼辦？</strong></summary>

先確認網址可在瀏覽器播放。若影片需要登入或年齡驗證，請用瀏覽器擴充套件匯出 `cookies.txt`，再到設定頁的 Input / Cookies 填入路徑。

</details>

<details>
<summary><strong>ffmpeg 未偵測到怎麼辦？</strong></summary>

打包版通常已處理常用依賴。若從原始碼執行，請把 ffmpeg 加入系統 PATH，或將 `ffmpeg-8.1-essentials_build/` 放在專案根目錄，與 `app/` 同一層。

</details>

<details>
<summary><strong>翻譯沒有回應怎麼排查？</strong></summary>

確認 API Key、Base URL 與模型名稱是否正確。若使用本地 LLM，可先用瀏覽器打開 `http://127.0.0.1:8080/v1/models` 或對應 server 的 `/v1/models` 測試。

</details>

<details>
<summary><strong>字幕分享手機打不開怎麼辦？</strong></summary>

確認手機和電腦在同一個區網，並允許 Windows 防火牆讓 port `8765` 連入。網址要使用電腦的區網 IP，例如 `http://192.168.1.10:8765`。

</details>

<details>
<summary><strong>辨識結果大量重複怎麼辦？</strong></summary>

如果使用 faster-whisper，請確認設定頁中的 repetition filter 已啟用。若使用 Qwen3-ASR，通常不需要開太強的重複過濾。

</details>

<details>
<summary><strong>為什麼 requirements.txt 沒一起安裝 PyTorch？</strong></summary>

PyTorch 必須依照 CUDA 版本選擇 cu118、cu121、cu124 等不同來源，無法在 requirements 裡替所有使用者寫死。

</details>

---

## 從原始碼執行

一般使用者建議使用打包版。以下流程適合開發、除錯或自行打包。

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1

# 依自己的 CUDA 版本安裝 PyTorch，以下以 CUDA 12.4 為例
pip install torch --extra-index-url https://download.pytorch.org/whl/cu124

pip install -r app/requirements.txt

copy app\config.example.yaml app\config.yaml
cd app
python main.py
```

本地 LLM 和 ffmpeg 的建議位置：

```text
floatwindow/
├── app/
├── llama/
├── ffmpeg-8.1-essentials_build/
└── stream-translator-gpt/
```

---

## 開發者資訊

### 專案結構

```text
stream-translator-gpt-floatwindow-ui/
├── app/
│   ├── main.py                     # PyQt6 WebView 入口
│   ├── windows.py                  # 主視窗與浮動字幕視窗
│   ├── services.py                 # FastAPI 後端與靜態檔服務
│   ├── backend/                    # REST API、設定、模型管理、核心流程
│   ├── frontend/                   # Vue 3 + Tailwind CSS + TypeScript
│   ├── config.example.yaml         # 設定範本
│   ├── requirements.txt            # 執行用依賴
│   └── requirements_full.txt       # 打包用依賴
├── stream-translator-gpt/          # 核心轉錄翻譯引擎 fork
└── README.md
```

### 系統需求

打包版共通需求：

| 項目 | 要求 |
|------|------|
| OS | Windows 10/11 64-bit |
| CPU / RAM | 建議 4 核心以上、16 GB RAM 以上；CPU 版與大型模型會需要更多記憶體 |
| 磁碟空間 | Full package 約 2-4 GB；首次使用模型會另外下載到 `models` 或自訂模型資料夾 |
| Python / Node.js | 一般使用者不需要安裝；只有從原始碼開發或自行打包時需要 |

不同 runtime profile 需求：

| 版本 | GPU / Driver | 備註 |
|------|------|------|
| CUDA | NVIDIA CUDA 相容獨立顯卡；建議 NVIDIA Driver 528+ | CUDA / PyTorch runtime 已包含在 Full package，不需要另外安裝 CUDA Toolkit 或 cuDNN；Parakeet CTC JA 需 CUDA 版 |
| CPU | 不需要獨立顯卡 | 速度較慢，建議先使用 Faster-Whisper small / medium、Qwen3-ASR 0.6B 或 SenseVoiceSmall；保留遠端 API / 遠端字幕能力 |
| ROCm Experimental | 支援 Windows ROCm/HIP 的 AMD 獨立顯卡與相容驅動 | Radeon RX 9070 XT 已由使用者實機確認可用；仍屬實驗版，預設避開 AMD 內顯 / APU，其他 AMD 顯卡如遇問題請附診斷結果 |

開發 / 自行打包需求：

| 項目 | 要求 |
|------|------|
| Python | 3.10-3.12，依目標 profile 準備 CUDA / CPU / ROCm 對應 PyTorch |
| Node.js | 18+，僅前端建構需要 |

---

## Credits

- Core project: [ionic-bond/stream-translator-gpt](https://github.com/ionic-bond/stream-translator-gpt)
- Mobile subtitle reference: [W-Nana/SubtitleOverlay](https://github.com/W-Nana/SubtitleOverlay)
- Local LLM runtime: [ggerganov/llama.cpp](https://github.com/ggerganov/llama.cpp)
