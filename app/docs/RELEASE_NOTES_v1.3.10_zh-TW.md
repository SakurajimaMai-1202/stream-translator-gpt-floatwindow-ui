# Stream Translator v1.3.10 更新說明

v1.3.10 主要改善本地 LLM、ASR 模型管理、Windows 啟動穩定性與使用者介面。CUDA、CPU、ROCm Experimental 三種 Runtime Profile 維持獨立，並延續 CPU sherpa-onnx sidecar 的相容性檢查。

## 本版重點

### 本地 LLM 與 llama.cpp

- 即時轉譯頁新增「使用本地 LLM」開關；關閉時不會啟動 llama.cpp server。
- 本地 LLM 控制卡會顯示目前模型名稱、Runtime 狀態、啟動中／已就緒／關閉等狀態。
- Llama 模型管理與 Runtime 管理的流程更清楚，模型未選定或 Runtime 未安裝時會提供對應提示。
- llama.cpp Runtime 會讀取已安裝版本並比對官方最新版本；版本已是最新時不再顯示不必要的更新操作。
- 依偵測到的 NVIDIA、AMD 或 CPU 環境選擇相符 Runtime，保留 CPU fallback。
- 強化 llama.cpp server 啟動參數、模型路徑與 OpenAI-compatible API 狀態檢查。
- Llama Runtime 與模型下載提供進度、驗證與完成提示，方便確認是否可直接使用。
- 三種 Full package 均不再內含 `llama` 資料夾；首次使用本地 LLM 時，請從 LLM 模型管理下載與硬體相符的 llama.cpp Runtime，避免攜帶過時 Runtime。

### ASR 模型管理與轉錄

- ASR 模型下載頁補上下載進度、目前檔案、大小與完成狀態。
- 使用者尚未下載目前選擇的 ASR 模型就開始轉譯時，會先提示並協助下載相容模型。
- 原生 GPU ASR 模型與 sherpa-onnx CPU 模型分流顯示，降低選錯模型格式的機會。
- CPU ASR sidecar 使用 isolated Python 啟動與匯入檢查，避免外部 Python 套件污染造成啟動失敗。
- CUDA／ROCm 切換至 CPU sherpa-onnx ASR 時，會清理不相容的 GPU-only ASR 狀態。

### 使用教學與介面

- 新增獨立「使用教學」頁面，說明快速開始、ASR 模型選擇與下載、llama.cpp Runtime、GGUF 模型與本地 LLM 設定。
- 教學頁只在使用者進入時開啟，不再每次啟動都顯示快速開始遮罩。
- 即時轉譯頁的進階設定預設展開，直接說明 ASR 引擎、ASR 模型與翻譯模型的用途。
- 本地 LLM 翻譯卡與字幕分享服務重新整理為左右欄對齊布局；執行日誌會填滿右欄可用空間。
- 系統執行日誌固定保留至少 400px 高度，並改善分享服務在不同視窗尺寸下的排列。
- 主視窗首次啟動預設大小調整為 `1287 × 917`；使用者已儲存的視窗大小與位置會繼續保留。
- 側邊欄顯示目前版本與使用教學入口，設定提示更容易找到對應頁面。

### 穩定性與打包

- Windows 配置檔暫時被其他程序鎖定時，保留已成功載入的設定並重試寫入，避免意外回退到預設值。
- 前端 production bundle 與三種 Runtime Profile 共用同一份更新後的 GUI，避免版本或介面不一致。
- 打包流程持續產生 CUDA、CPU、ROCm Experimental 三種版本，並對 CPU ASR sidecar、Runtime manifest、Profile 與 GUI SHA-256 進行驗證。
- 發布資產會產生 release manifest 與 SHA-256 清單，方便下載後確認檔案完整性。

## 下載與更新

請從 [GitHub v1.3.10 Release](https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/releases/tag/v1.3.10) 下載與硬體相符的 Profile。不要使用 GitHub 自動產生的 `Source code (zip)` 作為執行版。

### 全新安裝

1. 下載 CUDA、CPU 或 ROCm Experimental 的 Full package；CUDA 與 ROCm 需要下載該 Profile 的全部 `.partXX`。
2. 將分割檔與 `merge-full-package.bat` 放在同一資料夾並執行合併。
3. 使用 `SHA256SUMS-v1.3.10.txt` 驗證合併後的 ZIP。
4. 解壓縮到可寫入的獨立資料夾，再啟動 `Stream Translator.exe`。
5. 依使用教學下載 ASR 模型；需要本地翻譯時，再於 LLM 模型管理選擇 GGUF 並開啟本地 LLM。

### 更新既有安裝

1. 關閉 Stream Translator 與 llama.cpp server。
2. 備份舊資料夾內的 `config.yaml`。
3. 下載相同 Profile 的 `App-Update.zip`，解壓縮並覆蓋到原安裝資料夾。
4. 若程式提示缺少 CPU ASR sidecar，再下載 `StreamTranslator-CPU-ASR-Sidecar-v1.3.10.zip`。
5. 保留原本的 `config.yaml` 後重新啟動程式。

CUDA、CPU 與 ROCm 的 App Update 不可混用；CPU ASR sidecar 只提供 Runtime，不包含 ASR 模型權重。

## 已知注意事項

- ROCm for Windows 仍屬 Experimental，不同 AMD 顯示卡、驅動與 HIP Runtime 的結果可能不同。
- CPU Profile 使用 sherpa-onnx／ONNX Runtime，不使用 Faster-Whisper；請從 ASR 模型管理下載相容模型。
- llama.cpp 的 GGUF 模型不隨應用程式完整包預先內建，需在模型管理頁下載或指定現有檔案。
- 字幕分享服務只提供字幕頁面，沒有登入驗證；不要直接把分享埠暴露到 Internet。

## 驗證項目

- Python source compile check
- Config persistence tests
- Frontend Vite production build
- CUDA、CPU、ROCm Profile artifact validation
- CPU ASR sidecar isolated import check
- Full ZIP、分割檔重組、manifest 與 SHA-256 核對
