# Remote Subtitle Window

獨立的遠端字幕視窗，只讀取主程式既有的字幕分享 API，不修改主專案。

## 用法

主電腦啟動字幕翻譯後，在遠端電腦執行：

```powershell
.\RemoteSubtitleWindowReferenceStyle.exe --server http://主電腦IP:8765
```

例如：

```powershell
.\RemoteSubtitleWindowReferenceStyle.exe --server http://192.168.1.10:8765
```

也可以直接開啟 exe，按右上角齒輪輸入 `http://主電腦IP:8765`。

## 連接的 API

- `GET /api/translation/active-task`
- `GET /api/translation/stream/{task_id}`

程式會自動等待任務開始、斷線重連，並在任務結束後等待下一次翻譯。

## 操作

- 主視窗沒有系統標題欄。
- 背景使用 Windows layered window 的 per-pixel alpha，像剪輯軟體 overlay；字幕文字維持不透明。
- 拖曳字幕區可以移動視窗。
- 右下角小方塊可以縮放。
- 齒輪：設定遠端網址、字體大小、顯示筆數、背景透明度。
- `⇄`：切換精簡顯示。
- `F2`：開啟設定。
- `×`：清空目前字幕。

設定會存到 `%APPDATA%\Remote Subtitle Window\settings.json`。

## 打包 exe

在這個資料夾執行：

```powershell
.\build_exe.ps1
```

預設輸出：

```text
remote-subtitle-window\dist\RemoteSubtitleWindow.exe
```

如果舊版 exe 還開著，Windows 會鎖住檔案；這時可以先使用目前已產出的真透明版本：

```text
remote-subtitle-window\dist\RemoteSubtitleWindowReferenceStyle.exe
```

如果主程式在另一台電腦，Windows 防火牆需要允許主程式的字幕分享 port 被區網連入。
