<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { llamaApi, type TranslationModelRecommendationInfo } from '../services/llamaApi';
import { useLlamaStore } from '../stores/llama';

const router = useRouter();
const llamaStore = useLlamaStore();
const data = ref<TranslationModelRecommendationInfo | null>(null);
const loading = ref(false);
const error = ref('');
const filter = ref<'all' | 'recommended' | 'novel_game'>('all');

const visibleModels = computed(() => (data.value?.models || []).filter(model => {
  if (filter.value === 'recommended') return model.fit === 'recommended';
  if (filter.value === 'novel_game') return model.category === 'novel_game';
  return true;
}));

const fitText = { recommended: '推薦', possible: '可嘗試', unknown: '需手動確認', not_recommended: '顯存不足' };

async function load(refresh = false) {
  loading.value = true;
  error.value = '';
  try { data.value = await llamaApi.getModelRecommendations(refresh); }
  catch (reason: any) { error.value = reason?.response?.data?.detail || reason?.message || '硬體偵測失敗'; }
  finally { loading.value = false; }
}

async function applyDeployment(model: TranslationModelRecommendationInfo['models'][number]) {
  if (!model.deployment_config) return;
  llamaStore.updateServerConfig(model.deployment_config);
  await llamaStore.saveConfig();
  await router.push({ path: '/settings', query: { tab: 'llama', recommended_model: model.id } });
}

onMounted(() => load(false));
</script>

<template>
  <div class="mx-auto max-w-7xl space-y-5 p-5">
    <header class="flex flex-col gap-3 border-b border-white/10 pb-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <p class="text-xs font-bold uppercase tracking-[0.18em] text-cyan-300">Local translation model finder</p>
        <h1 class="mt-1 text-2xl font-bold">✨ 推薦翻譯模型下載</h1>
        <p class="mt-1 text-sm text-white/50">依顯卡型號與 VRAM 自動排序 GGUF 建議，下載後放入模型目錄再到 LLM 模型管理掃描。</p>
      </div>
      <button class="rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-4 py-2 text-sm font-semibold text-cyan-100 hover:bg-cyan-500/20 disabled:opacity-50" :disabled="loading" @click="load(true)">
        {{ loading ? '偵測中…' : '重新偵測硬體' }}
      </button>
    </header>

    <div v-if="error" class="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-red-200">{{ error }}</div>

    <section class="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
      <div class="rounded-2xl border border-cyan-400/20 bg-gradient-to-br from-cyan-500/10 to-indigo-500/10 p-5">
        <p class="text-xs font-semibold text-white/45">目前建議依據</p>
        <template v-if="data?.selected_gpu">
          <h2 class="mt-1 text-xl font-bold">{{ data.selected_gpu.name }}</h2>
          <div class="mt-3 flex flex-wrap gap-2 text-sm">
            <span class="rounded-full bg-white/10 px-3 py-1">{{ data.vram_gb }} GB VRAM</span>
            <span class="rounded-full bg-white/10 px-3 py-1 uppercase">{{ data.selected_gpu.backend }}</span>
            <span class="rounded-full bg-white/10 px-3 py-1">獨立顯卡</span>
          </div>
        </template>
        <template v-else>
          <h2 class="mt-1 text-lg font-bold">未讀取到可用的獨立顯卡 VRAM</h2>
          <p class="mt-2 text-sm text-amber-200">仍可瀏覽模型；請按模型容量與系統記憶體手動選擇。</p>
        </template>
      </div>
      <div class="rounded-2xl border border-white/10 bg-white/5 p-5 text-sm text-white/60">
        <p class="font-semibold text-white">判斷方式</p>
        <p class="mt-2 leading-6">{{ data?.notice || '正在讀取硬體資訊…' }}</p>
        <p v-if="data && data.detected_gpus.length > 1" class="mt-2 text-xs text-white/40">偵測到 {{ data.detected_gpus.length }} 張顯示裝置，已使用 VRAM 最大的獨立顯卡評估。</p>
        <p class="mt-2 text-xs text-amber-200/80">Sakura 系列模型標示為 CC BY-NC-SA 4.0、禁止商用；使用前請再次閱讀各模型頁授權。</p>
      </div>
    </section>

    <div class="flex flex-wrap gap-2">
      <button v-for="item in [{id:'all',label:'全部'}, {id:'recommended',label:'適合此電腦'}, {id:'novel_game',label:'小說／遊戲專用'}]" :key="item.id"
        :class="['rounded-full px-4 py-2 text-sm font-semibold transition', filter === item.id ? 'bg-indigo-500 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10']"
        @click="filter = item.id as any">{{ item.label }}</button>
    </div>

    <section class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <article v-for="model in visibleModels" :key="model.id" class="flex min-h-[290px] flex-col rounded-2xl border border-white/10 bg-slate-950/65 p-5 shadow-lg shadow-black/10">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div v-if="model.app_preferred" class="mb-1 w-fit rounded-full bg-emerald-500/15 px-2.5 py-1 text-[11px] font-bold text-emerald-300">★ 本程式首選</div>
            <h2 class="font-bold leading-5">{{ model.name }}</h2><p class="mt-1 text-xs text-white/35">{{ model.repo }}</p>
          </div>
          <span :class="['shrink-0 rounded-full px-2.5 py-1 text-xs font-bold', model.fit === 'recommended' ? 'bg-emerald-500/15 text-emerald-300' : model.fit === 'possible' ? 'bg-amber-500/15 text-amber-200' : model.fit === 'not_recommended' ? 'bg-red-500/15 text-red-200' : 'bg-white/10 text-white/60']">{{ fitText[model.fit] }}</span>
        </div>
        <div v-if="model.use_case" class="mt-3 w-fit rounded-md border border-fuchsia-400/25 bg-fuchsia-500/10 px-2.5 py-1 text-xs font-semibold text-fuchsia-200">{{ model.use_case }}</div>
        <p v-if="model.app_preference_reason" class="mt-3 rounded-lg border border-emerald-400/20 bg-emerald-500/5 p-2.5 text-xs leading-5 text-emerald-100/80">{{ model.app_preference_reason }}</p>
        <p class="mt-4 text-sm leading-6 text-white/65">{{ model.summary }}</p>
        <div class="mt-4 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
          <div class="rounded-lg border border-amber-400/15 bg-amber-500/5 p-3">
            <span class="text-amber-200/70">最低可用量化</span>
            <strong class="mt-1 block text-white/80">{{ model.minimum_quant }} · {{ model.minimum_size_gb }} GB</strong>
            <span class="mt-1 block text-white/40">最低 {{ model.min_vram_gb }} GB VRAM；品質可能下降</span>
          </div>
          <div class="rounded-lg border border-emerald-400/15 bg-emerald-500/5 p-3">
            <span class="text-emerald-200/70">建議量化</span>
            <strong class="mt-1 block text-white/80">{{ model.recommended_quant }} · {{ model.model_size_gb }} GB</strong>
            <span class="mt-1 block text-white/40">建議 {{ model.comfortable_vram_gb }} GB VRAM</span>
          </div>
        </div>
        <p class="mt-2 text-[11px] leading-5 text-white/35">{{ model.vram_basis }}</p>
        <div v-if="model.deployment_config" class="mt-3 rounded-lg border border-cyan-400/15 bg-cyan-500/5 p-3 text-xs">
          <p class="font-semibold text-cyan-200">建議部署參數</p>
          <p class="mt-1 leading-5 text-white/60">
            T={{ model.deployment_config.temp }} · P={{ model.deployment_config.top_p }} · K={{ model.deployment_config.top_k }}
            <template v-if="model.deployment_config.repeat_penalty"> · Repeat={{ model.deployment_config.repeat_penalty }}</template>
            <template v-if="model.deployment_config.n_ctx"> · Ctx={{ model.deployment_config.n_ctx }}</template>
            <template v-if="model.deployment_config.n_predict"> · Max={{ model.deployment_config.n_predict }}</template>
          </p>
          <p class="mt-1 text-white/35">{{ model.parameter_source }}</p>
          <p v-if="model.runtime_note" class="mt-2 leading-5 text-amber-200/80">⚠ {{ model.runtime_note }}</p>
        </div>
        <p class="mt-3 text-xs leading-5 text-white/45">{{ model.fit_reason }}</p>
        <div class="mt-auto grid gap-2 pt-4">
          <button v-if="model.deployment_config" type="button" class="rounded-lg border border-cyan-400/30 bg-cyan-500/10 px-4 py-2.5 text-sm font-bold text-cyan-100 hover:bg-cyan-500/20" @click="applyDeployment(model)">套用部署參數</button>
          <a :href="model.url" target="_blank" rel="noopener noreferrer" class="rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2.5 text-center text-sm font-bold hover:from-blue-500 hover:to-indigo-500">開啟 GGUF 下載頁 ↗</a>
        </div>
      </article>
    </section>
    <div v-if="!loading && visibleModels.length === 0" class="py-12 text-center text-white/45">這個篩選條件目前沒有合適模型。</div>
  </div>
</template>
