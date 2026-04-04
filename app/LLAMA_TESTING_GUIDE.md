# 快速測試 Llama 整合

## 測試步驟

### 1. 啟動後端
```powershell
cd G:\youtube-live-translator\floatwindow\ui2
.\venv\Scripts\Activate.ps1

# 安裝新的依賴
pip install openai google-generativeai httpx

# 啟動後端
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. 構建前端
```powershell
# 新開終端
cd G:\youtube-live-translator\floatwindow\ui2\frontend
npm install
npm run dev
```

### 3. 測試 API

在瀏覽器開啟：
- 前端: http://localhost:5173
- API 文檔: http://127.0.0.1:8000/api/docs

### 4. 測試 Llama 功能

#### 使用 Swagger UI（推薦）
1. 開啟 http://127.0.0.1:8000/api/docs
2. 找到 `/api/llama/models` 端點
3. 點擊 "Try it out"
4. 輸入模型目錄（例如：`G:\models`）
5. 點擊 "Execute"

#### 使用前端 UI
1. 開啟 http://localhost:5173
2. 點擊左側 "設定" 按鈕
3. 選擇 "🦙 Llama 設定" 分頁
4. 輸入模型目錄並掃描
5. 選擇模型並啟動伺服器
6. 測試翻譯功能

### 5. 整合測試

#### 切換翻譯引擎
1. 在設定頁面切換到 "翻譯選項"
2. 翻譯後端選擇 "🦙 Llama (本地)"
3. 儲存配置

#### 開始翻譯
1. 返回首頁
2. 輸入測試 URL（例如 YouTube 影片）
3. 點擊開始翻譯
4. 觀察是否使用 Llama 進行翻譯

---

## 故障排除

### 問題 1: 模組導入錯誤
```
ModuleNotFoundError: No module named 'llamaApi'
```

**解決**：確保檔案路徑正確，重新啟動開發伺服器

### 問題 2: Llama 伺服器啟動失敗
```
找不到 llama-server.exe
```

**解決**：檢查 `G:\youtube-live-translator\floatwindow\llama\llama-server.exe` 是否存在

### 問題 3: CORS 錯誤
```
Access-Control-Allow-Origin error
```

**解決**：後端已配置 CORS，確保後端正在運行

---

## 檢查清單

- [ ] 後端啟動成功（Port 8000）
- [ ] 前端啟動成功（Port 5173）
- [ ] 可以訪問 API 文檔
- [ ] 可以掃描模型列表
- [ ] 可以啟動 Llama 伺服器
- [ ] 可以執行測試翻譯
- [ ] 設定頁面顯示 Llama 分頁
- [ ] 翻譯選項包含 Llama 後端

---

## 預期結果

### API 回應範例

**GET /api/llama/models**
```json
[
  {
    "name": "llama-2-7b-chat.Q4_K_M.gguf",
    "path": "G:\\models\\llama-2-7b-chat.Q4_K_M.gguf",
    "size_mb": 4368.12,
    "modified_time": "1705896432.0"
  }
]
```

**POST /api/llama/server/start**
```json
{
  "status": "started",
  "pid": 12345,
  "url": "http://127.0.0.1:8080",
  "model": "llama-2-7b-chat.Q4_K_M.gguf"
}
```

**POST /api/llama/translate**
```json
{
  "original": "Hello, how are you?",
  "translated": "你好，你好嗎？",
  "model": "llama-2-7b-chat.Q4_K_M.gguf"
}
```

---

## 效能預期

### CPU 模式
- 啟動時間: ~5-10 秒
- 翻譯速度: ~1-2 秒/句

### GPU 模式（n_gpu_layers > 0）
- 啟動時間: ~3-5 秒
- 翻譯速度: ~0.3-0.8 秒/句

---

**測試日期**: 2026-01-22  
**版本**: v1.0.0
