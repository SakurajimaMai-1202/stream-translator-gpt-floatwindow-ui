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

## 套件說明

- CUDA、CPU 與 ROCm App Update 必須用於相同 Profile。
- Full package 適合全新安裝；App Update 適合從相同 Profile 的既有版本更新。
- CPU ASR sidecar 供 CUDA／ROCm 套件執行簡單模式的 CPU ASR。
