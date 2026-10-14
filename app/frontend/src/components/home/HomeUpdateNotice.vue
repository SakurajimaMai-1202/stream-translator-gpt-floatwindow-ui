<script setup lang="ts">
import { computed } from 'vue';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  availableAppUpdate: appUpdate, appUpdateNoticeDismissed, openAppUpdateSettings
} = useHomeContext();
// HomeView mounts this notice only while an update is available.
const availableAppUpdate = computed(() => appUpdate.value!);
</script>

<template>
      <div class="mb-4 rounded-xl border border-cyan-400/30 bg-cyan-950/70 p-3.5 text-cyan-100 shadow-lg shadow-cyan-950/20">
        <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div class="min-w-0">
            <div class="text-sm font-bold">Stream Translator v{{ availableAppUpdate.latest_version }} 已可更新</div>
            <p class="mt-1 text-xs leading-relaxed text-cyan-100/65">
              目前版本 v{{ availableAppUpdate.current_version }}。程式只會通知，不會自動下載或安裝。
            </p>
          </div>
          <div class="flex shrink-0 items-center gap-2">
            <button type="button" class="rounded-lg bg-cyan-500 px-3 py-1.5 text-xs font-bold text-slate-950 transition hover:bg-cyan-400" @click="openAppUpdateSettings">查看更新</button>
            <button type="button" class="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold text-white/65 transition hover:bg-white/10 hover:text-white" @click="appUpdateNoticeDismissed = true">稍後</button>
          </div>
        </div>
      </div>
</template>

<style scoped src="./home-shared.css"></style>
