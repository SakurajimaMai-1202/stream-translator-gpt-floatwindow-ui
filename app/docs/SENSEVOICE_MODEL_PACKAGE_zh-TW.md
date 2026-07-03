# SenseVoiceSmall 模型包

SenseVoiceSmall 可以另外提供成 GitHub Release asset，避免使用者第一次啟動時從 ModelScope 或 Hugging Face 下載過慢、失敗或卡住。

## 建議 Release 檔名

```text
StreamTranslator-SenseVoiceSmall-Model-v1.3.4.zip
```

## 使用者安裝方式

把模型包解壓到 Stream Translator 主程式資料夾。

解壓後應該出現：

```text
StreamTranslator\
  models\
    huggingface\
      modelscope\
        models\
          iic\
            SenseVoiceSmall\
```

CUDA、CPU、ROCm 三個版本都可以共用同一份模型資料夾。

## 程式載入順序

SenseVoiceSmall 啟動時會優先檢查本機模型：

1. `MODELSCOPE_CACHE\models\iic\SenseVoiceSmall`
2. `MODELSCOPE_CACHE\iic\SenseVoiceSmall`
3. `models\huggingface\modelscope\models\iic\SenseVoiceSmall`
4. `models\huggingface\modelscope\iic\SenseVoiceSmall`
5. `models\SenseVoiceSmall`

找得到本機模型時，FunASR 會直接用本機路徑，不會觸發線上下載。

## 製作模型包

先確認本機已有 SenseVoiceSmall 模型資料夾，然後在 `app` 目錄執行：

```powershell
.\packaging\build_sensevoice_model_package.ps1 -Version 1.3.4
```

如果模型在其他位置：

```powershell
.\packaging\build_sensevoice_model_package.ps1 -Version 1.3.4 -SourcePath "D:\Models\SenseVoiceSmall"
```

腳本會輸出：

```text
app\release-v1.3.4\StreamTranslator-SenseVoiceSmall-Model-v1.3.4.zip
```

並印出 SHA256，請把該 hash 補到 Release checksums 或 Release 說明。
