<script setup lang="ts">
import { computed } from 'vue';
import { useModelDownloadStore } from '../stores/modelDownload';
import type { ModelComputeBackend, ModelEngine } from '../services/api';

const props = withDefaults(defineProps<{
  title: string;
  engine: ModelEngine;
  computeBackend: ModelComputeBackend;
  models: string[];
  descriptions?: Record<string, string>;
  defaultDescription?: string;
}>(), {
  descriptions: () => ({}),
  defaultDescription: '',
});

const modelDownloadStore = useModelDownloadStore();
const visibleModels = computed(() => props.models || []);

function getTask(modelId: string) {
  return modelDownloadStore.getTask(props.engine, modelId, props.computeBackend);
}

function statusText(modelId: string) {
  if (modelDownloadStore.isDownloaded(props.engine, modelId, props.computeBackend)) return '已下載';
  const task = getTask(modelId);
  if (!task) return '未下載';
  if (task.status === 'failed') return '下載失敗';
  if (task.status === 'completed') return '已下載';
  if (task.status === 'downloading') return `下載中 ${(task.progress * 100).toFixed(0)}%`;
  return '準備中';
}

function statusClass(modelId: string) {
  if (modelDownloadStore.isDownloaded(props.engine, modelId, props.computeBackend)) return 'text-green-300';
  const task = getTask(modelId);
  if (!task) return 'text-white/50';
  if (task.status === 'failed') return 'text-red-300';
  if (task.status === 'completed') return 'text-green-300';
  return 'text-blue-300';
}

function canStart(modelId: string) {
  if (modelDownloadStore.isDownloaded(props.engine, modelId, props.computeBackend)) return false;
  const task = getTask(modelId);
  return !task || !['pending', 'downloading'].includes(task.status);
}

function description(modelId: string) {
  return props.descriptions[modelId] || props.defaultDescription;
}
</script>

<template>
  <div v-if="visibleModels.length > 0" class="asr-model-group bg-white/5 rounded-xl p-5 border border-white/10">
    <h3 class="text-lg font-semibold text-blue-300 mb-4">{{ title }}</h3>
    <div class="space-y-3">
      <div v-for="modelId in visibleModels" :key="`${engine}-${modelId}`" class="p-4 rounded-lg bg-white/5 border border-white/10">
        <div class="flex items-center justify-between gap-4">
          <div>
            <div class="text-white font-semibold">{{ modelId }}</div>
            <div v-if="description(modelId)" class="text-white/50 text-xs mt-1">{{ description(modelId) }}</div>
            <div :class="['text-sm mt-1', statusClass(modelId)]">{{ statusText(modelId) }}</div>
          </div>
          <button
            @click="modelDownloadStore.startDownload(engine, modelId, computeBackend)"
            :disabled="!canStart(modelId)"
            class="px-4 py-2 rounded-lg font-semibold transition disabled:opacity-50 disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-700 text-white"
          >
            {{ modelDownloadStore.isDownloaded(engine, modelId, computeBackend) ? '已下載' : '下載' }}
          </button>
        </div>
        <div v-if="getTask(modelId) && ['pending', 'downloading'].includes(getTask(modelId)!.status)" class="mt-3">
          <div class="h-2 bg-white/10 rounded-full overflow-hidden">
            <div
              class="h-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all"
              :style="{ width: `${Math.max(5, (getTask(modelId)?.progress || 0) * 100)}%` }"
            />
          </div>
          <div class="text-xs text-white/60 mt-1">{{ getTask(modelId)?.message }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.asr-model-group {
  /* 將每一組模型的重繪限制在自身，不建立整頁的大型 paint layer。 */
  contain: layout paint style;
  isolation: isolate;
}
</style>
