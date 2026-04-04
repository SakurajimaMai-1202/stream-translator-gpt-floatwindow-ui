================================================================
  Stream Translator
  可攜式免安裝版
================================================================

【最低系統需求】
  - Windows 10 / 11  (64-bit)
  - NVIDIA 顯示卡驅動程式 >= 550.x
    （無 NVIDIA 顯卡亦可執行，使用 CPU 模式，速度較慢）

【快速開始】
  1. 解壓縮此資料夾到任意位置（路徑不得含中文或特殊字元）
  2. 以文字編輯器開啟 config.yaml，填入以下設定：
       - openai_api_key   （使用 GPT 翻譯時需填入）
       - google_api_key   （使用 Gemini 翻譯時需填入）
  3. 雙擊 Stream Translator.exe 啟動

【目錄說明】
  Stream Translator.exe           主程式
  config.yaml                     設定檔（從 config.example.yaml 複製）
  _runtime/                       可攜式 Python 環境（含 torch + CUDA runtime）
  ffmpeg/bin/                     ffmpeg 8.1（音訊處理，自帶免安裝）
  llama/                          llama-server 二進位（本地模型推論）

【模型檔案】
  llama 模型檔案（*.gguf）需另外下載後放入任意位置，
  啟動後透過 UI 的「模型管理」頁面設定路徑。

  推薦模型（翻譯品質佳）：
    Orion-Qwen3.5-2B-SFT-v2603-Q4_K_M.gguf

【Whisper 模型】
  初次使用時程式會自動下載 Whisper 模型到 %USERPROFILE%\.cache\whisper\
  需要網路連線（約 140MB ~ 3GB，依所選模型大小而定）。

【常見問題】
  Q: 啟動後白畫面或無法開啟？
  A: 確認路徑不含中文，並嘗試以「系統管理員」身分執行。

  Q: GPU 未被使用？
  A: 請更新 NVIDIA 驅動至 550.x 以上版本。
     驅動下載：https://www.nvidia.com/drivers

  Q: 出現 VCRUNTIME 缺失錯誤？
  A: 安裝 Microsoft Visual C++ Redistributable (x64)
     https://aka.ms/vs/17/release/vc_redist.x64.exe

================================================================
