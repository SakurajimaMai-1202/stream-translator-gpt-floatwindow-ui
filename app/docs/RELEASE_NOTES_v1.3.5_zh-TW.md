# Stream Translator v1.3.5

v1.3.5 是全應用設定載入效能修正版。CUDA、CPU 與 ROCm Experimental 三個 package 共用相同主程式修正，runtime 與 ASR 支援範圍延續 v1.3.4。

## 本次更新重點

- 後端配置改用記憶體快取與檔案簽章偵測，只有 `config.yaml` 被外部修改時才重新解析。
- 前端所有頁面共用配置快照及進行中的讀取請求，避免同時發出多個完整配置請求。
- 保存、重置、匯入及跨視窗同步後直接套用後端回傳配置，不再立即重新讀取一次。
- 首頁的輸入、ASR 與翻譯設定由三次磁碟寫入合併為一次。
- 一般設定自動保存時，只有 runtime 設定真的改變才重新偵測硬體。
- 匯入配置後不再強制重新整理整個 WebView。
- 保留原子寫入、跨程序鎖與外部修改偵測，避免不同程序互相覆蓋設定。

## 效能驗證

- 100 次配置讀取由約 `447 ms` 降至約 `3.31 ms`，本機測試約提升 `135` 倍。
- 配置快取、外部修改刷新、跨程序保存與快照隔離測試均已通過。
- Production frontend build 已成功完成。

## 三版本說明

- CUDA：NVIDIA CUDA 正式版；包含 Faster-Whisper、Qwen3-ASR、SenseVoiceSmall 與 Parakeet CTC JA。
- CPU：CPU 相容版；使用 CPU-only PyTorch runtime，保留遠端 ASR／翻譯能力。
- ROCm Experimental：AMD ROCm/HIP 版；Radeon RX 9070 XT 與 SenseVoiceSmall 已有實機驗證紀錄。

## 更新方式

- 新使用者請下載對應硬體的 Full package 分割檔。
- 已使用 v1.3.4 且 profile 相同者，可以下載對應的 App Update ZIP 覆蓋更新。
- 關閉程式並備份 `config.yaml` 後再更新。
- CUDA、CPU、ROCm App Update 不可跨 profile 混用。
- v1.3.2 與 v1.3.3 存在已知設定頁問題，請直接升級 v1.3.5。
