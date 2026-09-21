# Stream Translator v1.4.8 更新說明

v1.4.8 改善簡單模式首次設定與 llama.cpp Runtime 的硬體相容性。本次先提供 CUDA 測試包確認實機行為，正式發布前仍會再完成全套封裝驗證。

## 主要更新

- 簡單模式會偵測 NVIDIA／AMD 顯卡及 VRAM，分為未滿 4 GB、4 GB～未滿 8 GB、8 GB 以上。
- 未滿 4 GB 使用 Hy-MT2 `i1-IQ3_XXS`；4 GB～未滿 8 GB 使用 `i1-IQ4_NL`；8 GB 以上使用 `i1-Q6_K`。
- 簡單模式只使用 GPU llama.cpp Runtime：NVIDIA 優先 CUDA、AMD 優先 HIP，原生 Runtime 不可執行時自動改用 Vulkan。
- 純 CPU 應用包也會透過 `nvidia-smi` 讀取 NVIDIA VRAM，避免 Windows 將大容量顯存誤判為未知。
- llama.cpp 下載器會直接查詢最新可下載的官方 nightly，不再停留於穩定版內舊的 nightly 指標。
- Runtime 驗證若發生 Windows `0xC0000005`，會保留錯誤資訊、清理失敗暫存檔，並嘗試 Vulkan GPU Runtime；既有可用版本不會被覆蓋。

## 套件說明

- CUDA、CPU 與 ROCm App Update 必須用於相同 Profile。
- 本次 CUDA 測試包用於確認 v1.4.8 的首次設定、Runtime 下載與本機翻譯流程。
