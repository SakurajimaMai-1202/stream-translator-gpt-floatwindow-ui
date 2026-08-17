# Stream Translator v1.4.1 更新說明

v1.4.1 是本機 LLM 與原生浮動字幕的穩定性更新，並針對 Llama 設定頁儲存、GGUF 掃描及長頁面滾動進行效能優化。

## 主要更新

### 本機 LLM 狀態與 GGUF 掃描

- 從「Llama 執行設定」啟動伺服器後，首頁的本機 LLM 開關會正確顯示為開啟；停止伺服器時也會同步關閉。
- 「套用並重啟」會在更換模型或參數時保留正確的啟用狀態，避免首頁與執行設定顯示不一致。
- GGUF 預設目錄為 `./models`，現在固定以 `Stream Translator.exe` 所在目錄為基準。即使從捷徑、下載目錄或其他工作目錄啟動，也不會掃描到錯誤位置。
- GGUF 遞迴掃描移到背景執行，降低含有大型 Hugging Face 快取目錄時對其他 API 的影響。

### Llama 設定儲存與頁面效能

- 連續調整 Llama 參數時，前端會合併並串行化儲存請求，避免舊請求較晚完成後覆蓋新設定。
- 相同的設定快照不會重複寫入 `config.yaml`。
- 儲存 `config.yaml` 與自訂 Llama 預設時的 YAML 寫入移出 FastAPI 主事件迴圈，改善按下儲存後整頁短暫卡住的情況。
- 儲存或刪除自訂預設後直接更新本地狀態，不再緊接着讀取整份設定。
- Llama 伺服器狀態輪詢降低為每 4 秒一次；資源資訊與 Runtime 版本分別使用短期快取。
- `nvidia-smi` 與 `llama-server --version` 移到背景執行，並避免在資料未改變時通知整個 Vue 長頁面重新更新。
- 移除長頁面卡片的 paint containment，減少 Qt WebEngine 快速滾動時重建大型畫面 tile 的開銷。

### 推薦翻譯模型

- 新增「推薦翻譯模型」頁面，依偵測到的獨立顯卡與 VRAM 排序 GGUF 模型。
- 提供 Gemma 4 E2B／E4B QAT、Hy-MT2 7B、Sakura GalTransl v4 4B 與 Sakura 14B Qwen3 v1.5 的建議量化、最低 VRAM 與舒適 VRAM 參考。
- Hy-MT2 會標示為本程式優先建議，因為現有翻譯流程具備 Hy-MT2 專用提示詞、術語與上下文策略。
- 可將模型建議的 `temperature`、`top_p`、`top_k`、`repeat_penalty`、context 與輸出長度套用到 Llama 執行設定。
- Sakura 系列頁面會顯示非商用授權提醒；下載與使用前仍應閱讀各模型頁面的最新授權。

### 本機翻譯參數

- Llama 翻譯 API 現在會實際套用已儲存的模型採樣參數，不再固定使用舊的內建數值。
- 支援 `temperature`、`top_p`、`top_k`、`repeat_penalty` 與 `n_predict`，讓推薦參數與自訂預設能真正影響推論。

### 原生 Qt 浮動字幕

- 原生字幕視窗改為直接使用 Qt Network 訂閱 FastAPI SSE，不再依賴首頁 WebView 逐筆轉發字幕。
- 新任務開始時才清除歷史；SSE 中斷時會使用遞增延遲自動重連。
- 同一字幕可從只有 timestamp 的中間 ASR 更新為具有 `segment_id` 的最終譯文，不會因識別鍵升級而變成重複兩行。
- 字幕歷史依視窗可用高度保留最新項目，改善頂部裁切與底部留白。
- 時間顯示改為本機實際收到字幕的時間，不再將媒體 timestamp 誤當成當地時間。
- 關閉原生字幕後會正確釋放 SSE client 與 Qt 視窗，再次開啟時不會被舊的 destroyed 事件清除新視窗。

## 下載版本

| 版本 | 適用硬體 | 說明 |
|---|---|---|
| CUDA | NVIDIA CUDA 相容獨立顯卡 | GPU 原生 ASR；也可安裝 sherpa-onnx CPU ASR sidecar。 |
| CPU | 沒有相容獨立顯卡或優先考量相容性 | sherpa-onnx／ONNX Runtime，不包含 PyTorch。 |
| ROCm Experimental | 支援 Windows ROCm／HIP 的 AMD 獨立顯卡 | 實驗性 GPU ASR；實際相容性取決於顯卡、驅動與 HIP Runtime。 |

Full package 為分割壓縮檔，請下載同一 Profile 的所有 `.partXX`，再使用 `merge-full-package.bat` 合併。不要只解壓 `.part01`。

## 從 v1.4.0 更新

1. 建議先關閉 Stream Translator 與 llama.cpp server，並備份 `config.yaml`。
2. 在「設定 → 一般設定」檢查更新，或下載與現有安裝相同 Profile 的 v1.4.1 App Update。
3. 等待下載、SHA-256 驗證與準備完成，再按「重新啟動並套用」。
4. v1.4.1 App Update 為 `app_only`，不會替換現有 `_runtime`；CUDA、CPU 與 ROCm 更新包不可交叉使用。

從更舊版本升級時，若內建更新器提示不相容，請下載同 Profile Full package，解壓到新資料夾後再複製舊的 `config.yaml`。

## 重要注意事項

- Full package 不包含 llama.cpp Runtime 與 GGUF 權重；需要本機翻譯時，請從「Llama 執行設定」安裝 Runtime，再將 GGUF 放入 `models` 目錄。
- CUDA／ROCm 版的 CPU ASR sidecar 只包含 Runtime，不包含 ASR 模型權重。
- ROCm for Windows 仍屬 Experimental，本版本沒有擴大保證的 AMD GPU 支援範圍。
- Sakura 模型授權可能限制商業使用，請以下載頁面當下顯示的授權為準。
