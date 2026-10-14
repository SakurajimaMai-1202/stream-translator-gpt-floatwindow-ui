<script setup lang="ts">
import { useHomeContext } from '../../composables/home/homeContext';
const {
  interfaceMode, readinessItems
} = useHomeContext();
</script>

<template>
      <section class="mb-4 rounded-xl border border-white/10 bg-slate-950/70 p-4" aria-labelledby="readiness-title">
        <div class="flex items-center justify-between gap-3">
          <div>
            <h2 id="readiness-title" class="text-base font-bold text-white">開始前確認</h2>
            <p class="mt-1 text-sm text-white/65">確認音訊來源和語音辨識準備完成後，就可以開始使用。</p>
          </div>
          <button type="button" class="rounded-lg border border-white/15 px-3 py-2 text-sm text-white/75 hover:bg-white/5" @click="interfaceMode.mode = null; interfaceMode.pendingMode = null; interfaceMode.onboardingStep = 'mode'">繼續設定</button>
        </div>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          <div v-for="item in readinessItems" :key="item.label" class="rounded-lg border border-white/10 bg-white/[0.03] p-3">
            <p class="text-sm font-bold text-white"><span :class="item.status === 'ready' ? 'text-emerald-300' : item.status === 'error' ? 'text-red-300' : 'text-amber-300'">{{ item.status === 'ready' ? '已完成' : item.status === 'error' ? '需要處理' : '待確認' }}</span> · {{ item.label }}</p>
            <p class="mt-1 text-sm leading-5 text-white/65">{{ item.detail }}</p>
          </div>
        </div>
      </section>
</template>

<style scoped src="./home-shared.css"></style>
