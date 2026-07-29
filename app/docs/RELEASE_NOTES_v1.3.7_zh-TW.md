# Stream Translator v1.3.7

v1.3.7 是執行體驗、Cookie 管理與三版本打包流程更新。CUDA、CPU 與 ROCm Experimental 共用同一份功能程式碼，並使用各自獨立且經驗證的 PyTorch／ASR runtime。

## 使用者功能與修正

- 新增瀏覽器 Cookie 與 `cookies.txt` 匯入流程，可依 YouTube、TikTok 等平台個別更新 Cookie。
- 瀏覽器 Cookie 讀取失敗時提供明確提示，並保留 Firefox 或 Netscape `cookies.txt` 的替代方式。
- 移除尚未正式整合的 Qwen3-ASR Streaming 功能標示，避免介面造成錯誤期待。
- 停止轉譯後會清除錄音裝置的綠色狀態通知。
- Windows WebView 預設採用較穩定的軟體渲染策略，改善啟動階段介面閃爍與畫面破損。
- 修正 Qt WebChannel 載入競態；正式版浮動字幕的齒輪會開啟獨立字幕設定視窗，不再誤顯示於透明字幕視窗內。

## CUDA

- 保留 Faster-Whisper、Qwen3-ASR offline、SenseVoiceSmall 與 Parakeet CTC 1.1B JA。
- Qwen3-ASR 與 Parakeet CTC JA 依既有策略使用 `bfloat16`。
- Parakeet CTC JA 僅包含於 CUDA runtime。

## CPU

- 使用 CPU-only PyTorch runtime，不攜帶 CUDA／ROCm PyTorch。
- 保留遠端 API、遠端字幕、Faster-Whisper、Qwen3-ASR 0.6B 與 SenseVoiceSmall。
- 預設 ASR device policy 為 `cpu`，避免誤用 GPU。

## ROCm Experimental

- 使用獨立 ROCm／HIP PyTorch runtime。
- 支援 Qwen3-ASR offline 與 SenseVoiceSmall；SenseVoiceSmall 已通過 AMD ROCm 實機驗證。
- 預設選擇 AMD 獨立顯示卡並排除內顯／APU；Radeon RX 9070 XT 已有實機驗證結果。

## 打包與下載

- GUI／前端只建置一次，再共用於 CUDA、CPU 與 ROCm 三個套件。
- 大量檔案複製改用多執行緒 `robocopy`。
- Final package 使用多執行緒 7-Zip Deflate 壓縮。
- Full package 自動分割成 `.partNN`，並執行重組 SHA256 與 ZIP 完整性驗證。
- Release 同時提供三版 App Update、分割 Full package、合併批次檔、manifest 與 SHA256 清單。
- App Update ZIP 已修正為根目錄直接包含主程式內容，解壓到既有同 profile 完整包即可正確覆蓋 UI 與後端程式。

## 更新注意事項

- Full package 使用者：下載同一 profile 的所有 `.partNN`，執行 `merge-full-package.bat` 後解壓。
- App Update 使用者：只能覆蓋到相同 profile 的既有完整包，不可混用 CUDA、CPU 與 ROCm App Update。
- 更新前請備份 `config.yaml`，並保留 `models`、`output`、`art` 與 `logs`。
- 首次使用前請到「ASR 模型管理」下載需要的模型。
