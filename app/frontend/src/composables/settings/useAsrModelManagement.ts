import { ref, computed, type Ref } from 'vue';
import { runtimeApi, type CpuAsrSidecarInstallStatus, type ModelComputeBackend, type ModelEngine } from '../../services/api';
import type { useTranslationStore } from '../../stores/translation';
import type { useModelDownloadStore } from '../../stores/modelDownload';
import type { useTranscriptionSettings } from './useTranscriptionSettings';

export function useAsrModelManagement(localConfig: Ref<any>, store: ReturnType<typeof useTranslationStore>, modelDownloadStore: ReturnType<typeof useModelDownloadStore>, transcription: ReturnType<typeof useTranscriptionSettings>) {
  const { runtimeStatus, effectiveAsrComputeBackend, allQwenModels, allSenseVoiceModels, allFunAsrModels, allParakeetModels, allFasterWhisperModels, allowedQwen3AsrModels, allowedSenseVoiceModels, allowedFunAsrModels, allowedParakeetModels, allowedFasterWhisperModels } = transcription;
  const modelManagementBackend = ref<ModelComputeBackend>(effectiveAsrComputeBackend.value);
  const cpuQwenModels = ['Qwen/Qwen3-ASR-0.6B', 'Qwen/Qwen3-ASR-1.7B'];
  const cpuSenseVoiceModels = ['iic/SenseVoiceSmall'];
  const cpuFunAsrModels = ['FunAudioLLM/Fun-ASR-Nano-2512'];
  const cpuParakeetModels = ['nvidia/parakeet-tdt-0.6b-v3', 'nvidia/parakeet-tdt_ctc-0.6b-ja'];
  const cpuQwenDescriptions = {
    'Qwen/Qwen3-ASR-0.6B': 'Sherpa-ONNX 專用 INT8 ONNX bundle；CPU 離線推論，不使用 PyTorch、CUDA dtype 或 4-bit 設定。',
    'Qwen/Qwen3-ASR-1.7B': 'Sherpa-ONNX INT8 1.7B CPU bundle；準確度較高，但下載約 2.4 GB、推論速度與記憶體需求也高於 0.6B。',
  };
  const cpuSenseVoiceDescriptions = {
    'iic/SenseVoiceSmall': 'Sherpa-ONNX INT8 多語言模型，支援中文、英文、日文、韓文與粵語；CPU 離線推論。',
  };
  const cpuFunAsrDescriptions = {
    'FunAudioLLM/Fun-ASR-Nano-2512': 'Sherpa-ONNX INT8 CPU bundle，支援中文、英文、日文及中文方言；目前不提供時間戳。',
  };
  const cpuParakeetDescriptions = {
    'nvidia/parakeet-tdt-0.6b-v3': 'Sherpa-ONNX INT8 TDT bundle；支援 25 種語言及自動語言辨識，不需要 NVIDIA GPU 或 NeMo。',
    'nvidia/parakeet-tdt_ctc-0.6b-ja': 'Sherpa-ONNX INT8 CTC 日文專用 bundle；語言固定為日文，不需要 NVIDIA GPU 或 NeMo。',
  };
  const gpuQwenModels = computed(() => runtimeStatus.value?.capabilities?.qwen3_asr_model_ids || allQwenModels);
  const gpuSenseVoiceModels = computed(() => runtimeStatus.value?.capabilities?.sensevoice_model_ids || allSenseVoiceModels);
  const gpuFunAsrModels = computed(() => runtimeStatus.value?.capabilities?.fun_asr_model_ids || allFunAsrModels);
  const gpuParakeetModels = computed(() => runtimeStatus.value?.capabilities?.parakeet_model_ids || allParakeetModels);
  const gpuFasterWhisperModels = computed(() => runtimeStatus.value?.capabilities?.faster_whisper_model_ids || allFasterWhisperModels);
  const managedDownloadedModels = computed(() =>
    modelDownloadStore.downloadedModels.filter((item) => item.compute_backend === modelManagementBackend.value)
  );
  const cpuAsrSidecarStatus = ref<CpuAsrSidecarInstallStatus | null>(null);
  const cpuAsrOfflineArchive = ref('');
  const cpuAsrSidecarBusy = computed(() =>
    ['starting', 'downloading', 'verifying', 'installing'].includes(cpuAsrSidecarStatus.value?.status || '')
  );
  const canInstallCpuAsrSidecar = computed(() =>
    ['cuda', 'rocm'].includes(runtimeStatus.value?.profile || '')
    && !cpuAsrSidecarBusy.value
  );
  const canCancelCpuAsrSidecar = computed(() =>
    cpuAsrSidecarBusy.value && cpuAsrSidecarStatus.value?.status !== 'installing'
  );
  let cpuAsrSidecarPollTimer: ReturnType<typeof setInterval> | null = null;

  function stopCpuAsrSidecarPolling() {
    if (cpuAsrSidecarPollTimer) clearInterval(cpuAsrSidecarPollTimer);
    cpuAsrSidecarPollTimer = null;
  }

  async function refreshCpuAsrSidecarStatus() {
    try {
      cpuAsrSidecarStatus.value = await runtimeApi.getCpuAsrSidecarStatus();
    } catch (error: any) {
      cpuAsrSidecarStatus.value = {
        status: 'error', progress: 0, message: '', installed: false, restart_required: false,
        bytes_downloaded: 0, bytes_total: 0, version: '', asset_name: '',
        healthy: false, health_error: '',
        error: error?.response?.data?.detail || error?.message || '無法取得 sidecar 狀態',
      };
    }
    if (!cpuAsrSidecarBusy.value) {
      stopCpuAsrSidecarPolling();
      if (cpuAsrSidecarStatus.value.installed) await store.loadRuntimeStatus();
    }
  }

  async function installCpuAsrSidecar() {
    try {
      cpuAsrSidecarStatus.value = await runtimeApi.installCpuAsrSidecar();
    } catch (error: any) {
      cpuAsrSidecarStatus.value = {
        status: 'error', progress: 0, message: '', installed: false, restart_required: false,
        bytes_downloaded: 0, bytes_total: 0, version: '', asset_name: '',
        healthy: false, health_error: '',
        error: error?.response?.data?.detail || error?.message || '無法啟動 sidecar 安裝',
      };
      return;
    }
    stopCpuAsrSidecarPolling();
    cpuAsrSidecarPollTimer = setInterval(() => void refreshCpuAsrSidecarStatus(), 1000);
  }

  async function cancelCpuAsrSidecarInstall() {
    try {
      cpuAsrSidecarStatus.value = await runtimeApi.cancelCpuAsrSidecarInstall();
    } catch (error: any) {
      cpuAsrSidecarStatus.value = {
        ...(cpuAsrSidecarStatus.value || {
          status: 'error', progress: 0, message: '', installed: false, restart_required: false,
          bytes_downloaded: 0, bytes_total: 0, version: '', asset_name: '', healthy: false, health_error: '',
        }),
        status: 'error', error: error?.response?.data?.detail || error?.message || '無法取消 sidecar 安裝',
      };
    }
  }

  async function importCpuAsrSidecarOffline() {
    const archive = cpuAsrOfflineArchive.value.trim();
    if (!archive) return;
    try {
      cpuAsrSidecarStatus.value = await runtimeApi.importCpuAsrSidecar(archive);
      if (cpuAsrSidecarStatus.value.installed) await store.loadRuntimeStatus();
    } catch (error: any) {
      cpuAsrSidecarStatus.value = {
        ...(cpuAsrSidecarStatus.value || {
          status: 'error', progress: 0, message: '', installed: false, restart_required: false,
          bytes_downloaded: 0, bytes_total: 0, version: '', asset_name: '', healthy: false, health_error: '',
        }),
        status: 'error', error: error?.response?.data?.detail || error?.message || '離線 Runtime 匯入失敗',
      };
    }
  }

  const qwenModelList = computed(() =>
    allQwenModels.filter(modelId => allowedQwen3AsrModels.value.includes(modelId))
  );
  const fasterWhisperModelList = computed(() =>
    allFasterWhisperModels.filter(modelId => allowedFasterWhisperModels.value.includes(modelId))
  );
  const senseVoiceModelList = computed(() =>
    allSenseVoiceModels.filter(modelId => allowedSenseVoiceModels.value.includes(modelId))
  );
  const funAsrModelList = computed(() =>
    allFunAsrModels.filter(modelId => allowedFunAsrModels.value.includes(modelId))
  );
  const parakeetModelList = computed(() =>
    allParakeetModels.filter(modelId => allowedParakeetModels.value.includes(modelId))
  );

  function getModelTask(engine: ModelEngine, modelId: string) {
    return modelDownloadStore.getTask(engine, modelId);
  }

  function canStartDownload(engine: ModelEngine, modelId: string): boolean {
    const task = getModelTask(engine, modelId);
    return !modelDownloadStore.isDownloaded(engine, modelId)
      && task?.status !== 'pending'
      && task?.status !== 'downloading';
  }

  async function startModelDownload(engine: ModelEngine, modelId: string) {
    await modelDownloadStore.startDownload(engine, modelId);
  }

  function getModelStatusText(engine: ModelEngine, modelId: string): string {
    if (modelDownloadStore.isDownloaded(engine, modelId)) return '已下載';
    const task = getModelTask(engine, modelId);
    if (!task) return '尚未下載';
    if (task.status === 'pending') return '等待下載';
    if (task.status === 'downloading') return task.message || '下載中';
    if (task.status === 'completed') return '下載完成';
    if (task.status === 'failed') return task.error || task.message || '下載失敗';
    return task.message || task.status;
  }

  function getModelStatusClass(engine: ModelEngine, modelId: string): string {
    if (modelDownloadStore.isDownloaded(engine, modelId)) return 'text-emerald-300';
    const status = getModelTask(engine, modelId)?.status;
    if (status === 'failed') return 'text-red-300';
    if (status === 'pending' || status === 'downloading') return 'text-blue-300';
    return 'text-white/50';
  }

  async function applyModelStoragePath() {
    await store.saveConfig(localConfig.value);
    await modelDownloadStore.refreshAll();
  }

  async function deleteDownloadedModel(engine: ModelEngine, modelId: string, computeBackend: ModelComputeBackend) {
    if (!confirm(`確定要刪除模型「${modelId}」嗎？之後使用時需要重新下載。`)) return;
    await modelDownloadStore.deleteModel(engine, modelId, computeBackend);
  }


  return {
    modelManagementBackend,
    cpuQwenModels,
    cpuSenseVoiceModels,
    cpuFunAsrModels,
    cpuParakeetModels,
    cpuQwenDescriptions,
    cpuSenseVoiceDescriptions,
    cpuFunAsrDescriptions,
    cpuParakeetDescriptions,
    gpuQwenModels,
    gpuSenseVoiceModels,
    gpuFunAsrModels,
    gpuParakeetModels,
    gpuFasterWhisperModels,
    managedDownloadedModels,
    cpuAsrSidecarStatus,
    cpuAsrOfflineArchive,
    cpuAsrSidecarBusy,
    canInstallCpuAsrSidecar,
    canCancelCpuAsrSidecar,
    stopCpuAsrSidecarPolling,
    refreshCpuAsrSidecarStatus,
    installCpuAsrSidecar,
    cancelCpuAsrSidecarInstall,
    importCpuAsrSidecarOffline,
    qwenModelList,
    fasterWhisperModelList,
    senseVoiceModelList,
    funAsrModelList,
    parakeetModelList,
    getModelTask,
    canStartDownload,
    startModelDownload,
    getModelStatusText,
    getModelStatusClass,
    applyModelStoragePath,
    deleteDownloadedModel,
  };
}
