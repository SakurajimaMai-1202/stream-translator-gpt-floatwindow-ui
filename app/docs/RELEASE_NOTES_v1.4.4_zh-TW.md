# Stream Translator v1.4.4 更新說明

v1.4.4 修正 v1.4.3 在部分 Windows 電腦上可能誤用系統舊版 `yt-dlp` 的問題。

## yt-dlp 執行環境修正

- 串流擷取現在會優先執行目前套件 runtime 內的 `python.exe -m yt_dlp`。
- 不再讓 Windows `PATH` 中另外安裝的舊版 `yt-dlp.exe` 覆蓋套件內版本。
- 找不到 runtime 模組時，才依序檢查 runtime 旁的執行檔與系統 `PATH`。
- 正式打包仍會先更新三端 runtime 與 CPU ASR Sidecar 內的 `yt-dlp` 至建置當下最新版。

## 發布驗證

- 新增 runtime 路徑驗證；若實際 yt-dlp 命令指向套件外部，打包驗證會直接失敗。
- 已加入「系統 PATH 存在舊版 yt-dlp」及「runtime Scripts 執行檔優先」回歸測試。
- CUDA、CPU、ROCm 的 Full 與 App Update 套件均會重新建置並執行健康檢查。

v1.4.3 的介面、浮動字幕、模型下載、ASR 穩定性與其他功能更新均完整保留。
