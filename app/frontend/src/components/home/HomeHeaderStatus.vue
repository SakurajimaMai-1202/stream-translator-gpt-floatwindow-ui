<script setup lang="ts">
import { computed } from 'vue';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  store, configWarnings, hasErrors
} = useHomeContext();

const latestQueueTrace = computed(() => store.latestSubtitle?.latency_trace);

const queueStatusText = computed(() => {
  const trace = latestQueueTrace.value;
  if (!trace || trace.asr_queue_depth == null) return '佇列未知';
  const seconds = Number(trace.asr_queue_audio_seconds || 0).toFixed(1);
  const wait = Math.round(trace.asr_queue_oldest_wait_ms || 0);
  return `ASR 佇列 ${trace.asr_queue_depth} 段 · ${seconds}s 音訊 · 最舊 ${wait}ms`;
});
</script>

<template>
      <div class="fw-page-header commercial-page-header mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2.5 sm:gap-3">
        <div class="min-w-0">
          <div class="mb-3">
            <h1 class="text-xl font-bold text-white sm:text-2xl">即時轉譯</h1>
            <p>選擇音訊來源，讓翻譯隨畫面同行。</p>
          </div>
          <div class="flex flex-wrap items-center gap-2 sm:gap-3">
          <!-- Status dot -->
          <div class="flex items-center gap-1.5 bg-white/5 px-2.5 py-0.5 rounded-full border border-white/10 text-xs">
            <div :class="[
              'w-1.5 h-1.5 rounded-full',
              store.isRunning ? 'bg-green-400 animate-pulse shadow shadow-green-400/50' : 'bg-gray-500'
            ]"></div>
            <span class="text-white/70 font-semibold">
              {{ store.isRunning ? '即時轉譯中' : '系統閒置' }}
            </span>
          </div>

          <!-- Configuration Status dot -->
          <div class="flex items-center gap-1.5 bg-white/5 px-2.5 py-0.5 rounded-full border border-white/10 text-xs">
            <div :class="[
              'w-1.5 h-1.5 rounded-full',
              hasErrors ? 'bg-red-400 animate-pulse' : (configWarnings.length > 0 ? 'bg-yellow-400 animate-pulse' : 'bg-green-400')
            ]"></div>
            <span class="text-white/70 font-semibold">
              {{ hasErrors ? '配置錯誤' : (configWarnings.length > 0 ? '配置警告' : '配置正常') }}
            </span>
          </div>
          <div v-if="store.isRunning" class="mt-2 text-xs text-cyan-200/80" role="status">{{ queueStatusText }}</div>
        </div>
        </div>
        <div class="flex min-w-0 items-center gap-2 max-md:w-full max-md:justify-between">
          <div v-if="store.currentUrl" class="text-white/60 text-xs truncate max-w-xs sm:max-w-md font-mono bg-white/5 px-2.5 py-0.5 rounded-lg border border-white/5">
            {{ store.currentUrl }}
          </div>
        </div>
      </div>
</template>

<style scoped src="./home-shared.css"></style>
