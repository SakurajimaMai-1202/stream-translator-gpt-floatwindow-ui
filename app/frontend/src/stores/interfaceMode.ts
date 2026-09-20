import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { configApi, runtimeApi, type CpuAsrSidecarInstallStatus } from '../services/api';
import { useModelDownloadStore } from './modelDownload';

const STARTER_MODELS = [
  { engine: 'sensevoice' as const, id: 'iic/SenseVoiceSmall', label: 'SenseVoice Small（中文）' },
  { engine: 'parakeet-ctc-ja' as const, id: 'nvidia/parakeet-tdt_ctc-0.6b-ja', label: 'Parakeet 0.6B（日文）' },
  { engine: 'parakeet-ctc-ja' as const, id: 'nvidia/parakeet-tdt-0.6b-v3', label: 'Parakeet v3（25 語言）' },
];

export const useInterfaceModeStore = defineStore('interfaceMode', () => {
  const mode = ref<'simple' | 'advanced' | null>(null);
  const loaded = ref(false);
  const busy = ref(false);
  const error = ref('');
  const pendingMode = ref<'simple' | 'advanced' | null>(null);
  const setupMessage = ref('');
  const sidecarStatus = ref<CpuAsrSidecarInstallStatus | null>(null);
  const isSimple = computed(() => mode.value === 'simple');
  const downloads = useModelDownloadStore();
  const preparingModels = ref(false);
  const modelProgress = computed(() => STARTER_MODELS.map(model => {
    const task = downloads.getTask(model.engine, model.id, 'cpu');
    const ready = downloads.isDownloaded(model.engine, model.id, 'cpu');
    return { ...model, ready, progress: ready ? 1 : downloads.displayProgress(task), message: ready ? '已就緒' : task?.error || task?.message || '等待下載' };
  }));

  async function prepareModels() {
    preparingModels.value = true;
    for (const [index, model] of STARTER_MODELS.entries()) {
      setupMessage.value = `正在準備 ASR 模型 ${index + 1}/${STARTER_MODELS.length}：${model.label}`;
      await downloads.ensureDownloaded(model.engine, model.id, 'cpu');
      if (!downloads.isDownloaded(model.engine, model.id, 'cpu')) throw new Error(`${model.label} 下載後未通過檔案檢查，請重試。`);
    }
  }

  async function prepareCpuAsr() {
    setupMessage.value = '正在檢查 CPU 語音辨識環境…';
    sidecarStatus.value = null;
    const runtime = await runtimeApi.getStatus();
    if (runtime.cpu_asr_runtime.available && !runtime.cpu_asr_runtime.is_sidecar) return;
    let status = await runtimeApi.getCpuAsrSidecarStatus();
    if (status.healthy && !status.restart_required) return;
    const active = ['starting', 'downloading', 'verifying', 'installing'];
    if (!status.healthy && !active.includes(status.status)) status = await runtimeApi.installCpuAsrSidecar();
    setupMessage.value = '正在準備 CPU 語音辨識環境，請保持程式開啟…';
    while (true) {
      sidecarStatus.value = status;
      if (status.healthy && !active.includes(status.status)) return;
      if (!active.includes(status.status)) throw new Error(status.error || status.health_error || 'CPU 語音辨識環境未準備完成，請重試。');
      await new Promise(resolve => setTimeout(resolve, 1000));
      status = await runtimeApi.getCpuAsrSidecarStatus();
    }
  }

  async function load() {
    error.value = '';
    busy.value = true;
    try {
      const config = await configApi.getConfig(true);
      const saved = config.interface?.mode;
      mode.value = saved === 'simple' || saved === 'advanced' ? saved : null;
      loaded.value = true;
    } catch {
      error.value = '無法讀取介面設定，請重試。';
    } finally {
      busy.value = false;
    }
  }

  async function select(value: 'simple' | 'advanced') {
    if (busy.value) return;
    if (mode.value === value && !pendingMode.value) return;
    busy.value = true;
    error.value = '';
    preparingModels.value = false;
    try {
      if (!mode.value || pendingMode.value) {
        pendingMode.value = value;
        await prepareCpuAsr();
        await prepareModels();
        if (sidecarStatus.value?.restart_required) throw new Error('CPU 環境與三個 ASR 模型已準備完成，請重新啟動程式。');
      }
      setupMessage.value = '正在儲存選擇…';
      await configApi.updateSection('interface', { mode: value });
      mode.value = value;
      pendingMode.value = null;
      sidecarStatus.value = null;
    } catch (cause: any) {
      error.value = cause?.response?.data?.detail || cause?.message || '介面模式或環境準備失敗，請重試。';
    } finally {
      busy.value = false;
    }
  }

  return { mode, loaded, busy, error, isSimple, pendingMode, setupMessage, sidecarStatus, preparingModels, modelProgress, load, select };
});
