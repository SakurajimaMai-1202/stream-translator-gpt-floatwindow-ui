# Stream Translator FloatWindow

Windows 即時語音辨識、翻譯與浮動字幕工具。可擷取線上影音網址、系統聲音或音訊輸入，透過本機／雲端 ASR 轉錄，再使用 OpenAI、Google Gemini 或本機 llama.cpp 翻譯。

[下載最新版](https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/releases/latest) · [v1.3.9 更新說明](app/docs/RELEASE_NOTES_v1.3.9_zh-TW.md) · [問題回報](https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/issues)

![Windows](https://img.shields.io/badge/platform-Windows-lightgrey)
![NVIDIA CUDA](https://img.shields.io/badge/GPU-NVIDIA%20CUDA-green)
![AMD ROCm](https://img.shields.io/badge/GPU-AMD%20ROCm%20Experimental-orange)
![CPU sherpa-onnx](https://img.shields.io/badge/CPU-sherpa--onnx-blueviolet)
![Release](https://img.shields.io/badge/release-v1.3.9-blue)

<img width="2381" height="1058" alt="Stream Translator FloatWindow" src="https://github.com/user-attachments/assets/0a663535-dd94-40a6-8444-3c00844bc563" />

## 演示影片

[觀看 Stream Translator FloatWindow 操作演示](https://youtu.be/p1O2Ecu4js0)

## 主要功能

- 即時轉錄 YouTube、Twitch、Bilibili、一般串流網址、音訊檔與系統聲音。
- 支援 NVIDIA CUDA、純 CPU 與 AMD ROCm Experimental 三種 Runtime Profile。
- 可在 CUDA／ROCm 版本內切換至 sherpa-onnx CPU ASR。
- 支援 OpenAI、Google Gemini、OpenAI-compatible API 與本機 llama.cpp 翻譯。
- 提供桌面浮動字幕、瀏覽器字幕頁、行動裝置字幕分享及 SRT／TXT／ASS 匯出。
- 內建 ASR 與 LLM 模型管理、llama.cpp Runtime 安裝與伺服器控制。
- 支援 VAD 切片、術語表、ASR 修正規則、字幕外觀與延遲資訊。

## v1.3.9 重點

v1.3.9 重新整理 Runtime、ASR 模型與設定流程：

- CPU 版本改用不含 PyTorch 的 sherpa-onnx／ONNX Runtime。
- CUDA 與 ROCm Full 包內含獨立 CPU ASR sidecar，可切換 GPU／CPU ASR。
- ASR 模型管理依原生 GPU 與 sherpa-onnx 模型分流，避免下載錯誤格式。
- 重新規劃 Llama 執行、模型選擇、伺服器啟動、測試翻譯與 Runtime 安裝流程。
- OpenAI ASR、OpenAI 翻譯與 Gemini 翻譯金鑰分開管理。
- 完善字幕分享頁與安全說明，並改善設定載入、頁面刷新及字幕畫面閃爍。
- 打包版內建 Node.js 22+，供 yt-dlp 處理新版 YouTube JavaScript 擷取流程。
- 修正 Windows 配置檔暫時鎖定時誤載入預設值的問題。

完整內容請見 [v1.3.9 更新說明](app/docs/RELEASE_NOTES_v1.3.9_zh-TW.md)。

## 下載版本選擇

請從 [GitHub Releases](https://github.com/SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui/releases/tag/v1.3.9) 下載，不要使用 GitHub 自動產生的 `Source code (zip)` 作為執行版。

| 版本 | 適用環境 | ASR Runtime | 完整包檔案 |
|---|---|---|---|
| CUDA | NVIDIA 顯示卡 | CUDA 原生 ASR＋sherpa-onnx CPU sidecar | `StreamTranslator-win64-CUDA-Full.zip.part01`～`.part03` |
| CPU | 無獨立顯示卡或只使用 CPU | sherpa-onnx／ONNX Runtime，不含 PyTorch | `StreamTranslator-win64-CPU-Full.zip.part01` |
| ROCm Experimental | 支援 Windows ROCm/HIP 的 AMD 顯示卡 | ROCm 原生 ASR＋sherpa-onnx CPU sidecar | `StreamTranslator-win64-ROCm-Experimental-Full.zip.part01`～`.part02` |

ROCm 支援仍屬實驗性質；不同 AMD 顯示卡、驅動與 Windows ROCm Runtime 的相容性可能不同。

### 合併完整包

1. 下載同一版本、同一 Profile 的所有 `.partXX`。
2. 將分割檔與 `merge-full-package.bat` 放在同一資料夾。
3. 執行 `merge-full-package.bat`。
4. 使用 `SHA256SUMS-v1.3.9.txt` 驗證合併後 ZIP。
5. 解壓縮至可寫入的獨立資料夾，再啟動 `Stream Translator.exe`。

不要只下載 `.part01` 後直接解壓縮；CUDA 與 ROCm 完整包必須先合併全部分割檔。

### 更新既有安裝

依目前安裝的 Profile 下載相符檔案：

- `StreamTranslator-CUDA-App-Update.zip`
- `StreamTranslator-CPU-App-Update.zip`
- `StreamTranslator-ROCm-Experimental-App-Update.zip`

更新前請關閉程式並備份 `config.yaml`。不要跨 Profile 混用 App Update。

CUDA／ROCm 使用者若缺少 CPU ASR sidecar，可在「ASR 模型管理」內安裝，或下載：

- `StreamTranslator-CPU-ASR-Sidecar-v1.3.9.zip`

Sidecar 只包含 CPU ASR Runtime，不包含模型權重；模型仍須在模型管理頁另行下載。

## 快速開始

1. 啟動 `Stream Translator.exe`。
2. 到「轉錄選項」確認 Runtime Profile 與 ASR 運算模式。
3. 到「ASR 模型管理」下載與目前引擎相符的模型。
4. 在「翻譯選項」選擇翻譯後端；不需翻譯時選擇停用。
5. 回到「即時轉譯」，輸入影音網址、選擇音訊檔或系統聲音。
6. 啟動轉譯並視需要開啟浮動字幕、瀏覽器字幕或行動字幕頁。

第一次載入大型模型可能需要較長時間。模型管理頁會區分原生 GPU 模型與 sherpa-onnx CPU 模型，兩者格式不可混用。

## ASR Runtime 與模型

### 運算模式切換

- `GPU 原生 ASR`：使用目前 CUDA／ROCm Profile 的主 Runtime。
- `CPU / sherpa-onnx`：使用獨立 CPU Runtime；CUDA／ROCm 安裝後需重新啟動程式。
- CPU Full 只提供 `CPU / sherpa-onnx`，不會載入 CUDA／ROCm Runtime。

實際切換會改變後端 Python Runtime、可選 ASR 引擎與可用模型，不只是介面標籤。

### 模型相容性

| 類型 | 建議 Profile | 說明 |
|---|---|---|
| Qwen3-ASR | CUDA／ROCm 原生；部分 CPU 模型可經 sherpa-onnx 使用 | 依模型頁顯示的 Runtime 格式下載 |
| Fun-ASR Nano／MLT Nano | CUDA／ROCm 或 sherpa-onnx CPU | 多語言模型，GPU 與 ONNX 模型分開管理 |
| SenseVoice | CUDA／ROCm 或 sherpa-onnx CPU | 適合中文、粵語、日文、英文等語音 |
| NVIDIA Parakeet | 主要為 CUDA；部分 sherpa-onnx CPU 版本 | 依語言與解碼器能力限制選擇 |
| faster-whisper | CUDA 原生 Runtime | CPU Profile 不含 faster-whisper；需要 CPU 時請改用 sherpa-onnx 模型或雲端 ASR |
| OpenAI Whisper API | 所有 Profile | 不需本機 ASR 模型，但需要 OpenAI ASR Key |

介面會依 Runtime、語言與模型能力隱藏或停用不相容選項。

## 翻譯後端與 API Key

ASR 與翻譯使用不同用途的金鑰，請在相對應欄位輸入：

| 用途 | 設定位置 | 預設端點 |
|---|---|---|
| OpenAI 雲端 ASR | 轉錄選項／OpenAI ASR | `https://api.openai.com/v1` |
| OpenAI GPT 翻譯 | 翻譯選項／OpenAI | `https://api.openai.com/v1` |
| Google Gemini 翻譯 | 翻譯選項／Gemini | Google 官方 Gemini API |
| llama.cpp／LM Studio | 翻譯選項／OpenAI-compatible | 依本機伺服器位置設定 |

OpenAI ASR Key 不會自動當作翻譯 Key 使用；OpenAI 翻譯與 Gemini 也各自獨立，避免用途混淆。

## 本機 Llama 翻譯

「Llama 執行設定」集中提供：

- 快速選擇已下載的 GGUF 模型。
- 設定 GPU layers、context、埠號與其他 llama-server 參數。
- 套用設定並重新啟動伺服器。
- 查看伺服器狀態並直接測試翻譯。
- 從 llama.cpp 官方 Release 選擇適合目前硬體的 Windows Runtime 並安裝。

預設 llama.cpp OpenAI-compatible 端點為 `http://127.0.0.1:8080/v1`。若使用 LM Studio，常見端點為 `http://127.0.0.1:1234/v1`。

### 教學：使用 hy-mt2-7b-IQ4 翻譯

以下以 `hy-mt2-7b-IQ4` GGUF 量化模型為例。這是翻譯 LLM，不是 ASR 模型；語音仍需先由 CUDA 原生 ASR、sherpa-onnx CPU ASR 或雲端 ASR 轉成文字。

#### 1. 準備 GGUF 模型

1. 取得 `hy-mt2-7b-IQ4` 的 GGUF 檔案。請依模型發布頁的檔名與授權條款下載，建議使用 IQ4 量化版本以降低 VRAM／RAM 需求。
2. 啟動程式，開啟「LLM 模型管理」或「Llama 執行設定」的模型目錄。
3. 將 GGUF 檔案放入模型目錄，例如：

   ```text
   models/
   └─ llama/
      └─ hy-mt2-7b-IQ4.gguf
   ```

4. 回到 Llama 頁面按「重新整理」，確認模型名稱、檔案大小與路徑都已顯示。模型檔只需要下載一次，CUDA、CPU 與 ROCm 的 llama.cpp Runtime 可以共用同一份 GGUF。

#### 2. 安裝 llama.cpp Runtime

1. 在「Llama 執行設定」的 Runtime 區按「檢查更新」或「下載 Runtime」。
2. 依目前硬體選擇 Windows Runtime：NVIDIA 選 CUDA，沒有 NVIDIA CUDA 時選 CPU；ROCm 使用者選頁面標示的 Experimental Runtime。
3. 安裝完成後確認 `llama-server.exe` 與相依 DLL 位於程式的 `llama` Runtime 目錄。

Runtime 與 GGUF 模型是兩個不同項目：Runtime 決定推論後端，GGUF 決定實際翻譯模型。只下載模型而沒有 llama.cpp Runtime，伺服器不會啟動。

#### 3. 設定並啟動伺服器

在「Llama 執行設定」填入或確認以下值：

| 設定 | 建議值 | 說明 |
|---|---|---|
| Model | `hy-mt2-7b-IQ4.gguf` | 從模型選擇器挑選，不要手動輸入錯誤路徑 |
| Host | `127.0.0.1` | 只讓本機 Stream Translator 存取 |
| Port | `8080` | 必須與翻譯端點一致 |
| GPU layers | `auto` 或依 VRAM 調整 | VRAM 不足時降低；CPU Runtime 設為 0 |
| Context | `4096` 起 | 記憶體足夠時再提高 |
| Threads | `auto` | CPU Runtime 可依實際核心數調整 |

按「套用並重啟伺服器」，等待狀態變成 Running，再按「測試翻譯」。測試成功應能看到 `/v1/models` 回應與一段翻譯結果。

#### 4. 指定 Stream Translator 翻譯後端

1. 開啟「翻譯選項」。
2. 翻譯後端選擇「本機 LLM／OpenAI-compatible」。
3. Base URL 填入 `http://127.0.0.1:8080/v1`。
4. Model 填入 `hy-mt2-7b-IQ4` 或伺服器 `/v1/models` 回報的 model id。
5. API Key 若 llama.cpp 未啟用驗證可填任意非空值；不要把 OpenAI ASR Key 當成本機伺服器密碼。
6. 儲存後按翻譯連線測試，再回到「即時轉譯」開始工作。

翻譯流程會是：音訊輸入 → ASR 轉錄 → llama.cpp／hy-mt2-7b-IQ4 翻譯 → 字幕輸出。若只測試 Llama 翻譯，可在 Llama 頁直接使用「測試翻譯」，不必啟動音訊擷取。

#### 5. 常見問題

- **伺服器啟動後立即停止**：確認 GGUF 路徑存在、Runtime 與硬體相符，並降低 GPU layers 或 context。
- **VRAM 不足**：先將 GPU layers 降低，或改用更低量化模型；CPU ASR 與 Llama 翻譯可同時使用，但仍需要足夠 RAM。
- **連線測試失敗**：確認 llama-server 狀態為 Running、埠號未被其他程式占用，且 Base URL 包含 `/v1`。
- **翻譯語言不正確**：確認翻譯提示詞、來源／目標語言及模型的翻譯格式；hy-mt2-7b-IQ4 是翻譯模型，不負責語音辨識。
- **CPU ASR 能用但 Llama 不能用**：兩者是獨立 Runtime。CPU ASR sidecar 只負責 sherpa-onnx 語音辨識，仍需另外安裝 llama.cpp CPU Runtime 才能使用本機 LLM 翻譯。

## 字幕分享

啟用字幕分享後，可使用頁面顯示的網址存取：

- 桌面瀏覽器字幕頁。
- 行動裝置字幕頁。
- 公開字幕 API。

同一區域網路內的手機需使用電腦的區網 IP，不能使用手機上的 `127.0.0.1`。若無法連線，請確認：

- 手機與電腦位於同一網路。
- Windows 防火牆允許程式使用指定埠。
- 路由器未啟用 AP isolation／用戶端隔離。
- 分享功能已啟用且後端服務仍在執行。

字幕分享未提供公開網際網路的身分驗證。不要直接將埠暴露到 Internet；若需外網存取，請自行配置具備 HTTPS 與驗證的反向代理或 VPN。

## 媒體輸入注意事項

- v1.3.9 打包版內建 Node.js 22+，yt-dlp 會自動指定 JavaScript Runtime。
- YouTube、Twitch 等平台可能要求登入 Cookie；可在輸入選項選擇瀏覽器 Cookie 或匯入 Netscape `cookies.txt`。
- 使用瀏覽器 Cookie 時，Firefox 通常比受 App-Bound Encryption 保護的 Chromium 瀏覽器更容易讀取。
- 系統聲音擷取使用 Windows 音訊裝置；請確認輸出裝置與程式選擇一致。

## 設定與資料位置

- 使用者設定：`config.yaml`
- ASR／LLM 模型：程式可寫入的 `models` 目錄或模型管理頁顯示的位置
- 字幕匯出：由輸出與通知設定指定
- 日誌：程式資料目錄下的 `logs`

請勿將程式解壓到需要系統管理員權限才能寫入的位置。Windows 若暫時鎖定配置檔，v1.3.9 會重試並保留已載入設定，不再直接回退預設值。

## 從原始碼執行

需求：Windows 10／11、Python 3.10～3.12、Node.js 18+、npm、Git 與 FFmpeg。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r .\app\requirements.txt
pip install -e .\stream-translator-gpt

cd .\app\frontend
npm install
npm run build
cd ..\..

Copy-Item .\app\config.example.yaml .\app\config.yaml
cd .\app
python .\main.py
```

不同 Runtime Profile 的依賴與打包方式不同；建立正式發佈包前請閱讀 [打包說明](app/packaging/README.md)，不要在同一個 Python 環境混裝 CPU、CUDA 與 ROCm PyTorch。

## 建立發佈包

```powershell
cd .\app

# 快速驗證
.\build_all_profiles.ps1 -Version 1.3.9 -Mode Quick -ReuseRuntimeCache

# 正式發佈
.\build_all_profiles.ps1 `
  -Version 1.3.9 `
  -Mode Final `
  -ReuseRuntimeCache `
  -CompressionLevel 7 `
  -SplitSizeMiB 1900 `
  -CopyThreads 16
```

正式資產輸出至 `app/release-v1.3.9-assets/`，包含 App Update、Full package 分割檔、manifest、SHA-256 清單與合併工具。

## 專案來源

- 核心專案：[ionic-bond/stream-translator-gpt](https://github.com/ionic-bond/stream-translator-gpt)
- 行動字幕參考：[W-Nana/SubtitleOverlay](https://github.com/W-Nana/SubtitleOverlay)
- 本機 LLM Runtime：[ggerganov/llama.cpp](https://github.com/ggerganov/llama.cpp)
