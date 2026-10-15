import { isModelInstallBusy, isRuntimeInstallBusy, useLocalTranslationSetup } from '../composables/useLocalTranslationSetup';
import { computed, onScopeDispose, ref, watch } from 'vue';
import { defineStore } from 'pinia';
import { configApi, modelApi, runtimeApi, translationApi, type CpuAsrSidecarInstallStatus } from '../services/api';
import { useModelDownloadStore } from './modelDownload';
import { llamaApi, type TranslationModelRecommendationInfo } from '../services/llamaApi';
import { normalizeAsrLanguage } from '../utils/asrCapabilities';
import { simpleAsrModel } from '../utils/simpleAsr';

function starterModel(language: string) {
  const id = simpleAsrModel(language);
  if (!id) return null;
  return id === 'iic/SenseVoiceSmall'
    ? { engine: 'sensevoice' as const, id, label: '中文語音辨識' }
    : { engine: 'parakeet-ctc-ja' as const, id, label: normalizeAsrLanguage(language) === 'ja' ? '日文語音辨識' : '多語言語音辨識' };
}

export const useInterfaceModeStore = defineStore('interfaceMode', () => {
  const mode = ref<'simple' | 'advanced' | null>(null);
  const loaded = ref(false);
  const busy = ref(false);
  const localViewJobBusy = ref(false);
  const error = ref('');
  const pendingMode = ref<'simple' | 'advanced' | null>(null);
  const setupMessage = ref('');
  const sidecarStatus = ref<CpuAsrSidecarInstallStatus | null>(null);
  const isSimple = computed(() => mode.value === 'simple');
  const downloads = useModelDownloadStore();
  const preparingModels = ref(false);
  const onboardingStep = ref<'mode' | 'purpose' | 'translation' | 'local' | 'preparing'>('mode');
  const selectedSource = ref<'url' | 'file' | 'system_audio' | 'microphone' | 'process_audio'>('system_audio');
  const selectedLanguage = ref('ja');
  const translationChoice = ref<'local' | 'cloud' | null>(null);
  const googleApiKey = ref('');
  const hardware = ref<TranslationModelRecommendationInfo | null>(null);
  const localSetup = useLocalTranslationSetup(setupMessage);
  const { runtimeInstallStatus, localModelInstallStatus } = localSetup;
  // Local-translation jobs (runtime install, GGUF download) lock the 本地翻譯 page;
  // ASR model downloads additionally lock only the mode switch.
  const localTranslationJobBusy = computed(() => localViewJobBusy.value || localSetup.running.value
    || isRuntimeInstallBusy(runtimeInstallStatus.value)
    || localSetup.runtimeBackgroundBusy.value
    || isModelInstallBusy(localModelInstallStatus.value));
  const localJobBusy = computed(() => localTranslationJobBusy.value || downloads.activeTasks.length > 0);
  let statusTimer: ReturnType<typeof setTimeout> | undefined;
  let polling = false;
  let disposed = false;
  function schedulePoll() {
    if (statusTimer) clearTimeout(statusTimer);
    statusTimer = undefined;
    // An in-flight poll reschedules itself when it finishes; never run two loops.
    if (!disposed && !polling && localTranslationJobBusy.value) statusTimer = setTimeout(pollLocalJobs, 2000);
  }
  async function pollLocalJobs() {
    statusTimer = undefined;
    polling = true;
    try {
      const results = await Promise.allSettled([
        llamaApi.getRuntimeInstallStatus(), llamaApi.getSimpleModelInstallStatus(),
      ]);
      if (disposed) return;
      if (results[0].status === 'fulfilled') {
        runtimeInstallStatus.value = results[0].value;
        localSetup.runtimeBackgroundBusy.value = isRuntimeInstallBusy(results[0].value);
      }
      if (results[1].status === 'fulfilled') localModelInstallStatus.value = results[1].value;
    } finally {
      polling = false;
    }
    schedulePoll();
  }
  watch(localTranslationJobBusy, schedulePoll, { flush: 'sync' });
  onScopeDispose(() => { disposed = true; if (statusTimer) clearTimeout(statusTimer); });
  const existingAsrStoragePath = ref('');
  const existingLlamaServerExe = ref('');
  const existingLlamaModelPath = ref('');
  const offlineCpuAsrArchive = ref('');
  const selectedStarterModel = computed(() => starterModel(selectedLanguage.value));
  const modelProgress = computed(() => selectedStarterModel.value ? [selectedStarterModel.value].map(model => {
    const task = downloads.getTask(model.engine, model.id, 'cpu');
    const ready = downloads.isDownloaded(model.engine, model.id, 'cpu');
    return { ...model, ready, progress: ready ? 1 : downloads.displayProgress(task), message: ready ? '已就緒' : task?.error || task?.message || '等待下載' };
  }) : []);

  async function prepareModels() {
    preparingModels.value = true;
    const model = selectedStarterModel.value;
    if (!model) throw new Error('這個語言沒有簡單模式的 CPU 辨識模型，請改用進階模式。');
    setupMessage.value = `正在準備唯一需要的資源：${model.label}`;
    await downloads.ensureDownloaded(model.engine, model.id, 'cpu');
    if (!downloads.isDownloaded(model.engine, model.id, 'cpu')) throw new Error(`${model.label} 下載後未通過檔案檢查，請重試。`);
  }

  async function cancelPreparation() {
    const active = downloads.activeTasks.slice();
    await Promise.all(active.map(task => downloads.cancelTask(task.task_id)));
    preparingModels.value = false;
    busy.value = false;
    setupMessage.value = '已取消模型下載；已完成的設定未變更。';
    error.value = '準備流程已取消，可重新選擇或稍後設定。';
    onboardingStep.value = 'translation';
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

  async function setSimpleModeDefaults() {
    const config = await configApi.getConfig(true);
    const model = selectedStarterModel.value;
    if (!model) throw new Error('所選語言無法使用簡單模式。');
    await configApi.updateSection('transcription', {
      language: selectedLanguage.value, backend: model.engine, asr_compute_backend: 'cpu',
      model: model.id,
      ...(model.engine === 'sensevoice' ? { sensevoice_model: model.id } : { nemo_asr_model: model.id }),
    });
    await configApi.updateSection('input', { ...(config.input || {}), audio_source: selectedSource.value });
    if (!config.translation?.target_language) {
      await configApi.updateSection('translation', { target_language: 'Traditional Chinese' });
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
    if (busy.value || localJobBusy.value) return;
    if (mode.value === value && !pendingMode.value) return;
    busy.value = true;
    error.value = '';
    preparingModels.value = false;
    try {
      if (!mode.value && value === 'advanced' && !pendingMode.value) {
        setupMessage.value = '正在開啟進階模式…';
        await configApi.updateSection('interface', { mode: 'advanced' });
        mode.value = 'advanced';
        return;
      }
      if (!mode.value && value === 'simple' && !pendingMode.value) {
        pendingMode.value = value;
        onboardingStep.value = 'purpose';
        return;
      }
      if (!mode.value || pendingMode.value) {
        pendingMode.value = value;
        await prepareCpuAsr();
        await prepareModels();
        if (sidecarStatus.value?.restart_required) throw new Error('CPU 環境與三個 ASR 模型已準備完成，請重新啟動程式。');
        if (value === 'simple') await setSimpleModeDefaults();
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

  async function continueFromPurpose() {
    if (busy.value || !selectedStarterModel.value) return;
    busy.value = true;
    error.value = '';
    try {
      setupMessage.value = '正在偵測這台電腦可用的翻譯方式…';
      hardware.value = await llamaApi.getModelRecommendations(true);
      onboardingStep.value = 'translation';
    } catch (cause: any) {
      error.value = cause?.response?.data?.detail || cause?.message || '無法取得翻譯方式資訊。';
    } finally { busy.value = false; }
  }

  async function skipSetup() {
    if (busy.value) return;
    busy.value = true;
    error.value = '';
    try {
      await configApi.updateSection('interface', { mode: 'advanced' });
      mode.value = 'advanced';
      pendingMode.value = null;
      onboardingStep.value = 'mode';
    } catch (cause: any) {
      error.value = cause?.response?.data?.detail || cause?.message || '無法保存稍後設定狀態。';
    } finally { busy.value = false; }
  }

  function openExistingResources() {
    if (busy.value) return;
    pendingMode.value = 'advanced';
    onboardingStep.value = 'local';
    error.value = '';
  }

  async function configureExistingResources() {
    if (busy.value) return;
    busy.value = true;
    error.value = '';
    try {
      const asrPath = existingAsrStoragePath.value.trim();
      const serverExe = existingLlamaServerExe.value.trim();
      const modelPath = existingLlamaModelPath.value.trim();
      const sidecarArchive = offlineCpuAsrArchive.value.trim();
      const validatedAsr = asrPath ? await modelApi.validateStorage(asrPath) : null;
      const validatedRuntime = serverExe ? await llamaApi.validateRuntime(serverExe) : null;
      const validatedModel = modelPath ? await llamaApi.validateModel(modelPath) : null;
      if (sidecarArchive) {
        setupMessage.value = '正在匯入離線 CPU ASR Runtime…';
        const status = await runtimeApi.importCpuAsrSidecar(sidecarArchive);
        sidecarStatus.value = status;
        if (!status.healthy) throw new Error(status.error || status.health_error || '離線 CPU ASR Runtime 驗證失敗。');
      }
      if (validatedAsr) await configApi.updateSection('models', { storage_path: validatedAsr.path });
      if (serverExe || modelPath) {
        const config = await configApi.getConfig(true);
        await configApi.updateSection('llama', {
          ...(config.llama || {}),
          server_exe: validatedRuntime?.path || '',
          model_path: validatedModel?.path || '',
          model_dir: validatedModel ? validatedModel.path.replace(/[\\/][^\\/]+$/, '') : (config.llama?.model_dir || ''),
          local_llm_enabled: false,
        });
      }
      await configApi.updateSection('interface', { mode: 'advanced' });
      mode.value = 'advanced';
      pendingMode.value = null;
      onboardingStep.value = 'mode';
    } catch (cause: any) {
      error.value = cause?.response?.data?.detail || cause?.message || '本機資源設定失敗。';
    } finally { busy.value = false; }
  }

  async function finishSimpleMode() {
    setupMessage.value = '正在準備 CPU 語音辨識…';
    await prepareCpuAsr();
    await prepareModels();
    if (sidecarStatus.value?.restart_required) throw new Error('環境已準備完成，請重新啟動程式後繼續。');
    await setSimpleModeDefaults();
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
      await localSetup.run(hardware.value);
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

  return { mode, loaded, busy, localJobBusy, localTranslationJobBusy, localViewJobBusy, error, isSimple, pendingMode, setupMessage, sidecarStatus, preparingModels,
    modelProgress, onboardingStep, selectedSource, selectedLanguage, selectedStarterModel,
    translationChoice, googleApiKey, hardware, runtimeInstallStatus,
    localModelInstallStatus, existingAsrStoragePath, existingLlamaServerExe, existingLlamaModelPath,
    offlineCpuAsrArchive, load, select, continueFromPurpose, configureCloud, configureLocal, cancelPreparation, backToModeChoice,
    skipSetup, openExistingResources, configureExistingResources };
});
