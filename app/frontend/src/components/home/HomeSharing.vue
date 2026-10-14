<script setup lang="ts">
import AppIcon from '../AppIcon.vue';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  publicPort, activeCopyPath, subtitleSharingEnabled, subtitleSharingStatusKnown, isUpdatingSubtitleSharing, getPublicBase, copyLink, toggleSubtitleSharing
} = useHomeContext();
</script>

<template>
          <!-- 🌐 公開分享連結 -->
          <div class="fw-panel home-sharing-panel bg-slate-950/90 rounded-2xl border border-indigo-500/20 shadow-sm p-4">
            <div class="flex items-center justify-between mb-2.5">
              <h2 class="text-xs font-bold text-white tracking-widest uppercase flex items-center gap-1.5">
                <span class="w-1.5 h-1.5 rounded-full bg-indigo-400"></span>
                <AppIcon name="url" class="h-4 w-4" /> 字幕分享服務
              </h2>
              <button @click="toggleSubtitleSharing" :disabled="isUpdatingSubtitleSharing || !subtitleSharingStatusKnown"
                class="px-2 py-1 text-xs rounded-lg transition duration-200 border"
                :class="subtitleSharingEnabled
                  ? 'bg-emerald-600/80 hover:bg-emerald-600 border-emerald-500/30 text-white'
                  : 'bg-rose-600/80 hover:bg-rose-600 border-rose-500/30 text-white'">
                {{ isUpdatingSubtitleSharing ? '同步中...' : (!subtitleSharingStatusKnown ? '狀態未知' : (subtitleSharingEnabled ? '分享啟用' : '分享關閉')) }}
              </button>
            </div>

            <div v-if="!subtitleSharingStatusKnown" class="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs leading-relaxed text-amber-200">
              尚未連接字幕分享服務，連線恢復後會顯示實際狀態與分享連結。
            </div>

            <div v-else-if="subtitleSharingEnabled" class="space-y-2.5">
              <p class="text-white/60 text-xs leading-tight">廣播服務已運行於連接埠 {{ publicPort }}。此連結僅顯示字幕，無設定權限。</p>

              <div class="space-y-2">
                <!-- 電腦版 -->
                <div class="flex items-center gap-2.5 bg-white/5 rounded-xl p-2.5 border border-white/5 group hover:bg-white/10 transition duration-200">
                  <AppIcon name="desktop" class="h-5 w-5 text-blue-300" />
                  <div class="flex-1 min-w-0">
                    <div class="text-white/60 text-xs font-bold">電腦端字幕</div>
                    <div class="text-white/60 text-xs truncate font-mono mt-0.5">{{ getPublicBase() }}/desktop</div>
                  </div>
                  <button @click="copyLink('/desktop')"
                    class="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white text-xs rounded-lg transition-all font-semibold shadow-sm shadow-indigo-600/10">
                    {{ activeCopyPath === '/desktop' ? '已複製' : '複製' }}
                  </button>
                </div>

                <!-- 手機版 -->
                <div class="flex items-center gap-2.5 bg-white/5 rounded-xl p-2.5 border border-white/5 group hover:bg-white/10 transition duration-200">
                  <AppIcon name="mobile" class="h-5 w-5 text-blue-300" />
                  <div class="flex-1 min-w-0">
                    <div class="text-white/60 text-xs font-bold">行動端字幕</div>
                    <div class="text-white/60 text-xs truncate font-mono mt-0.5">{{ getPublicBase() }}/mobile</div>
                  </div>
                  <button @click="copyLink('/mobile')"
                    class="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white text-xs rounded-lg transition-all font-semibold shadow-sm shadow-indigo-600/10">
                    {{ activeCopyPath === '/mobile' ? '已複製' : '複製' }}
                  </button>
                </div>
              </div>
              <p class="text-white/60 text-xs text-center tracking-wide mt-1">請確保本機防火牆允許對外存取此連接埠</p>
            </div>

            <div v-else class="p-3 rounded-xl border border-rose-500/20 bg-rose-500/5 text-rose-300 text-xs leading-relaxed text-center">
              字幕廣播服務目前已關閉，外部裝置將無法存取字幕網頁。
            </div>
          </div>
</template>

<style scoped src="./home-shared.css"></style>
