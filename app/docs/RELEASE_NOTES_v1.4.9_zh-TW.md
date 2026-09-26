# Stream Translator v1.4.9 更新說明

本版提供 CUDA、CPU、ROCm 三種套件；請依硬體選擇 Full package 或同 Profile App Update。

## 主要更新

- 新安裝與「重置預設」改用 FireRed OmniStreamVAD 原生 START／END 事件切段。預設最短音訊 0.7 秒、原生最長切片 6 秒、前綴保留 0.25 秒；原生語音閾值 0.35、平滑 5 frame、起音回溯 5 frame、最短語音 8 frame、最長語音 2000 frame、句尾靜音 20 frame。既有 `config.yaml` 保留使用者已儲存的設定。
- 修正桌面視窗中 WARP 等外部連結按下後無法開啟的問題；首次模式選擇加入 WARP 下載與「流量和 DNS」連線指引。
- 修正 App Update 在 Windows 後端尚未退出時遇到 `WinError 5` 的情況；更新器等待主程式與後端關閉，並改善檔案移動及回復流程。
- 修正即時字幕重疊去除後仍顯示未翻譯原文的情況。
- 簡單模式初次設定會為未指定語言的使用者預設日文辨識與繁體中文翻譯；改善 Windows 顯示卡顯存偵測及顯存未知時的模型建議。
- 模型下載增加獨立記錄，方便追查下載來源與失敗原因。

## 套件與更新

- 提供 CUDA、CPU 與 ROCm Experimental 的 Full package 和同 Profile App Update；CUDA／ROCm 可另外使用 CPU ASR sidecar。
- v1.4.9 App Update 使用 `runtime_replace`，包含完整且與 Profile 相符的 `_runtime`，以帶入原生 VAD 程式碼與依賴；更新器會在啟動失敗時回復舊 Runtime。App Update 僅適用於相同 Profile，跨 Profile 請使用對應 Full package。
- CUDA App Update 以 `.part01`、`.part02` 提供；將兩檔與 `merge-full-package.bat` 放在同一資料夾合併成 ZIP，再交給更新器。CPU 與 ROCm App Update 是單一 ZIP。
- 下載檔案、合併腳本與 SHA-256 清單請見 v1.4.9 GitHub Release。
