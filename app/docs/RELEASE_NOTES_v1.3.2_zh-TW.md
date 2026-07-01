# Stream Translator v1.3.2

v1.3.2 是 CUDA / CPU / ROCm 三版本同步更新。這版重點是把 runtime profile 的能力邊界整理清楚，並讓 CUDA 版新增 Parakeet CTC 1.1B JA。

## 下載提醒

- 請依硬體下載 CUDA / CPU / ROCm Experimental 對應的 Full package。
- App Update 只能覆蓋同 profile 的完整包，不要混用 CUDA / CPU / ROCm 更新包。
- GitHub 分割包請把同一組 `.part*`、`merge-full-package.bat`、`SHA256SUMS-v1.3.2.txt` 放在同一個資料夾。
- 合併後請用 `SHA256SUMS-v1.3.2.txt` 驗證檔案完整性。

## CUDA 版

- 新增 Parakeet CTC 1.1B JA experimental。
- Parakeet CTC JA 使用 `grider-transwithai/parakeet-ctc-1.1b-ja`，僅限 CUDA 版與日文輸入。
- Parakeet 預設使用 `bfloat16`；目前已可正式跑，穩態顯存約 4GB，載入峰值會略高。
- Parakeet 載入流程改用 NVIDIA NeMo，並加入參數量、buffer、CUDA allocated / reserved / max allocated 診斷。
- CUDA runtime profile 驗證會檢查 NeMo、FunASR、torchaudio、Qwen3-ASR、Faster-Whisper 與 PyInstaller。
- 保留 Faster-Whisper 全系列、Qwen3-ASR 0.6B / 1.7B / 1.7B-JA、Qwen3 streaming experimental 與 SenseVoiceSmall compatibility。

## CPU 版

- CPU 版保留遠端 API / 遠端字幕能力，適合沒有獨顯或先測功能的環境。
- CPU profile 會強制 CPU device policy，避免誤用顯卡。
- Faster-Whisper 建議使用 small / medium。
- Qwen3-ASR offline 支援 0.6B。
- Qwen3-ASR streaming 0.6B 仍列 experimental，速度需依機器測試。
- SenseVoiceSmall CPU 可用，不先標慢速；實際速度受 CPU 與音訊長度影響。

## ROCm Experimental

- Qwen3-ASR offline 支援 0.6B / 1.7B / 1.7B-JA，CUDA / ROCm 預設使用 `bfloat16`。
- Qwen3-ASR streaming 仍列 experimental，因上游明確列 CUDA / Apple Silicon / CPU，未正式列 ROCm。
- SenseVoiceSmall 在 ROCm profile 先列 experimental，需更多 AMD 實機 ASR smoke test 後再提升狀態。
- Radeon RX 9070 XT 已由使用者實機測試確認可用。
- 裝置策略預設使用 auto discrete GPU，避免選到 AMD 內顯 / APU 或虛擬顯示裝置。
- Parakeet CTC JA 目前仍只放 CUDA 版，不放 ROCm，因它依賴 NVIDIA NeMo / CUDA 路線。

## 共通改進

- Runtime Profile UI / capability matrix 會依 CUDA / CPU / ROCm 顯示不同 ASR 能力。
- 輸入語言拆分繁體中文與簡體中文，Qwen3-ASR 會在底層映射為 Chinese。
- 模型管理支援 Parakeet / SenseVoice / Qwen3-ASR / Faster-Whisper 的下載、列出與刪除。
- 顯卡偵測會優先獨顯，避免誤選內顯、APU 或虛擬顯示裝置。
- 浮動字幕視窗的透明控制按鈕不再遮住字幕文字。
- 三個 Full package / App Update 都會寫入對應 profile 的教學、更新說明與診斷提示。

## 更新建議

- 新使用者請下載對應 profile 的 Full package。
- 舊版同 profile 使用者可用 App Update 覆蓋更新。
- 若更換 CUDA / CPU / ROCm profile，建議重新下載對應 Full package。
- 更新前請保留 `models`、`config.yaml`、`output`、`art`、`logs` 等資料夾。
