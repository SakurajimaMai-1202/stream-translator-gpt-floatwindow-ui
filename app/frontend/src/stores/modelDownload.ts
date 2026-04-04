import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { modelApi, type DownloadedModelInfo, type ModelDownloadTask, type ModelEngine } from '../services/api';

const POLL_INTERVAL_MS = 1500;

export const useModelDownloadStore = defineStore('modelDownload', () => {
  const tasks = ref<ModelDownloadTask[]>([]);
  const downloadedModels = ref<DownloadedModelInfo[]>([]);
  const isLoading = ref(false);
  const errorMessage = ref('');
  const successMessage = ref('');

  const activeTasks = computed(() =>
    tasks.value.filter((task) => task.status === 'pending' || task.status === 'downloading')
  );

  const taskMap = computed(() => {
    return tasks.value.reduce<Record<string, ModelDownloadTask>>((acc, task) => {
      acc[`${task.engine}:${task.model_id}`] = task;
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
    tasks.value = result.tasks || [];
  }

  async function loadDownloadedModels() {
    const result = await modelApi.getDownloadedModels();
    downloadedModels.value = result.models || [];
  }

  async function refreshAll() {
    isLoading.value = true;
    errorMessage.value = '';
    try {
      await Promise.all([loadTasks(), loadDownloadedModels()]);
    } catch (error: any) {
      errorMessage.value = `載入模型資訊失敗: ${error?.message || error}`;
    } finally {
      isLoading.value = false;
    }
  }

  async function startDownload(engine: ModelEngine, modelId: string) {
    clearMessages();
    try {
      const existing = taskMap.value[`${engine}:${modelId}`];
      if (existing && (existing.status === 'pending' || existing.status === 'downloading')) {
        successMessage.value = '此模型已在下載中';
        return;
      }

      const response = await modelApi.startDownload({
        engine,
        model_id: modelId
      });

      successMessage.value = response.message || '下載任務已啟動';
      await loadTasks();
      startPolling();
    } catch (error: any) {
      errorMessage.value = `啟動下載失敗: ${error?.response?.data?.detail || error?.message || error}`;
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

  function getTask(engine: ModelEngine, modelId: string): ModelDownloadTask | undefined {
    return taskMap.value[`${engine}:${modelId}`];
  }

  function isDownloaded(engine: ModelEngine, modelId: string): boolean {
    return downloadedModels.value.some((item) => item.engine === engine && item.model_id === modelId);
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
    activeTasks,
    isLoading,
    errorMessage,
    successMessage,
    refreshAll,
    startDownload,
    pollOnce,
    startPolling,
    stopPolling,
    getTask,
    isDownloaded,
    formatSize,
    clearMessages
  };
});
