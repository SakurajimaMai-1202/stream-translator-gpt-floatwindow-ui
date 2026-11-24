# 文件索引

## 使用與更新

- [操作指南](../../USER_GUIDE.md)：首次設定、音源、辨識模型、翻譯、字幕分享與匯出。
- [免安裝使用說明](PORTABLE_GUIDE_zh-TW.txt)：可攜式套件的基本操作。
- [更新摘要](UPDATE_NOTES_zh-TW.txt)：目前版本的主要更新。
- [v1.6.1 更新說明](RELEASE_NOTES_v1.6.1_zh-TW.md)：功能亮點、套件選擇與更新方式。
- [手動更新指南](MANUAL_UPDATE_zh-TW.md)：ZIP 與分割更新包的操作方式。
- [術語預設](HY_MT2_GLOSSARY_PRESETS.md)：HY-MT2 詞庫預設的使用說明。

## 開發參考

- [應用程式目錄說明](../README.md)：程式目錄與文件導覽。
- [打包說明](../packaging/README.md)：建置腳本、執行環境與封裝配置。
- [打包流程](PACKAGING_zh-TW.md)：建置方式與輸出位置。
- [Runtime Profiles](RUNTIME_PROFILES_zh-TW.md)：CPU、CUDA 與 ROCm 套件的支援範圍。
- [翻譯管線](TRANSLATION_PIPELINE.md)：翻譯流程與設定。
- [SenseVoice 模型封裝](SENSEVOICE_MODEL_PACKAGE_zh-TW.md)：模型封裝參考。
- [環境變數](#環境變數)：程式及打包流程讀取的環境變數、用途與預設值。

## 歷史版本更新說明

- [v1.5.0](RELEASE_NOTES_v1.5.0_zh-TW.md)
- [v1.4.10](RELEASE_NOTES_v1.4.10_zh-TW.md)
- [v1.4.9](RELEASE_NOTES_v1.4.9_zh-TW.md)
- [v1.4.8](RELEASE_NOTES_v1.4.8_zh-TW.md)
- [v1.4.7](RELEASE_NOTES_v1.4.7_zh-TW.md)
- [v1.4.6](RELEASE_NOTES_v1.4.6_zh-TW.md)
- [v1.4.5](RELEASE_NOTES_v1.4.5_zh-TW.md)
- [v1.4.4](RELEASE_NOTES_v1.4.4_zh-TW.md)
- [v1.4.3](RELEASE_NOTES_v1.4.3_zh-TW.md)
- [v1.4.2](RELEASE_NOTES_v1.4.2_zh-TW.md)
- [v1.4.1](RELEASE_NOTES_v1.4.1_zh-TW.md)
- [v1.4.0](RELEASE_NOTES_v1.4.0_zh-TW.md)
- [v1.3.11](RELEASE_NOTES_v1.3.11_zh-TW.md)
- [v1.3.10](RELEASE_NOTES_v1.3.10_zh-TW.md)
- [v1.3.9](RELEASE_NOTES_v1.3.9_zh-TW.md)
- [v1.3.7](RELEASE_NOTES_v1.3.7_zh-TW.md)
- [v1.3.6](RELEASE_NOTES_v1.3.6_zh-TW.md)
- [v1.3.5](RELEASE_NOTES_v1.3.5_zh-TW.md)
- [v1.3.4](RELEASE_NOTES_v1.3.4_zh-TW.md)
- [v1.3.3](RELEASE_NOTES_v1.3.3_zh-TW.md)
- [v1.3.2](RELEASE_NOTES_v1.3.2_zh-TW.md)
- [v1.3.1](RELEASE_NOTES_v1.3.1_zh-TW.md)

## 環境變數

下表列出應用程式程式碼與打包腳本會讀取的環境變數。作業系統與 Python／第三方套件的通用環境變數未逐一列出。

| 名稱 | 用途 | 預設值 | 設定者 |
| --- | --- | --- | --- |
| `FLOATWINDOW_ADMIN_TOKEN` | 管理 API 驗證權杖；管理 API 預設綁定 `127.0.0.1`，桌面程式選用的管理埠預設為 `8010`。字幕分享服務仍依 `server.public_port`（預設 `8765`）綁定 `0.0.0.0`，供區網公開存取。桌面程式未收到值時會產生隨機權杖。 | 桌面啟動時自動產生 | launcher／使用者 |
| `FLOATWINDOW_ADMIN_HOST` | 管理 API 綁定位址；非 loopback 位址會擴大可存取範圍。 | `127.0.0.1` | 使用者 |
| `FLOATWINDOW_BACKEND_PORT` | 開發前端連接的後端埠號。 | launcher 啟動開發前端時設定，預設 `8001` | launcher |
| `STREAM_TRANSLATOR_CONFIG_FILE` | 指定設定檔路徑。 | 打包版為執行檔旁的 `config.yaml`；開發版為 `app/config.yaml` | 使用者／launcher |
| `STREAM_TRANSLATOR_PACKAGED_PROFILE` | 覆寫打包執行環境 profile（`cpu`、`cuda` 或 `rocm`）。 | 未設定時依封裝資訊判定 | launcher／使用者 |
| `VK_LOADER_LAYERS_DISABLE` | 控制 llama.cpp 子程序的 Vulkan 隱式層；程式預設設為 `~implicit~`，使用者已有值時保留原值。 | 子程序預設 `~implicit~` | launcher（使用者值優先） |
| `STREAM_TRANSLATOR_USE_WEB_SUBTITLE` | 設為 `1` 時讓浮動字幕使用舊 WebView fallback。 | 未啟用 | 使用者／launcher |
| `STREAM_TRANSLATOR_BACKEND_RELOAD` | 開發時啟用後端自動 reload。 | 未啟用 | 使用者 |
| `STREAM_TRANSLATOR_UI_PERF` | 設為 `1` 時記錄 Qt 主執行緒延遲診斷。 | 未啟用 | 使用者 |
| `STREAM_TRANSLATOR_UI_PERF_REPORT_MS` | UI 延遲摘要回報間隔（毫秒，最小 1000）。 | `10000` | 使用者 |
| `STREAM_TRANSLATOR_YTDLP_VERSION` | 打包時指定 yt-dlp 版本；指定值仍須符合目前官方最新版本。 | 官方最新版本 | build script／使用者 |
| `STREAM_TRANSLATOR_BUILD_PYTHON` | 指定開發模式 CLI 相容性偵測使用的 Python。 | 自動尋找 | 使用者／build script |
| `STREAM_TRANSLATOR_UPDATE_RELEASE_API` | 覆寫 App 更新檢查使用的 Release API URL。 | 專案預設 API | 使用者／launcher |
| `STREAM_TRANSLATOR_CPU_ASR_SIDECAR_URL` | 覆寫 CPU ASR sidecar 壓縮檔下載網址。 | 依目前版本組成的 GitHub Release URL | 使用者／launcher |
| `STREAM_TRANSLATOR_LOG_DIR` | 指定應用程式及翻譯流程日誌目錄。 | 打包版執行檔旁 `logs`；開發版 `app/logs` | launcher／使用者 |
| `STREAM_TRANSLATOR_ASR_CORRECTION_LOG` | 指定 ASR 修正紀錄檔路徑。 | 依日誌目錄與內建檔名 | 使用者／launcher |
| `STREAM_TRANSLATOR_ASR_CORRECTION_LOG_DIR` | 指定 ASR 修正紀錄目錄；桌面程式會傳給辨識子程序。 | 日誌目錄中的預設修正紀錄位置 | launcher／使用者 |
| `MODELSCOPE_CACHE` | 指定 ModelScope 模型快取目錄。 | ModelScope 預設快取位置 | 使用者 |
| `SHERPA_ONNX_MODEL_DIR` | 指定 sherpa-onnx 模型目錄。 | 套件預設模型目錄 | 使用者 |
| `SHERPA_ONNX_NUM_THREADS` | 設定 sherpa-onnx CPU 執行緒數。 | sherpa-onnx 預設值 | 使用者 |
| `OPENAI_API_KEY` | OpenAI 憑證 fallback；程式設定的金鑰會傳入翻譯子程序環境。 | 未設定；可由程式設定提供 | 使用者／launcher |
| `GOOGLE_API_KEY` | Google Gemini 憑證 fallback；程式設定的金鑰會傳入翻譯子程序環境。 | 未設定；可由程式設定提供 | 使用者／launcher |
| `OPENAI_BASE_URL` | 判定及設定 OpenAI-compatible API 位址。 | 未設定；可由程式設定提供 | 使用者／launcher |
| `http_proxy`、`https_proxy`、`HTTP_PROXY`、`HTTPS_PROXY` | 翻譯子程序連線使用的代理伺服器。 | 未設定；可由程式 proxy 設定提供 | 使用者／launcher |
| `PATH` | Windows 執行檔搜尋路徑；桌面啟動器會加入 bundled Qt 路徑。 | 作業系統環境值 | launcher／作業系統 |
| `ProgramFiles`、`LOCALAPPDATA` | 定位 Windows 安裝與使用者資料目錄。 | `ProgramFiles` 為 `C:\Program Files`；`LOCALAPPDATA` 未設定時略過 | 作業系統 |
| `XDG_CACHE_HOME` | Whisper 套件快取目錄根路徑。 | 平台預設快取目錄 | 使用者／作業系統 |
| `PROCESSOR_IDENTIFIER` | 補充 Windows CPU 型號偵測資訊。 | 未設定 | 作業系統 |
| `VITE_APP_VERSION` | 傳入 Vite 的前端版本字串。 | 打包腳本 `-Version`，預設 `1.6.1` | build script |
| `PYTHONUTF8`、`PYTHONIOENCODING`、`PYTHONUNBUFFERED` | 翻譯子程序文字編碼與輸出緩衝設定。 | launcher 設為 `1`、`utf-8`、`1` | launcher |
| `QTWEBENGINE_CHROMIUM_FLAGS`、`QT_OPENGL` | Qt WebEngine Chromium 旗標與 OpenGL 模式，由渲染初始化調整。 | 依啟動環境與渲染初始化決定 | launcher／使用者 |
| `MPLCONFIGDIR` | Matplotlib 設定目錄。 | 暫存目錄下的 `stream-translator-matplotlib` | launcher／作業系統 |
| `CPU_ASR_SIDECAR_TEST_ASSET` | 測試用 CPU ASR sidecar 本機資產路徑。 | 未設定時略過該測試 | 使用者／CI |
| `QT_QPA_PLATFORM` | 測試時指定 Qt 平台外掛。 | 測試使用 `offscreen` | 測試／CI |

上述設定可能包含憑證；文件不列出任何實際金鑰或權杖值。
