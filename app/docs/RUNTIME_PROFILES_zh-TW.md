# Runtime Profiles 設計

目標：FloatWindow 維持同一份功能程式碼，依照 runtime profile 切換 CUDA、CPU、ROCm 的依賴、預設值、裝置選擇與打包輸出。之後修功能只改一次，不再分叉維護 CUDA 版與 ROCm 版。

## Profile 命名

| Profile | 對外名稱 | 狀態 | 用途 |
| --- | --- | --- | --- |
| `cuda` | `StreamTranslator-win64-CUDA` | Official | NVIDIA CUDA 使用者 |
| `cpu` | `StreamTranslator-win64-CPU` | Compatibility | 無獨顯或不能使用 GPU 的使用者 |
| `rocm` | `StreamTranslator-win64-ROCm-Experimental` | Experimental | AMD ROCm 測試使用者 |

打包輸出：

```text
app/build-runtime-cache/cuda-runtime
app/build-runtime-cache/cpu-runtime
app/build-runtime-cache/rocm-runtime

app/dist-cuda
app/dist-cpu
app/dist-rocm
```

## 支援矩陣

### CUDA

| 功能 | 支援 |
| --- | --- |
| Faster-Whisper | 全系列 |
| Qwen3-ASR offline | 0.6B / 1.7B / 1.7B-JA |
| Qwen3-ASR streaming | 0.6B Streaming，experimental，English only |
| Qwen3-ASR default dtype | `bfloat16` |
| 預設 device policy | `auto_discrete` |

### CPU

| 功能 | 支援 |
| --- | --- |
| Faster-Whisper | small / medium，慢速 |
| Qwen3-ASR offline | 0.6B |
| Qwen3-ASR streaming | 0.6B Streaming，experimental，English only，速度待測 |
| Qwen3-ASR default dtype | `float32` |
| 預設 device policy | `cpu` |

CPU profile 會把預設的 Qwen3 `bfloat16` 改成 `float32`，避免 CPU runtime 跑到不穩或不支援的 dtype。

### ROCm

| 功能 | 支援 |
| --- | --- |
| Faster-Whisper | GPU 不正式承諾；必要時走 CPU fallback |
| Qwen3-ASR offline | 0.6B / 1.7B / 1.7B-JA |
| Qwen3-ASR streaming | 先列 experimental，不當正式承諾 |
| Qwen3-ASR default dtype | `bfloat16` |
| 預設 device policy | `auto_discrete` |

ROCm streaming 只列 experimental，原因是上游頁面明確寫 CUDA / Apple Silicon / CPU，沒有寫 ROCm。

## Runtime Config

```yaml
runtime:
  profile: cuda
  device_policy: auto_discrete
  device_index: null
  device_name: ''
  allow_integrated_gpu: false
```

`profile` 可用值：

- `cuda`
- `cpu`
- `rocm`

`device_policy` 可用值：

- `auto_discrete`：預設，只選離散 GPU。
- `auto_any`：允許任何符合 backend 的 GPU，通常不建議。
- `manual`：依照 `device_index` 或 `device_name` 指定。
- `cpu`：強制 CPU。

## GPU 選擇策略

### CUDA

- 只自動選 NVIDIA GPU。
- 多張 NVIDIA GPU 時選 VRAM 最大者。
- 跳過 Intel / AMD 內顯。

### ROCm

- 只自動選 AMD GPU。
- 預設跳過 AMD APU / iGPU。
- 只有 `allow_integrated_gpu: true` 時才允許 Ryzen APU / AMD iGPU experimental。

### CPU

- 不選 GPU。
- ASR device 強制 CPU。

## 內顯判斷 heuristic

預設視為 integrated 的名稱片段：

```text
Intel
UHD
Iris
Integrated
APU
Radeon Graphics
AMD Radeon(TM) Graphics
```

預設視為 discrete 的名稱片段：

```text
NVIDIA GeForce
NVIDIA RTX
NVIDIA GTX
NVIDIA Quadro
NVIDIA RTX A
AMD Radeon RX
AMD Radeon PRO
AMD Instinct
```

這是保守 heuristic。若使用者真的要測內顯，可以用 `allow_integrated_gpu` override。

## 已落地元件

| 元件 | 責任 |
| --- | --- |
| `app/backend/core/runtime_profiles.py` | 定義 profile capability 與預設 dtype/device policy |
| `app/backend/core/hardware_detector.py` | 偵測 GPU、分類 vendor、判斷內顯/獨顯 |
| `app/backend/core/runtime_status.py` | 組合目前 profile、capability、device selection 狀態 |
| `app/backend/api/runtime.py` | 提供 `/api/runtime/status` |
| `stream-translator-gpt/stream_translator_gpt/runtime_accelerator.py` | 在 ASR runtime 內再次依 torch 實際裝置選 GPU |
| `app/build_release.ps1` | profile-aware release 打包入口 |
| `app/build_runtime.ps1` | profile-aware runtime cache 入口 |
| `app/check_runtime_profile_env.ps1` | 打包前檢查 build Python 是否符合 profile |
| `app/validate_runtime_artifact.ps1` | 打包後檢查 dist artifact 是否符合 profile |
| `app/validate_runtime_matrix.ps1` | 打包後檢查 CUDA / CPU / ROCm artifact 矩陣 |

## 打包策略

打包主入口：

```powershell
.\build_release.ps1 -Profile cuda
.\build_release.ps1 -Profile cpu
.\build_release.ps1 -Profile rocm
```

相容入口仍保留：

```powershell
.\build_cuda_release.ps1
.\build_cuda_runtime.ps1
```

這兩個等同於 `-Profile cuda`。

各 profile 需要由對應的 build Python 環境提供正確 torch runtime。打包腳本會驗證：

- CUDA profile：`torch.version.cuda` 必須存在。
- CPU profile：會強制 CPU policy；建議用 CPU torch 減少體積。
- ROCm profile：`torch.version.hip` 必須存在。

打包前可先跑：

```powershell
.\check_runtime_profile_env.ps1 -Profile cuda
.\check_runtime_profile_env.ps1 -Profile cpu
.\check_runtime_profile_env.ps1 -Profile rocm -Python "F:\AI\rocm-runtime\python.exe"
```

`build_runtime.ps1` 也會做同樣的前置檢查，CUDA / ROCm 的 torch backend 不符合時會在複製 runtime 前停止。

runtime cache 會寫入 `_runtime/runtime-version.json`，其中 `profile` 表示發行 profile，`torch_backend` 表示實際 torch backend。CPU profile 如果用 CUDA torch 打包，`profile` 會是 `cpu`，`torch_backend` 會是 `cuda`，並以 `policy_forces_cpu: true` 表示功能層仍強制 CPU。

full package 的 `config.yaml` 會依 profile 注入 runtime 預設：

- CUDA / ROCm：`device_policy: auto_discrete`
- CPU：`device_policy: cpu`

打包後可用同一套 validator 驗證 artifact：

```powershell
.\validate_runtime_artifact.ps1 -Profile cuda
.\validate_runtime_artifact.ps1 -Profile cpu -ExpectedTorchBackend cuda
.\validate_runtime_artifact.ps1 -Profile rocm
```

目前尚未具備 ROCm/HIP build Python 時，可用：

```powershell
.\validate_runtime_matrix.ps1 -CpuExpectedTorchBackend cuda -AllowMissingRocm
```

最終完成門檻是不帶 `-AllowMissingRocm` 也通過。

## Smoke Test 建議

CUDA：

- Faster-Whisper small
- Qwen3-ASR 0.6B，`bfloat16`

CPU：

- Faster-Whisper small / medium
- Qwen3-ASR 0.6B，`float32`

ROCm：

- Qwen3-ASR 0.6B，`bfloat16`
- Qwen3-ASR 1.7B，依 VRAM 測試

## 待辦

1. 在實機 CUDA / CPU / ROCm build Python 上各跑一次 `build_runtime.ps1`。
2. 在三種 full package 中驗證 `config.yaml` 的 `runtime.profile` 注入。
3. 補實機 smoke test 結果，尤其是 ROCm streaming 與 CPU streaming 速度。

## ROCm 無卡建置與診斷

目前建置機可以驗證 ROCm runtime package 結構、`torch.version.hip`、`qwen_asr` import、`runtime.profile: rocm` 注入與 artifact matrix，但如果建置機沒有 AMD ROCm 顯卡，就不能宣稱 ROCm GPU ASR inference 已實機通過。

ROCm release 應維持 `Experimental`，並把驗證狀態拆開：

```text
package_validated: yes
runtime_import_validated: yes
torch_execution_validated: depends on target machine
gpu_inference_validated: no, unless diagnose_runtime.ps1 passes on AMD GPU
asr_inference_validated: no, unless a real ASR smoke test was run
```

包內會附上 `diagnose_runtime.ps1`。有 AMD 顯卡的測試者在 package 根目錄執行：

```powershell
.\diagnose_runtime.ps1 -Profile rocm
```

如果要測 APU/iGPU 實驗路徑，可明確打開：

```powershell
.\diagnose_runtime.ps1 -Profile rocm -AllowIntegratedGpu
```

診斷 JSON 會列出：

- Python / platform。
- runtime manifest。
- PyTorch 版本、CUDA/HIP 欄位、torch backend。
- torch 可見 GPU、device name、VRAM、是否被視為 integrated。
- Qwen3-ASR package 是否可 import。
- selector 最後選到的 `device_map`。
- 輕量 torch tensor execution smoke 結果。
- `asr_inference_validated` 固定為 `false`，直到另外跑完整音檔 ASR smoke test。

這樣即使本機沒有 ROCm 卡，也能先發出結構正確、標示保守的 ROCm Experimental 包；真正的 AMD GPU 實機結果則用診斷 log 回收。
