# llama.cpp 顯卡選擇修正

日期：2026-10-09

## 行為

- CPU Full 偵測 AMD 或 Intel Arc 獨顯時，預設推薦 Vulkan；NVIDIA 保留 CUDA 優先。ROCm 套件的 llama.cpp 亦預設 Vulkan，ASR 後端未變更。HIP／SYCL 仍可手動選擇。
- 透過實際選用的 llama-server `--list-devices` 列舉裝置，不使用 Windows 顯卡編號代替 Runtime 裝置 ID。
- 自動選擇排除內顯，在可用獨顯中選擇記憶體最大者；啟動以 `--device` 及 `--split-mode none` 明確使用單卡。可手動選擇，亦可自行開啟內顯選項。
- 修正 Intel Arc Graphics／140V／130V、AMD Radeon 680M／780M 等內顯名稱判定，DXGI 提供專用／共享記憶體輔助辨識。
- 保存手動裝置 ID 與名稱；裝置消失、被排除或 ID 對應名稱變更時拒絕啟動，不靜默改用其他卡。
- UI 區分已指定顯卡與已確認模型卸載的顯卡。只列出裝置或初始化後端不構成實際使用證據；須有裝置放置／緩衝紀錄及正數卸載層數。
- 新版 Runtime 開啟必要的日誌層級以提供卸載證據，舊版不支援時維持未確認。GPU 層數為 0 時，支援裝置參數的 Runtime 使用 `--device none`；舊版可啟動，但顯示裝置尚未確認。

## 驗證

- 硬體判定、後端推薦、Runtime 安裝、裝置解析、啟動參數、環境變數隔離及既有相容性回歸：68 項通過。
- Vue／TypeScript／Vite production build 通過，本機 `backend/static` 已更新。
- RTX 4060 Ti、llama.cpp b11429 CUDA12、既有 HY-MT1.5 1.8B GGUF：隔離連接埠 18921 啟動，33 層實際卸載，狀態 confirmed=true，短 completion 有輸出，測試程序停止。此測試直接呼叫 Runtime，不驗收翻譯內容或 OpenCC 最終輸出。
- 實機證據：`app/release-validation-v1.5.0/llama-gpu-selection-smoke.json`；重現入口：`tools/llama_gpu_selection_smoke.py`。

## 限制

沒有 AMD／Intel 實體雙顯卡筆電、長時間直播或完整桌面視覺操作實測；名稱與 DXGI 判定無法保證涵蓋所有驅動命名。未知名稱可能需使用者確認。

本次未重新產生 Full／App Update ZIP，未推送或發布。既有發行 ZIP 與待發布更新說明維持其原有套件內容；需後續重新打包驗收，才會包含這次顯卡選擇功能。
