<script setup lang="ts">
import AppIcon from '../AppIcon.vue';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  store
} = useHomeContext();
</script>

<template>
      <div class="mb-4 p-3.5 bg-red-950/80 border border-red-500/30 text-red-200 rounded-xl flex justify-between items-center text-sm">
        <span class="flex items-center gap-2"><AppIcon name="error" class="h-4 w-4 shrink-0" /> {{ store.errorMessage }}</span>
        <button type="button" aria-label="關閉" @click="store.clearError()" class="text-red-300 hover:text-white transition p-1"><AppIcon name="close" class="h-4 w-4" /></button>
      </div>
</template>

<style scoped src="./home-shared.css"></style>
