import { computed, ref } from 'vue';
import { defineStore } from 'pinia';
import { configApi, runtimeApi, translationApi, type CpuAsrSidecarInstallStatus } from '../services/api';
import { useModelDownloadStore } from './modelDownload';
import { llamaApi, type ModelInstallStatus, type RuntimeInstallStatus, type TranslationModelRecommendationInfo } from '../services/llamaApi';
import { useLlamaStore } from './llama';

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
  const onboardingStep = ref<'mode' | 'translation' | 'preparing'>('mode');
  const translationChoice = ref<'local' | 'cloud' | null>(null);
  const googleApiKey = ref('');
  const hardware = ref<TranslationModelRecommendationInfo | null>(null);
  const runtimeInstallStatus = ref<RuntimeInstallStatus | null>(null);
  const localModelInstallStatus = ref<ModelInstallStatus | null>(null);
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
      onboardingStep.value = mode.value ? 'mode' : 'mode';
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
      if (!mode.value && value === 'simple' && !pendingMode.value) {
        pendingMode.value = value;
        onboardingStep.value = 'translation';
        setupMessage.value = '正在偵測顯示卡與顯存…';
        hardware.value = await llamaApi.getModelRecommendations(true);
        return;
      }
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
      onboardingStep.value = 'mode';
      sidecarStatus.value = null;
    } catch (cause: any) {
      error.value = cause?.response?.data?.detail || cause?.message || '介面模式或環境準備失敗，請重試。';
    } finally {
      busy.value = false;
    }
  }

  async function waitForRuntime() {
    for (let index = 0; index < 3600; index++) {
      const status = await llamaApi.getRuntimeInstallStatus();
      runtimeInstallStatus.value = status;
      setupMessage.value = status.message || '正在準備本機翻譯引擎…';
      if (status.state === 'completed') return;
      if (status.state === 'error') throw new Error(status.error || 'llama.cpp 安裝失敗');
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    throw new Error('llama.cpp 安裝逾時，請重試。');
  }

  async function waitForLocalModel(): Promise<string> {
    for (let index = 0; index < 10800; index++) {
      const status = await llamaApi.getSimpleModelInstallStatus();
      localModelInstallStatus.value = status;
      setupMessage.value = status.message || '正在下載本機翻譯模型…';
      if (status.state === 'completed') {
        if (!status.path) throw new Error('翻譯模型安裝完成，但找不到模型檔案。');
        return status.path;
      }
      if (status.state === 'error') throw new Error(status.error || '翻譯模型下載失敗');
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    throw new Error('翻譯模型下載逾時，請重試。');
  }

  async function finishSimpleMode() {
    setupMessage.value = '正在準備 CPU 語音辨識…';
    await prepareCpuAsr();
    await prepareModels();
    if (sidecarStatus.value?.restart_required) throw new Error('環境已準備完成，請重新啟動程式後繼續。');
    await configApi.updateSection('interface', { mode: 'simple' });
    mode.value = 'simple';
    pendingMode.value = null;
    onboardingStep.value = 'mode';
    sidecarStatus.value = null;
  }

  async function configureCloud() {
    if (!googleApiKey.value.trim()) {
      error.value = '請先貼上 Google AI Studio API Key。';
      return;
    }
    busy.value = true;
    error.value = '';
    onboardingStep.value = 'preparing';
    translationChoice.value = 'cloud';
    try {
      setupMessage.value = '正在儲存 Gemini 翻譯設定…';
      await translationApi.testGemini(googleApiKey.value.trim());
      await configApi.updateSection('translation', {
        backend: 'gemini', google_api_key: googleApiKey.value.trim(), gemini_model: 'gemini-2.5-flash-lite',
      });
      await finishSimpleMode();
    } catch (cause: any) {
      error.value = cause?.response?.data?.detail || cause?.message || 'Gemini 設定失敗，請重試。';
      onboardingStep.value = 'translation';
    } finally { busy.value = false; }
  }

  async function configureLocal() {
    const setup = hardware.value?.simple_setup;
    if (!setup?.supported) {
      error.value = setup?.reason || '這台電腦不適合自動設定本機翻譯，請選擇雲端翻譯。';
      return;
    }
    busy.value = true;
    error.value = '';
    onboardingStep.value = 'preparing';
    translationChoice.value = 'local';
    try {
      setupMessage.value = '正在選擇適合這台電腦的 llama.cpp…';
      const release = await llamaApi.getRuntimeReleases();
      const variant = release.recommended_variant;
      if (!variant) throw new Error('無法判斷這台電腦適用的 llama.cpp Runtime。');
      const selected = release.variants.find(item => item.id === variant);
      if (!selected?.installable) throw new Error(selected?.compatibility_error || '找不到可安裝的 llama.cpp Runtime。');
      if (!(release.is_latest && release.installed_variant === variant)) {
        await llamaApi.installRuntime(variant);
        await waitForRuntime();
      }
      setupMessage.value = `正在下載 ${setup.quant} 翻譯模型…`;
      await llamaApi.installSimpleModel(setup.model_id);
      const modelPath = await waitForLocalModel();
      const port = await llamaApi.getAvailablePort(8080);
      await configApi.updateSection('llama', {
        local_llm_enabled: false, model_dir: modelPath.replace(/[\\/][^\\/]+$/, ''), model_path: modelPath,
        host: '127.0.0.1', port, n_ctx: 4096, n_gpu_layers: 999, n_threads: 4, n_parallel: 1,
        temp: 0.7, top_p: 0.6, top_k: 20, repeat_penalty: 1.05, n_predict: 4096,
        flash_attn: 'auto', no_mmap: false,
      });
      await configApi.updateSection('translation', { backend: 'llama' });
      setupMessage.value = `正在啟動本機翻譯服務（連接埠 ${port}）…`;
      await llamaApi.startServer({
        model_path: modelPath, host: '127.0.0.1', port, n_ctx: 4096, n_gpu_layers: 999,
        n_threads: 4, n_parallel: 1, temp: 0.7, top_p: 0.6, top_k: 20,
        repeat_penalty: 1.05, n_predict: 4096, flash_attn: 'auto', no_mmap: false,
      });
      for (let index = 0; index < 180; index++) {
        const status = await llamaApi.getServerStatus();
        if (status.is_ready) break;
        if (!status.is_running) throw new Error(status.last_error || '本機翻譯模型無法啟動。');
        if (index === 179) throw new Error('本機翻譯模型載入逾時。');
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      // 使用者在本次導引中明確選擇並啟動本機模型，因此只開啟本次工作階段。
      await useLlamaStore().setLocalLlmEnabled(true);
      await finishSimpleMode();
    } catch (cause: any) {
      error.value = cause?.response?.data?.detail || cause?.message || '本機翻譯設定失敗，請重試。';
      onboardingStep.value = 'translation';
    } finally { busy.value = false; }
  }

  function backToModeChoice() {
    if (busy.value) return;
    pendingMode.value = null;
    onboardingStep.value = 'mode';
    translationChoice.value = null;
    error.value = '';
  }

  return { mode, loaded, busy, error, isSimple, pendingMode, setupMessage, sidecarStatus, preparingModels,
    modelProgress, onboardingStep, translationChoice, googleApiKey, hardware, runtimeInstallStatus,
    localModelInstallStatus, load, select, configureCloud, configureLocal, backToModeChoice };
});
