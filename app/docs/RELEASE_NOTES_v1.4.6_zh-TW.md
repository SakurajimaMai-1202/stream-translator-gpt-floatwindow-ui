# Stream Translator v1.4.6 更新說明

v1.4.6 新增首次啟動的簡單／進階模式，讓新使用者可以直接使用 CPU ASR 搭配 API 翻譯，不必先理解 GPU Runtime、模型格式或大量進階參數。

## 最推薦的新手用法

下載 `StreamTranslator-win64-CPU-Full.zip`，直接解壓後啟動程式，選擇「簡單模式」，再設定 OpenAI、Gemini 或 OpenAI-compatible API 翻譯。CPU Full 包不需要 NVIDIA／AMD 獨立顯示卡，也不需要另外安裝 CPU ASR sidecar。

首次選擇介面模式時，程式會確認 CPU ASR Runtime，並預先準備以下三個模型；已下載的項目會自動略過：

- SenseVoice Small：繁體與簡體中文。
- Parakeet 0.6B 日文模型：日文。
- Parakeet TDT 0.6B v3：其餘 25 種支援語言。

## 簡單模式

- 首次開啟時選擇簡單或進階模式，選擇會保存，側欄可隨時切換。
- 簡單模式只保留音訊來源、輸入／目標語言、翻譯後端、字幕與開始／停止等常用功能。
- 依輸入語言自動切換 CPU ASR 引擎與模型；中文使用 SenseVoice，日文使用日文 Parakeet，其餘支援語言使用 Parakeet v3。
- 翻譯後端直接放在首頁；API Key 與詳細參數仍可進入翻譯詳細設定調整。
- 小視窗下側欄導覽可獨立捲動，介面模式切換器固定可見。

## 進階模式

- 保留完整 ASR 引擎、GPU／CPU 運算模式、模型管理、VAD、術語表、執行日誌、字幕分享與本機 LLM 控制。
- CUDA／ROCm Full 包仍包含 CPU ASR sidecar；若環境缺少或損壞，首次準備流程會自動下載、驗證並提示重新啟動。

## 介面修正

- 修正原生模式選單在深色介面出現白色區塊。
- 修正短選單向上展開時與控制項距離過遠。
- 修正進階模式在小視窗下無法捲動到底部切回簡單模式。
- 修正部分 Windows 環境因系統 `PATH` 內其他 Qt DLL 干擾，啟動時出現 `DLL load failed while importing QtWidgets`。

## 升級注意事項

- v1.4.6 App Update 為同 Profile 更新；CUDA、CPU 與 ROCm 更新包不可交叉使用。
- 現有 `config.yaml`、術語表、ASR 修正規則、Cookies、輸出與已下載模型可保留。
- 新手與相容性優先使用者建議直接下載 CPU Full 包；若只使用 API 翻譯，不需要下載本機 LLM。
