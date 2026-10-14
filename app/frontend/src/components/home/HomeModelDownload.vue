<script setup lang="ts">
import AppIcon from '../AppIcon.vue';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  store, modelDownloadStore, isPreparingAsrModel, selectedAsrModelId, selectedDownloadEngine, selectedModelComputeBackend, selectedAsrDownloadTask, selectedAsrModelDownloaded, addLog
} = useHomeContext();

async function downloadSelectedAsrModel() {
  if (!selectedDownloadEngine.value || selectedAsrModelDownloaded.value) return;
  try {
    isPreparingAsrModel.value = true;
    addLog(`⬇️ 開始下載 ASR 模型：${selectedAsrModelId.value}`);
    await modelDownloadStore.ensureDownloaded(
      selectedDownloadEngine.value,
      selectedAsrModelId.value,
      selectedModelComputeBackend.value,
    );
    addLog(`✅ ASR 模型下載完成：${selectedAsrModelId.value}`);
  } catch (error: any) {
    const message = error.response?.data?.detail || error.message || '模型下載失敗';
    store.errorMessage = message;
    addLog(`❌ ASR 模型下載失敗：${message}`);
  } finally {
    isPreparingAsrModel.value = false;
  }
}
</script>

<template>
            <div
             
              class="mb-4 rounded-xl border p-3"
              :class="selectedAsrDownloadTask?.status === 'failed' ? 'border-rose-400/20 bg-rose-950/20' : 'border-cyan-400/15 bg-cyan-950/20'"
            >
              <div class="flex items-center justify-between gap-3">
                <div class="min-w-0">
                  <div class="flex items-center gap-2 text-xs font-bold text-cyan-200">
                    <AppIcon :name="selectedAsrDownloadTask && ['pending', 'downloading'].includes(selectedAsrDownloadTask.status) ? 'download' : 'model_management'" class="h-4 w-4" />
                    <span>{{ selectedAsrDownloadTask && ['pending', 'downloading'].includes(selectedAsrDownloadTask.status) ? 'ASR 模型下載中' : '尚未下載 ASR 模型' }}</span>
                    <span v-if="selectedAsrDownloadTask && ['pending', 'downloading'].includes(selectedAsrDownloadTask.status)" class="rounded-full bg-cyan-400/10 px-2 py-0.5 text-cyan-300">
                      {{ (modelDownloadStore.displayProgress(selectedAsrDownloadTask) * 100).toFixed(1) }}%
                    </span>
                  </div>
                  <p class="mt-1 truncate text-xs font-semibold text-white/80">{{ selectedAsrModelId }}</p>
                  <p class="mt-0.5 text-xs text-white/60">
                    {{ selectedAsrDownloadTask?.error || selectedAsrDownloadTask?.message || '開始轉譯時會提醒並可自動下載，完成後接續啟動。' }}
                  </p>
                </div>
                <button
                  v-if="!selectedAsrDownloadTask || !['pending', 'downloading'].includes(selectedAsrDownloadTask.status)"
                  type="button"
                  class="flex-shrink-0 rounded-lg bg-cyan-600 px-3 py-1.5 text-xs font-bold text-white transition hover:bg-cyan-500 disabled:cursor-not-allowed disabled:opacity-50"
                  :disabled="isPreparingAsrModel"
                  @click="downloadSelectedAsrModel"
                >
                  {{ isPreparingAsrModel ? '準備中…' : '立即下載' }}
                </button>
              </div>
              <div v-if="selectedAsrDownloadTask && ['pending', 'downloading'].includes(selectedAsrDownloadTask.status)" class="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10">
                <div
                  class="h-full rounded-full bg-blue-500 transition-all duration-500"
                  :style="{ width: `${Math.max(3, modelDownloadStore.displayProgress(selectedAsrDownloadTask) * 100)}%` }"
                ></div>
              </div>
            </div>
</template>

<style scoped src="./home-shared.css"></style>
