<script setup lang="ts">
import AppIcon from '../AppIcon.vue';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  store, isLoading, isPreparingAsrModel, isConfigReady, handleStart, handleStop, openSubtitleWindow
} = useHomeContext();
</script>

<template>
            <!-- 控制按鈕 (啟動/停止 與 字幕視窗) -->
            <div class="hidden gap-3 md:flex">
              <!-- 啟動/停止按鈕 -->
              <button
                v-if="!store.isRunning"
                @click="handleStart"
                :disabled="isLoading || isPreparingAsrModel || !isConfigReady"
                class="flex-1 home-primary-action bg-blue-600 hover:bg-blue-500 disabled:from-slate-800 disabled:to-slate-900 disabled:text-white/40 disabled:border-white/5 disabled:shadow-none text-white font-bold py-3.5 px-5 rounded-xl transition-all duration-200 active:scale-[0.98] shadow-lg shadow-indigo-600/20 flex items-center justify-center gap-2"
              >
                <AppIcon :name="isPreparingAsrModel ? 'download' : 'play'" class="h-4 w-4" />
                <span class="text-sm font-semibold">{{ isPreparingAsrModel ? '正在下載 ASR 模型…' : isLoading ? '啟動中…' : '啟動即時轉譯' }}</span>
              </button>

              <button
                v-else
                @click="handleStop"
                :disabled="isLoading"
                class="flex-1 home-stop-action bg-red-600 hover:bg-red-500 disabled:from-slate-800 disabled:to-slate-900 disabled:text-white/40 disabled:border-white/5 disabled:shadow-none text-white font-bold py-3.5 px-5 rounded-xl transition-all duration-200 active:scale-[0.98] shadow-lg shadow-red-600/20 flex items-center justify-center gap-2"
              >
                <AppIcon name="stop" class="h-4 w-4" />
                <span class="text-sm font-semibold">{{ isLoading ? '停止中…' : '停止即時轉譯' }}</span>
              </button>

              <!-- 字幕視窗按鈕 -->
              <button
                @click="openSubtitleWindow"
                class="home-inline-subtitle-button px-5 py-3.5 bg-white/10 hover:bg-white/15 text-white font-semibold rounded-xl transition-all shadow-md shadow-cyan-600/10 flex items-center justify-center gap-1.5 text-sm"
                title="開啟字幕懸浮視窗"
                aria-label="開啟字幕視窗"
              >
                <AppIcon name="subtitle-window" class="h-4 w-4" /> <span class="hidden sm:inline">字幕視窗</span>
              </button>
            </div>
</template>

<style scoped src="./home-shared.css"></style>
