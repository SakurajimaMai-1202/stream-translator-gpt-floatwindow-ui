# Stream Translator v1.4.2 更新說明

> 2026-08-29 第二次重新打包：修正 Full package 混入 Qt 6.9 與 WebEngine 6.11，造成全新解壓後無法載入 `QtWebEngineWidgets` 的問題。Qt／WebEngine 已統一為 6.9.1，建置與更新預檢也會實際載入 WebEngine；若 GUI DLL 無法載入，建置會停止，更新器則會回復上一版。

v1.4.2 著重改善 YouTube 直播翻譯延遲、串流恢復能力、字幕顯示空間與大量詞表匯入的穩定性。

## 主要更新

### YouTube 直播翻譯

- 修正翻譯工作完成後，下一句仍需等待新字幕事件才會開始翻譯的排程問題。
- YouTube 音訊連續 8 秒沒有資料時會自動重新連線，並先送出斷流前已累積的語音。
- yt-dlp 會持續重試暫時缺失的直播片段，降低只翻幾句便停止的情況。
- 串流重連時會重置 VAD 邊界，正常結束時也會送出最後一段有效語音。
- 修正弱語音後方靜音較多時，整段語音可能被靜默丟棄的問題。

### 翻譯與關閉穩定性

- 翻譯逾時後，尚未返回的供應商請求仍會占用併發額度，避免逾時持續累積背景請求。
- 重用 OpenAI HTTP client，減少每句重新建立連線的開銷。
- 停止直播或關閉程式時，會清理 ffmpeg、yt-dlp、串流讀取執行緒及仍在執行的翻譯任務。
- 使用者主動關閉造成的程序結束不再被誤記為異常崩潰。

### 原生浮動字幕

- 新安裝的字幕視窗預設高度由 200px 調整為 300px。
- 舊版 `config.yaml` 的 200px 視窗會套用最低 240px，改善只能看到一筆字幕的情況。

### 詞語表與 ASR 校正表

- CSV 大量匯入改為合併後一次儲存，避免深層監聽器逐筆觸發大量設定寫入。
- 相同標準詞會合併並去除重複別名。
- 設定寫入加入 30 秒逾時與匯入中狀態，失敗時會顯示明確錯誤。

## 下載版本

| 版本 | 適用硬體 | 說明 |
|---|---|---|
| CUDA | NVIDIA CUDA 相容獨立顯卡 | GPU 原生 ASR；也可安裝 sherpa-onnx CPU ASR sidecar。 |
| CPU | 沒有相容獨立顯卡或優先考量相容性 | sherpa-onnx／ONNX Runtime，不包含 PyTorch。 |
| ROCm Experimental | 支援 Windows ROCm／HIP 的 AMD 獨立顯卡 | 實驗性 GPU ASR；實際相容性取決於顯卡、驅動與 HIP Runtime。 |

Full package 為分割壓縮檔，請下載同一 Profile 的所有 `.partXX`，再使用 `merge-full-package.bat` 合併。不要只解壓 `.part01`。

## 從 v1.4.1 更新

1. 建議先關閉 Stream Translator 與 llama.cpp server，並備份 `config.yaml`。
2. 在「設定 → 一般設定」檢查更新，或下載與現有安裝相同 Profile 的 v1.4.2 App Update。
3. 等待下載、SHA-256 驗證與準備完成，再按「重新啟動並套用」。
4. v1.4.2 App Update 為 `app_only`，不會替換現有 `_runtime`；CUDA、CPU 與 ROCm 更新包不可交叉使用。

從更舊版本升級時，若內建更新器提示不相容，請下載同 Profile Full package，解壓到新資料夾後再複製舊的 `config.yaml`。

## 重要注意事項

- Full package 不包含 llama.cpp Runtime 與 GGUF 權重；本機翻譯使用者需另外安裝 Runtime 與模型。
- CUDA／ROCm 版的 CPU ASR sidecar 只包含 Runtime，不包含 ASR 模型權重。
- ROCm for Windows 仍屬 Experimental。
