# Stream Translator v1.3.1

本次發行同時提供 CUDA、CPU、ROCm Experimental 三種 runtime profile。三個版本共用同一份主程式碼，依 package 內的 runtime profile 切換預設值、ASR 支援範圍與顯卡選擇策略。

## 下載建議

- NVIDIA 獨立顯卡使用者：下載 CUDA Full package。
- 沒有可用獨立顯卡或只想測功能：下載 CPU Full package。
- AMD ROCm/HIP 使用者：下載 ROCm Experimental Full package。
- 已經有同 profile 完整包的使用者，可下載對應的 App-Update zip 覆蓋更新。
- 不要用 CUDA App-Update 覆蓋 CPU 或 ROCm 完整包；App-Update 必須和原本 Full package 的 profile 相同。

## v1.3.1 更新重點

- 新增 CUDA / CPU / ROCm runtime profile 打包矩陣。
- 三種 package 會寫入不同的 runtime profile、預設裝置策略與 profile 專屬說明。
- Runtime Profile 設定頁會優先避開內顯，預設使用 auto discrete GPU。
- ROCm profile 改用 package 內的 `_runtime\python.exe` 探測 GPU/torch 支援架構，修正 RX 9070 XT / gfx1201 類型顯卡可能顯示 `No GPU selected` 的問題。
- 輸入語言拆分繁體中文與簡體中文；Qwen3-ASR 會映射為 Chinese。
- 每個 Full package 會附上 `diagnose_runtime.ps1`，方便回報 runtime、GPU、Qwen3-ASR 狀態。

## CUDA 版

定位：正式版，給 NVIDIA CUDA 使用者。

支援範圍：

- Faster-Whisper 全系列
- Qwen3-ASR offline：0.6B / 1.7B / 1.7B-JA
- Qwen3-ASR streaming：0.6B Streaming，experimental，English only

注意事項：

- Qwen3-ASR 預設使用 bf16。
- 預設裝置策略為 auto_discrete，會優先選擇獨立 GPU。
- 若沒有 NVIDIA CUDA GPU，請改用 CPU 包；AMD 使用者請使用 ROCm Experimental 包。

## CPU 版

定位：相容版，給沒有可用 GPU 或想先測功能的使用者。

支援範圍：

- Faster-Whisper：small / medium，速度較慢
- Qwen3-ASR offline：0.6B
- Qwen3-ASR streaming：0.6B Streaming，experimental，English only，速度待測
- 保留 OpenAI API 遠端 ASR / 翻譯能力

注意事項：

- CPU profile 會強制使用 CPU policy，不承諾 GPU 加速。
- 大型模型在 CPU 上會很慢，建議先用 Faster-Whisper small / medium 或 Qwen3-ASR 0.6B。
- 目前 CPU package runtime 體積仍接近 CUDA 包；未來若改純 CPU torch runtime，可再降低體積。

## ROCm Experimental 版

定位：實驗版，給 AMD ROCm/HIP 使用者。

支援範圍：

- Qwen3-ASR offline：0.6B / 1.7B / 1.7B-JA
- Qwen3-ASR streaming：先列 experimental；上游明確列 CUDA / Apple Silicon / CPU，未正式列 ROCm
- Faster-Whisper GPU 不正式承諾；必要時請改用 CUDA 或 CPU 包

注意事項：

- Qwen3-ASR 預設使用 bf16。
- 預設裝置策略為 auto_discrete，會避免選到 AMD 內顯 / APU。
- 目前建置機沒有 ROCm 獨立顯卡，已驗證 package 結構、HIP runtime manifest 與 ROCm torch 支援架構，但不宣稱 ROCm GPU ASR 實機推論已通過。
- 若 ROCm 使用者仍看到 `No GPU selected`，請執行 `diagnose_runtime.ps1 -Profile rocm` 並回報輸出。

## Full package 分卷合併

GitHub Release 單一 asset 有大小限制，因此 Full package 以分卷上傳。

PowerShell 合併範例：

```powershell
$output = [IO.File]::Create(".\StreamTranslator-win64-CUDA-Full.zip")
try {
  Get-ChildItem ".\StreamTranslator-win64-CUDA-Full.zip.part*" | Sort-Object Name | ForEach-Object {
    $input = [IO.File]::OpenRead($_.FullName)
    try { $input.CopyTo($output) } finally { $input.Dispose() }
  }
} finally {
  $output.Dispose()
}
```

也可以使用 7-Zip 或其他支援分卷合併的工具，依序合併 `.part01`, `.part02`, `.part03`。

合併後請對照 `SHA256SUMS-v1.3.1.txt` 驗證檔案完整性。

## 更新方式

新使用者：

1. 下載對應 profile 的 Full package 分卷。
2. 合併成 Full zip。
3. 解壓縮到英文或簡短路徑，例如 `D:\StreamTranslator`。
4. 執行 `Stream Translator.exe`。

既有使用者：

1. 關閉 Stream Translator。
2. 備份 `config.yaml`。
3. 下載和原本 Full package profile 相同的 App-Update zip。
4. 解壓縮到既有資料夾並覆蓋同名檔案。
5. 保留 `models`, `config.yaml`, `output`, `art`, `logs` 等資料夾。
6. 重新啟動 Stream Translator。
