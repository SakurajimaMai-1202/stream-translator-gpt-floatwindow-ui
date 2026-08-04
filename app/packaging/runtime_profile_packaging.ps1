function Get-RuntimeProfilePackageInfo {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("cuda", "cpu", "rocm")]
        [string]$RuntimeProfile
    )

    $label = $RuntimeProfile.ToUpperInvariant()
    if ($RuntimeProfile -eq "rocm") {
        $suffix = "ROCm-Experimental"
    } else {
        $suffix = $label
    }

    [pscustomobject]@{
        Profile = $RuntimeProfile
        Label = $label
        Suffix = $suffix
        DistDirName = "dist-$RuntimeProfile"
        RuntimeCacheName = "$RuntimeProfile-runtime"
        PackageName = "StreamTranslator-win64-$suffix"
        AppUpdateZip = "StreamTranslator-$suffix-App-Update.zip"
        FullZip = "StreamTranslator-win64-$suffix-Full.zip"
    }
}

function Set-RuntimeProfileInConfigText {
    param(
        [Parameter(Mandatory = $true)]
        [string]$ConfigText,
        [Parameter(Mandatory = $true)]
        [ValidateSet("cuda", "cpu", "rocm")]
        [string]$RuntimeProfile
    )

    $lines = $ConfigText -split "\r?\n", -1
    $inRuntime = $false
    $profileUpdated = $false
    $devicePolicyUpdated = $false
    $devicePolicy = if ($RuntimeProfile -eq "cpu") { "cpu" } else { "auto_discrete" }
    for ($index = 0; $index -lt $lines.Count; $index++) {
        $line = $lines[$index]
        if ($line -match '^\S[^:]*:\s*$') {
            $inRuntime = $line -match '^runtime:\s*$'
            continue
        }
        if ($inRuntime -and $line -match '^(\s*)profile:\s*\w+\s*$') {
            $lines[$index] = "$($Matches[1])profile: $RuntimeProfile"
            $profileUpdated = $true
            continue
        }
        if ($inRuntime -and $line -match '^(\s*)device_policy:\s*\w+\s*$') {
            $lines[$index] = "$($Matches[1])device_policy: $devicePolicy"
            $devicePolicyUpdated = $true
        }
    }

    if (-not $profileUpdated) {
        throw "runtime.profile not found in config template"
    }
    if (-not $devicePolicyUpdated) {
        throw "runtime.device_policy not found in config template"
    }

    return ($lines -join "`n").TrimEnd() + "`n"
}

function Write-Utf8NoBomTextFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    [System.IO.File]::WriteAllText($Path, $Text.TrimEnd() + "`r`n", [System.Text.UTF8Encoding]::new($false))
}

function Get-RuntimeProfileDocText {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet("cuda", "cpu", "rocm")]
        [string]$RuntimeProfile,
        [string]$Version = "1.3.8",
        [Parameter(Mandatory = $true)]
        [ValidateSet("portable_guide", "update_notes", "readme")]
        [string]$Document
    )

    $packageInfo = Get-RuntimeProfilePackageInfo -RuntimeProfile $RuntimeProfile
    $builtAt = Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"

    if ($RuntimeProfile -eq "cuda") {
        $name = "Stream Translator CUDA"
        $status = "正式版"
        $runtime = "NVIDIA CUDA / PyTorch CUDA"
        $requirements = "需要相容的 NVIDIA 獨立顯示卡與 NVIDIA Driver；不需要另外安裝 Python、CUDA Toolkit、cuDNN 或 pip 套件。"
        $models = @(
            "Faster-Whisper 全系列",
            "Qwen3-ASR offline: 0.6B / 1.7B / 1.7B-JA",
            "SenseVoiceSmall: compatibility，offline sliced transcription",
            "NVIDIA Parakeet: experimental，CUDA only；0.6B 日文 / 1.1B 英文，混合 TDT/CTC"
        )
        $notes = @(
            "本版本是 NVIDIA CUDA 主線版。",
            "Qwen3-ASR 在 CUDA / ROCm profile 預設使用 bf16。",
            "SenseVoiceSmall 使用 FunASR runtime；首次使用前可先在模型管理預下載 iic/SenseVoiceSmall。",
            "NVIDIA Parakeet 使用 NVIDIA NeMo runtime；打包 CUDA runtime 前請確認 build Python 已安裝 app/requirements_cuda_parakeet.txt。",
            "官方模型預設使用 TDT decoder 與 bfloat16；英文／日文依模型固定。官方模型授權為 CC-BY-4.0。",
            "預設裝置策略為 auto_discrete，會優先選擇獨立 GPU，避免誤選內顯。"
        )
        $warning = "若沒有可用 NVIDIA CUDA GPU，請改用 CPU 包；AMD ROCm 使用者請改用 ROCm Experimental 包。"
    } elseif ($RuntimeProfile -eq "cpu") {
        $name = "Stream Translator CPU"
        $status = "相容版"
        $runtime = "CPU profile / sherpa-onnx INT8"
        $requirements = "不需要 NVIDIA 或 AMD 獨立顯示卡。五個本地模型都透過 sherpa-onnx 在 CPU 執行。"
        $models = @(
            "Parakeet TDT 0.6B v3 INT8: English",
            "Parakeet TDT-CTC 0.6B INT8: Japanese",
            "Fun-ASR Nano / SenseVoiceSmall / Qwen3-ASR 0.6B: INT8"
        )
        $notes = @(
            "本版本是 CPU 相容版，不會承諾 GPU 加速。",
            "CPU profile 會把 ASR device policy 寫成 cpu，避免誤用顯卡。",
            "CPU 版保留遠端 API / 遠端字幕能力，可用於沒有獨顯的相容環境。",
            "SenseVoiceSmall 不預先標慢速；請依實際 CPU 與音訊長度測試速度。",
            "CPU package 使用 sherpa-onnx runtime，不攜帶 PyTorch、NeMo、CUDA 或 ROCm runtime。"
        )
        $warning = "CPU 版適合沒有可用獨顯或想先測功能的使用者；大型模型會很慢。"
    } else {
        $name = "Stream Translator ROCm Experimental"
        $status = "實驗版"
        $runtime = "AMD ROCm / HIP PyTorch"
        $requirements = "需要支援 Windows ROCm/HIP 的 AMD 獨立顯示卡與相容驅動。本包不承諾 AMD 內顯 / APU 可用。"
        $models = @(
            "Qwen3-ASR offline: 0.6B / 1.7B / 1.7B-JA",
            "SenseVoiceSmall: 已由 AMD ROCm 實機驗證可用",
            "Faster-Whisper GPU 不正式承諾；必要時請改用 CUDA 或 CPU 包"
        )
        $notes = @(
            "本版本是 AMD ROCm Experimental，不是 NVIDIA CUDA 版。",
            "Qwen3-ASR 在 CUDA / ROCm profile 預設使用 bf16。",
            "SenseVoiceSmall 已通過 AMD ROCm 實機測試；仍建議使用 smoke_sensevoice_asr.ps1 在目標機器確認音訊與模型 cache。",
            "預設裝置策略為 auto_discrete，會避免選到 AMD 內顯 / APU；沒有 ROCm 獨顯時會在診斷中標示未驗證。",
            "Radeon RX 9070 XT 已由使用者實機測試確認可用。"
        )
        $warning = "目前建置機沒有 ROCm 獨立顯卡；package 結構與 HIP runtime manifest 可驗證，Radeon RX 9070 XT 已由使用者實機確認可用，其他 AMD 顯卡仍請附診斷結果回報。"
    }

    $modelLines = ($models | ForEach-Object { "- $_" }) -join "`r`n"
    $noteLines = ($notes | ForEach-Object { "- $_" }) -join "`r`n"

    if ($Document -eq "portable_guide") {
        return @"
$name 可攜版使用說明
====================================

版本定位
--------
- Package: $($packageInfo.PackageName)
- Version: $Version
- Profile: $RuntimeProfile
- 狀態: $status
- Runtime: $runtime
- 打包時間: $builtAt

第一次使用
----------
1. 解壓縮完整包 ZIP 到英文或簡短路徑，例如 D:\StreamTranslator。
2. 執行 Stream Translator.exe。
3. 第一次使用 ASR 模型時，模型會下載到 models\huggingface 或你在設定中指定的模型資料夾。
4. 若 Windows 跳出安全性提醒，請確認來源是你下載的正式發行包後再允許執行。

環境需求
--------
$requirements

本版本 ASR 支援範圍
------------------
$modelLines

模型資料夾建議
--------------
- 預設模型資料夾: models\huggingface
- 若磁碟空間不足，建議在設定中改到容量較大的磁碟，例如 D:\StreamTranslatorModels。
- 重新安裝或更新時，請保留 models、config.yaml、output、art、logs 等資料夾。

App Update 包更新方式
--------------------
App Update 包只更新主程式與 Python 程式碼，不包含完整 runtime、模型與個人設定。
1. 關閉 Stream Translator。
2. 備份 config.yaml。
3. 將 App Update ZIP 解壓到既有完整包資料夾，覆蓋同名檔案。
4. 不要刪除 models、config.yaml、output、art、logs。
5. 重新啟動 Stream Translator。

注意事項
--------
$noteLines
- $warning
"@
    }

    if ($Document -eq "update_notes") {
        return @"
$name v$Version 更新說明
====================================

版本定位
--------
- Package: $($packageInfo.PackageName)
- Version: $Version
- Profile: $RuntimeProfile
- 狀態: $status
- Runtime: $runtime
- 打包時間: $builtAt

本次更新重點
------------
- 翻譯管線會依 Hy-MT2、一般聊天模型與結構化線上 API 選擇不同 prompt、取樣參數與輸出解析策略。
- Hy-MT2 使用專用純文字提示格式；Gemma 等一般模型使用聊天提示；OpenAI / Gemini 可使用結構化輸出。
- 原文與譯文維持成對提交，翻譯工作可平行執行，但字幕會依 segment_id 保持原始順序。
- 新增 ASR 重疊文字去重與短句組句器，降低重複字幕並改善過短片段的翻譯語境。
- 新增直播低延遲音訊參數：擷取間隔、最短／目標／最長片段、句尾靜音、前綴保留與動態 VAD。
- UI、config.yaml 與實際音訊管線使用相同欄位，移除未接入管線的舊設定混淆。
- 浮動與桌面字幕視窗可顯示每句 ASR、排隊、翻譯及總處理延遲。
- 延遲狀態會顯示在時間後方，並可獨立調整文字顏色。
- 浮動字幕視窗會在移動、縮放與關閉時保存位置及尺寸，重新開啟後可正確還原。
- 新增機器可讀字幕事件；舊 runtime 仍可透過 latency log 相容顯示 ASR／翻譯延遲。
- 保留 v1.3.5 的配置快取、原子寫入、跨程序鎖與外部 config.yaml 修改偵測。
- CUDA / CPU / ROCm 繼續共用同一份功能程式碼，依 runtime profile 提供不同 torch 與 ASR 能力。

本版本支援範圍
--------------
$modelLines

版本注意
--------
$noteLines
- $warning

更新建議
--------
- 新使用者請下載 Full.zip。
- 已有同 profile 完整包的使用者，可使用對應的 App-Update.zip 覆蓋更新。
- 不要用 CUDA App Update 覆蓋 ROCm 或 CPU 完整包；三個 profile 的 App Update 需對應使用。
"@
    }

    return @"
$name
====================================

Package: $($packageInfo.PackageName)
Version: $Version
Profile: $RuntimeProfile
Status: $status
Runtime: $runtime
Built at: $builtAt

This folder is generated by the runtime profile packaging flow.

Environment:
$requirements

Supported ASR scope:
$modelLines

Notes:
$noteLines
- $warning
"@
}

function Write-RuntimeProfileDocs {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Destination,
        [Parameter(Mandatory = $true)]
        [ValidateSet("cuda", "cpu", "rocm")]
        [string]$RuntimeProfile,
        [string]$Version = "1.3.8"
    )

    if (-not (Test-Path $Destination)) {
        New-Item $Destination -ItemType Directory -Force | Out-Null
    }

    Write-Utf8NoBomTextFile `
        -Path (Join-Path $Destination "PORTABLE_GUIDE_zh-TW.txt") `
        -Text (Get-RuntimeProfileDocText -RuntimeProfile $RuntimeProfile -Version $Version -Document "portable_guide")
    Write-Utf8NoBomTextFile `
        -Path (Join-Path $Destination "UPDATE_NOTES_zh-TW.txt") `
        -Text (Get-RuntimeProfileDocText -RuntimeProfile $RuntimeProfile -Version $Version -Document "update_notes")

    $internalDir = Join-Path $Destination "_internal"
    if (Test-Path $internalDir) {
        Write-Utf8NoBomTextFile `
            -Path (Join-Path $internalDir "README.txt") `
            -Text (Get-RuntimeProfileDocText -RuntimeProfile $RuntimeProfile -Version $Version -Document "readme")
    }
}
