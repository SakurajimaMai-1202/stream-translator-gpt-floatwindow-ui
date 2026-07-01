# Stream Translator v1.3.3

v1.3.3 是 v1.3.2 的修補版，重點修正設定頁操作、ASR 引擎選擇互斥、ROCm SenseVoice runtime 缺漏，並重新提供 CUDA / CPU / ROCm Experimental 三版本完整包與 App Update。

## 共同修正

- 修正設定頁切換時的整頁閃爍感，移除主內容 route fade transition。
- 修正第一次從側邊欄點「ASR模型管理」時會先落到「一般設定」的問題。
- 將「模型管理」命名調整為「ASR模型管理」，避免和 Llama / 自訂模型管理混淆。
- 修正「系統設定 > 轉錄選項」可能同時勾選 Qwen3-ASR / SenseVoiceSmall / Parakeet CTC JA 等不同 ASR 後端的問題。
- 載入舊設定檔時會自動整理 ASR 後端旗標；啟動轉錄時後端也會收斂為單一 ASR backend，避免舊 YAML 殘留多選狀態。

## CUDA 版

- 保留 v1.3.2 的 Parakeet CTC 1.1B JA experimental 支援。
- Parakeet CTC JA 預設使用 `bfloat16`，正式驗證可啟動並可進行日文 ASR。
- 保留 Qwen3-ASR 0.6B / 1.7B / 1.7B-JA、SenseVoiceSmall、Faster-Whisper 支援。
- 轉錄選項改為單一 ASR 後端選擇，避免 CUDA 版同時送出多個 ASR flags。

## CPU 版

- 保留遠端翻譯與本機 ASR 設定能力。
- 保留 Faster-Whisper small / medium、Qwen3-ASR 0.6B、SenseVoiceSmall CPU 支援。
- 修正設定頁 ASR 多選狀態，CPU package 不會因舊設定誤送 CUDA / ROCm 專用 ASR flags。

## ROCm Experimental 版

- 修正 SenseVoiceSmall 無法使用的 runtime 依賴問題；ROCm build runtime 會包含 FunASR。
- 保留 Qwen3-ASR 0.6B / 1.7B / 1.7B-JA，CUDA / ROCm 預設皆使用 `bfloat16`。
- SenseVoiceSmall 在 ROCm 仍標示 experimental；已針對 AMD ROCm/HIP runtime 重新打包，實機仍建議用 `diagnose_runtime.ps1` 和 `smoke_sensevoice_asr.ps1` 驗證。
- Parakeet CTC JA 維持 CUDA-only，不會在 ROCm package 顯示為可用正式選項。

## 更新建議

- 新使用者請下載對應硬體的 Full package。
- 已有 v1.3.2 同 profile 完整包的使用者，可使用對應的 App Update 覆蓋更新。
- 不要混用 CUDA / CPU / ROCm 的 App Update；App Update 必須覆蓋同 profile 的完整包。
- 覆蓋更新前建議備份 `config.yaml`，並保留 `models`、`output`、`art`、`logs`。
