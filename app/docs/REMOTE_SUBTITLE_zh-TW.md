# 遠端浮動字幕

在另一台 Windows 電腦顯示 FloatWindow 主機的即時字幕，使用主程式相同的原生 Qt 浮動視窗。只需獨立執行檔，不需安裝翻譯模型或 backend。

```powershell
.\StreamTranslatorRemoteSubtitle.exe --server http://主電腦IP:8765
```

也可直接啟動，在「設定…」的「主機網址」填入（預設分享連接埠為 8765）。可以填：

- 區網位址：`192.168.100.181:8765` 或 `http://192.168.100.181:8765`
- 反向代理網域：`https://字幕.example.com`，或有子路徑的 `https://example.com/subs`
- 直接貼上主程式「字幕分享服務」的電腦端／行動端連結（`…/desktop`、`…/mobile`），會自動去掉頁面路徑與 `?`、`#` 之後的內容

未指定協定時使用 http；支援 http／https。主機必須開啟「字幕分享」，並開始翻譯。主機尚未翻譯時會顯示「等待主機翻譯」。

Windows 防火牆須允許主機 TCP 8765 的傳入連線。此為無驗證的公開字幕分享服務。若透過反向代理公開，代理必須轉送至 **8765 公開分享埠**，並停用 SSE 回應緩衝，保留長時間串流連線。

系統匣選單可開啟設定、切換滑鼠穿透、顯示／隱藏字幕或結束。啟用滑鼠穿透後仍可透過系統匣關閉穿透。字幕視窗的 × 會結束程式；若只想暫時隱藏請使用系統匣。

按「套用」儲存主機與外觀設定；切換主機會清除舊字幕並重新連線。設定儲存在 `%APPDATA%\Stream Translator Remote Subtitle\settings.json`；未設定 APPDATA 時使用使用者家目錄下的同名資料夾。

## 建置

準備已安裝 PyInstaller 與 PyQt6 的 `app\venv` 或根目錄 `.venv`（也可指定 `STREAM_TRANSLATOR_BUILD_PYTHON`），從儲存庫根目錄執行：

```powershell
pwsh -File app/packaging/build_remote_subtitle.ps1
```

輸出為 `app\dist-remote-subtitle\StreamTranslatorRemoteSubtitle.exe`。建置腳本不安裝套件，也不執行主程式或前端建置。
