================================================================
  Stream Translator v1.5.0 — Windows 可攜式免安裝版
================================================================

【選擇下載包】
  - CPU：不需要獨立顯卡；可用 ASR 引擎依此 Runtime Profile 而定。
  - CUDA：需要相容的 NVIDIA 顯卡及驅動。
  - ROCm Experimental：需要相容的 AMD ROCm/HIP 顯卡及驅動。
  - 下載資產、支援引擎及相容更新條件以該版本 Release 說明為準。

【快速開始】
  1. 解壓縮完整包；若是 .partNN 分卷，先取得同一 profile 的全部
     分卷與對應合併工具，合併後再解壓。單一 ZIP 可直接解壓。
  2. 執行 Stream Translator.exe。
  3. 在「ASR 模型管理」下載模型，再於「轉錄選項」選擇相同模型。
  4. 在「翻譯選項」設定本地 LLM、線上 API，或選擇不翻譯。
  5. 回到「即時轉譯」選擇來源與語言，啟動並查看字幕。

【本地翻譯】
  - GGUF 模型另行下載，在「Llama 執行設定」指定模型及 Runtime。
  - 推薦頁提供模型下載、量化與顯存參考；需求隨模型及參數改變。
  - AMD／Intel 推薦 Vulkan、NVIDIA 推薦 CUDA，
    可手動選顯卡並顯示實際使用裝置，內顯預設排除。
  - 2026-10-10 重建的 v1.5.0 套件包含上述功能。
  - llama.cpp 翻譯顯卡與 ASR Runtime 分開設定；Vulkan 翻譯
    不代表 ASR 也支援 Vulkan。GPU 層數為 0 時使用 CPU。

【主要資料】
  Stream Translator.exe           主程式
  config.yaml                     使用者設定
  _runtime\                       對應 profile 的 Python Runtime
  models\                         模型快取（可於設定指定其他位置）
  ffmpeg\bin\                     音訊處理工具
  llama\                          選配 llama.cpp 執行檔
  output\、art\、logs\            輸出、圖片與日誌

【更新】
  - App Update 不能單獨當作完整包安裝；請遵守 Release 的版本、
    profile 與 Runtime 相容條件。
  - 更新前備份 config.yaml，保留模型與個人資料。
  - 勿將不同 profile 的 Runtime 混合覆蓋。

【排錯】
  - 啟動或模型載入失敗：查看 logs，確認驅動、Runtime、模型
    完整性及記憶體。健康檢查通過不代表模型推論已驗證。
  - 選到內顯：分別檢查轉錄與 Llama 顯卡設定及實際執行狀態。
  - 缺少 VCRUNTIME：安裝 Microsoft Visual C++ Redistributable x64：
    https://aka.ms/vs/17/release/vc_redist.x64.exe

完整功能、下載與更新紀錄請參考專案 README 及該版本 Release。
================================================================
