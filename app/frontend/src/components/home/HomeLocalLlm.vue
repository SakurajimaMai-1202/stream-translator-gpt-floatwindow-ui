<script setup lang="ts">
import { computed } from 'vue';
import AppIcon from '../AppIcon.vue';
import { useHomeContext } from '../../composables/home/homeContext';
const {
  router, llamaStore, selectedBackend, externalFamilyEndpoint, translationEnabled, addLog
} = useHomeContext();

const localLlmModelName = computed(() => {
  const value = llamaStore.currentModel || llamaStore.selectedModelPath;
  if (!value) return '尚未選擇模型';
  return value.split(/[\\/]/).pop()?.replace(/\.gguf$/i, '') || value;
});

const localLlmStatusLabel = computed(() => {
  if (llamaStore.isLoading) return llamaStore.localLlmEnabled ? '正在啟動' : '正在停止';
  if (llamaStore.isServerReady) return '服務已就緒';
  if (llamaStore.isServerRunning) return '模型載入中';
  if (llamaStore.localLlmEnabled && llamaStore.serverStatus.last_error) return '啟動失敗';
  return llamaStore.localLlmEnabled ? '等待啟動' : '目前關閉';
});

const localLlmStatusDescription = computed(() => {
  if (!llamaStore.selectedModelPath) return '請先到「LLM 模型管理」選擇 GGUF 模型';
  if (llamaStore.isServerReady) {
    const runningUrl = llamaStore.serverStatus.server_url;
    if (runningUrl) return `本機翻譯正在 ${runningUrl} 運行`;
    return `本機翻譯正在連接埠 ${llamaStore.serverConfig.port} 運行`;
  }
  if (llamaStore.isLoading || llamaStore.isServerRunning) return '正在載入模型，完成後即可開始轉譯';
  if (llamaStore.localLlmEnabled && llamaStore.serverStatus.last_error) return llamaStore.serverStatus.last_error;
  return '開啟後會啟動 llama.cpp，關閉則不使用本地模型';
});

// The toggle means "this app runs llama-server"; the 'llama' backend means
// "use a llama-compatible endpoint", which may also be LM Studio.
const localLlmUsageHint = computed<'external' | 'idle' | null>(() => {
  const backend = selectedBackend.value;
  const usesLlamaBackend = translationEnabled.value && (backend === 'llama' || backend === 'localllm');
  if (usesLlamaBackend && !llamaStore.localLlmEnabled) return 'external';
  const usesNoLocalModel = !translationEnabled.value || ['none', 'gpt', 'gemini'].includes(backend);
  if (usesNoLocalModel && !externalFamilyEndpoint.value && (llamaStore.localLlmEnabled || llamaStore.isServerRunning)) return 'idle';
  return null;
});

async function stopLocalLlm() {
  try {
    await llamaStore.setLocalLlmEnabled(false);
    addLog('已停用本地 LLM');
  } catch (error: any) {
    addLog(`本地 LLM 停止失敗: ${error.response?.data?.detail || error.message}`);
  }
}

async function handleLocalLlmToggle(event: Event) {
  const enabled = (event.target as HTMLInputElement).checked;
  try {
    await llamaStore.setLocalLlmEnabled(enabled);
    addLog(enabled ? '✅ 已啟用本地 LLM' : '⏹️ 已停用本地 LLM');
  } catch (error: any) {
    addLog(`❌ 本地 LLM 切換失敗: ${error.response?.data?.detail || error.message}`);
  }
}
</script>

<template>
          <!-- 本地 LLM 快速控制 -->
          <div
            class="relative overflow-hidden rounded-2xl border p-4 transition-all duration-300"
            :class="llamaStore.localLlmEnabled
              ? 'border-emerald-400/25 bg-slate-950/90'
              : 'border-white/5 bg-slate-950/90'"
          >
            <div v-if="llamaStore.localLlmEnabled" class="pointer-events-none absolute inset-y-0 left-0 w-1 bg-emerald-400/60"></div>
            <div class="flex items-center justify-between gap-4">
              <div class="flex min-w-0 items-center gap-3">
                <div
                  class="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-xl border text-lg transition-colors"
                  :class="llamaStore.localLlmEnabled ? 'border-emerald-400/20 bg-emerald-400/10' : 'border-white/5 bg-white/[0.03]'"
                >
                  <AppIcon name="brain" class="h-5 w-5" />
                </div>
                <div class="min-w-0">
                  <div class="mb-1 flex flex-wrap items-center gap-2">
                    <h3 class="text-xs font-bold tracking-wide text-white">本地 LLM 翻譯</h3>
                    <span
                      class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-bold"
                      :class="llamaStore.isServerReady
                        ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300'
                        : llamaStore.isServerRunning || llamaStore.isLoading
                          ? 'border-amber-400/25 bg-amber-400/10 text-amber-300'
                          : 'border-white/10 bg-white/5 text-white/60'"
                    >
                      <span
                        class="h-1.5 w-1.5 rounded-full"
                        :class="llamaStore.isServerReady ? 'bg-emerald-400' : llamaStore.isServerRunning || llamaStore.isLoading ? 'animate-pulse bg-amber-400' : 'bg-slate-500'"
                      ></span>
                      {{ localLlmStatusLabel }}
                    </span>
                  </div>
                  <p class="truncate text-xs font-semibold" :class="llamaStore.selectedModelPath ? 'text-cyan-200/90' : 'text-amber-300/80'">
                    {{ localLlmModelName }}
                  </p>
                  <p class="mt-0.5 max-w-[560px] truncate text-xs text-white/60" :title="localLlmStatusDescription">
                    {{ localLlmStatusDescription }}
                  </p>
                  <p v-if="localLlmUsageHint === 'external'" class="mt-1.5 text-xs leading-5 text-cyan-200/90" role="status">
                    翻譯後端為 Llama，但本機伺服器未開啟：將使用外部 llama 相容服務（例如 LM Studio）。
                    <button type="button" class="ml-1 underline underline-offset-2 hover:text-white" @click="router.push({ path: '/settings', query: { tab: 'translation' } })">查看服務位址</button>
                  </p>
                  <p v-else-if="localLlmUsageHint === 'idle'" class="mt-1.5 flex flex-wrap items-center gap-2 text-xs leading-5 text-amber-200/90" role="status">
                    <span>目前翻譯未使用本機模型，伺服器仍在佔用顯存。</span>
                    <button type="button" class="local-llm-inline-action rounded-md border border-amber-300/30 px-2 text-amber-100 hover:bg-amber-300/10 disabled:opacity-50" :disabled="llamaStore.isLoading" @click="stopLocalLlm">停止伺服器</button>
                  </p>
                </div>
              </div>

              <label
                class="flex flex-shrink-0 items-center gap-2.5"
                :class="llamaStore.isLoading || (!llamaStore.selectedModelPath && !llamaStore.localLlmEnabled) ? 'cursor-not-allowed opacity-45' : 'cursor-pointer'"
                :title="!llamaStore.selectedModelPath ? '請先到 LLM 模型管理選擇模型' : llamaStore.localLlmEnabled ? '關閉本地 LLM' : '啟動本地 LLM'"
              >
                <span class="text-xs font-bold" :class="llamaStore.localLlmEnabled ? 'text-emerald-300' : 'text-white/65'">
                  {{ llamaStore.localLlmEnabled ? '開啟' : '關閉' }}
                </span>
                <span class="relative inline-flex">
                  <input
                    type="checkbox"
                    class="peer sr-only"
                    :checked="llamaStore.localLlmEnabled"
                    :disabled="llamaStore.isLoading || (!llamaStore.selectedModelPath && !llamaStore.localLlmEnabled)"
                    @change="handleLocalLlmToggle"
                  />
                  <span class="h-6 w-12 rounded-full border border-white/10 bg-slate-700 shadow-inner transition-all duration-300 peer-checked:border-emerald-400/40 peer-checked:bg-emerald-500 peer-focus-visible:ring-2 peer-focus-visible:ring-emerald-300/50"></span>
                  <span class="absolute left-1 top-1 h-4 w-4 rounded-full bg-white shadow-md transition-transform duration-300 peer-checked:translate-x-6"></span>
                </span>
              </label>
            </div>
          </div>
</template>

<style scoped src="./home-shared.css"></style>
