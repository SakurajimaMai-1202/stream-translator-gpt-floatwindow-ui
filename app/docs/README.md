# App 文件

## 使用與更新

- [App README](../README.md)：功能、目前版本狀態、套件選擇與啟動方式。
- [免安裝使用說明](PORTABLE_GUIDE_zh-TW.txt)：隨 CUDA 發行包提供的使用說明。
- [目前更新摘要](../UPDATE_NOTES_zh-TW.txt)：v1.5.0 目前套件的重點更新。
- [v1.5.0 完整更新說明](RELEASE_NOTES_v1.5.0_zh-TW.md)：功能、套件選擇、驗證範圍及更新步驟。
- [打包流程](PACKAGING_zh-TW.md)：開發者打包步驟與輸出位置。

2026-10-10 重建的 v1.5.0 CPU、CUDA 與 ROCm Experimental Full／App Update 套件包含全站介面統一、指定應用程式收音、llama.cpp 單卡選擇與 Index 模型推薦。套件建置與檢查通過；實際硬體、模型推論及長時間直播的驗證範圍請看完整更新說明。

## 實作與驗證

- [指定應用程式音訊](PROCESS_AUDIO_CAPTURE_IMPLEMENTATION_REPORT_2026-10-09_zh-TW.md)
- [llama.cpp 顯卡選擇](LLAMA_GPU_SELECTION_IMPLEMENTATION_2026-10-09_zh-TW.md)
- [翻譯模型家族與設定](TRANSLATION_FAMILY_IMPLEMENTATION_REPORT_2026-10-03_zh-TW.md)
- [全站介面驗證](../release-validation-v1.5.0/ui-unification-2026-10-10/validation.md)

打包腳本實作與 PyInstaller spec 位於 [packaging](../packaging/)。app 根目錄保留簡短入口腳本，相容既有打包指令。歷史版本的 RELEASE_NOTES 文件保留供版本比對。
