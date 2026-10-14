<script setup lang="ts">
import AppIcon from '../AppIcon.vue';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  configWarnings, hasErrors, goToWarningPage
} = useHomeContext();
</script>

<template>
      <div class="mb-4 p-4 rounded-xl bg-slate-950/90 border"
        :class="hasErrors ? 'border-red-500/30 bg-red-500/10' : 'border-yellow-500/30 bg-yellow-500/10'">
        <div class="flex items-center gap-2 mb-2">
          <AppIcon :name="hasErrors ? 'error' : 'warning'" :class="['h-4 w-4', hasErrors ? 'text-red-300' : 'text-yellow-300']" />
          <span class="font-bold text-white text-xs tracking-wider uppercase">配置檢查</span>
        </div>
        <ul class="space-y-1.5">
          <li v-for="(warning, idx) in configWarnings" :key="idx"
            class="flex items-center justify-between text-xs"
            :class="warning.level === 'error' ? 'text-red-300/90' : 'text-yellow-300/90'">
            <span class="flex items-center gap-2">
              <span class="w-1.5 h-1.5 rounded-full" :class="warning.level === 'error' ? 'bg-red-400' : 'bg-yellow-400'"></span>
              {{ warning.message }}
            </span>
            <button v-if="warning.page" type="button" @click="goToWarningPage(warning.page)"
              class="px-2 py-0.5 bg-white/10 hover:bg-white/20 text-white rounded text-xs transition border border-white/5">
              {{ warning.actionLabel || '前往設定' }}
            </button>
          </li>
        </ul>
      </div>
</template>

<style scoped src="./home-shared.css"></style>
