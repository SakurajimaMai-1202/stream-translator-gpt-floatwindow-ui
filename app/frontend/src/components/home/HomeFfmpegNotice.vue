<script setup lang="ts">
import AppIcon from '../AppIcon.vue';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  ffmpegWarningDismissed
} = useHomeContext();
</script>

<template>
      <div class="mb-4 p-3.5 bg-yellow-950/70 border border-yellow-500/30 text-yellow-200 rounded-xl flex justify-between items-start gap-3">
        <div class="flex-1">
          <div class="flex items-center gap-1.5 font-bold text-sm"><AppIcon name="warning" class="h-4 w-4" /> 未偵測到 ffmpeg</div>
          <p class="text-xs text-yellow-100/70 mt-1 leading-relaxed">
            目前系統找不到 ffmpeg，可先安裝或確認路徑。這不會阻止 UI 啟動，但音訊處理可能失敗。
          </p>
        </div>
        <button type="button" aria-label="關閉" @click="ffmpegWarningDismissed = true" class="text-yellow-300/80 hover:text-white transition p-1"><AppIcon name="close" class="h-4 w-4" /></button>
      </div>
</template>

<style scoped src="./home-shared.css"></style>
