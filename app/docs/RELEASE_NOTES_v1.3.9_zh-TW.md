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

## 翻譯、Llama 與操作流程

- OpenAI 雲端 ASR、OpenAI GPT 翻譯與 Google Gemini 翻譯改用各自獨立的 API Key 欄位，舊版一般設定金鑰會自動遷移。
- OpenAI 與 Gemini 使用預設官方端點，翻譯頁補齊用途、模型、端點與連線測試說明。
- Llama 執行頁可快速選擇 GGUF 模型、套用並重啟伺服器，並整合測試翻譯流程。
- Llama Runtime 管理可直接讀取 llama.cpp 官方 Release，依 CPU／CUDA／ROCm 推薦 Windows Runtime，並在頁面內下載安裝。

## 字幕分享與介面穩定性

- 字幕分享頁提供桌面版與行動版完整網址、區網 IP 偵測、複製按鈕、防火牆與公開網路安全說明。
- 字幕外觀預設開啟原文、翻譯、時間戳、處理延遲與自動捲動，既有使用者會進行一次性遷移。
- 設定頁、字幕外觀與應用啟動加入穩定載入骨架，限制 Qt WebChannel 等待時間，降低刷新與配置覆蓋造成的空白閃爍。
- 修正 Windows 配置原子寫入遇到暫時鎖定時誤退回預設值；現在會跨程序鎖定、重試並保留已讀取配置。

## 媒體輸入與打包

- 打包版內建 Node.js 22+ JavaScript Runtime，yt-dlp 會自動啟用 EJS 元件，改善新版 YouTube 格式擷取。
- CPU／CUDA／ROCm Full 與 App Update 均由打包流程驗證內建 JavaScript Runtime。
- 修正 ASR Runtime Python 解析參數不一致、CPU sidecar 選擇與模型管理未分流等問題。
