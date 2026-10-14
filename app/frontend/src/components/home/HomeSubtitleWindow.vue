<script setup lang="ts">
import { useHomeContext } from '../../composables/home/homeContext';
const {
  router, openSubtitleWindow
} = useHomeContext();
</script>

<template>
          <!-- Floating subtitle window control -->
          <div class="home-subtitle-control fw-panel rounded-2xl border border-white/10 bg-slate-950/90 p-4">
            <div class="mb-3 flex items-start justify-between gap-3">
              <div>
                <h2 class="text-sm font-bold text-white">浮動字幕窗</h2>
                <p class="mt-1 text-xs leading-relaxed text-white/65">字幕顯示於獨立桌面視窗，主視窗專注於轉譯控制。</p>
              </div>
              <span class="rounded-md border border-cyan-400/20 bg-cyan-400/10 px-2 py-1 text-xs font-semibold text-cyan-200">獨立視窗</span>
            </div>
            <button
              type="button"
              class="w-full border border-blue-400/30 bg-blue-500/15 px-4 py-2.5 text-sm font-semibold text-blue-100 transition hover:bg-blue-500/25"
              title="開啟字幕懸浮視窗"
              @click="openSubtitleWindow"
            >
              開啟字幕視窗
            </button>
            <button
              type="button"
              class="mt-3 flex w-full items-center justify-between border-t border-white/10 bg-transparent px-0 pt-3 text-left text-xs text-white/60 hover:text-white"
              @click="router.push('/subtitle-style')"
            >
              <span>調整字幕外觀（字型、配色、透明度、位置）</span>
              <span class="text-blue-300" aria-hidden="true">→</span>
            </button>
          </div>
</template>

<style scoped src="./home-shared.css"></style>
