# 使用本機更新包

直接開啟新版 `StreamTranslatorUpdater.exe`，選取 App Update 更新包和原安裝目錄，按「驗證更新包」。確認顯示的版本、Profile 與安裝路徑後，關閉主程式，再按「套用更新」。

CUDA 分割包請將全部 `.zip.partNN` 放在同一目錄並選取 `.zip.part01`，更新器會自動合併。可將對應版本的 `SHA256SUMS-版本.txt` 放在更新包旁，更新器會驗證每段與合併包的 SHA-256；沒有清單時會顯示提示，仍檢查 ZIP CRC 與套件內容。SHA-256 清單應與更新包一起從可信來源下載。

安裝目錄必須含 `Stream Translator.exe`、`config.yaml` 和 `_runtime/runtime-version.json`。CPU、CUDA、ROCm 不可混用；不支援降版、不符合最低升級版本的安裝、Full 包、CPU ASR Sidecar 包或舊式部分 Runtime 更新包。

套用時沿用既有更新流程：備份設定、術語、ASR 修正與 Cookies，保留上一版檔案，檢查新版 GUI/DLL，重新啟動。失敗時嘗試回復上一版。模型、輸出與其他使用者資料不在更新包允許覆蓋的範圍。

新版更新器會從系統暫存目錄執行，避免鎖住安裝目錄內需要替換的更新器。內建線上更新的 `--plan` 入口維持可用；`--preview` 仍可明確啟動預覽。

也可預填路徑（仍由使用者在介面驗證及套用）：

```powershell
.\StreamTranslatorUpdater.exe --package 'D:\Downloads\StreamTranslator-CPU-App-Update.zip' --install-dir 'D:\StreamTranslator'
```
