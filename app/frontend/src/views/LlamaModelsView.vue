<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useLlamaStore } from '../stores/llama';

const store = useLlamaStore();
const router = useRouter();
const modelDirectory = ref('');
const search = ref('');
const filteredModels = computed(() => store.models.filter(model =>
  model.name.toLowerCase().includes(search.value.trim().toLowerCase())
));

async function scan() {
  await store.loadModels(modelDirectory.value);
  await store.saveConfig();
}

async function selectModel(path: string) {
  store.selectModel(path);
  await store.saveConfig();
}

onMounted(async () => {
  await store.initialize();
  modelDirectory.value = store.modelDirectory;
});
</script>

<template>
  <div class="p-5 max-w-7xl mx-auto space-y-5">
    <header class="flex flex-col lg:flex-row lg:items-center justify-between gap-3 border-b border-white/10 pb-4">
      <div><h1 class="text-xl font-bold">🧠 LLM 模型管理</h1><p class="text-white/50 text-sm mt-1">掃描及選擇 GGUF；模型不會在選取瞬間中斷目前服務。</p></div>
      <button @click="router.push({ path: '/settings', query: { tab: 'llama' } })" class="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 font-semibold">前往執行設定</button>
    </header>
    <div v-if="store.errorMessage" class="p-3 rounded-lg bg-red-500/15 border border-red-500/30 text-red-200">{{ store.errorMessage }}</div>
    <section class="rounded-2xl bg-slate-950/70 border border-white/10 p-5 space-y-4">
      <div class="grid grid-cols-1 lg:grid-cols-[1fr_auto] gap-3">
        <input v-model="modelDirectory" class="px-4 py-2.5 rounded-lg bg-white/5 border border-white/15" placeholder="GGUF 模型目錄，例如 D:\\Models" />
        <button @click="scan" :disabled="store.isLoading" class="px-5 py-2 rounded-lg bg-blue-600 disabled:opacity-40 font-semibold">{{ store.isLoading ? '掃描中…' : '掃描 GGUF' }}</button>
      </div>
      <input v-model="search" class="w-full px-4 py-2 rounded-lg bg-white/5 border border-white/15" placeholder="搜尋模型名稱" />
      <p class="text-xs text-white/45">選擇後請到「Llama 執行設定」按「套用並重啟」。</p>
    </section>
    <section class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <button v-for="model in filteredModels" :key="model.path" @click="selectModel(model.path)"
        :class="['text-left rounded-xl border p-4 transition', store.selectedModelPath === model.path ? 'border-cyan-400 bg-cyan-500/10' : 'border-white/10 bg-white/5 hover:bg-white/10']">
        <div class="font-semibold break-words">{{ model.name }}</div><div class="text-sm text-white/50 mt-2">{{ model.size_mb.toFixed(0) }} MB</div>
        <div class="text-xs text-white/35 mt-2 break-all">{{ model.path }}</div>
        <div v-if="store.selectedModelPath === model.path" class="text-cyan-300 text-sm mt-3">✓ 已選為下次載入模型</div>
      </button>
    </section>
    <div v-if="!store.isLoading && filteredModels.length === 0" class="text-center text-white/45 py-16">尚未找到 GGUF 模型</div>
  </div>
</template>
