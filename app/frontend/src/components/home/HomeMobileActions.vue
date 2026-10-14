<script setup lang="ts">
import AppIcon from '../AppIcon.vue';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  store, isLoading, isPreparingAsrModel, selectedInputLanguage, selectedOutputLanguage, translationEnabled, isConfigReady, handleStart, handleStop
} = useHomeContext();
</script>

<template>
    <!-- Mobile primary action bar -->
    <div class="mobile-action-bar fixed inset-x-0 bottom-0 z-30 border-t border-white/10 bg-slate-950/95 px-3 pb-3 pt-2 shadow-[0_-12px_35px_rgba(2,6,23,0.8)] backdrop-blur md:hidden">
      <div class="mx-auto flex max-w-7xl items-center gap-2">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-1.5 text-xs font-bold text-white/80">
            <span :class="store.isRunning ? 'text-green-400' : 'text-slate-500'">●</span>
            <span>{{ store.isRunning ? '即時轉譯中' : '準備啟動' }}</span>
          </div>
          <p class="mt-0.5 truncate text-xs text-white/60">
            {{ selectedInputLanguage }} → {{ translationEnabled ? selectedOutputLanguage : '僅轉錄' }}
          </p>
        </div>
        <button
          v-if="!store.isRunning"
          type="button"
          class="min-h-12 min-w-[9.5rem] rounded-xl home-primary-action bg-blue-600 px-4 text-sm font-bold text-white shadow-lg shadow-indigo-600/25 transition active:scale-[0.98] disabled:from-slate-800 disabled:to-slate-900 disabled:text-white/40 disabled:shadow-none"
          :disabled="isLoading || isPreparingAsrModel || !isConfigReady"
          @click="handleStart"
        >
          <span class="inline-flex items-center justify-center gap-1.5"><AppIcon :name="isPreparingAsrModel ? 'download' : 'play'" class="h-4 w-4" />{{ isPreparingAsrModel ? '下載模型中' : isLoading ? '啟動中…' : '開始轉譯' }}</span>
        </button>
        <button
          v-else
          type="button"
          class="min-h-12 min-w-[9.5rem] rounded-xl home-stop-action bg-red-600 px-4 text-sm font-bold text-white shadow-lg shadow-red-600/25 transition active:scale-[0.98] disabled:from-slate-800 disabled:to-slate-900 disabled:text-white/40 disabled:shadow-none"
          :disabled="isLoading"
          @click="handleStop"
        >
          <span class="inline-flex items-center justify-center gap-1.5"><AppIcon name="stop" class="h-4 w-4" />{{ isLoading ? '停止中…' : '停止轉譯' }}</span>
        </button>
      </div>
    </div>
</template>

<style scoped src="./home-shared.css"></style>
