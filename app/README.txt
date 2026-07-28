================================================================
  Stream Translator
  Windows 可攜式免安裝版
================================================================

【最低系統需求】
  - Windows 10 / 11 64-bit
  - CUDA 版：相容的 NVIDIA 獨立顯示卡與驅動程式
  - CPU 版：不需要獨立顯示卡
  - ROCm Experimental 版：相容的 AMD ROCm/HIP 獨立顯示卡與驅動程式

【快速開始】
  1. 將完整包解壓縮到英文或簡短路徑，例如 D:\StreamTranslator。
  2. 執行 Stream Translator.exe。
  3. 開啟「ASR 模型管理」，先下載準備使用的語音辨識模型。
  4. 在「翻譯選項」設定本地 LLM 或線上 API。
  5. 回到「即時轉譯」選擇音訊來源、輸入語言與目標語言。

【目錄說明】
  Stream Translator.exe           主程式
  config.yaml                     使用者設定
  _runtime\                       對應 CUDA／CPU／ROCm profile 的 Python runtime
  models\                         ASR 與 Hugging Face／ModelScope 模型快取
  ffmpeg\bin\                     音訊處理工具
  llama\                          選配的 llama.cpp 執行檔

【模型說明】
  - ASR 模型請優先從程式內的「ASR 模型管理」下載。
  - SenseVoiceSmall 可使用 GitHub Release 提供的獨立模型包。
  - GGUF 翻譯模型需另外下載，再於 Llama 設定指定模型路徑。
  - 模型檔案通常較大，首次下載需要網路連線與足夠磁碟空間。

【更新方式】
  - Full package：下載相同 profile 的所有 .partNN，執行
    merge-full-package.bat 合併後再解壓。
  - App Update：只能覆蓋到相同 profile 的既有完整包。
  - 更新前請備份 config.yaml，並保留 models、output、art 與 logs。

【常見問題】
  Q: 啟動後白畫面、閃爍或無法開啟？
  A: 請更新顯示卡驅動，並避免使用過長或含特殊符號的安裝路徑。

  Q: GPU 未被使用或選到內顯？
  A: 到「轉錄選項」重新整理 Runtime Profile，保持
     Auto discrete GPU；只有實驗需要時才允許 integrated GPU。

  Q: 出現 VCRUNTIME 缺失錯誤？
  A: 安裝 Microsoft Visual C++ Redistributable (x64)：
     https://aka.ms/vs/17/release/vc_redist.x64.exe

================================================================
