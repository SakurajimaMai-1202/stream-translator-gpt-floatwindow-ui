# Stream Translator v1.3.6

v1.3.6 是直播翻譯與字幕延遲可觀測性更新。CUDA、CPU 與 ROCm Experimental 三個 package 共用同一份功能程式碼，依 runtime profile 使用各自的 PyTorch 與 ASR 能力。

## 本次更新重點

- 翻譯模型策略分流：Hy-MT2、一般聊天模型、OpenAI 相容 API 與 Gemini 使用各自適合的提示、取樣與輸出解析。
- Hy-MT2 使用專用純文字提示格式，不套用一般 system prompt。
- 原文與翻譯維持成對顯示；翻譯可非阻塞平行處理，畫面仍依字幕順序提交。
- 新增 ASR 重疊去重與短句組句器，降低重複文字並改善翻譯語境。
- 音訊與 VAD 參數完整接入 UI、YAML、CLI 與實際管線，提供更低延遲的直播切段控制。
- 浮動字幕與桌面字幕可顯示每句 ASR、排隊、翻譯及總處理延遲。
- 延遲資訊放在時間後方，可獨立調整文字顏色。
- 新增機器可讀字幕事件；舊 runtime 可透過 latency log 相容顯示。
- 保留 v1.3.5 的配置讀取快取、原子保存、跨視窗同步與外部修改偵測。

## 翻譯模型建議

- Hy-MT2：選擇 `Hy-MT2 專用` 模型策略，適合 llama.cpp / OpenAI-compatible 本地服務。
- Gemma 或其他聊天模型：選擇 `一般聊天模型`，使用 system + user 訊息。
- OpenAI / Gemini：可使用 `結構化 API`，降低模型回傳說明文字或重複前文的機率。
- 不確定時可先使用 `自動判斷`；若本地模型名稱無法辨識，請手動指定策略。

## 三版本說明

- CUDA：NVIDIA CUDA 正式版；包含 Faster-Whisper、Qwen3-ASR、SenseVoiceSmall 與 Parakeet CTC JA。
- CPU：CPU 相容版；使用 CPU-only PyTorch runtime，保留本地與遠端 ASR／翻譯能力。
- ROCm Experimental：AMD ROCm/HIP 版；Radeon RX 9070 XT、Qwen3-ASR 與 SenseVoiceSmall 已有實機驗證紀錄。

## 更新方式

- 新使用者請下載對應硬體的 Full package 分割檔，合併後解壓。
- 第一次啟動後，請先到「ASR模型管理」下載需要的模型。
- 已使用 v1.3.5 且 profile 相同者，可下載對應的 App Update ZIP 覆蓋更新。
- 更新前請關閉程式並備份 `config.yaml`。
- CUDA、CPU、ROCm App Update 不可跨 profile 混用。
- 更新後第一次啟動請重新確認翻譯模型策略與字幕延遲顯示設定。
