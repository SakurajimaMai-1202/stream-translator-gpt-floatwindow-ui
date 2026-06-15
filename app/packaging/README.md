# Packaging

此資料夾保存打包實作，不建議直接從其他工作目錄呼叫。

- `build_cuda_release.ps1`：建立 CUDA Full 與 App Update 發行包。
- `build_cuda_runtime.ps1`：建立或重用精簡 CUDA Python Runtime。
- `build_legacy.ps1`：舊版單一完整包流程。
- `stream-translator-llm-gui.spec`：GUI 的 PyInstaller onedir 規格。

一般請在 `app` 目錄執行相容入口：

```powershell
.\build_cuda_release.ps1
```
