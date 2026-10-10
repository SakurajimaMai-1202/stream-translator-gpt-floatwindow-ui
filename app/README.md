# Stream Translator — 應用程式使用與開發指南

即時擷取直播、影片或音訊裝置，透過 ASR 語音辨識與本地或線上翻譯，顯示原文及譯文字幕。

版本、下載資產與更新紀錄請看[專案 README](../README.md)。本文件說明 v1.5.0 介面；CPU、CUDA 與 ROCm Experimental 套件已於 2026-10-10 重新建置。

## 一般使用者：從完整包開始

1. 依硬體及需要的 ASR 引擎選擇 CPU、CUDA 或 ROCm Experimental 完整包。支援項目以該版本的 Runtime Profile 說明為準。
2. 若資產是分卷 `.partNN`，下載同一 profile 的所有分卷及對應合併工具，合併後再解壓；單一 ZIP 直接解壓即可。
3. 執行 `Stream Translator.exe`，到「ASR 模型管理」下載模型，再於「轉錄選項」選擇相同引擎與模型。
4. 在「翻譯選項」選擇翻譯後端與目標語言。本地 LLM、線上 API 或不翻譯依需求設定；本地 LLM 並非必備。
5. 回到「即時轉譯」選擇來源，啟動後查看字幕；可依需求開啟浮動字幕與檔案輸出。

首次下載模型需要網路與足夠磁碟空間。磁碟、記憶體及顯存需求隨模型、量化和上下文長度改變，請參考模型管理及推薦頁。

## 設定頁的分工

| 頁面 | 用途 |
| --- | --- |
| ASR 模型管理 | 模型下載、下載狀態與模型儲存位置 |
| 轉錄選項 | ASR 引擎、語言、Runtime Profile 與辨識參數 |
| 翻譯選項 | 翻譯後端、語言、模型策略、提示詞與進階參數 |
| 推薦翻譯模型 | 模型介紹、官方下載與部署參數；包含 HY-MT2、Index-Translate 2B／9B 等選項 |
| Llama 執行設定 | GGUF 模型、llama.cpp Runtime、顯卡、常用參數與試譯 |
| 字幕與輸出設定 | 字幕外觀、顯示模式及輸出選項 |

目前原始碼介面使用一致的深色樣式。常用設定優先顯示，Runtime、提示詞或生成參數等進階項目可展開調整。

## 本地翻譯與雙顯卡

使用本地翻譯時，先下載 GGUF 模型，再於「Llama 執行設定」選擇模型與相容 Runtime，啟動並試譯。外部服務則在翻譯設定填寫其 API 位址與必要憑證。

目前原始碼的 llama.cpp 自動選擇以獨立顯卡優先：NVIDIA 推薦 CUDA，AMD 與 Intel 推薦 Vulkan。可手動改選，介面分別顯示選擇的裝置與執行時確認的裝置；內顯預設排除，可按需求允許。GPU 層數設為 0 時使用 CPU。實際可用裝置仍取決於 Runtime 與驅動。

**ASR 與 llama.cpp 是不同的執行後端。** CPU／CUDA／ROCm 完整包名稱描述 Python／ASR Runtime；選到 Vulkan 翻譯顯卡不代表 ASR 也會走 Vulkan。請分別確認兩者的支援及設定。

## 從原始碼執行

Windows 10／11 64-bit。先準備相容 Python、Node.js／npm、FFmpeg，以及目標 profile 所需的驅動和 Python 推論套件。`app/requirements.txt` 不包含 PyTorch 變體、FFmpeg 執行檔、llama-server 或系統驅動；CPU 與額外引擎另有對應 requirements，請搭配根目錄建置說明。

在專案根目錄建立環境並安裝應用相依套件：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r app/requirements.txt
```

另依目標 profile 安裝相容的推論套件，再建置前端：

```powershell
cd app/frontend
npm ci
npm run build
cd ../..
```

Vite 將產物輸出至 `app/backend/static`。從根目錄的「快速啟動_UI2.bat」啟動，或直接執行：

```powershell
cd app
..\.venv\Scripts\python.exe main.py --prod
```

啟動批次檔會清理既有應用視窗與相關連接埠；不需要清理時使用上面的直接啟動指令。`UI2` 是沿用的啟動檔名稱，目前程式目錄為 `app`。

前端開發可在 `app/frontend` 執行 `npm run dev`；此模式仍需另行啟動後端，並確認 `vite.config.ts` 的 API proxy 連接埠與後端一致。

## 更新、資料與排錯

- App Update 用於相容的既有安裝，不能取代完整包。依版本的 updater／sidecar 相容條件操作，勿混用 profile 的 Runtime。
- 更新前備份 `config.yaml`，保留模型、輸出、圖片與日誌；確認資料位置後再移動安裝目錄。
- 模型載入失敗先確認模型完整性、Runtime 支援與記憶體，再查看 `logs`。線上 API 失敗則確認端點、金鑰及服務回應。
- 啟動失敗可先執行 EXE 的 `--update-health-check`，並查看日誌；這項檢查不代表實際 ASR 或翻譯推論已通過。
- 若缺少 Visual C++ Runtime，安裝 [Microsoft Visual C++ Redistributable x64](https://aka.ms/vs/17/release/vc_redist.x64.exe)。

發布前需分別確認原始碼、建置產物、完整包啟動與模型推論；前端建置成功不能代替完整包驗證。
