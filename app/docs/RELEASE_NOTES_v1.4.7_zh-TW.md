# Stream Translator v1.4.7 更新說明

v1.4.7 讓簡單模式的首次設定更完整。使用者選擇簡單模式後，可以直接選擇本機翻譯或 Gemini 雲端翻譯，程式會自動完成需要的環境與模型設定。

## 主要更新

- 首次啟動會引導選擇簡單模式或進階模式，並記住選擇。
- 本機翻譯會偵測 NVIDIA GPU 與 VRAM：4 GB 使用 Hy-MT2 i1-IQ3_XXS，8 GB 以上使用 i1-Q6_K。
- 本機流程會自動下載 llama.cpp 與翻譯模型，並驗證模型大小及 SHA-256。
- Gemini 雲端翻譯會引導取得 API Key，預設模型為 `gemini-2.5-flash-lite`。
- 簡單模式首頁加入本機模型啟動開關、服務狀態與實際連接埠。
- 簡單模式固定使用 CPU ASR，中文使用 SenseVoice，其他支援語言自動選擇 Parakeet。
- 輸入語言與目標語言相同時直接顯示辨識原文，不呼叫翻譯模型。
- 修正切換回簡單模式時重複檢查與下載環境的問題。
- 修正更新器可能繼承主程式的 Qt DLL 路徑，造成更新後無法載入 `PyQt6.QtCore`；更新器現在固定使用自身 Qt Runtime，並由更新包提供相符版本。
- 音訊切片預設調整為 0.7／4／8 秒，FireRed VAD 預設每 2 個 frame 計算。
- llama.cpp 的 Flash Attention 改為 `auto`，由 Runtime 依模型與硬體自行判斷；Hy-MT 預設停用 mmap，避免新版 llama.cpp 啟動失敗。
- llama.cpp 伺服器日誌改為獨立記錄，啟動失敗時更容易確認 Runtime、模型與參數問題。
- 本機 LLM 啟動開關改為每次開啟程式時保持關閉，避免未經確認便自動占用 GPU 或記憶體。
- 浮動字幕會依視窗高度自然向上捲動，優先保留最舊字幕的完整中文翻譯，再將原文從頂端捲出；最小高度仍可閱讀至少兩筆字幕。
- 浮動字幕控制按鈕會在滑鼠移入時顯示，閒置 2.5 秒後自動隱藏，並修正時間與延遲顏色及設定預覽位置。
- 修正介面模式選單在小視窗中無法切換、下拉選單飛離原位，以及選單與版本號間距不足的問題。

## 套件說明

- CUDA、CPU 與 ROCm App Update 必須用於相同 Profile。
- Full package 適合全新安裝；App Update 適合從相同 Profile 的既有版本更新。
- CPU ASR sidecar 供 CUDA／ROCm 套件執行簡單模式的 CPU ASR。
- 本次重新封裝仍維持 v1.4.7；同版本更新請重新下載 App Update，或使用最新 Full package 全新安裝。
