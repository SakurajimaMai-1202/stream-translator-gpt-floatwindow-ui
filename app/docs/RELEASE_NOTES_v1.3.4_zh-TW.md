# Stream Translator v1.3.4

v1.3.4 是 v1.3.3 的緊急修補版，修正打包後在設定頁點選轉錄/ASR 選項時 WebView 可能整個凍結、只能關閉程式的問題，並重新整理 CPU runtime。

## 重要注意事項

- v1.3.2 不建議繼續使用，請直接升級 v1.3.4。
- v1.3.3 包含部分修正，但打包後仍可能在設定頁點選轉錄/ASR 選項時凍結，請直接升級 v1.3.4。
- App Update 只能覆蓋同 profile 完整包；不要用 CUDA App Update 覆蓋 CPU 或 ROCm 完整包。
- CPU 版已改用 CPU-only PyTorch runtime，不會攜帶 CUDA / ROCm GPU torch runtime。

## 修正內容

- 修正 ASR 選項互斥 watcher 反覆觸發自己的問題。
- 保留 v1.3.3 的「ASR模型管理」命名、設定頁初始 tab 修正、ROCm SenseVoice / FunASR runtime 修正。
- 轉錄選項仍會維持單一 ASR 後端，不會同時選到 Qwen3-ASR / SenseVoiceSmall / Parakeet CTC JA。
- CPU package runtime 改為 `torch 2.12.1+cpu` / `torchaudio 2.11.0+cpu`，Full package 約 1.33 GiB。
- 補上 `omnivad` runtime dependency，避免乾淨 CPU runtime 缺少 FireRed VAD 相關模組。

## 影響範圍

- CUDA / CPU / ROCm Experimental 三個 package 都建議更新。
- 已下載 v1.3.2 / v1.3.3 的使用者建議直接升級 v1.3.4。
- 已有同 profile 完整包者可用對應 App Update 覆蓋；不要跨 CUDA / CPU / ROCm 混用 App Update。
