# Stream Translator FloatWindow

Windows 即時語音辨識、翻譯與浮動字幕工具。它能擷取直播網址、系統聲音、麥克風或本機影音，先以本機／雲端 ASR 轉成文字，再交由 OpenAI、Google Gemini 或本機 LLM 翻譯，最後輸出成桌面字幕、區網字幕頁或字幕檔。

[下載最新版](https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/releases/latest) · [v1.4.2 更新說明](app/docs/RELEASE_NOTES_v1.4.2_zh-TW.md) · [回報問題](https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/issues)

![Windows](https://img.shields.io/badge/platform-Windows-lightgrey)
![NVIDIA CUDA](https://img.shields.io/badge/GPU-NVIDIA%20CUDA-green)
![AMD ROCm](https://img.shields.io/badge/GPU-AMD%20ROCm%20Experimental-orange)
![CPU sherpa-onnx](https://img.shields.io/badge/CPU-sherpa--onnx-blueviolet)
![Release](https://img.shields.io/badge/release-v1.4.2-blue)

<img width="2381" height="1058" alt="Stream Translator FloatWindow" src="https://github.com/user-attachments/assets/0a663535-dd94-40a6-8444-3c00844bc563" />

## 演示影片

[觀看 Stream Translator FloatWindow 功能演示](https://youtu.be/p1O2Ecu4js0)

## 適合哪些用途

- 觀看 YouTube、Twitch、Bilibili、X 等直播時產生即時翻譯字幕。
- 擷取遊戲、播放器、瀏覽器或會議軟體的系統聲音。
- 使用麥克風進行即時語音辨識、口譯或會議記錄。
- 將字幕置頂顯示於全螢幕影片或遊戲上方。
- 在同一個區網內，讓手機、平板或另一台電腦同步觀看字幕。
- 使用本機 ASR 與本機 LLM，建立較重視隱私或離線可用的工作流程。

## 功能總覽

處理流程如下：

```text
音訊來源 → VAD 語音切片 → ASR 語音辨識 → ASR 文字修正 → LLM 翻譯 → 術語檢查 → 字幕顯示／匯出
```

| 功能 | 說明 |
|---|---|
| 多種音源 | 支援直播 URL、本機影音、麥克風與 Windows 系統音訊（WASAPI Loopback）。URL 來源透過 yt-dlp 處理，支援範圍取決於網站與 yt-dlp。 |
| 本機與雲端 ASR | 提供 Qwen3-ASR、Fun-ASR、SenseVoice、NVIDIA Parakeet、faster-whisper 與 OpenAI Whisper API；實際選項會依 Runtime Profile 顯示。 |
| Runtime Profile | 提供 CUDA、CPU、ROCm Experimental 三種打包版。CUDA／ROCm Full 包也可透過獨立 sherpa-onnx CPU sidecar 切換到 CPU ASR。 |
| VAD 與即時處理 | 提供 **FireRedVAD**（目前預設，透過 OmniVAD；未指定路徑時使用內建模型）與 **Silero VAD**。VAD 先偵測語音區段再送入 ASR，可調整偵測門檻、動態門檻、計算頻率，以及最短／目標／最長切片長度，在反應速度、句子完整度與 CPU 負載之間取捨。 |
| 多種翻譯後端 | 支援 OpenAI GPT、Google Gemini、OpenAI-compatible API，以及程式內管理的 llama.cpp 本機伺服器。 |
| 浮動字幕 | 置頂字幕視窗支援逐字流式顯示，可調整字型、顏色、透明度、位置與顯示行數；右側紅／綠燈可直接判斷是否正在收音。 |
| 字幕分享 | 內建區網字幕頁與遠端字幕 API，手機、平板或其他電腦可用瀏覽器觀看。 |
| 字幕匯出 | 可保留辨識與翻譯結果，輸出 SRT、TXT、ASS 等格式。 |
| ASR 修正規則 | 在翻譯前修正辨識錯誤，適合人名、作品名與固定誤辨。格式為 `正確詞,誤辨詞1,誤辨詞2`。 |
| 翻譯術語表 | 約束譯文中的固定譯名，格式為 `原文,譯文`。它作用於翻譯階段，與 ASR 修正規則不同。 |
| 模型與 Runtime 管理 | 可在介面內檢查、下載與切換 ASR 模型、GGUF 模型及 llama.cpp Runtime；下載進度與格式會依 GPU／CPU 分流。 |
| 內建更新器 | 支援啟動時檢查 GitHub Release、首頁新版通知、下載進度、SHA-256 驗證、同 Profile 套用與更新回復。 |

> v1.3.11 起，術語表與 ASR 修正規則的 CSV／TSV 匯入支援引號、欄位內逗號、Tab、換行與 UTF-8 BOM；匯出使用 UTF-8 BOM 與 CRLF，方便 Excel 正確辨識繁體中文。

## v1.4.2 更新重點

v1.4.2 的重點包括：

- 修正翻譯排程未及時釋放工作槽，導致前一句要等下一句出現才開始翻譯的問題。
- YouTube 直播音訊停滯時會自動重連、送出斷流前的語音，並持續重試暫時缺失的直播片段。
- 修正弱語音可能被靜默丟棄，以及翻譯逾時後背景請求可能持續累積的問題。
- 關閉直播或程式時會完整清理 ffmpeg、yt-dlp、讀取執行緒與翻譯任務。
- 原生字幕預設高度提高至 300px，舊版 200px 設定也會保留至少 240px，改善只能看到一筆字幕。
- 詞語表與 ASR 校正表改為合併後一次儲存，降低大量 CSV 匯入造成的設定寫入壓力。

完整內容請見 [v1.4.2 更新說明](app/docs/RELEASE_NOTES_v1.4.2_zh-TW.md)。

## 下載：先選對執行版本

請從 [GitHub Releases v1.4.2](https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/releases/tag/v1.4.2) 下載。GitHub 自動提供的 `Source code (zip)` 不是可直接執行的 Windows 完整包。

| 版本 | 適用硬體 | 本機 ASR 路徑 | Full package |
|---|---|---|---|
| CUDA | NVIDIA CUDA 相容獨立顯示卡 | CUDA 原生 ASR；亦含 sherpa-onnx CPU sidecar | `StreamTranslator-win64-CUDA-Full.zip.part01`～`.part03` |
| CPU | 無獨立顯示卡、相容性優先 | sherpa-onnx／ONNX Runtime，不包含 PyTorch | `StreamTranslator-win64-CPU-Full.zip.part01` |
| ROCm Experimental | 支援 Windows ROCm／HIP 的 AMD 獨立顯示卡 | ROCm 原生 ASR；亦含 sherpa-onnx CPU sidecar | `StreamTranslator-win64-ROCm-Experimental-Full.zip.part01`～`.part02` |

ROCm 版本仍屬實驗性支援，能否使用取決於顯示卡、驅動程式與 Windows ROCm Runtime 相容性。若不確定，先使用 CPU 版。

### 合併與安裝 Full package

1. 下載同一 Profile 的全部 `.partXX`，並下載 `merge-full-package.bat`。
2. 將檔案放在同一資料夾，雙擊 `merge-full-package.bat`。
3. 以 `SHA256SUMS-v1.4.2.txt` 驗證合併後的 ZIP。
4. 解壓到一般可寫入路徑，例如 `D:\Apps\StreamTranslator`。
5. 執行 `Stream Translator.exe`。

不要只解壓 `.part01`；CUDA 與 ROCm 完整包必須先合併所有分割檔。

### 更新既有安裝

同一 Profile 的舊版可使用對應 App Update：

- `StreamTranslator-CUDA-App-Update.zip`
- `StreamTranslator-CPU-App-Update.zip`
- `StreamTranslator-ROCm-Experimental-App-Update.zip`

更新器會在套用前備份 `config.yaml`、自訂術語、ASR 修正規則與 Cookies，最多保留五份。App Update 只能套用相同 Profile，不要以 CUDA 更新包更新 CPU 或 ROCm 安裝。

更新包有兩種模式：`app_only` 不包含也不替換 `_runtime`；`runtime_replace` 必須包含完整 Runtime，並會在啟動失敗時回復舊 Runtime。低於最低可直接升級版本的安裝會在下載前提示改用同 Profile Full package。

從 v1.4.0 起，上述流程已整合到「設定 → 一般設定」。從更舊版本首次升級到 v1.4.0 時，請完整解壓相同 Profile 的 App Update；更新包已包含 `StreamTranslatorUpdater.exe`，不需另外下載。

CUDA／ROCm 使用者若缺少 CPU ASR sidecar，可在「ASR 模型管理」內安裝，或下載 `StreamTranslator-CPU-ASR-Sidecar-v1.4.2.zip`。Sidecar 只含 CPU ASR Runtime，模型權重仍需另外下載。

v1.4.2 的 Full package 不包含 `llama` 資料夾。需要本機翻譯時，請在「LLM 模型管理」另外下載 GGUF 與相符的 llama.cpp Runtime。

## 第一次使用教學

### 1. 啟動與確認 Runtime

1. 執行 `Stream Translator.exe`。
2. 開啟「轉錄選項」，確認目前 Runtime Profile 與 ASR 運算模式。
3. CUDA／ROCm 可選「GPU 原生 ASR」或「CPU / sherpa-onnx」；CPU 版固定使用 sherpa-onnx。
4. 切換運算模式後，重新確認 ASR 引擎與模型。這項切換會改變實際 Python Runtime 與模型格式，不只是介面名稱。

### 2. 選擇音訊來源

| 來源 | 適用情境 | 使用方式 |
|---|---|---|
| URL 串流 | YouTube、Twitch、Bilibili、X 或其他 yt-dlp 支援來源 | 貼上網址；受限內容可在輸入設定指定 Netscape 格式 `cookies.txt`。 |
| 系統音訊 | 遊戲、瀏覽器、播放器、會議軟體 | 選擇正在播放聲音的輸出裝置。建議避免同時開啟多個回授裝置。 |
| 麥克風 | 口譯、會議、現場發言 | 選擇麥克風，先觀察音量與 VAD 是否正常觸發。 |
| 本機檔案 | 測試模型、轉錄已下載影音 | 選擇檔案後執行；適合先比較不同模型結果。 |

### 3. 下載並選擇 ASR 模型

1. 開啟「ASR 模型管理」。
2. 確認管理頁目前顯示的是 GPU 還是 CPU 模型。
3. 下載欲使用的模型，等待狀態變成「已下載」。
4. 回到「轉錄選項」，選擇相同 ASR 引擎與模型。
5. 設定輸入語言；固定語言模型會自動限制可選語言。

若開始轉譯時顯示模型缺失，回到模型管理頁檢查「運算後端、引擎、模型 ID」三者是否一致。GPU 權重與 sherpa-onnx CPU bundle 不能互換。

### 4. 設定翻譯

1. 到「翻譯選項」選擇 OpenAI、Gemini 或 OpenAI-compatible／本機 LLM。
2. 設定目標語言。
3. 雲端後端填入各自的 API Key 與模型名稱；本機後端先啟動 llama.cpp、LM Studio 或相容伺服器。
4. 使用設定頁的連線／測試翻譯功能確認回應正常。
5. 回到首頁開啟翻譯。若只需要原文字幕，可關閉翻譯以降低延遲與費用。

OpenAI ASR、OpenAI GPT 翻譯與 Gemini 翻譯的金鑰彼此獨立，不會互相代用。

#### Gemini API Key 詳細流程

1. 登入 [Google AI Studio API Keys](https://aistudio.google.com/app/apikey)，按「Create API key」；若畫面要求選專案，選擇或匯入要使用的 Google Cloud 專案。
2. 複製新建立的 Gemini API Key。請把它當成密碼保管，不要放進 Git、公開截圖或貼文；長時間使用前也請確認 Google 帳戶的配額與計費設定。
3. 回到「設定」→「翻譯選項」，將「翻譯後端」選為「Google Gemini」。
4. 將金鑰貼到「Google Gemini」區塊的「API Key」，模型名稱保留預設值或改成 Google AI Studio 目前可用的 Gemini 模型；API Base URL 保留 `https://generativelanguage.googleapis.com/v1beta`。
5. 按「測試連線」；測試成功後回到首頁，開啟「翻譯」並按「啟動即時轉譯」。

如果測試失敗，先檢查金鑰是否完整、模型名稱是否可用、網路與 Google API 配額是否正常。Google 的金鑰管理與安全規則可能更新，請參考 [Gemini API 金鑰說明](https://ai.google.dev/gemini-api/docs/api-key)。

### 5. 開始轉譯

1. 確認音源、輸入語言、目標語言、ASR 與翻譯後端。
2. 按下「啟動即時轉譯」。首次載入本機模型可能需要較久時間。
3. 先觀察原文字幕：原文已錯時應調整 ASR，而不是先修改翻譯提示詞。
4. 再觀察譯文：原文正確但譯文不佳時，才調整翻譯模型、提示詞或術語表。
5. 需要桌面覆蓋時開啟浮動字幕；需要手機觀看時開啟字幕分享並使用介面顯示的區網網址。

## ASR 模型選擇指南

ASR 決定「聽到了什麼」。選型時依序考慮：硬體與 Runtime、主要語言、準確度、延遲、是否允許音訊上傳。模型管理頁顯示的可用清單是目前 Profile 的最終依據。

### 快速推薦

| 使用情境 | 建議起點 | 原因 |
|---|---|---|
| NVIDIA、多語內容、品質優先 | `Qwen/Qwen3-ASR-1.7B` | 泛用多語與品質取向；顯存不足可改 0.6B 或嘗試 4-bit。 |
| NVIDIA、顯存有限或低延遲 | 優先切換「CPU / sherpa-onnx」Runtime，使用 INT8 Qwen3-ASR 0.6B、Parakeet 0.6B 或 SenseVoiceSmall；若 CPU 效能不足，再改用 GPU Qwen3-ASR 0.6B／faster-whisper small | CPU ASR 不占用顯存，可把有限 VRAM 留給本機翻譯 LLM；是否能維持即時速度取決於 CPU。 |
| NVIDIA、日文動畫／遊戲 | `jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame`；另可比較日文 Parakeet | 日文內容取向；專有名詞仍建議配合 ASR 修正規則。 |
| NVIDIA、英文 | `nvidia/parakeet-tdt_ctc-1.1b` 或 Qwen3-ASR | Parakeet 英文模型為固定語言選擇；Qwen 適合混合語言。 |
| AMD ROCm | 先用 Qwen3-ASR 0.6B，再測 1.7B | ROCm 為 Experimental，從較保守模型開始較容易排除環境問題。 |
| CPU、泛用多語 | sherpa-onnx Qwen3-ASR 0.6B 或 Parakeet TDT 0.6B v3 | INT8 ONNX CPU 路徑，不需 PyTorch 或獨顯。 |
| CPU、日文 | sherpa-onnx Parakeet 0.6B 日文或 SenseVoiceSmall | 固定日文模型方向明確；實際品質請用自己的音源比較。 |
| 中、英、日及中文方言 | Fun-ASR Nano 或 SenseVoiceSmall | 適合亞洲語言情境；Fun-ASR CPU bundle 目前不提供時間戳。 |
| 不想下載模型或占用本機資源 | OpenAI Whisper API | 所有 Profile 可用，但需要網路、API Key，音訊會送往雲端且可能產生費用。 |

### 模型家族比較

| ASR 家族 | 目前用途 | 主要取捨 |
|---|---|---|
| Qwen3-ASR | 0.6B 適合資源保守；1.7B 適合品質優先；另有日文 Anime／Galgame 模型 | 多語泛用，GPU 模型與 CPU ONNX bundle 分開下載。1.7B 需要較多顯存。 |
| NVIDIA Parakeet | 0.6B v3 多語、0.6B 日文、1.1B 英文與 1.1B 日文等固定用途 | CUDA 原生版本依賴 NeMo；CPU 只提供模型管理頁列出的 sherpa-onnx bundle，並非所有 GPU 型號都有 CPU 對應版。 |
| Fun-ASR Nano／MLT Nano | 中文、英文、日文與多語內容 | GPU 與 CPU 格式分開。CPU 目前提供 Nano 2512 bundle；MLT 是否可選以 Profile 能力為準。 |
| SenseVoiceSmall | 中文、粵語、日文、英文等短語音辨識 | 體積與速度取向，適合 CPU 比較；複雜長句請用實際素材驗證。 |
| faster-whisper | Whisper small、medium、large-v3、large-v3-turbo 等 | 成熟的泛用多語路徑；目前打包架構中屬 GPU 原生 Runtime，CPU Profile 請改用 sherpa-onnx 或雲端 ASR。 |
| OpenAI Whisper API | 雲端語音辨識 | 省本機資源但依賴網路、費用與資料上傳政策。 |

### ASR 調整原則

- 先用同一段代表性音訊比較，不要只看模型大小。建議包含安靜對話、背景音樂、快速語速與專有名詞。
- 1.7B 不一定在所有硬體上都比 0.6B 更適合；字幕落後太多時，較小模型的整體體驗可能更好。
- Whisper／faster-whisper 的初始提示詞可協助提供上下文；Parakeet 的現行路徑不使用這個提示詞。
- 人名或作品名被穩定誤辨時，使用 ASR 修正規則；它會在翻譯之前修正文句。
- VAD 可選 FireRedVAD 或 Silero VAD。FireRedVAD 是目前介面預設，透過 OmniVAD 載入；模型路徑留空或填 `auto` 時使用內建模型，也可指定 `.omnivad` 模型。
- 辨識句子過碎或延遲太高時，再調整 VAD 門檻與最短／目標／最長切片。提高 `VAD 計算頻率`欄位的間隔值可降低 CPU 使用量，但會增加語音偵測延遲；VAD、ASR 與翻譯都會影響端到端延遲。

## 翻譯後端與模型選擇指南

翻譯模型決定「如何把正確原文翻成目標語言」。先判斷是否能使用雲端，再依內容類型、隱私、成本與硬體選擇。

### 後端怎麼選

| 後端 | 適合情境 | 優點 | 注意事項 |
|---|---|---|---|
| OpenAI GPT | 希望快速完成設定、重視泛用品質 | 雲端部署簡單、模型選擇彈性 | 需要 OpenAI 翻譯 Key、網路與 API 費用；模型 ID 以帳號實際可用清單為準。 |
| Google Gemini | 重視速度與成本彈性 | 適合大量即時文字 | 需要 Gemini Key；模型名稱與可用性會隨服務更新。 |
| llama.cpp | 希望離線、資料留在本機 | 程式可管理 GGUF、Runtime 與伺服器 | 速度與品質取決於 GGUF、量化、RAM／VRAM、GPU layers 和 context。 |
| LM Studio／其他 OpenAI-compatible API | 已有本機模型伺服器 | 管理與切換模型方便 | Base URL、model id 與伺服器實際回傳值必須一致。 |

常見端點：OpenAI 為 `https://api.openai.com/v1`、程式管理的 llama.cpp 為 `http://127.0.0.1:8080/v1`、LM Studio 常見為 `http://127.0.0.1:1234/v1`。

### 本機翻譯模型怎麼選

以下沿用舊版 README 的選型方向，模型名稱與授權仍應以模型發布頁為準。

| 模型系列 | 建議用途 | 選擇方向 |
|---|---|---|
| Hy-MT2 | 多語翻譯、日常直播字幕 | 1.8B Q4 較省資源、適合長時間運行；7B Q4 品質取向，通常需要更多 RAM／VRAM。 |
| Sakura | 日文到中文、Galgame、輕小說語氣 | 7B 適合中階硬體，14B 適合品質優先；許多 Sakura 模型有非商用限制，使用前務必查閱授權。 |
| Gemma 等泛用模型 | 翻譯兼一般文字理解 | 提示詞遵循能力通常較彈性，但專門翻譯語氣應以實際內容測試。 |

### 依硬體搭配

下表是起始配置，不是保證值。實際占用會受量化格式、context、KV cache、GPU offload、驅動程式與同時運行的 ASR 影響。

| 硬體／目標 | ASR＋翻譯建議 |
|---|---|
| CPU-only | sherpa-onnx 小型 ASR＋GPT／Gemini；若要全本機，使用較小 GGUF 並預期較高延遲。 |
| NVIDIA 6GB | **建議 CPU / sherpa-onnx ASR＋GPU LLM**：ASR 先用 INT8 Qwen3-ASR 0.6B、Parakeet 0.6B 或 SenseVoiceSmall，將 6GB VRAM 優先留給 Hy-MT2 1.8B Q4 等本機翻譯模型。若 CPU ASR 無法即時，再改用 GPU Qwen3-ASR 0.6B／faster-whisper small，並縮小 LLM 或改用雲端翻譯。 |
| NVIDIA 8GB | Qwen3-ASR 0.6B＋Hy-MT2 1.8B Q4；日文可使用 Parakeet＋Hy-MT2 1.8B Q4。 |
| NVIDIA 12GB 穩定優先 | Qwen3-ASR 1.7B＋Hy-MT2 1.8B Q4。 |
| NVIDIA 12GB 品質優先 | Qwen3-ASR 1.7B＋Hy-MT2 7B Q4，但顯存可能偏緊；必要時降低 GPU layers 或讓翻譯部分落到 CPU。 |
| NVIDIA 16GB+ | Qwen3-ASR 1.7B＋Hy-MT2 7B 較高量化，或 Sakura 14B Q4。 |
| AMD ROCm | 先確認 ASR 穩定；翻譯可使用獨立 llama.cpp Runtime 或雲端 API，不要假設 PyTorch ROCm 與 llama.cpp 使用相同後端。 |

### 翻譯品質調整順序

1. 先確認原文 ASR 正確；錯字應在 ASR 階段處理。
2. 確認來源語言、目標語言與模型名稱。
3. 保持「模型翻譯策略」為 `auto`；只有本機模型名稱無法識別時才手動指定 Hy-MT2 等策略。
4. 使用翻譯術語表固定角色名、地名與專業術語。術語表不會修正 ASR 原文。
5. 再依需求調整提示詞、輸出長度、context 與並行數。即時字幕通常重視短回應與穩定延遲，不宜盲目提高輸出上限。

## 教學：使用 hy-mt2-7b-IQ4 本機翻譯

`hy-mt2-7b-IQ4` 是翻譯用 GGUF，不是 ASR 模型。完整流程仍是「音訊 → ASR → Hy-MT2 翻譯 → 字幕」。

1. 在「LLM 模型管理」下載或匯入 `hy-mt2-7b-IQ4.gguf`。
2. 在「Llama 執行設定」下載與硬體相符的 llama.cpp Runtime。GGUF 是模型，Runtime 是執行模型的程式，兩者缺一不可。
3. 選擇模型後設定 Host `127.0.0.1`、Port `8080`、Context 先用 `4096`，GPU layers 使用 `auto` 或依顯存調低。
4. 啟動伺服器，確認狀態為 Running，再執行「測試翻譯」。
5. 到「翻譯選項」選擇本機 LLM／OpenAI-compatible，Base URL 填 `http://127.0.0.1:8080/v1`。
6. Model 填伺服器 `/v1/models` 回傳的 model id；未啟用驗證的 llama.cpp 可使用任意非空 API Key。

若模型載入失敗，先檢查 GGUF 路徑與 Runtime 架構；若顯存不足，降低 GPU layers、context 或改用較小／較低量化模型。CPU ASR sidecar 與 llama.cpp Runtime 是兩套獨立元件，安裝其中一個不會自動提供另一個。

## 字幕分享

啟用字幕分享後，程式會顯示本機與區網網址。其他裝置需與電腦位於同一網路，並使用區網 IP，而不是 `127.0.0.1`。

若手機無法開啟：

- 允許 Windows 防火牆放行程式或對應連接埠。
- 確認路由器未啟用 AP isolation／用戶端隔離。
- 確認服務仍在運行，且手機使用介面顯示的正確網址。
- 不要直接把未加密字幕服務暴露到 Internet；遠端使用請自行加上 HTTPS、驗證或 VPN。

## 媒體輸入注意事項

- v1.4.2 Full package 內含 Node.js 22+，供 yt-dlp 處理需要 JavaScript Runtime 的來源。
- 部分 YouTube／Twitch 內容可能需要登入、地區權限或 cookies；請匯出 Netscape 格式 `cookies.txt`。
- Chromium 的 App-Bound Encryption 可能阻止直接讀取瀏覽器 cookies，匯出檔通常較穩定。
- 系統音訊請選擇實際播放裝置；無聲時先確認 Windows 音量混音器與輸出裝置。

## 設定與資料位置

- 使用者設定：程式可寫入位置的 `config.yaml`
- ASR／LLM 模型：`models` 目錄或模型管理頁顯示的路徑
- 字幕輸出：首頁輸出設定指定的資料夾
- 日誌：程式目錄附近的 `logs`

更新或搬移前請備份設定與自訂規則。若程式位於受保護目錄，Windows 權限可能讓設定寫入其他使用者資料位置。

## 常見問題

### 第一次啟動或第一次辨識很久

模型可能正在下載、驗證或載入。請查看模型管理進度與日誌，不要在下載途中重複啟動。

### 翻譯沒有回應

先用設定頁測試連線。檢查 API Key、Base URL 與 model id；本機伺服器可測試 `/v1/models`。`127.0.0.1:8080` 與 `127.0.0.1:8080/v1` 用途不同，翻譯 Base URL 通常需要 `/v1`。

### 原文錯、譯文也跟著錯

這是 ASR 問題。先更換 ASR 模型、確認輸入語言、檢查音源與 VAD，再用 ASR 修正規則處理穩定出現的專有名詞誤辨。

### 原文正確，但固定譯名不一致

這是翻譯階段問題。加入翻譯術語表，或調整翻譯模型與提示詞；不要把譯名規則放進 ASR 修正表。

### CUDA／ROCm 版切到 CPU 後找不到模型

CPU 模式使用 sherpa-onnx bundle，不會直接使用原生 GPU 權重。到 ASR 模型管理切換至 CPU 分頁，下載對應模型；若 Runtime 缺失，先安裝 CPU ASR sidecar。

## 從原始碼執行

需求：Windows 10／11、Python 3.10～3.12、Node.js 18+、npm、Git 與 FFmpeg。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r .\app\requirements.txt
pip install -e .\stream-translator-gpt

cd .\app\frontend
npm install
npm run build
cd ..\..

Copy-Item .\app\config.example.yaml .\app\config.yaml
cd .\app
python .\main.py
```

原始碼環境不會自動具備三種打包版的 Runtime；PyTorch、CUDA／ROCm 與模型依賴需依目標 Profile 安裝。詳見 [打包說明](app/packaging/README.md)。

## 建立發佈包

```powershell
cd .\app

# 快速驗證
.\build_all_profiles.ps1 -Version 1.4.2 -Mode Quick -ReuseRuntimeCache

# 正式發佈
.\build_all_profiles.ps1 `
  -Version 1.4.2 `
  -Mode Final `
  -ReuseRuntimeCache `
  -CompressionLevel 7 `
  -SplitSizeMiB 1900 `
  -CopyThreads 16
```

正式資產輸出至 `app/release-v1.4.2-assets/`，包含 App Update、Full package 分割檔、manifest 與 SHA-256 清單。

## 專案來源

- 核心專案：[ionic-bond/stream-translator-gpt](https://github.com/ionic-bond/stream-translator-gpt)
- 行動字幕參考：[W-Nana/SubtitleOverlay](https://github.com/W-Nana/SubtitleOverlay)
- 本機 LLM Runtime：[ggerganov/llama.cpp](https://github.com/ggerganov/llama.cpp)
