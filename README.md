# Stream Translator FloatWindow

**Windows 即時語音辨識、翻譯與浮動字幕工具。**

將直播、影片、遊戲或麥克風音訊轉為原文與翻譯字幕，透過桌面浮動視窗或區網字幕頁呈現。可依硬體與使用需求，選擇本機模型、雲端服務，或兩者搭配的處理方式。

[下載最新版](https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/releases/latest) · [更新說明](app/docs/RELEASE_NOTES_v1.5.0_zh-TW.md) · [操作指南](USER_GUIDE.md) · [觀看示範](https://youtu.be/p1O2Ecu4js0) · [回報問題](https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/issues)

![Version](https://img.shields.io/badge/version-v1.5.0-blue)
![Windows](https://img.shields.io/badge/platform-Windows-lightgrey)
![CPU](https://img.shields.io/badge/ASR-CPU-blueviolet)
![CUDA](https://img.shields.io/badge/ASR-NVIDIA%20CUDA-green)
![ROCm](https://img.shields.io/badge/ASR-ROCm%20Experimental-orange)

## 主要功能

| 功能 | 說明 |
| --- | --- |
| 多種音訊來源 | 支援直播網址、本機影音、麥克風、Windows 系統音訊與指定應用程式音訊。 |
| 即時辨識與翻譯 | 提供多種語音辨識引擎，可搭配 OpenAI、Google Gemini、OpenAI-compatible API 或本機翻譯模型。 |
| 桌面浮動字幕 | 置頂顯示原文與譯文，可自訂字型、顏色、透明度、位置與顯示行數。 |
| 區網字幕分享 | 透過瀏覽器，讓同一網路內的手機、平板或其他電腦同步觀看字幕。 |
| 字幕匯出 | 保存辨識與翻譯結果，支援 SRT、TXT、ASS 等格式。 |
| 術語與辨識修正 | 分別管理 ASR 修正規則與翻譯術語表，處理人名、作品名及固定譯名。 |
| 模型管理 | 在介面內下載、匯入及切換語音辨識模型、GGUF 翻譯模型與 llama.cpp 執行環境。 |
| 更新管理 | 提供新版通知、檔案完整性檢查、同類型套件更新、備份及失敗回復。 |

適合直播字幕、遊戲與影音翻譯、麥克風轉錄，以及需要跨裝置觀看字幕的使用情境。完成模型與執行環境準備後，可使用本機音源搭配本機辨識及翻譯；使用雲端服務時則需要網路與對應 API 金鑰。

## v1.5.0 更新亮點

- **介面更新：** 統一深色視覺與設定層級，集中常用操作，改善模型管理與窄視窗使用體驗。
- **桌面操作流暢度：** 改善首頁下拉選單與設定保存反應；Windows 控制介面預設使用軟體渲染，ASR／LLM 的 GPU 加速不受影響。可加上 `--enable-webview-gpu` 測試介面 GPU 加速。
- **應用程式收音：** 選擇指定程式作為音訊來源，提供收音測試與目標關閉提示。
- **翻譯顯卡選擇：** 支援手動指定本機翻譯使用的顯卡，顯示模型的 GPU 載入狀態。
- **模型與字幕改善：** 新增 Index-Translate 2B／9B GGUF 推薦，改善翻譯設定保存、繁體中文輸出與字幕銜接。
- **安裝與更新改善：** 優化首次設定、來源檢查及手動更新，支援 ZIP 與分割更新包。

完整內容請參閱 [v1.5.0 更新說明](app/docs/RELEASE_NOTES_v1.5.0_zh-TW.md)。

## 下載與安裝

### 選擇套件

從 [GitHub Releases](https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/releases/latest) 下載與使用需求相符的完整包。

| 套件 | 適用情境 | 完整包檔名 |
| --- | --- | --- |
| **CPU** | 使用 CPU 語音辨識，或搭配雲端翻譯；不需獨立顯卡 | `StreamTranslator-win64-CPU-Full.zip` |
| **CUDA** | 使用支援 CUDA 的 NVIDIA 顯示卡進行本機語音辨識 | `StreamTranslator-win64-CUDA-Full.zip.part01`～`.part03` |
| **ROCm Experimental** | 使用相容的 AMD 顯示卡；相容性依顯卡、驅動與模型而異 | `StreamTranslator-win64-ROCm-Experimental-Full.zip` |

初次使用可從 **CPU 完整包＋雲端翻譯**開始。CPU 完整包已內附 CPU ASR 執行環境，無須另裝 CPU ASR Sidecar。

套件類型決定語音辨識的執行環境；本機翻譯的顯卡與 llama.cpp 執行環境可另外設定。CPU 版也能搭配 GPU 本機翻譯。

### 安裝步驟

1. **下載完整包。** CPU／ROCm 下載對應 ZIP；CUDA 請下載全部 3 個分卷及 `merge-full-package.bat`，放在同一資料夾後執行合併。
2. **確認檔案完整性。** 使用發布頁提供的 `SHA256SUMS-v1.5.0.txt` 核對下載檔案。
3. **解壓並啟動。** 解壓到可寫入的資料夾，例如 `D:\Apps\StreamTranslator`，執行 `Stream Translator.exe`。
4. **完成首次設定。** 選擇音訊來源與辨識語言，依提示準備模型；需要翻譯時，再設定翻譯服務或本機模型。

CUDA 完整包須先合併為 ZIP 再解壓。請下載上述 Full 完整包；GitHub 自動提供的 `Source code` 檔案供原始碼使用。

完整包內附執行環境，但大型 ASR／GGUF 模型與 llama.cpp 翻譯執行環境需依需求準備。使用 API 翻譯時無須下載本機翻譯模型。

### 更新既有安裝

使用與目前安裝類型相同的 App Update：

| 目前套件 | 更新包 |
| --- | --- |
| CPU | `StreamTranslator-CPU-App-Update.zip` |
| CUDA | `StreamTranslator-CUDA-App-Update.zip.part01`、`.part02` |
| ROCm Experimental | `StreamTranslator-ROCm-Experimental-App-Update.zip` |

1. 備份 `config.yaml`、Cookies、術語與自訂規則，停止正在執行的辨識與翻譯任務。
2. 下載對應更新包與 SHA-256 清單。CUDA 更新包需下載全部 2 個分卷並放在同一資料夾。
3. 使用程式提供的更新功能；手動更新器可直接選擇 ZIP 或 `.zip.part01`，依提示完成更新。
4. 更新後確認版本為 **v1.5.0**，再啟動原本使用的音源、辨識模型與翻譯服務。

更新包包含對應執行環境，並保留既有模型、設定與輸出檔案。切換 CPU／CUDA／ROCm 類型，或無法識別的舊版安裝，請使用完整包；v1.3.11 以下版本亦建議使用完整包。

CUDA／ROCm 使用者若要改用 CPU 語音辨識，可匯入 `StreamTranslator-CPU-ASR-Sidecar-v1.5.0.zip`，再於模型管理頁準備對應的 CPU 模型。

## 開始使用

1. **選擇音訊來源：** 貼上直播網址，或選擇本機影音、系統音訊、麥克風及指定應用程式。
2. **準備辨識模型：** 在「ASR 模型管理」下載模型，再於「轉錄選項」選擇相同引擎、模型與輸入語言。
3. **設定翻譯：** 選擇翻譯後端及目標語言，填入 API 金鑰或啟動本機模型，使用測試功能確認回應。
4. **啟動轉譯：** 在首頁開始辨識，依需要開啟浮動字幕、字幕分享或檔案輸出。只需要原文字幕時，可關閉翻譯。

指定應用程式收音需要 Windows build 20348 以上。瀏覽器可能共用程序，因此無法保證只擷取單一分頁或視窗的音訊。

## 模型與翻譯服務

### 語音辨識

可用引擎與模型格式依套件類型而異，以「ASR 模型管理」顯示的清單為準。

| 引擎 | 選擇方向 |
| --- | --- |
| **Qwen3-ASR** | 提供 0.6B、1.7B 及日文特化模型；GPU 權重與 CPU ONNX 模型分別準備。 |
| **NVIDIA Parakeet** | 提供多語、日文與英文模型；CUDA 與 CPU 可用型號依模型清單而異。 |
| **Fun-ASR／SenseVoice** | 適用於中文、英文、日文等內容，具體語言支援依模型而異。 |
| **faster-whisper** | 提供 Whisper 多種尺寸模型，目前打包版使用 GPU 原生執行環境。 |
| **OpenAI Whisper API** | 使用雲端辨識，無須下載本機模型；需網路與 API 金鑰，可能產生費用。 |

選擇模型時，請同時考量主要語言、硬體資源與字幕延遲。若搭配本機翻譯模型，CPU ASR 可將顯存留給翻譯；是否能維持即時速度仍取決於 CPU 與音源。

### 翻譯後端

| 後端 | 使用方式 |
| --- | --- |
| **OpenAI** | 設定 API 金鑰與可用模型，適合使用雲端文字翻譯。 |
| **Google Gemini** | 使用 Gemini API 金鑰，模型與配額依帳戶服務而定。 |
| **llama.cpp** | 透過程式管理 GGUF 模型與執行環境，在本機執行翻譯。 |
| **OpenAI-compatible API** | 連接 LM Studio 或其他相容服務，設定對應 Base URL 與模型名稱。 |

雲端語音辨識會將音訊傳送至服務商；雲端文字翻譯會將辨識文字傳送至服務商。API 費用與配額依各服務規定。

### 本機翻譯模型

| 模型系列 | 選擇方向 |
| --- | --- |
| **HY-MT2** | 提供 1.8B 與 7B；較小模型節省資源，較大模型需要更多記憶體與顯存。 |
| **Index-Translate** | 官方 2B／9B GGUF；Q4_K_M 約 **1.31／5.78 GB**，推薦頁顯存估算為 **4／8 GB**。 |
| **Sakura** | 日文到中文模型，涵蓋 Galgame 與文學語氣；使用前請確認所選模型授權。 |
| **其他 GGUF 模型** | 可依語言與內容需求匯入，翻譯效果取決於模型、提示詞及參數。 |

模型大小與顯存需求為選型參考。實際占用還會受上下文長度、量化格式與同時執行的語音辨識影響。

本機翻譯可在「Llama 執行設定」選擇顯卡：NVIDIA 優先使用 CUDA，AMD／Intel Arc 獨顯建議使用 Vulkan。程式管理的 llama.cpp 預設翻譯端點為 `http://127.0.0.1:8081/v1`；LM Studio 常見端點為 `http://127.0.0.1:1234/v1`，請以實際服務設定為準。

## 字幕與資料管理

- **字幕外觀：** 自訂字型、配色、透明度、位置與行數，搭配桌面浮動視窗或瀏覽器字幕頁。
- **字幕分享：** 使用介面顯示的區網網址，讓同一網路內的裝置觀看；需要允許 Windows 防火牆連線。
- **辨識修正：** ASR 修正規則在翻譯前處理固定誤辨，格式為 `正確詞,誤辨詞1,誤辨詞2`。
- **翻譯術語：** 術語表固定譯名，格式為 `原文,譯文`，可與辨識修正分別管理。
- **設定與模型：** 設定保存在可寫入位置的 `config.yaml`；模型路徑可於模型管理頁查看，輸出位置由首頁指定。

字幕分享預設供區網使用。需要跨網路存取時，請使用具驗證的 HTTPS 或 VPN 配置。

## 常見問題

### 第一次使用為什麼需要等待？

首次使用可能需要下載或載入模型。請查看模型管理頁的進度，待模型準備完成後開始辨識。

### 沒有收到音訊或無法解析直播網址？

先執行來源測試。系統音訊請確認 Windows 的實際播放裝置；直播網址可能受網站變更、地區限制或登入狀態影響，部分內容需要 Netscape 格式的 `cookies.txt`。

### 翻譯沒有回應？

使用設定頁的測試功能，確認 API 金鑰、Base URL 與模型名稱。本機翻譯請先確認模型伺服器已啟動；OpenAI 語音辨識、OpenAI 翻譯與 Gemini 使用各自的金鑰設定。

### 字幕錯字或譯名不一致，應如何調整？

原文辨識錯誤時，先確認音源、語言與 ASR 模型，再使用辨識修正規則；原文正確但譯名不一致時，使用翻譯術語表或調整翻譯設定。

### 切換 CPU 辨識後找不到模型？

CPU 模式使用對應的 sherpa-onnx 模型，無法直接沿用 GPU 權重。請在模型管理頁準備 CPU 模型；CUDA／ROCm 使用者也需確認 CPU ASR Sidecar 已就緒。

## 文件與專案資訊

- [操作與設定指南](USER_GUIDE.md)
- [版本更新說明](app/docs/RELEASE_NOTES_v1.5.0_zh-TW.md)
- [手動更新指南](app/docs/MANUAL_UPDATE_zh-TW.md)
- [開發與打包文件](app/packaging/README.md)
- [文件索引](app/docs/README.md)

### 專案來源

- 核心專案：[ionic-bond/stream-translator-gpt](https://github.com/ionic-bond/stream-translator-gpt)
- 行動字幕參考：[W-Nana/SubtitleOverlay](https://github.com/W-Nana/SubtitleOverlay)
- 本機模型執行環境：[llama.cpp](https://github.com/ggerganov/llama.cpp)
