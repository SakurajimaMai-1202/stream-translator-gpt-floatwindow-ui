# Stream Translator v1.4.0 更新說明

v1.4.0 集中改善程式更新、CPU ASR sidecar、遠端字幕顯示與 Gemini 翻譯設定，並將更新前的使用者資料保護流程整合到 UI。

## 主要更新

### UI 內建程式更新

- 在「設定 → 一般設定」直接檢查 GitHub Releases 的最新版本。
- 程式啟動後會自動檢查一次；有新版時在首頁顯示通知，但不會自動下載、安裝或啟動更新器。
- 依目前的 CUDA、CPU 或 ROCm Profile 選擇相符的 App Update，不會跨 Profile 套用。
- 顯示下載百分比、容量、驗證、準備與完成狀態；下載中可取消，重新開始時會延續暫存檔。
- 下載後驗證 GitHub Release 提供的 SHA-256，並檢查版本、Profile 與更新包內容。
- 更新檔會先放入隔離暫存區，再由獨立的 `StreamTranslatorUpdater.exe` 關閉主程式、套用檔案並重新啟動。
- 更新器在新版啟動失敗時會嘗試回復上一版程式檔。

### 更新前的使用者資料備份

- 套用更新前會備份 `config.yaml`。
- 同時備份翻譯術語表、ASR 修正規則與設定中引用的 Cookies 檔案。
- 備份最多保留最近五份，避免更新過程無限制累積資料。
- 更新包不會覆蓋模型、輸出檔與日誌；開發／原始碼模式不提供自動套用更新。

### CPU ASR sidecar

- CUDA／ROCm 版本可在「ASR 模型管理」下載並安裝獨立的 sherpa-onnx CPU ASR Runtime。
- 已安裝的 sidecar 會執行健康檢查；異常時可選擇修復安裝或重新安裝。
- 顯示實際下載百分比、已下載容量與總容量。
- 下載中可取消，下一次可以使用既有暫存進度繼續下載。
- sidecar 資產依目前應用程式版本從 GitHub Release 取得，安裝後會驗證必要檔案與 Runtime 版本。

### 電腦版與手機版字幕

- 電腦網頁版與手機網頁版改用接近浮動字幕的打字機式流式渲染。
- 新字幕會逐字顯示，不會在每次收到 ASR／翻譯增量時整段閃現。
- 同一時間片段收到修正版內容時，會保留共同前綴並從正確位置繼續輸出。
- 使用 Unicode 字元處理，中文、日文與 emoji 不會因 UTF-16 字串切割而破壞。
- 保留原有字幕歷史、自動捲動與手機版操作行為。

### Gemini API 翻譯教學

- 「使用教學」新增 Gemini API Key 取得、設定、測試連線與開始翻譯流程。
- README 同步補上 Google AI Studio API Key 說明與安全提醒。
- Gemini API Base URL 預設顯示為 `https://generativelanguage.googleapis.com/v1beta`。
- 明確說明 OpenAI ASR、OpenAI GPT 與 Gemini 使用不同 API Key，不能互相代用。

## 全新安裝

1. 下載與硬體相符的 CUDA、CPU 或 ROCm Full package。
2. 使用所有 `.partNN` 與 `merge-full-package.bat` 合併完整包，再用 SHA-256 清單驗證。
3. 解壓到一般可寫入的資料夾，執行 `Stream Translator.exe`。
4. 在「ASR 模型管理」下載目前 Profile 可用的 ASR 模型；需要本機翻譯時，再安裝 llama.cpp Runtime 與 GGUF 模型。

## 從舊版更新

1. 確認新版與目前安裝使用相同 Profile。
2. 在「設定 → 一般設定」按「檢查更新」，確認版本與更新說明。
3. 按「下載並準備更新」，等待驗證與準備完成。
4. 確認備份項目後按「重新啟動並套用」。
5. 若目前版本不符合更新包的最低可升級版本，請改下載同 Profile Full package 全新安裝。

從 v1.3.11 首次升級時，請手動完整解壓同 Profile 的 v1.4.0 `App-Update.zip` 並覆蓋原安裝目錄。更新包已包含 `StreamTranslatorUpdater.exe`，不需另外下載；之後即可使用 UI 內建更新。CUDA、CPU、ROCm 不可混用。CPU ASR sidecar 只包含 Runtime，不包含模型權重。

## 重要注意事項

- GitHub Release 必須提供與目前 Profile 相符的 App Update；沒有相符資產時不會執行更新。
- 更新前請確認程式與 llama.cpp server 可以正常關閉，更新器才有辦法安全替換檔案。
- Gemini API Key 請視同密碼，不要提交到 Git、公開截圖或貼文；配額與計費依 Google AI Studio／Google Cloud 專案而定。
- ROCm for Windows 仍屬 Experimental，實際支援取決於 AMD 顯示卡、驅動與 HIP Runtime。
- 字幕分享服務仍建議只在可信任的區域網路使用，不要直接暴露到 Internet。
