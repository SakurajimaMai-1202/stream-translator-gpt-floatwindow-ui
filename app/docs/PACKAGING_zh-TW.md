# 打包流程

本專案的目標是維持同一份功能程式碼，依照 runtime profile 產生不同發行包。

## Runtime Profiles

| Profile | 產物目錄 | Full zip | App Update zip |
| --- | --- | --- | --- |
| `cuda` | `app/dist-cuda/StreamTranslator-win64-CUDA/` | `StreamTranslator-win64-CUDA-Full.zip` | `StreamTranslator-CUDA-App-Update.zip` |
| `cpu` | `app/dist-cpu/StreamTranslator-win64-CPU/` | `StreamTranslator-win64-CPU-Full.zip` | `StreamTranslator-CPU-App-Update.zip` |
| `rocm` | `app/dist-rocm/StreamTranslator-win64-ROCm-Experimental/` | `StreamTranslator-win64-ROCm-Experimental-Full.zip` | `StreamTranslator-ROCm-Experimental-App-Update.zip` |

## 建議入口

在 `app` 目錄執行：

```powershell
.\build_release.ps1 -Profile cuda
.\build_release.ps1 -Profile cpu
.\build_release.ps1 -Profile rocm
```

只重建 runtime cache：

```powershell
.\build_runtime.ps1 -Profile cuda
.\build_runtime.ps1 -Profile cpu
.\build_runtime.ps1 -Profile rocm
```

舊入口仍保留：

```powershell
.\build_cuda_release.ps1
.\build_cuda_runtime.ps1
```

這兩個舊入口等同於 `-Profile cuda`。

## Build Python 要求

打包腳本不負責在線安裝不同 torch 版本。請先準備對應 profile 的 Python 環境，必要時用 `STREAM_TRANSLATOR_BUILD_PYTHON` 指向該環境。

| Profile | Build Python 內的 torch 要求 |
| --- | --- |
| `cuda` | CUDA 版 PyTorch，`torch.version.cuda` 必須存在 |
| `cpu` | CPU 或 GPU 版 PyTorch 皆可，但打包後設定會強制 CPU profile；建議用 CPU 版降低體積 |
| `rocm` | ROCm/HIP 版 PyTorch，`torch.version.hip` 必須存在 |

範例：

```powershell
$env:STREAM_TRANSLATOR_BUILD_PYTHON = "F:\AI\floatwindow\app\venv\Scripts\python.exe"
.\check_runtime_profile_env.ps1 -Profile cuda
.\build_release.ps1 -Profile cuda -SkipFullZip
```

也可以直接指定 Python：

```powershell
.\check_runtime_profile_env.ps1 -Profile rocm -Python "F:\AI\rocm-runtime\python.exe"
```

檢查結果解讀：

- `cuda` 必須顯示 `cuda` 欄位。
- `rocm` 必須顯示 `hip` 欄位。
- `cpu` 若顯示 CUDA/HIP 會出現警告，代表可以打 CPU profile，但 runtime 仍包含 GPU 版 torch，檔案會比較大。

`build_runtime.ps1` 會在複製 runtime 前做同樣檢查。若用 CUDA torch 去跑 `-Profile rocm`，會在前置檢查階段直接停止，不會先複製大型 runtime。

## Runtime manifest

每個 runtime cache 會產生 `_runtime/runtime-version.json`，用來確認 profile 與 torch backend 是否一致。重要欄位：

| 欄位 | 說明 |
| --- | --- |
| `schema` | manifest 格式版本，目前為 `2` |
| `profile` | 打包 profile：`cuda` / `cpu` / `rocm` |
| `torch_backend` | 實際 torch backend：`cuda` / `cpu` / `rocm` |
| `cuda` | CUDA torch 版本，非 CUDA runtime 為空 |
| `hip` | ROCm/HIP torch 版本，非 ROCm runtime 為空 |
| `policy_forces_cpu` | CPU profile 會是 `true`，表示功能層會強制 CPU |

## Artifact 驗證

打包後請用 validator 檢查發行目錄、`config.yaml`、runtime manifest 與 App Update zip：

```powershell
.\validate_runtime_artifact.ps1 -Profile cuda
.\validate_runtime_artifact.ps1 -Profile cpu -ExpectedTorchBackend cuda
.\validate_runtime_artifact.ps1 -Profile rocm
```

若 CPU 是用純 CPU torch build Python 打包，請改用：

```powershell
.\validate_runtime_artifact.ps1 -Profile cpu -ExpectedTorchBackend cpu
```

目前本機已驗證的 CPU 包是 policy-only CPU 包，所以 `profile` 是 `cpu`，但 `torch_backend` 是 `cuda`，且 `policy_forces_cpu` 是 `true`。

也可以一次檢查整個矩陣：

```powershell
.\validate_runtime_matrix.ps1 -CpuExpectedTorchBackend cuda -AllowMissingRocm
```

正式完成三種 profile 實包後，請移除 `-AllowMissingRocm`：

```powershell
.\validate_runtime_matrix.ps1 -CpuExpectedTorchBackend cuda
```

## Config 注入

每個 full package 會從 `config.example.yaml` 產生 `config.yaml`，並自動寫入：

```yaml
runtime:
  profile: cuda
  device_policy: auto_discrete
```

CPU 與 ROCm 包會分別寫成 `cpu` / `rocm`。CPU 包會同步寫入 `device_policy: cpu`；CUDA 與 ROCm 包維持 `device_policy: auto_discrete`。其餘功能設定仍共用同一份 config 範本。

## 支援邊界

完整支援矩陣請見 `app/docs/RUNTIME_PROFILES_zh-TW.md`。

重點：

- CUDA：正式支援 Faster-Whisper 全系列、Qwen3-ASR offline 0.6B / 1.7B / 1.7B-JA，Qwen3 streaming 先列 experimental。
- CPU：正式列 Faster-Whisper small / medium 慢速、Qwen3-ASR offline 0.6B；Qwen3 streaming 速度待測。
- ROCm：正式列 Qwen3-ASR offline 0.6B / 1.7B / 1.7B-JA；streaming 只列 experimental，不作正式承諾。

## Runtime diagnostics

每個 full package 與 App Update package 會附上 `diagnose_runtime.ps1`。這個工具用來收集目標機器上的 runtime JSON log，尤其是 ROCm Experimental 包在沒有 AMD 顯卡的建置機上無法做實機推論驗證時。

在 package 根目錄執行：

```powershell
.\diagnose_runtime.ps1 -Profile rocm
```

常用參數：

```powershell
.\diagnose_runtime.ps1 -Profile cuda
.\diagnose_runtime.ps1 -Profile cpu
.\diagnose_runtime.ps1 -Profile rocm -AllowIntegratedGpu
.\diagnose_runtime.ps1 -Profile rocm -Output .\rocm-diagnostics.json
```

診斷工具會驗證 runtime manifest、PyTorch CUDA/HIP backend、Qwen3-ASR import、GPU 選擇策略與輕量 torch tensor execution。它不會宣稱完整 ASR inference 已通過；完整 ASR smoke test 仍需要實際音檔與模型 cache。
