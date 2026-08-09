# Stream Translator v1.3.10 更新說明

本次更新集中改善三件事：本地 LLM 更容易設定、ASR 模型可直接下載管理，以及即時轉譯頁面更清楚穩定。

## 主要更新

### 本地 LLM／llama.cpp

- 即時轉譯頁新增「本地 LLM 翻譯」開關，開啟時才會啟動 llama.cpp；關閉後不占用顯示卡與記憶體。
- 直接顯示目前選擇的 GGUF 模型、Runtime 版本及啟動狀態。
- llama.cpp Runtime 會依 NVIDIA、AMD 或 CPU 環境推薦適合版本，並提供下載進度、驗證與完成提示。
- 已安裝最新 Runtime 時不再顯示「下載更新」，避免重複安裝。
- 強化模型路徑、啟動參數及 OpenAI-compatible API 相容性檢查。

> 從 v1.3.10 起，CUDA、CPU、ROCm Full package 都不再內含頂層 `llama` Runtime 資料夾。第一次使用本地 LLM 時，請在「LLM 模型管理」下載 Runtime；GGUF 模型也需另外下載或指定現有檔案。

### ASR 模型下載與轉錄

- ASR 模型管理會顯示下載進度、目前檔案、容量及完成狀態。
- 尚未安裝所選 ASR 模型就開始轉譯時，程式會先提示並協助下載。
- GPU ASR 與 CPU sherpa-onnx 模型分開顯示，降低模型與 Runtime 選錯的情況。
- CPU ASR sidecar 改用隔離環境啟動，減少外部 Python 套件造成的衝突。
- 切換 CUDA／ROCm／CPU ASR 時會自動清理不相容設定。

### 使用教學與介面

- 新增「使用教學」頁，說明 ASR 模型、llama.cpp Runtime、GGUF 模型及本地翻譯設定。
- 即時轉譯的進階設定預設展開，翻譯模型與 ASR 模型用途更容易理解。
- 本地 LLM 卡片、執行日誌及字幕分享服務重新排版，左右欄高度與間距更一致。
- 主視窗第一次啟動預設為 `1287 × 917`；已儲存的視窗大小不受影響。
- 修正讀取設定時偶爾跳出 PowerShell／CMD 視窗的問題。

### 穩定性與媒體輸入

- 修正 Windows 暫時鎖定 `config.yaml` 時可能回退到預設設定的問題。
- 打包版內建 Node.js 22+，供 yt-dlp 處理新版 YouTube JavaScript 擷取流程。
- 三種 Runtime Profile 使用同一份 GUI，並驗證 Runtime manifest、CPU ASR sidecar 與執行檔 SHA-256。

## 下載哪個版本

請從 [GitHub v1.3.10 Release](https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/releases/tag/v1.3.10) 下載。請勿使用 GitHub 自動產生的 `Source code (zip)` 當作執行版。

| 版本 | 適用環境 | 說明 |
|---|---|---|
| CUDA | NVIDIA 顯示卡 | 建議 NVIDIA 使用者下載 |
| CPU | 無獨立顯示卡或只使用 CPU ASR | 使用 sherpa-onnx／ONNX Runtime |
| ROCm Experimental | 支援 ROCm/HIP 的 AMD 顯示卡 | Windows ROCm 仍屬實驗性支援 |

## 全新安裝

1. 下載硬體對應的 Full package。CUDA Full 需要 `.part01` 與 `.part02`；CPU、ROCm 下載對應的 `.part01`。
2. 將所有分割檔與 `merge-full-package.bat` 放在同一資料夾。
3. 執行 `merge-full-package.bat` 合併 ZIP，並用 `SHA256SUMS-v1.3.10.txt` 驗證。
4. 解壓縮至可寫入的獨立資料夾，啟動 `Stream Translator.exe`。
5. 從 ASR 模型管理下載需要的語音模型；要使用本地翻譯時，再安裝 llama.cpp Runtime 與 GGUF 模型。

## 從舊版更新

1. 關閉 Stream Translator 與正在執行的 llama.cpp server。
2. 備份原安裝資料夾內的 `config.yaml`。
3. 下載與原本相同 Profile 的 `App-Update.zip`，解壓縮並覆蓋原安裝資料夾。
4. 保留原本的 `config.yaml`，重新啟動程式。
5. 若程式提示缺少 CPU ASR sidecar，再安裝 `StreamTranslator-CPU-ASR-Sidecar-v1.3.10.zip`。

CUDA、CPU、ROCm 的 App Update 不可混用。CPU ASR sidecar 只包含 Runtime，不包含 ASR 模型。

## 使用前注意

- ROCm for Windows 仍是 Experimental，不同 AMD 顯示卡、驅動及 HIP Runtime 的相容性可能不同。
- CPU Profile 不使用 Faster-Whisper，請下載 sherpa-onnx 相容模型。
- YouTube、Twitch 等平台仍可能要求登入 Cookie；可在輸入選項選擇瀏覽器 Cookie 或匯入 `cookies.txt`。
- 字幕分享服務沒有登入驗證，請勿直接將分享埠暴露到 Internet。
- 所有正式資產均附 manifest 與 SHA-256 清單，可用於檔案完整性檢查。
