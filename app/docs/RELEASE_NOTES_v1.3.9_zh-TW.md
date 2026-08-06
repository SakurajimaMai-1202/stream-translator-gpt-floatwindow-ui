# Stream Translator v1.3.9 更新說明

v1.3.9 主要改善 Runtime Profile、CPU ASR、模型管理、Llama 操作流程與設定穩定性。CUDA、CPU、ROCm Experimental 維持各自獨立的主 Runtime；CUDA／ROCm 使用者也能在同一套程式中切換至 sherpa-onnx CPU ASR。

## 發佈內容

| Profile | 主要 Runtime | CPU ASR sidecar | 適用環境 |
|---|---|---|---|
| CUDA | NVIDIA CUDA 原生 ASR | Full 包內建 | NVIDIA 顯示卡 |
| CPU | sherpa-onnx／ONNX Runtime | 不需要，主 Runtime 即為 CPU ASR | 純 CPU 或無相容 GPU |
| ROCm Experimental | AMD ROCm/HIP 原生 ASR | Full 包內建 | 支援 Windows ROCm 的 AMD 顯示卡 |

三種 Profile 都提供個別 App Update，且不可跨 Profile 混用。

## 1. CPU ASR 架構重整

- 新增實際有效的 `CPU / sherpa-onnx` 運算模式與獨立 Runtime 探測。
- CPU Full 改用不含 PyTorch 的 sherpa-onnx／ONNX Runtime，降低體積與依賴衝突。
- CPU Profile 不再提供 faster-whisper；既有 faster-whisper 使用者需改用 CUDA 原生 Runtime、sherpa-onnx CPU 模型或雲端 ASR。
- CUDA／ROCm Full 內建獨立 CPU ASR sidecar，可在保留 GPU 原生 ASR 的同時切換 CPU ASR。
- Runtime 切換會改變後端 Python、可用引擎與模型，不再只是介面選項。
- Runtime 狀態新增 CPU 型號顯示，方便確認目前實際運算裝置。
- 修正 `_resolve_profile_python()` 參數不一致造成轉譯無法啟動的錯誤。
- 修正 CPU sidecar 選擇、Runtime Python 解析與 Profile 狀態同步問題。

## 2. ASR 模型管理分流

- 原生 CUDA／ROCm 模型與 sherpa-onnx CPU 模型改為分開管理。
- Sherpa-ONNX 分頁更新模型描述、格式、語言與 Runtime 相容性資訊。
- 模型清單依目前 Runtime、ASR 引擎、語言及能力表過濾，避免選到不相容模型。
- 修正 Parakeet TDT 0.6B v3 在日文輸入下無法切換的問題。
- 補強 Parakeet、Fun-ASR、SenseVoice 與 Qwen3-ASR 的 CPU 能力與模型路徑處理。
- 模型下載使用可攜式模型目錄，避免不同 Profile 共用錯誤格式的權重。

Sidecar 只包含 Runtime，不包含模型權重；切換 CPU ASR 後仍需到 Sherpa-ONNX 模型頁下載相符模型。

## 3. CPU ASR sidecar 安裝

- CUDA／ROCm 的「ASR 模型管理」可下載版本相符的 CPU sidecar。
- 安裝流程包含下載進度、SHA-256 驗證、安全解壓、Runtime import 驗證與失敗回復。
- 使用同磁碟 staging 與替換流程，降低 Windows 跨磁碟或檔案鎖定造成的安裝失敗。
- 安裝完成後需重新啟動程式，再於「轉錄選項」選擇 `CPU / sherpa-onnx`。
- v1.3.9 安裝器預設只接受 v1.3.9 sidecar，避免 Runtime 與應用版本不一致。

獨立資產：`StreamTranslator-CPU-ASR-Sidecar-v1.3.9.zip`

## 4. Llama 執行與模型流程

- Llama 執行設定改為獨立操作頁。
- 可快速選擇已下載的 GGUF 模型，不必手動輸入完整路徑。
- 將模型、GPU layers、context、埠號與啟動參數整理為較清晰的執行流程。
- 提供「套用並重新啟動」，設定變更後可直接重啟 llama-server。
- 伺服器狀態與測試翻譯整合在同一操作區域。
- 模型管理與執行設定分離，避免下載模型與啟動伺服器混在同一表單。
- Llama Runtime 管理可讀取 llama.cpp 官方 Release，依 CPU／CUDA／ROCm 推薦 Windows Runtime，並直接下載安裝。

## 5. 翻譯後端與金鑰

- OpenAI 雲端 ASR、OpenAI GPT 翻譯與 Google Gemini 翻譯改用各自獨立的 API Key。
- 舊版共用金鑰會進行一次性遷移，之後各用途分開儲存。
- OpenAI 與 Gemini 預設使用官方端點。
- 翻譯頁補充後端用途、模型、端點、金鑰位置與連線測試說明。
- OpenAI-compatible 本機服務保留自訂 Base URL 與模型設定。
- 修正自訂翻譯提示詞啟用時，術語表未一併傳入翻譯器的問題。

## 6. 字幕分享與外觀

- 字幕分享設定補齊桌面版、行動版與 API 網址。
- 新增區網 IP 偵測、複製按鈕、Windows 防火牆與公開網路安全說明。
- 字幕外觀預設開啟原文、翻譯、時間戳、處理延遲與自動捲動。
- 既有使用者只執行一次預設值遷移，之後尊重手動關閉的選項。
- 改善桌面、行動與浮動字幕頁的初始化流程，降低重新整理時的空白與閃爍。

字幕分享沒有內建公開 Internet 身分驗證。外網使用時應透過具備 HTTPS 與驗證的反向代理或 VPN。

## 7. 設定載入與介面穩定性

- 設定頁、字幕外觀與主畫面加入穩定的載入狀態，避免先顯示預設值再跳回使用者配置。
- 限制 Qt WebChannel 等待時間，避免通道未建立時整頁長時間空白。
- 減少重複 API 請求、狀態覆蓋與頁面切換造成的閃爍。
- Windows 配置原子寫入加入跨程序鎖定與重試。
- 修正暫存檔替換遇到 `[WinError 5] 存取被拒` 時誤報「配置載入失敗」並回退預設值的問題。
- 配置讀取使用記憶體快取並偵測外部變更，同時回傳隔離副本避免非預期寫入。

## 8. VAD、字幕處理與延遲

- VAD 預設改為 FireRed VAD。
- 強化 ASR 重疊去重、字幕組裝與片段後處理。
- 新增延遲統計與追蹤資訊，便於辨識 VAD、ASR、翻譯與字幕輸出的耗時。
- 新增翻譯術語表稽核，協助檢查指定詞彙是否依設定輸出。
- 改善 Windows 標準輸入輸出編碼處理，降低打包版日誌亂碼。

## 9. 媒體輸入與 yt-dlp

- 打包版內建 Node.js 22+ JavaScript Runtime。
- yt-dlp 自動加入 `--js-runtimes node:<path>`，支援新版 YouTube EJS 擷取流程。
- CPU／CUDA／ROCm Full 與 App Update 都會由打包流程驗證 Node.js Runtime。
- 改善打包版找不到 JavaScript Runtime、部分 YouTube 格式缺失的警告。

## 10. 打包與驗證

- CPU Runtime manifest 升級為 schema 3，記錄 sherpa-onnx 版本、torch-free 狀態與應用版本。
- CUDA／ROCm Full 內建相同版本的 CPU sidecar manifest。
- 打包流程驗證 Profile、Python Runtime、必要 imports、Node.js、sidecar 與應用版本。
- Final 模式建立 App Update、Full ZIP 分割檔、合併工具、release manifest 與 SHA-256 清單。
- v1.3.9 GitHub Release 的 15 個資產已逐一核對檔名、位元組大小與 SHA-256。

## 升級方式

### 從舊版完整升級

1. 備份目前的 `config.yaml`。
2. 下載與硬體相符的 v1.3.9 Full package 全部分割檔。
3. 使用 `merge-full-package.bat` 合併。
4. 使用 `SHA256SUMS-v1.3.9.txt` 驗證 ZIP。
5. 解壓至新的獨立資料夾後啟動。
6. 確認設定與模型路徑後，再移除舊版。

### 更新既有 v1.3.9 Profile

1. 關閉 Stream Translator 與 llama-server。
2. 下載與目前 Profile 相符的 App Update。
3. 備份 `config.yaml` 後覆蓋應用檔案。
4. 重新啟動並確認 Runtime Profile。

不要使用 CUDA App Update 更新 CPU／ROCm 安裝，其他組合亦同。

## 已知限制

- ROCm for Windows 仍為 Experimental，實際支援取決於 AMD 顯示卡、驅動與 Runtime。
- Sherpa-ONNX 與原生 GPU 模型格式不同，不能直接共用同一份模型檔。
- CPU Profile 不支援 faster-whisper，舊版下載的 faster-whisper 模型不會出現在 CPU／Sherpa-ONNX 模型清單。
- CPU sidecar 必須與應用版本一致，安裝後需重新啟動。
- 本機大型模型第一次載入會較慢，並需要足夠 RAM／VRAM 與磁碟空間。
- 平台 Cookie、串流格式與 YouTube 擷取能力可能隨網站更新而變動。

## 下載與驗證

- [GitHub v1.3.9 Release](https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/releases/tag/v1.3.9)
- `release-manifest-v1.3.9.json`：資產結構、Profile 與完整包雜湊
- `SHA256SUMS-v1.3.9.txt`：所有發佈檔案的 SHA-256
- `merge-full-package.bat`：合併 Full package 分割檔
