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
  if (task.status === 'downloading') return `下載中 ${(modelDownloadStore.displayProgress(task) * 100).toFixed(1)}%`;
  if (task.status === 'cancelling') return '取消中';
  if (task.status === 'cancelled') return '已取消';
  return '準備中';
}

function statusClass(modelId: string) {
  if (modelDownloadStore.isDownloaded(props.engine, modelId, props.computeBackend)) return 'is-ready';
  const task = getTask(modelId);
  if (!task || task.status === 'cancelled') return 'is-idle';
  if (task.status === 'failed') return 'is-error';
  if (task.status === 'completed') return 'is-ready';
  return 'is-active';
}

function canStart(modelId: string) {
  if (modelDownloadStore.isDownloaded(props.engine, modelId, props.computeBackend)) return false;
  const task = getTask(modelId);
  return !task || !['pending', 'downloading', 'cancelling'].includes(task.status);
}

function actionText(modelId: string) {
  if (modelDownloadStore.isDownloaded(props.engine, modelId, props.computeBackend)) return '已下載';
  const task = getTask(modelId);
  if (task?.status === 'failed') return '重試下載';
  if (task && ['pending', 'downloading', 'cancelling'].includes(task.status)) return '處理中';
  return '下載';
}

async function startDownload(modelId: string) {
  try {
    await modelDownloadStore.startDownload(props.engine, modelId, props.computeBackend);
  } catch {
    // The shared store exposes the actionable error in the management page.
  }
}

function description(modelId: string) {
  return props.descriptions[modelId] || props.defaultDescription;
}
</script>

<template>
  <section v-if="visibleModels.length > 0" class="asr-model-group" :aria-label="title">
    <header class="group-heading">
      <h3>{{ title }}</h3>
      <span class="group-count">{{ visibleModels.length }} 個模型</span>
    </header>
    <ul class="model-list">
      <li v-for="modelId in visibleModels" :key="`${engine}-${modelId}`" class="model-item">
        <div class="model-row">
          <div class="model-content">
            <div class="model-name">{{ modelId }}</div>
            <p v-if="description(modelId)" class="model-description">{{ description(modelId) }}</p>
            <span :class="['model-state', statusClass(modelId)]">{{ statusText(modelId) }}</span>
          </div>
          <button
            type="button"
            @click="startDownload(modelId)"
            :disabled="!canStart(modelId)"
            :aria-label="`${actionText(modelId)} ${modelId}`"
            :class="['model-action', { 'is-installed': modelDownloadStore.isDownloaded(engine, modelId, computeBackend) }]"
          >
            {{ actionText(modelId) }}
          </button>
        </div>
        <div v-if="getTask(modelId) && ['pending', 'downloading', 'cancelling'].includes(getTask(modelId)!.status)" class="download-progress">
          <div
            class="progress-track"
            role="progressbar"
            :aria-label="`${modelId} 下載進度`"
            :aria-valuenow="Math.round(modelDownloadStore.displayProgress(getTask(modelId)) * 100)"
            :aria-valuetext="statusText(modelId)"
            aria-valuemin="0"
            aria-valuemax="100"
          >
            <div
              class="progress-fill"
              :style="{ width: `${modelDownloadStore.displayProgress(getTask(modelId)) * 100}%` }"
            />
          </div>
          <p class="progress-message">{{ getTask(modelId)?.message }}</p>
        </div>
        <p v-if="getTask(modelId)?.status === 'failed'" class="download-error" role="status">{{ getTask(modelId)?.error || getTask(modelId)?.message }}</p>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.asr-model-group { color:var(--fw-text);background:var(--fw-surface);border:1px solid var(--fw-border);border-radius:16px;overflow:hidden;font-family:system-ui,-apple-system,"Segoe UI",sans-serif; }
.group-heading { display:flex;align-items:center;justify-content:space-between;gap:1rem;padding:1.1rem 1.25rem;border-bottom:1px solid var(--fw-border); }
.group-heading h3 { margin:0;font-size:1rem;line-height:1.35;letter-spacing:-.01em;font-weight:600; }
.group-count { font-size:.75rem;color:var(--fw-text-secondary);white-space:nowrap; }
.model-list { list-style:none;padding:0;margin:0; }
.model-item { padding:1rem 1.25rem; }
.model-item + .model-item { border-top:1px solid #ffffff0e; }
.model-row { display:flex;align-items:center;justify-content:space-between;gap:1.25rem; }
.model-content { min-width:0; }
.model-name { font-size:.9375rem;font-weight:550;line-height:1.5;overflow-wrap:anywhere; }
.model-description { margin:.25rem 0 0;font-size:.8125rem;line-height:1.55;color:var(--fw-text-secondary);overflow-wrap:anywhere; }
.model-state { display:inline-block;margin-top:.5rem;font-size:.75rem;line-height:1.4; }
.is-idle { color:var(--fw-text-secondary); }.is-ready { color:#9bddb9; }.is-error,.download-error { color:#f4b6bb; }.is-active { color:#9abff6; }
.model-action { flex-shrink:0;min-width:96px;min-height:44px;border:1px solid #598cc066;border-radius:10px;background:var(--fw-primary-soft);color:var(--fw-text);font:inherit;font-size:.875rem;font-weight:600;padding:.6rem 1rem;cursor:pointer;touch-action:manipulation;transition:background 120ms ease,transform 100ms ease; }
.model-action:hover:not(:disabled) { background:#335b8d; }.model-action:active:not(:disabled) { background:#3d679a;transform:scale(.98); }.model-action:focus-visible { outline:2px solid var(--fw-primary);outline-offset:3px; }.model-action:disabled { opacity:.55;cursor:not-allowed; }.model-action.is-installed { background:#ffffff06;border-color:#ffffff18;color:var(--fw-text-secondary); }
.download-progress { margin-top:.9rem; }.progress-track { height:5px;border-radius:5px;overflow:hidden;background:var(--fw-border); }.progress-fill { height:100%;background:var(--fw-primary); }.progress-message,.download-error { margin:.4rem 0 0;font-size:.75rem;line-height:1.5;overflow-wrap:anywhere; }.progress-message { color:var(--fw-text-secondary); }
@media(max-width:640px) { .group-heading { padding:1rem; }.model-item { padding:1rem; }.model-row { gap:.75rem; }.model-action { min-width:80px;padding:.6rem .75rem; } }
@media(prefers-reduced-motion:reduce) { .model-action { transition:none; }.model-action:active:not(:disabled) { transform:none; } }
@media(prefers-contrast:more) { .asr-model-group { border-color:#8b9bb5; }.model-description,.group-count,.is-idle,.progress-message { color:#d2dbea; }.model-item + .model-item,.group-heading { border-color:#8b9bb5; } }
</style>
