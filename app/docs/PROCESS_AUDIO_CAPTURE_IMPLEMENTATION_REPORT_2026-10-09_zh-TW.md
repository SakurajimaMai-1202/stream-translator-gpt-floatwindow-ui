# 指定應用程式音訊實作與驗證紀錄

日期：2026-10-09

## 完成行為

首頁及首次設定新增「指定應用程式音訊」。選擇目前開啟的視窗、測試收音，再啟動原有字幕流程。收音測試、模型啟動及執行期間禁止切換來源／目標。來源測試區分可開啟但無聲、收到音訊與擷取失敗。

底層擷取所選程序及其子程序，不保證同一瀏覽器的单一視窗／分頁隔離。Chrome、Edge、Brave、Opera、Firefox、Vivaldi 只沿同一路徑、較早建立的同名父程序尋找根節點；一般程式不向同名父程序擴張擷取範圍。

PID 和 Windows FILETIME 建立時間一起驗證，FILETIME 及 HWND 以字串傳遞，避免 JavaScript 精度損失。每次開始重新取得清單、驗證目標；重新開啟程式後須重新選擇，不直接沿用儲存 PID。目標擷取程序退出時結束並提示，不自動退回系統音訊或麥克風。

新來源與其他翻譯任務並行時回報衝突，避免既有共用常駐子程序的資源問題。停止先於背景啟動的競態已修正。伺服器錯誤訊息不再被 SSE 斷線訊息覆蓋，終止後解除執行旗標。

## 架構與打包

- Windows Process Loopback API，最低 build 20348；原生 x64 DLL 靜態連結 C++ runtime。
- DLL 由翻譯 Python 子程序延遲載入，保留載入至程序退出；不新增外部擷取 EXE。
- 原生輸出 48 kHz stereo float32，五秒有界緩衝，記錄遺失／中斷。
- Python 使用 63-tap Hamming FIR、7200 Hz cutoff 及連續 3:1 降採樣，轉成 16 kHz mono float32／512-sample frames。這個轉換只需要 NumPy。
- 擷取在 `loop()` 開始，避免 ASR 模型初始化期間先錄音而積壓。兩條啟動路徑均接入；中斷沿用 `AUDIO_STREAM_GAP` 契約。
- GUI 只載入 ctypes 目標列舉模組；DLL 與 NumPy 留在外部 ASR runtime。
- profile runtime、profile release、CPU sidecar 建置先確保 DLL 存在且不比原生來源／建置腳本舊；runtime artifact 驗證新增 DLL 載入檢查。
- setuptools package-data 包含 `native/*.dll`。DLL 為本機建置產物，不追蹤進 Git；新 checkout 需先建置。

原生建置：

```powershell
& .\stream-translator-gpt\native\build.ps1
```

需要 Visual Studio Desktop C++ 工具與含 `audioclientactivationparams.h` 的 Windows SDK。GUI 與 ASR runtime 必須一起更新；舊 runtime 若缺少必要 CLI 參數會明確阻擋，缺 DLL 會報錯，不切換來源。

## 已執行驗證

| 範圍 | 結果／證據 |
|---|---|
| 原生建置 | MSVC x64 DLL 編譯成功 |
| 程序隔離 | 兩個 sibling 程序同時播放 440／880 Hz，只擷取目標；非目標測試頻率約低 94 dB，不能推廣為所有應用程式隔離保證 |
| 原生生命週期 | 十次靜音啟停，handles 146→146、threads 5→5；FILETIME 不符拒絕，目標退出回報錯誤 |
| PCM 與後端 | 52 個測試通過，涵蓋封包邊界、抗混疊、靜音停止、例外清理、PID 重用、舊 runtime、來源映射及停止競態 |
| 前端 SSE | 六個實際 store 回歸情境通過，涵蓋目標退出、終止狀態、最終字幕及舊連線回呼 |
| 前端建置 | Vue／TypeScript／Vite 通過，更新本機 backend/static |
| 真實視窗 | 建立暫時 minimized Win32 STATIC 視窗；列舉 HWND／PID／FILETIME／標題，退出後驗證拒絕 |
| 一般 main 流程 | 日文六秒 fixture，真正程序音訊→FireRed native VAD→SenseVoice CPU→字幕組句→exporter，輸出兩筆日文字幕 |
| 常駐模型流程 | 同一實際 VAD／ASR／字幕鏈通過，正常停止 |
| profile runtime | 在隔離的 package 副本，以現有 CPU／CUDA／ROCm runtime 分別確認 DLL、NumPy PCM 轉換與輸出幀，均退出 0；沒有修改 runtime cache |
| 凍結 GUI 模組 | 實際最小 PyInstaller 包建置並隱藏啟動，後端目標模組可匯入且包內沒有 NumPy；非完整 GUI 發行包 |

證據位於 `benchmark-results/process-audio-capture-20261009/`：

- `report.json`：原生隔離、退出與資源測試。
- `targets-report.json`：Win32 視窗列舉與目標驗證。
- `main-pipeline-report.json`、`pipeline-report.json`：兩條真正 ASR／字幕路徑。
- `runtime-validation.json`：三種 cached runtime 的隔離 package 驗證。
- `frozen-validation.json`：輕量 GUI 模組實際凍結及啟動。

重現入口為 `tools/process_audio_capture_smoke.py`、`tools/process_audio_targets_smoke.py`、`tools/process_audio_pipeline_smoke.py`、`tools/process_audio_runtime_validation.py`、`tools/process_audio_frozen_probe.py`。播放測試會發出短測試音／fixture 聲音。

## 驗證限制與剩餘驗收

- 兩條 ASR 實測使用本機 SenseVoice CPU ONNX 模型，翻譯關閉、HF offline。沒有測外部翻譯服務，也不能據此宣稱 GPU ASR 已實測。
- 三種 runtime 檢查是隔離 package 與 DLL／PCM 驗證，不是三種完整發行包的安裝與更新測試。
- 輕量凍結探針不是完整 GUI 包；沙箱沒有列出使用者桌面視窗，真實列舉另外用受控 Win32 視窗驗證。
- 尚未對使用者實際瀏覽器多分頁、通話程式、耳機切換、實際首頁畫面及長時間直播進行驗收。
- 原生中斷／緩衝過載由有界緩衝與 gap 處理，極端 COM 停滯使用有界停止等待；需長時間壓力測試補強證據。
- 已修改建置與 artifact 驗證腳本，但尚未重新產生完整 CPU／CUDA／ROCm 發行 ZIP。
- 本次保留原有未提交變更，沒有改寫使用者模型／設定，沒有推送、標籤或發布。

第一版原始碼與本機核心流程已可使用；完成上述真實應用程式與完整包驗收後，才可視為計劃中的完整發行驗收完成。
