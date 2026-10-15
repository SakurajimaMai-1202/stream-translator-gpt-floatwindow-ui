import { computed, getCurrentScope, onScopeDispose, ref, type Ref } from 'vue';
import { configApi } from '../services/api';
import { llamaApi, type ModelInstallStatus, type RuntimeInstallStatus, type TranslationModelRecommendationInfo } from '../services/llamaApi';

export const isRuntimeInstallBusy = (status: RuntimeInstallStatus | null) =>
  !!status && !['idle', 'completed', 'error'].includes(status.state);
export const isModelInstallBusy = (status: ModelInstallStatus | null) =>
  !!status && ['resolving', 'downloading', 'verifying'].includes(status.state);

export async function cancelModelInstallWithRetry(jobId?: string) {
  let cancelled: ModelInstallStatus;
  try {
    cancelled = await llamaApi.cancelModelInstall(jobId);
  } catch (cause: any) {
    if (cause?.response?.status === 409) return await llamaApi.getSimpleModelInstallStatus();
    throw cause;
  }
  const status = await llamaApi.getSimpleModelInstallStatus();
  const trackedId = jobId || cancelled.job_id;
  return isModelInstallBusy(status) && status.job_id === trackedId
    ? await llamaApi.cancelModelInstall(trackedId) : status;
}

export function useLocalTranslationSetup(setupMessage: Ref<string> = ref('')) {
  const runtimeInstallStatus = ref<RuntimeInstallStatus | null>(null);
  const localModelInstallStatus = ref<ModelInstallStatus | null>(null);
  const running = ref(false);
  const cancelled = ref(false);
  const runtimeBackgroundBusy = ref(false);
  let disposed = false;
  let runtimeTimer: ReturnType<typeof setTimeout> | undefined;
  // Also used from a Pinia store, where there is no component instance but there is an effect scope.
  if (getCurrentScope()) onScopeDispose(() => { disposed = true; if (runtimeTimer) clearTimeout(runtimeTimer); });
  async function pollBackgroundRuntime() {
    if (disposed) return;
    try {
      const status = await llamaApi.getRuntimeInstallStatus();
      runtimeInstallStatus.value = status;
      runtimeBackgroundBusy.value = isRuntimeInstallBusy(status);
    } catch { /* Keep locked and retry if status is unavailable. */ }
    if (!disposed && runtimeBackgroundBusy.value) runtimeTimer = setTimeout(pollBackgroundRuntime, 2000);
  }
  const phase = ref<'runtime' | 'model' | 'saving' | ''>('');
  const progress = computed(() => Math.round(Math.min(1, Math.max(0,
    (phase.value === 'model' ? localModelInstallStatus.value?.progress : runtimeInstallStatus.value?.progress) || 0)) * 100));
  function checkCancelled() {
    if (disposed || cancelled.value) throw new Error(setupMessage.value);
  }
  async function cancel() {
    if (!running.value || phase.value === 'saving') return;
    const cancellingModel = phase.value === 'model';
    cancelled.value = true;
    setupMessage.value = phase.value === 'runtime'
      ? '翻譯引擎仍在背景安裝，完成後可再按「開始設定」。'
      : '已取消設定。';
    if (phase.value === 'runtime') runtimeBackgroundBusy.value = true;
    // If the install request is still pending, run() cancels its returned job ID.
    if (cancellingModel && localModelInstallStatus.value?.job_id) {
      localModelInstallStatus.value = await cancelModelInstallWithRetry(localModelInstallStatus.value.job_id);
      if (isModelInstallBusy(localModelInstallStatus.value)) {
        cancelled.value = false;
        throw new Error("??????????????????");
      }
    }
  }
  async function waitForRuntime() {
    for (let index = 0; index < 3600; index++) {
      checkCancelled();
      const status = await llamaApi.getRuntimeInstallStatus();
      checkCancelled();
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
      checkCancelled();
      const status = await llamaApi.getSimpleModelInstallStatus();
      checkCancelled();
      localModelInstallStatus.value = status;
      if (status.state === 'cancelled') throw new Error('已取消設定。');
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

  async function run(hardware: TranslationModelRecommendationInfo | null, existing?: {
    runtime: RuntimeInstallStatus; model: ModelInstallStatus;
  }) {
    if (running.value || runtimeBackgroundBusy.value || disposed) return;
    const setup = hardware?.simple_setup;
    if (!existing && !setup?.supported) throw new Error(setup?.reason || '這台電腦不適合自動設定本機翻譯，請選擇雲端翻譯。');
    running.value = true;
    cancelled.value = false;
    phase.value = 'runtime';
    runtimeInstallStatus.value = null;
    localModelInstallStatus.value = null;
    try {
      const runtime = existing?.runtime ?? await llamaApi.getRuntimeInstallStatus();
      checkCancelled();
      runtimeInstallStatus.value = runtime;
      const attachingModel = isModelInstallBusy(existing?.model ?? null);
      if (attachingModel) localModelInstallStatus.value = existing!.model;
      if (isRuntimeInstallBusy(runtime)) {
        phase.value = 'runtime';
        await waitForRuntime();
      } else if (!attachingModel) {
        phase.value = 'runtime';
        setupMessage.value = '正在選擇適合這台電腦的 llama.cpp…';
        const release = await llamaApi.getRuntimeReleases();
        const variant = release.recommended_variant;
        if (!variant) throw new Error('無法判斷這台電腦適用的 llama.cpp Runtime。');
        if (variant === 'cpu') throw new Error('簡單模式不使用 CPU llama.cpp Runtime，請選擇 Gemini 或到進階模式手動設定。');
        const selected = release.variants.find(item => item.id === variant);
        if (!selected?.installable) throw new Error(selected?.compatibility_error || '找不到可安裝的 llama.cpp Runtime。');
        if (!(release.is_latest && release.installed_variant === variant)) {
          checkCancelled();
          await llamaApi.installRuntime(variant);
          await waitForRuntime();
        }
      }
      checkCancelled();
      phase.value = 'model';
      if (!attachingModel) {
        if (!setup?.supported) throw new Error(setup?.reason || '無法取得本機翻譯模型設定，請重新偵測。');
        setupMessage.value = `正在下載 ${setup.quant} 翻譯模型…`;
        const job = await llamaApi.installSimpleModel(setup.model_id);
        localModelInstallStatus.value = { job_id: job.job_id, state: 'resolving' } as ModelInstallStatus;
        if (cancelled.value) {
          localModelInstallStatus.value = await cancelModelInstallWithRetry(job.job_id);
          if (isModelInstallBusy(localModelInstallStatus.value)) {
            cancelled.value = false;
            throw new Error("??????????????????");
          }
        }
      }
      checkCancelled();
      const modelPath = await waitForLocalModel();
      checkCancelled();
      phase.value = 'saving';
      const port = await llamaApi.getAvailablePort(8081);
      await configApi.updateSection('llama', {
        local_llm_enabled: false, model_dir: modelPath.replace(/[\\/][^\\/]+$/, ''), model_path: modelPath,
        host: '127.0.0.1', port, n_ctx: 4096, n_gpu_layers: 999, n_threads: 4, n_parallel: 1,
        temp: 0.7, top_p: 0.6, top_k: 20, repeat_penalty: 1.05, n_predict: 4096,
        model_profile_id: 'hy-mt2-7b',
        flash_attn: 'auto', no_mmap: false,
      });
      await configApi.updateSection('translation', { backend: 'llama' });
      // 首次導引只安裝並設定 Runtime/模型。模型服務由使用者進入首頁後
      // 透過「本地 LLM 翻譯」開關啟動，避免完成下載便立刻占用 VRAM。
      setupMessage.value = `本機翻譯已準備完成（預設連接埠 ${port}），進入首頁後可手動啟動。`;
    } finally {
      running.value = false;
      if (runtimeBackgroundBusy.value && !disposed) runtimeTimer = setTimeout(pollBackgroundRuntime, 2000);
    }
  }
  async function restore(hardware: TranslationModelRecommendationInfo | null) {
    const [runtime, model] = await Promise.all([
      llamaApi.getRuntimeInstallStatus(), llamaApi.getSimpleModelInstallStatus(),
    ]);
    if (disposed || (!isRuntimeInstallBusy(runtime) && !isModelInstallBusy(model))) return false;
    // A download started on the advanced page is a different model; finishing it here
    // would write the simple-setup profile for the wrong file.
    if (isModelInstallBusy(model) && model.model_id !== hardware?.simple_setup?.model_id) {
      setupMessage.value = '另一個翻譯模型正在下載，完成後再按「開始設定」。';
      return false;
    }
    await run(hardware, { runtime, model });
    return !cancelled.value;
  }
  return { runtimeBackgroundBusy, restore, setupMessage, runtimeInstallStatus, localModelInstallStatus, running, cancelled, phase, progress, run, cancel };
}
