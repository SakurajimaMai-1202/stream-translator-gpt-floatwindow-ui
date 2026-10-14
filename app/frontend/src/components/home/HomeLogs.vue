<script setup lang="ts">
import AppIcon from '../AppIcon.vue';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  logs, logContainer
} = useHomeContext();

function clearLogs() {
  logs.value = [];
}
</script>

<template>
          <!-- 執行日誌 -->
          <div class="home-log-panel flex h-[240px] min-h-0 flex-col fw-panel rounded-2xl border border-white/10 bg-slate-950/90 p-4 shadow-sm">
            <div class="flex items-center justify-between mb-2.5">
              <h2 class="text-xs font-bold text-white tracking-widest uppercase flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full bg-blue-400"></span>
                <AppIcon name="log" class="h-4 w-4" /> 系統執行日誌
              </h2>
              <button
                @click="clearLogs"
                class="text-xs text-white/60 hover:text-white/80 transition-colors flex items-center gap-1 px-2.5 py-1 bg-white/5 hover:bg-white/10 rounded-lg border border-white/5"
              >
                <AppIcon name="trash" class="h-4 w-4" /> 清除
              </button>
            </div>
            <div :ref="(el: any) => (logContainer = el)" class="min-h-0 flex-1 overflow-y-auto bg-black/40 rounded-xl p-3 font-mono text-xs leading-relaxed custom-scrollbar border border-white/5">
              <div v-for="(log, idx) in logs" :key="idx" class="mb-1 break-words text-green-400/80 last:mb-0">{{ log }}</div>
              <div v-if="logs.length === 0" class="text-white/60 h-full flex items-center justify-center italic">暫無執行日誌，等待啟動...</div>
            </div>
          </div>
</template>

<style scoped src="./home-shared.css"></style>
