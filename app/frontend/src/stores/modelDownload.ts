import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { modelApi, type DownloadedModelInfo, type ModelDownloadTask, type ModelEngine, type ModelComputeBackend, type ModelStorageInfo } from '../services/api';

const POLL_INTERVAL_MS = 1500;

export const useModelDownloadStore = defineStore('modelDownload', () => {
  const tasks = ref<ModelDownloadTask[]>([]);
  const downloadedModels = ref<DownloadedModelInfo[]>([]);
  const storageInfo = ref<ModelStorageInfo | null>(null);
  const isLoading = ref(false);
  const errorMessage = ref('');
  const successMessage = ref('');

  const activeTasks = computed(() =>
    tasks.value.filter((task) => task.status === 'pending' || task.status === 'downloading')
  );

  const taskMap = computed(() => {
    return tasks.value.reduce<Record<string, ModelDownloadTask>>((acc, task) => {
      acc[`${task.compute_backend}:${task.engine}:${task.model_id}`] = task;
      return acc;
    }, {});
  });

  let pollTimer: number | null = null;

  function clearMessages() {
    errorMessage.value = '';
    successMessage.value = '';
  }

  async function loadTasks() {
    const result = await modelApi.getTasks();
    const nextTasks = result.tasks || [];
    if (JSON.stringify(tasks.value) !== JSON.stringify(nextTasks)) {
      tasks.value = nextTasks;
    }
  }

  async function loadDownloadedModels() {
    const result = await modelApi.getDownloadedModels();
    const nextModels = result.models || [];
    if (JSON.stringify(downloadedModels.value) !== JSON.stringify(nextModels)) {
      downloadedModels.value = nextModels;
    }
  }

  async function loadStorage() {
    const result = await modelApi.getStorage();
    if (JSON.stringify(storageInfo.value) !== JSON.stringify(result.storage)) {
      storageInfo.value = result.storage;
    }
  }

  async function refreshAll() {
    isLoading.value = true;
    errorMessage.value = '';
    try {
      await Promise.all([loadTasks(), loadDownloadedModels(), loadStorage()]);
    } catch (error: any) {
      errorMessage.value = `載入模型資訊失敗: ${error?.message || error}`;
    } finally {
      isLoading.value = false;
    }
  }

  async function startDownload(engine: ModelEngine, modelId: string, computeBackend: ModelComputeBackend = 'gpu') {
    clearMessages();
    try {
      const existing = taskMap.value[`${computeBackend}:${engine}:${modelId}`];
      if (existing && (existing.status === 'pending' || existing.status === 'downloading')) {
        successMessage.value = '此模型已在下載中';
        return existing.task_id;
      }

      const response = await modelApi.startDownload({
        engine,
        model_id: modelId,
        compute_backend: computeBackend,
      });

      successMessage.value = response.message || '下載任務已啟動';
      await loadTasks();
      startPolling();
      return response.task_id;
    } catch (error: any) {
      errorMessage.value = `啟動下載失敗: ${error?.response?.data?.detail || error?.message || error}`;
      throw error;
    }
  }

  async function ensureDownloaded(engine: ModelEngine, modelId: string, computeBackend: ModelComputeBackend = 'gpu') {
    await loadDownloadedModels();
    if (isDownloaded(engine, modelId, computeBackend)) return;

    const taskId = await startDownload(engine, modelId, computeBackend);
    if (!taskId) throw new Error('無法建立模型下載任務');

    while (true) {
      await loadTasks();
      const task = tasks.value.find((item) => item.task_id === taskId);
      if (!task) throw new Error('找不到模型下載任務');
      if (task.status === 'completed') {
        await loadDownloadedModels();
        successMessage.value = `模型下載完成：${modelId}`;
        return;
      }
      if (task.status === 'failed') {
        throw new Error(task.error || task.message || '模型下載失敗');
      }
      await new Promise(resolve => window.setTimeout(resolve, POLL_INTERVAL_MS));
    }
  }

  async function openStorage() {
    clearMessages();
    try {
      const response = await modelApi.openStorage();
      successMessage.value = response.message;
    } catch (error: any) {
      errorMessage.value = `開啟資料夾失敗: ${error?.response?.data?.detail || error?.message || error}`;
    }
  }

  async function deleteModel(engine: ModelEngine, modelId: string, computeBackend: ModelComputeBackend = 'gpu') {
    clearMessages();
    try {
      const response = await modelApi.deleteModel(engine, modelId, computeBackend);
      successMessage.value = response.message;
      await loadDownloadedModels();
    } catch (error: any) {
      errorMessage.value = `刪除模型失敗: ${error?.response?.data?.detail || error?.message || error}`;
    }
  }

  async function pollOnce() {
    try {
      await loadTasks();

      const hasActive = activeTasks.value.length > 0;
      if (!hasActive) {
        await loadDownloadedModels();
        stopPolling();
      }
    } catch (error: any) {
      errorMessage.value = `輪詢任務失敗: ${error?.message || error}`;
      stopPolling();
    }
  }

  function startPolling() {
    if (pollTimer !== null) return;

    pollTimer = window.setInterval(() => {
      pollOnce();
    }, POLL_INTERVAL_MS);
  }

  function stopPolling() {
    if (pollTimer !== null) {
      window.clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function getTask(engine: ModelEngine, modelId: string, computeBackend: ModelComputeBackend = 'gpu'): ModelDownloadTask | undefined {
    return taskMap.value[`${computeBackend}:${engine}:${modelId}`];
  }

  function isDownloaded(engine: ModelEngine, modelId: string, computeBackend: ModelComputeBackend = 'gpu'): boolean {
    return downloadedModels.value.some((item) =>
      item.compute_backend === computeBackend && item.engine === engine && item.model_id === modelId
    );
  }

  function formatSize(sizeBytes: number): string {
    if (!sizeBytes || sizeBytes <= 0) return '未知大小';
    const kb = 1024;
    const mb = kb * 1024;
    const gb = mb * 1024;
    if (sizeBytes >= gb) return `${(sizeBytes / gb).toFixed(2)} GB`;
    if (sizeBytes >= mb) return `${(sizeBytes / mb).toFixed(2)} MB`;
    if (sizeBytes >= kb) return `${(sizeBytes / kb).toFixed(2)} KB`;
    return `${sizeBytes} B`;
  }

  return {
    tasks,
    downloadedModels,
    storageInfo,
    activeTasks,
    isLoading,
    errorMessage,
    successMessage,
    refreshAll,
    startDownload,
    ensureDownloaded,
    openStorage,
    deleteModel,
    pollOnce,
    startPolling,
    stopPolling,
    getTask,
    isDownloaded,
    formatSize,
    clearMessages
  };
});
