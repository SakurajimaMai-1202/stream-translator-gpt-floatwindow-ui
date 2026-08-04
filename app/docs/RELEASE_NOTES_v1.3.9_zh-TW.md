# Stream Translator v1.3.9

v1.3.9 重整 CPU ASR 架構，CUDA、CPU 與 ROCm Experimental 三包維持各自獨立的主要 runtime，同時讓 CUDA／ROCm 使用者可選擇安裝 sherpa-onnx CPU ASR sidecar，在同一套程式中切換 GPU ASR 與 CPU ASR。

## CPU ASR 與模型

- 新增 `CPU / sherpa-onnx` 運算模式與獨立 runtime 探測。
- 支援 Parakeet TDT 0.6B v3、NVIDIA Parakeet TDT-CTC 0.6B 日文、Fun-ASR Nano 2512、SenseVoice 與 Qwen3-ASR 0.6B 的 CPU 能力與模型選擇。
- 修正 Parakeet TDT 0.6B v3 在日文輸入語言下無法切換的問題；模型語言限制改由能力表處理。
- CPU runtime 不含 PyTorch，使用 sherpa-onnx／ONNX Runtime，降低 runtime 體積與 CPU 推論依賴衝突。

## 獨立 Sidecar 安裝

- CUDA／ROCm 設定頁的「ASR 模型管理」可下載並安裝版本相符的 CPU ASR sidecar。
- 安裝流程包含下載進度、SHA-256 驗證、安全解壓、runtime 實際 import 驗證、同磁碟 staging 與失敗回復。
- Sidecar 安裝完成後請重新啟動程式，再於轉錄選項切換至 `CPU / sherpa-onnx`。
- App-Update 不重複內含 sidecar；既有 CUDA／ROCm 使用者可另行下載 `StreamTranslator-CPU-ASR-Sidecar-v1.3.9.zip`。

## 三包差異

- CPU Full：主 runtime 即為 torch-free sherpa-onnx CPU runtime。
- CUDA Full：保留原 CUDA ASR runtime，並內建 CPU ASR sidecar。
- ROCm Full：保留原 ROCm Experimental runtime，並內建 CPU ASR sidecar。
- 三種 App-Update：只更新程式與各 profile 必要依賴，不附帶大型 sidecar。

## 使用提醒

- Sidecar 必須與程式版本一致；v1.3.9 安裝器預設只抓取 v1.3.9 Release 資產。
- sherpa-onnx 模型仍需依模型管理頁下載；runtime sidecar 不包含模型權重。
- ROCm 支援維持 Experimental；新增 CPU sidecar 不會改動 ROCm 主 runtime。
