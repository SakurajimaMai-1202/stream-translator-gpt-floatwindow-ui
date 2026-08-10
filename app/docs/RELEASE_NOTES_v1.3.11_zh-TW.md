# Stream Translator v1.3.11 更新說明

v1.3.11 集中改善手機操作、ASR 模型下載、中文辨識輸出與術語／修正規則管理；桌面版原有操作方式維持不變。

## 主要更新

### 手機操作與字幕頁

- 主控制頁會在手機寬度下切換為觸控版面，桌面版仍保留固定左側選單。
- 手機導覽由右上角開啟，選單從右側滑出；音訊來源、語言選擇與進階設定改為適合窄螢幕的排列，進階設定預設展開。
- 新增固定於手機底部的開始／停止轉譯列，並預留安全捲動空間，避免遮住字幕分享內容。
- 手機上會明確標示「電腦麥克風」「電腦系統音訊」與「電腦本地檔案」，避免誤認為手機本身的音訊來源。
- 電腦端字幕頁在手機瀏覽器開啟時，會自動縮小卡片、字體、延遲資訊與控制列；原有行動端字幕頁仍可繼續使用。
- 浮動字幕視窗改為逐字流式渲染；同一片段收到增量或修正版內容時會自然接續，不再整段文字瞬間跳出。
- 浮動字幕右側控制列新增收音狀態燈：綠燈表示正在收音／轉譯，紅燈表示尚未開始或已停止。

### ASR 模型與下載進度

- 模型下載改為顯示實際百分比、已下載容量與總容量，不再只顯示階段式假進度。
- Hugging Face 與 sherpa-onnx 模型下載都會持續更新進度，完成後再驗證必要模型檔案。
- CPU／sherpa-onnx 新增 Qwen3-ASR 1.7B INT8 選項，與 0.6B 分開顯示及下載。
- CPU ASR Runtime 更新至 sherpa-onnx 1.13.4。
- 下拉選單會依可用空間決定向上或向下展開，並跟隨手機視窗與軟體鍵盤重新定位。

### 中文 ASR 與修正規則

- 保留繁體中文、簡體中文及對應 script 選擇，ASR 後處理會依設定統一繁簡輸出。
- 清除 Qwen3-ASR 可能附帶的控制標記，避免非字幕內容出現在結果中。
- 修正「記錄已套用修正」與「學習別名」開關未完整傳入 ASR Runtime 的問題。
- Runtime 與 CPU ASR sidecar 都會驗證 OpenCC 支援，避免打包後才發現缺少中文轉換依賴。

### 本地檔案與 CSV 管理

- 桌面 WebView 的「本地檔案」新增 Windows 原生檔案選擇器，可把完整路徑直接交給轉譯後端。
- 支援常用影音格式，並改善未輸入網址或檔案路徑時的提示與定位。
- 術語表與 ASR 修正規則匯入支援引號、逗號、Tab、欄位換行及 UTF-8 BOM。
- 匯出 CSV 使用 Excel 較容易正確辨識的 UTF-8 BOM 與 CRLF，並合併舊版設定中的有效資料、排除重複項目。

## 下載哪個版本

請從 [GitHub v1.3.11 Release](https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/releases/tag/v1.3.11) 下載。GitHub 自動提供的 `Source code (zip)` 不是可直接執行的 Windows 完整包。

| 版本 | 適用環境 | 說明 |
|---|---|---|
| CUDA | NVIDIA 顯示卡 | 建議 NVIDIA 使用者下載 |
| CPU | 無獨立顯示卡或主要使用 CPU ASR | 使用 sherpa-onnx／ONNX Runtime |
| ROCm Experimental | 支援 ROCm/HIP 的 AMD 顯示卡 | Windows ROCm 仍屬實驗性支援 |

## 全新安裝

1. 下載硬體對應的 Full package 全部分割檔與 `merge-full-package.bat`。
2. 將同一 Profile 的 `.partNN` 放在同一資料夾，執行合併腳本。
3. 使用 `SHA256SUMS-v1.3.11.txt` 核對下載檔案，再解壓縮合併後的 ZIP。
4. 啟動 `Stream Translator.exe`，到「ASR 模型管理」下載需要的模型。
5. 要使用本地翻譯時，再從「LLM 模型管理」安裝 llama.cpp Runtime 並選擇 GGUF 模型。

## 從舊版更新

1. 關閉 Stream Translator 與 llama.cpp server。
2. 備份原安裝資料夾中的 `config.yaml`。
3. 下載與原本相同 Profile 的 v1.3.11 `App-Update.zip`，解壓縮並覆蓋原安裝資料夾。
4. 保留原本的 `config.yaml`，重新啟動程式。
5. CUDA／ROCm 使用者若要使用 CPU ASR，請確認已安裝 v1.3.11 CPU ASR sidecar。

CUDA、CPU、ROCm 的 App Update 不可混用。CPU ASR sidecar 只包含 Runtime，不包含模型權重。

## 重要注意事項

- CPU Qwen3-ASR 1.7B 模型下載與記憶體需求都明顯高於 0.6B；一般電腦建議先測試 0.6B。
- CPU Profile 不使用 Faster-Whisper，請下載 sherpa-onnx 相容模型。
- ROCm for Windows 仍是 Experimental，實際支援取決於 AMD 顯示卡、驅動與 HIP Runtime。
- 手機控制頁操作的是執行 Stream Translator 的電腦；「系統音訊」與「麥克風」不是手機本身的輸入。
- 字幕分享服務沒有登入驗證，請只在可信任的區域網路使用，不要直接暴露到 Internet。
- YouTube、Twitch 等來源仍可能需要登入 Cookie；可在輸入選項選擇瀏覽器 Cookie 或匯入 `cookies.txt`。
- 正式資產附有 release manifest 與 SHA-256 清單，可用於核對檔案完整性。
