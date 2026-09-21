# Stream Translator v1.4.8 更新說明

v1.4.8 改善簡單模式首次設定、llama.cpp Runtime 硬體相容性，以及浮動字幕在不同視窗高度下的顯示行為。

## 主要更新

- 簡單模式會偵測 NVIDIA／AMD 顯卡及 VRAM，分為未滿 4 GB、4 GB～未滿 8 GB、8 GB 以上。
- 未滿 4 GB 使用 Hy-MT2 `i1-IQ3_XXS`；4 GB～未滿 8 GB 使用 `i1-IQ4_NL`；8 GB 以上使用 `i1-Q6_K`。
- 簡單模式只使用 GPU llama.cpp Runtime：CUDA 應用固定使用 CUDA、ROCm 應用固定使用 HIP；CPU 應用會依偵測到的 NVIDIA、AMD 或 Intel Arc 顯卡推薦 CUDA、HIP、SYCL 或 Vulkan，不使用 CPU llama.cpp Runtime。
- 純 CPU 應用包也會透過 `nvidia-smi` 讀取 NVIDIA VRAM，避免 Windows 將大容量顯存誤判為未知。
- NVIDIA Runtime 會安裝同一版的 CUDA 主套件及對應 `cudart`；AMD 使用 HIP／ROCm，Intel Arc 使用 SYCL，避免混裝不相容的附加 Runtime。
- 外部 llama-server 啟動時會隔離 PyInstaller／Qt DLL 路徑，修正新版 llama.cpp 在 Windows 發生 `0xC0000005` 的問題。
- Hy-MT2 預設停用 mmap，Flash Attention 可選 `on | off | auto`，預設交由 llama.cpp 自動判斷。
- llama.cpp 執行記錄會獨立保存，方便檢查原生 Runtime 的載入與退出原因。
- Runtime 與模型下載顯示實際百分比；Hy-MT2 模型會從 Hugging Face blob metadata 取得檔案大小及 SHA-256 後再下載驗證。
- 首次導引只完成 Runtime／模型下載與參數設定，不會直接啟動本地翻譯服務或占用 VRAM；進入首頁後由使用者手動開啟。
- 本地 LLM 開關每次啟動程式時預設關閉。
- 浮動字幕會依可用高度自然向上捲動，最小高度仍保留可讀行數，並避免裁掉翻譯行或留下大片空白。
- 浮動字幕控制按鈕可自動隱藏，時間軸顏色會正確套用，設定預覽在小高度視窗也能看見。
- 修正更新器與主程式封裝環境的 Qt DLL 載入問題。

## 套件說明

- CUDA、CPU 與 ROCm App Update 必須用於相同 Profile。
- 三種 Full package 都不預載 GGUF；簡單模式選擇本機翻譯後，才會依硬體下載對應 Runtime 與 Hy-MT2 模型。
- CPU Full 是新手使用 CPU ASR 搭配 Gemini／OpenAI／OpenAI-compatible API 翻譯的最簡單選擇。
