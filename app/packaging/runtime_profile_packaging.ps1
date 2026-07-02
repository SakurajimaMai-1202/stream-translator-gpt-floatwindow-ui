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
        [string]$Version = "1.3.4",
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
            "Qwen3-ASR streaming: 0.6B Streaming，experimental，English only",
            "SenseVoiceSmall: compatibility，offline sliced transcription",
            "Parakeet CTC 1.1B JA: experimental，CUDA only，Japanese-only，模型 grider-transwithai/parakeet-ctc-1.1b-ja"
        )
        $notes = @(
            "本版本是 NVIDIA CUDA 主線版。",
            "Qwen3-ASR 在 CUDA / ROCm profile 預設使用 bf16。",
            "SenseVoiceSmall 使用 FunASR runtime；首次使用前可先在模型管理預下載 iic/SenseVoiceSmall。",
            "Parakeet CTC JA 使用 NVIDIA NeMo runtime；打包 CUDA runtime 前請確認 build Python 已安裝 app/requirements_cuda_parakeet.txt。",
            "Parakeet CTC JA 預設使用 bfloat16；實測可正式跑，穩態顯存約 4GB，載入峰值會略高。",
            "預設裝置策略為 auto_discrete，會優先選擇獨立 GPU，避免誤選內顯。"
        )
        $warning = "若沒有可用 NVIDIA CUDA GPU，請改用 CPU 包；AMD ROCm 使用者請改用 ROCm Experimental 包。"
    } elseif ($RuntimeProfile -eq "cpu") {
        $name = "Stream Translator CPU"
        $status = "相容版"
        $runtime = "CPU profile / PyTorch CPU-only"
        $requirements = "不需要 NVIDIA 或 AMD 獨立顯示卡。CPU 速度會比 GPU 慢，建議先使用 Faster-Whisper small / medium 或 Qwen3-ASR 0.6B。"
        $models = @(
            "Faster-Whisper: small / medium 慢速",
            "Qwen3-ASR offline: 0.6B",
            "Qwen3-ASR streaming: 0.6B Streaming，experimental，English only，速度待測",
            "SenseVoiceSmall: compatibility，CPU 可用，速度待測"
        )
        $notes = @(
            "本版本是 CPU 相容版，不會承諾 GPU 加速。",
            "CPU profile 會把 ASR device policy 寫成 cpu，避免誤用顯卡。",
            "CPU 版保留遠端 API / 遠端字幕能力，可用於沒有獨顯的相容環境。",
            "SenseVoiceSmall 不預先標慢速；請依實際 CPU 與音訊長度測試速度。",
            "CPU package 使用 CPU-only PyTorch runtime，不會攜帶 CUDA / ROCm GPU torch runtime。"
        )
        $warning = "CPU 版適合沒有可用獨顯或想先測功能的使用者；大型模型會很慢。"
    } else {
        $name = "Stream Translator ROCm Experimental"
        $status = "實驗版"
        $runtime = "AMD ROCm / HIP PyTorch"
        $requirements = "需要支援 Windows ROCm/HIP 的 AMD 獨立顯示卡與相容驅動。本包不承諾 AMD 內顯 / APU 可用。"
        $models = @(
            "Qwen3-ASR offline: 0.6B / 1.7B / 1.7B-JA",
            "Qwen3-ASR streaming: experimental；上游明確列 CUDA / Apple Silicon / CPU，未正式列 ROCm",
            "SenseVoiceSmall: experimental；需 AMD 實機 ASR smoke test 後再提升狀態",
            "Faster-Whisper GPU 不正式承諾；必要時請改用 CUDA 或 CPU 包"
        )
        $notes = @(
            "本版本是 AMD ROCm Experimental，不是 NVIDIA CUDA 版。",
            "Qwen3-ASR 在 CUDA / ROCm profile 預設使用 bf16。",
            "SenseVoiceSmall 在 ROCm profile 先列 experimental；package validation 不等於 AMD GPU ASR inference 已通過。",
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
- CUDA / CPU / ROCm 共用同一份主程式碼，依 runtime profile 切換預設值與 package 名稱。
- 新增 runtime profile 設定與打包驗證，避免 CUDA、CPU、ROCm package 混用 runtime。
- 新增顯卡選擇策略，預設使用 auto_discrete，避免誤選內顯。
- 輸入語言已拆分繁體中文與簡體中文；Qwen3-ASR 會映射為 Chinese。
- CUDA 版新增 Parakeet CTC 1.1B JA experimental；僅限日文輸入，使用 NVIDIA NeMo 與 grider-transwithai/parakeet-ctc-1.1b-ja。
- 設定頁「模型管理」更名為「ASR模型管理」，並修正第一次點入時落到一般設定的問題。
- 轉錄選項會整理為單一 ASR 後端，避免 Qwen3-ASR / SenseVoiceSmall / Parakeet CTC JA 同時被選取。
- ROCm Experimental 版補齊 FunASR runtime，修正 SenseVoiceSmall 因缺少 funasr 無法啟動的問題。
- 每個 package 會附上 diagnose_runtime.ps1，用於收集目標機器的 runtime / GPU / Qwen3-ASR / FunASR 狀態。
- 每個 package 會附上 smoke_sensevoice_asr.ps1，可用短音檔驗證 SenseVoiceSmall 真實 ASR 推論。

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
        [string]$Version = "1.3.4"
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
