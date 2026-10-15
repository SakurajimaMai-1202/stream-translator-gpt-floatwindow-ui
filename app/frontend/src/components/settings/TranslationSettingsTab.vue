<script setup lang="ts">
import { onMounted, reactive, toRaw } from 'vue';
import axios from 'axios';
import UiSelect from '../UiSelect.vue';
import { useSettingsTabBindings } from '../../composables/settings/settingsContext';
const {
  glossaryScopeOptions, activeTab, activeTranslationFamily, familyDetecting, servedModels, scheduleFamilyDetection, checkHyMt2Backend, deleteCustomModel, effectiveGlossaryCount, familyLabel, familySettings, hyMt2EffectiveBackend, hyMt2HealthChecking, hyMt2HealthResult, localConfig, openCustomModelDialog, previewBusy, previewContext, previewError, previewLatencyLabel, previewResult, previewText, previewValidationStatus, runTranslationPreview, selectedGlossaryPresetLabel, targetLanguageOptions, testConnection, testingGemini, testingGpt, translationBackendOptions, translationModelFamilyOptions, translationOutputFormatOptions
} = useSettingsTabBindings();
type CloudBackend = 'gpt' | 'gemini';
const cloudModels = reactive<Record<CloudBackend, { ids: string[]; busy: boolean; status: string }>>({
  gpt: { ids: [], busy: false, status: '' },
  gemini: { ids: [], busy: false, status: '' },
});
async function loadCloudModels(backend: CloudBackend) {
  const state = cloudModels[backend];
  state.busy = true;
  state.ids = [];
  state.status = '正在載入…';
  try {
    const response = await axios.post('/api/translation/list-models', {
      backend, config: { translation: toRaw(localConfig.value.translation) },
    });
    state.ids = response.data.models;
    state.status = state.ids.length ? `已載入 ${state.ids.length} 個模型` : '帳號沒有可用模型';
  } catch (error: any) {
    state.status = error?.response?.data?.detail || '載入失敗，請稍後再試';
  } finally { state.busy = false; }
}
// The preview returns glossary_hits as {source: target}.
function glossaryHitLabels(hits: unknown): string[] {
  if (!hits || typeof hits !== 'object') return [];
  return Object.entries(hits as Record<string, unknown>).map(([source, target]) => `${source}→${target}`);
}
// Re-check whenever the tab opens; the server may have switched models meanwhile.
onMounted(scheduleFamilyDetection);
</script>

<template>
          <div class="settings-paint-section apple-settings apple-translation">
            <header class="apple-page-header"><h2>翻譯選項</h2><p>選擇翻譯服務與語言，再依模型調整術語、前文與字幕風格。</p></header>

            <!-- 基本翻譯設定 -->
            <div class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="commercial-section-title">基本設定</h3>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label class="block text-white/70 font-semibold mb-2">翻譯服務</label>
                  <UiSelect aria-label="翻譯服務" v-model="localConfig.translation.backend" :options="translationBackendOptions" />
                  <p class="text-white/40 text-xs mt-1">雲端服務需要 API Key；本機模型在「本地翻譯」頁設定。</p>
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2">目標語言</label>
                  <UiSelect aria-label="目標語言" v-model="localConfig.translation.target_language" :options="targetLanguageOptions" />
                  <p class="text-white/40 text-xs mt-1">翻譯的目標語言</p>
                </div>
              </div>

            <!-- OpenAI GPT 設定 -->
            <div v-if="localConfig.translation.backend === 'gpt'" class="mt-4">
              <h3 class="text-lg font-semibold text-green-300 mb-4">OpenAI GPT</h3>
              <div class="space-y-4">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">GPT 模型</label>
                    <div class="flex gap-2">
                    <input v-model="localConfig.translation.gpt_model" type="text" list="gpt-available-models" placeholder="gpt-4o-mini"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-green-400" />
                      <button type="button" @click="loadCloudModels('gpt')" :disabled="cloudModels.gpt.busy" class="shrink-0 px-3 py-2 rounded-lg bg-blue-600/20 text-blue-300 text-xs disabled:opacity-50">載入可用模型</button>
                    </div>
                    <datalist id="gpt-available-models"><option v-for="id in cloudModels.gpt.ids" :key="id" :value="id" /></datalist>
                    <p role="status" aria-live="polite" class="text-white/60 text-xs mt-1">{{ cloudModels.gpt.status }}</p>
                    <p class="text-white/40 text-xs mt-1">可直接輸入模型名稱，或按「載入可用模型」從帳號讀取。</p>
                  </div>

                  <div>
                    <label class="block text-white/70 font-semibold mb-2">API Key <span class="text-white/40 text-xs">(選填)</span></label>
                    <div class="flex gap-2">
                      <input v-model="localConfig.translation.openai_api_key" type="password" placeholder="sk-..."
                        class="flex-1 px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-green-400" />
                      <button @click="testConnection('gpt')" :disabled="testingGpt" 
                        class="bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 font-semibold px-4 rounded-lg transition text-xs whitespace-nowrap flex items-center justify-center gap-1.5 min-w-[95px]">
                        <span v-if="testingGpt" class="inline-block w-3 h-3 border-2 border-blue-300 border-t-transparent rounded-full animate-spin"></span>
                        <span>測試連線</span>
                      </button>
                    </div>
                    <p class="text-white/50 text-xs mt-1">僅供 OpenAI GPT 雲端翻譯使用，不會提供給 OpenAI 語音轉錄或 Gemini。</p>
                  </div>

                  <details class="md:col-span-2 apple-inline-disclosure"><summary>API 端點</summary><div class="apple-disclosure-body">
                    <label class="block text-white/70 font-semibold mb-2">API Base URL</label>
                    <input v-model="localConfig.translation.gpt_base_url" type="text" placeholder="https://api.openai.com/v1"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-green-400" />
                    <p class="text-white/40 text-xs mt-1">OpenAI 預設端點；使用相容服務時可自行修改。</p>
                  </div></details>
                </div>
              </div>
            </div>

            <!-- Google Gemini 設定 -->
            <div v-if="localConfig.translation.backend === 'gemini'" class="mt-4">
              <h3 class="text-lg font-semibold text-blue-300 mb-4">Google Gemini</h3>
              <div class="space-y-4">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">Gemini 模型</label>
                    <div class="flex gap-2">
                    <input v-model="localConfig.translation.gemini_model" type="text" list="gemini-available-models" placeholder="gemini-2.5-flash-lite"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                      <button type="button" @click="loadCloudModels('gemini')" :disabled="cloudModels.gemini.busy" class="shrink-0 px-3 py-2 rounded-lg bg-blue-600/20 text-blue-300 text-xs disabled:opacity-50">載入可用模型</button>
                    </div>
                    <datalist id="gemini-available-models"><option v-for="id in cloudModels.gemini.ids" :key="id" :value="id" /></datalist>
                    <p role="status" aria-live="polite" class="text-white/60 text-xs mt-1">{{ cloudModels.gemini.status }}</p>
                    <p class="text-white/40 text-xs mt-1">可直接輸入模型名稱，或按「載入可用模型」從帳號讀取。</p>
                  </div>

                  <div>
                    <label class="block text-white/70 font-semibold mb-2">API Key <span class="text-white/40 text-xs">(選填)</span></label>
                    <div class="flex gap-2">
                      <input v-model="localConfig.translation.google_api_key" type="password" placeholder="AIza..."
                        class="flex-1 px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                      <button @click="testConnection('gemini')" :disabled="testingGemini" 
                        class="bg-blue-600/20 hover:bg-blue-600/40 text-blue-300 border border-blue-500/30 font-semibold px-4 rounded-lg transition text-xs whitespace-nowrap flex items-center justify-center gap-1.5 min-w-[95px]">
                        <span v-if="testingGemini" class="inline-block w-3 h-3 border-2 border-blue-300 border-t-transparent rounded-full animate-spin"></span>
                        <span>測試連線</span>
                      </button>
                    </div>
                    <p class="text-white/50 text-xs mt-1">僅供 Google Gemini 雲端翻譯使用，不會用於 ASR 或 OpenAI GPT。</p>
                  </div>

                  <details class="md:col-span-2 apple-inline-disclosure"><summary>API 端點</summary><div class="apple-disclosure-body">
                    <label class="block text-white/70 font-semibold mb-2">API Base URL（通常不用修改）</label>
                    <input v-model="localConfig.translation.gemini_base_url" type="text" placeholder="https://generativelanguage.googleapis.com/v1beta"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                    <p class="text-white/40 text-xs mt-1">Gemini REST API 的版本端點；官方服務通常保留 /v1beta 即可。</p>
                  </div></details>
                </div>
              </div>
            </div>

            <section v-if="localConfig.translation.backend.startsWith('custom:')" class="apple-current-service mt-4">
              <div><h3>目前自訂服務</h3><p>{{ localConfig.translation.backend.replace('custom:', '') }}</p></div>
              <div class="apple-endpoint-copy" v-for="model in (localConfig.translation.custom_models || []).filter((item: any) => item.name === localConfig.translation.backend.replace('custom:', ''))" :key="model.name">
                <span>{{ model.model_name || '未指定模型 ID' }}</span><span>{{ model.base_url || model.api_base || '預設端點' }}</span>
              </div>
            </section>
              <div v-if="localConfig.translation.backend !== 'none'" class="mt-4">
                <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition">
                  <input v-model="localConfig.translation.paired_subtitle_mode" type="checkbox"
                    class="w-5 h-5 accent-blue-500 mt-0.5" />
                  <div>
                    <span class="text-white font-medium">原文與翻譯成對顯示</span>
                    <p class="text-white/50 text-sm mt-1">翻譯完成前不顯示該組字幕；翻譯失敗時略過整組，避免原文與譯文錯位。</p>
                  </div>
                </label>
              </div>
            </div>
            <!-- 進階翻譯設定 (所有後端共用，但不翻譯時隱藏) -->
            <div v-if="localConfig.translation.backend !== 'none'" class="bg-white/5 rounded-xl p-5 border border-white/10">
              <h3 class="commercial-section-title">翻譯優化</h3>
              <p class="text-white/40 text-xs mt-2"><template v-if="familyDetecting">正在偵測模型…</template><template v-else-if="localConfig.translation.translation_model_family === 'auto' && ['hy_mt2', 'index_translate'].includes(activeTranslationFamily)">已自動偵測到 {{ familyLabel }}<template v-if="servedModels.length">（伺服器模型：{{ servedModels[0] }}）</template></template><template v-else>模型類型：{{ translationModelFamilyOptions.find(option => option.value === activeTranslationFamily)?.label || '一般翻譯' }}<template v-if="servedModels.length">（伺服器模型：{{ servedModels[0] }}）</template>。如果模型沒有被正確識別，可在下方「進階：模型與推理設定」手動指定。</template></p>
              <label class="mt-4 flex items-center gap-2 font-semibold text-white"><input v-model="localConfig.translation.family_optimizer_auto" type="checkbox" class="h-4 w-4 accent-blue-500" />依模型自動套用翻譯優化</label>
              <p class="mt-1 text-sm text-white/55">偵測到 HY-MT2 或 Index-Translate 時，自動使用術語、前文與台灣繁中風格。</p>
              <div v-if="['hy_mt2', 'index_translate'].includes(activeTranslationFamily)" class="mt-4 border-t border-white/10 pt-4">
              <div class="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p class="font-semibold text-white">{{ familyLabel }} 翻譯優化</p>
                  <p class="mt-1 text-sm text-white/55">讓日文直播字幕參考術語、前文與台灣繁中風格。</p>
                </div>
                <label :class="['flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm font-semibold text-white', localConfig.translation.family_optimizer_auto ? 'cursor-default' : 'cursor-pointer']">
                  <input v-if="!localConfig.translation.family_optimizer_auto" v-model="localConfig.translation[familySettings + '_optimizer_enabled']" type="checkbox" class="h-4 w-4 accent-blue-500" />
                  {{ localConfig.translation.family_optimizer_auto ? '術語與前文：自動套用' : (localConfig.translation[familySettings + '_optimizer_enabled'] ? '術語與前文已啟用' : '啟用術語與前文') }}
                </label>
              </div>
              <div class="mt-4 flex flex-wrap items-center gap-2">
                <button type="button" :disabled="hyMt2HealthChecking" class="rounded-lg bg-white/10 px-3 py-2 text-sm text-white hover:bg-white/20 disabled:opacity-50" @click="checkHyMt2Backend">{{ hyMt2HealthChecking ? '連線測試中…' : '測試模型連線' }}</button>
              </div>
              <p v-if="hyMt2HealthResult" class="mt-2 text-sm text-white/75" role="status">{{ hyMt2HealthResult }}</p>
              <div class="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-blue-400/20 bg-blue-400/5 px-3 py-2 text-sm text-white/70">
                <span>術語情境：{{ selectedGlossaryPresetLabel }}</span>
                <UiSelect v-model="localConfig.translation.translation_glossary_scope" :options="[{ value: '', label: '全域術語' }, ...glossaryScopeOptions]" />
                <span class="text-white/35">·</span>
                <span>約 {{ effectiveGlossaryCount }} 個原詞</span>
                <button type="button" class="text-blue-300 underline" @click="activeTab = 'terminology'">管理術語</button>
              </div>
              <details class="mt-4 border-t border-white/10 pt-4 space-y-3">
                <summary class="cursor-pointer font-semibold text-blue-200">試譯與策略比較</summary>
                <textarea v-model="previewText" maxlength="4000" rows="3" aria-label="試譯日文" placeholder="輸入目前要翻譯的日文" class="w-full rounded-lg border border-white/20 bg-white/5 p-3 text-white" />
                <textarea v-model="previewContext" maxlength="4000" rows="2" aria-label="試譯前文" placeholder="前文（選填；每行一句，最多 5 句）" class="w-full rounded-lg border border-white/20 bg-white/5 p-3 text-white" />
                <button type="button" :disabled="previewBusy || !previewText.trim()" class="rounded-lg bg-blue-500/25 px-3 py-2 text-blue-100 disabled:opacity-50" @click="runTranslationPreview">{{ previewBusy ? '正在比較…' : '比較基本與優化' }}</button>
                <p v-if="previewError" role="alert" class="text-red-300">{{ previewError }}</p>
                <div v-if="previewResult" class="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <article v-for="mode in ['basic', 'optimized']" :key="mode" class="rounded-lg border border-white/15 p-3 space-y-2">
                    <h5 class="text-blue-200">{{ mode === 'basic' ? (activeTranslationFamily === 'hy_mt2' ? '基本翻譯（沿用詞庫）' : '基本翻譯') : '優化翻譯' }}</h5>
                    <p class="text-white whitespace-pre-wrap">{{ previewResult[mode].translation || '未取得可用譯文' }}</p>
                    <p v-if="previewResult[mode].error" role="alert" class="text-sm text-red-300">{{ previewResult[mode].error }}</p>
                    <p class="text-xs text-white/60">耗時 {{ previewLatencyLabel(previewResult[mode].latency_ms) }} · 修正 {{ previewResult[mode].retry_count }} 次</p>
                    <div class="flex flex-wrap items-center gap-1 text-xs text-white/60">
                      <span>命中術語：</span>
                      <span v-for="label in glossaryHitLabels(previewResult[mode].glossary_hits)" :key="label" class="rounded-full bg-blue-500/20 px-2 py-0.5">{{ label }}</span>
                      <span v-if="!glossaryHitLabels(previewResult[mode].glossary_hits).length">無</span>
                    </div>
                    <p class="text-xs text-white/60">驗證：{{ previewValidationStatus(previewResult[mode]) }}</p>
                    <p class="text-xs text-white/45">{{ previewResult[mode].validation_enforced ? '異常譯文會自動重試修正' : '基本結果只顯示檢查結果，不自動修正' }}</p>
                    <details v-if="previewResult[mode].attempts?.length" class="text-xs text-white/60">
                      <summary class="cursor-pointer">檢視技術記錄</summary>
                      <pre class="mt-2 whitespace-pre-wrap break-all">{{ JSON.stringify(previewResult[mode].attempts, null, 2) }}</pre>
                    </details>
                  </article>
                </div>
                <p class="text-xs text-white/45">試譯使用目前設定與直播相同策略；結果不代表日文譯意已人工驗證。</p>
              </details>
              </div>
              <p v-else-if="!familyDetecting" class="mt-4 text-sm text-white/60">這個模型沒有專屬翻譯優化，使用一般翻譯。</p>
              <details class="apple-inline-disclosure mt-4">
                <summary>進階：模型與推理設定</summary>
                <div class="apple-disclosure-body">
              <UiSelect aria-label="模型翻譯策略" v-model="localConfig.translation.translation_model_family" :options="translationModelFamilyOptions" />
              <div v-if="['hy_mt2', 'index_translate'].includes(activeTranslationFamily)">
              <div class="mt-4">
                <div class="mt-3 space-y-1 text-xs text-white/55">
                  <p>目前模型：{{ hyMt2EffectiveBackend }}</p>
                  <p>模型測試只確認連線與回應格式；設定會在重新開始翻譯工作階段後生效。</p>
                  <p v-if="localConfig.translation[familySettings + '_glossary_folder']">JSON 術語資料夾未計入上方數量。</p>
                </div>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                <div class="md:col-span-2">
                  <label class="block text-white/70 mb-1">模型伺服器</label>
                  <UiSelect v-model="localConfig.translation[familySettings + '_provider']" :options="[
                    { value: 'existing', label: '沿用目前翻譯服務' },
                    { value: 'lm_studio', label: 'LM Studio' },
                    { value: 'llama_cpp', label: '本機 llama.cpp 伺服器' }
                  ]" />
                </div>
                <template v-if="localConfig.translation[familySettings + '_provider'] === 'lm_studio'">
                  <label class="text-white/70">LM Studio Server URL
                    <input v-model="localConfig.translation[familySettings + '_lm_studio_url']" type="text" placeholder="http://127.0.0.1:1234/v1" class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                  </label>
                  <label class="text-white/70">模型名稱（需與伺服器顯示的一致）
                    <input v-model="localConfig.translation[familySettings + '_lm_studio_model']" type="text" placeholder="伺服器上的模型名稱" class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                  </label>
                  <label class="text-white/70">此服務 API Key（選填）
                    <input v-model="localConfig.translation[familySettings + '_lm_studio_api_key']" type="password" autocomplete="off" placeholder="服務要求驗證時填寫" class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                  </label>
                </template>
                <template v-if="localConfig.translation[familySettings + '_provider'] === 'llama_cpp'">
                  <label class="text-white/70">llama-server URL
                    <input v-model="localConfig.translation[familySettings + '_llama_cpp_url']" type="text" placeholder="http://127.0.0.1:8081/v1" class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                  </label>
                  <label class="text-white/70">模型名稱（需與伺服器顯示的一致）
                    <input v-model="localConfig.translation[familySettings + '_llama_cpp_model']" type="text" placeholder="伺服器上的模型名稱" class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                  </label>
                  <label class="text-white/70">此服務 API Key（選填）
                    <input v-model="localConfig.translation[familySettings + '_llama_cpp_api_key']" type="password" autocomplete="off" placeholder="服務要求驗證時填寫" class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                  </label>
                </template>
              </div>
              </div>
              <details class="mt-4 rounded-lg border border-white/10 p-3">
                <summary class="cursor-pointer text-sm text-blue-200">術語、前文與風格設定</summary>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                <label class="text-white/70 md:col-span-2">JSON 術語資料夾（選填；相對於設定檔）
                  <input v-model="localConfig.translation[familySettings + '_glossary_folder']" type="text" placeholder="例如：data/glossary" class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                </label>
                <label class="text-white/70">前文句數（0–5）
                  <input v-model.number="localConfig.translation[familySettings + '_context_window']" type="number" min="0" max="5" class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                </label>
                <label class="text-white/70">前文字數上限
                  <input v-model.number="localConfig.translation[familySettings + '_max_context_chars']" type="number" min="0" max="4000" class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                </label>
                <label class="text-white/70">最多術語數
                  <input v-model.number="localConfig.translation[familySettings + '_max_terms']" type="number" min="0" max="30" class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                </label>
                <label class="flex items-center gap-2 text-white/70"><input v-model="localConfig.translation[familySettings + '_style']" type="checkbox" />台灣口語字幕風格</label>
                <label v-if="localConfig.translation[familySettings + '_style']" class="text-white/70 md:col-span-2">字幕風格指示（最多 500 字）
                  <textarea v-model="localConfig.translation[familySettings + '_style_text']" maxlength="500" rows="2" class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                </label>
                <label class="text-white/70 md:col-span-2">個人翻譯偏好（最多 500 字）
                  <textarea v-model="localConfig.translation[familySettings + '_preferences']" maxlength="500" rows="2" class="w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" placeholder="例如：人名沿用術語表，不任意補主詞" />
                </label>
                <label class="flex items-center gap-2 text-white/70"><input v-model="localConfig.translation[familySettings + '_debug']" type="checkbox" />記錄提示詞與輸出（包含字幕內容）</label>
              </div>
              </details>
              </div>
                </div>
              </details>
            </div>
                        <!-- 自訂模型管理（固定顯示，避免切換後端時找不到） -->
            <details class="apple-disclosure"><summary>自訂模型管理<span>{{ localConfig.translation.custom_models?.length || 0 }} 個服務</span></summary><div class="apple-disclosure-body">
              <div class="flex items-center justify-between mb-4">
                <div>
                  <h3 class="text-lg font-semibold text-orange-300">自訂模型管理</h3>
                  <p class="text-white/50 text-xs mt-1">管理相容 OpenAI API 的自訂模型端點</p>
                </div>
                <button @click="openCustomModelDialog()" class="bg-orange-600 hover:bg-orange-700 text-white font-semibold py-2 px-4 rounded-lg transition flex items-center gap-2">
                  <span>+</span>
                  <span>新增模型</span>
                </button>
              </div>

              <div v-if="localConfig.translation.custom_models && localConfig.translation.custom_models.length > 0" class="space-y-2">
                <div v-for="(model, idx) in localConfig.translation.custom_models" :key="idx"
                  class="flex items-center justify-between p-4 bg-white/5 rounded-lg border border-white/10 hover:border-orange-500/30 transition">
                  <div class="flex-1">
                    <div class="flex items-center gap-2">
                      <span class="text-white font-medium">{{ model.name }}</span>
                      <span class="px-2 py-0.5 bg-orange-500/20 text-orange-300 text-xs rounded">自訂</span>
                    </div>
                    <div class="flex items-center gap-3 mt-1 text-sm text-white/40">
                      <span>{{ model.model_name }}</span>
                      <span>•</span>
                      <span class="truncate max-w-xs">{{ model.base_url || model.api_base || '預設端點' }}</span>
                    </div>
                  </div>
                  <div class="flex gap-2 ml-4">
                    <button @click="openCustomModelDialog(Number(idx))" class="px-3 py-1.5 bg-blue-500/20 hover:bg-blue-500/30 text-blue-400 rounded transition">
                      編輯
                    </button>
                    <button @click="deleteCustomModel(Number(idx))" class="px-3 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded transition">
                      刪除
                    </button>
                  </div>
                </div>
              </div>
              <div v-else class="text-center py-6 text-white/40">

                <div class="text-sm">尚未新增自訂模型</div>
                <div class="text-xs mt-1">點擊上方按鈕新增第一個模型</div>
              </div>
            </div></details>


            <details v-if="localConfig.translation.backend !== 'none'" class="apple-disclosure">
              <summary>進階設定</summary><div class="apple-disclosure-body">
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">


                <div>
                  <label class="block text-white/70 font-semibold mb-2">輸出格式</label>
                  <UiSelect v-model="localConfig.translation.translation_output_format" :options="translationOutputFormatOptions" />
                  <p class="text-white/40 text-xs mt-1">HY-MT2 與 Index-Translate 使用純文字；支援的 API 才會使用 JSON。</p>
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2 flex items-center gap-1.5">
                    歷史訊息數量
                    <span class="tooltip-container text-white/40 hover:text-blue-300 transition text-sm">
                      ⓘ
                      <span class="tooltip-text">
                        提供最近字幕作為理解背景。大於 0 時會強制單工翻譯，避免上下文順序錯亂。
                      </span>
                    </span>
                  </label>
                  <input v-model.number="localConfig.translation.translation_history_size" type="number" min="0" max="20"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2 flex items-center gap-1.5">
                    翻譯超時 (秒)
                    <span class="tooltip-container text-white/40 hover:text-blue-300 transition text-sm">
                      ⓘ
                      <span class="tooltip-text">
                        翻譯 API 的最長等待時間，超過此時間將跳過該句以避免延遲累積。
                      </span>
                    </span>
                  </label>
                  <input v-model.number="localConfig.translation.translation_timeout" type="number" min="5" max="60"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2">最大並行翻譯數</label>
                  <input v-model.number="localConfig.translation.translation_max_concurrency" type="number" min="0" max="8"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-white/40 text-xs mt-1">0 使用策略預設；本地模型建議 1，線上 API 建議 2。</p>
                </div>

                <div>
                  <label class="block text-white/70 font-semibold mb-2">每段最大輸出 Token</label>
                  <input v-model.number="localConfig.translation.translation_max_output_tokens" type="number" min="16" max="2048" step="16"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  <p class="text-white/40 text-xs mt-1">直播短字幕建議 128，較長字幕可使用 192 或 256。</p>
                </div>

                <div>
                  <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer">
                    <input v-model="localConfig.translation.deduplicate_asr_overlap" type="checkbox"
                      class="w-5 h-5 accent-blue-500 mt-0.5" />
                    <span>
                      <span class="block text-white font-medium">跨片段重疊去重</span>
                      <span class="block text-white/50 text-sm mt-1">翻譯前移除相鄰 ASR 片段重複的開頭文字。</span>
                    </span>
                  </label>
                </div>

                <div>
                  <label class="flex items-start gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer">
                    <input v-model="localConfig.translation.subtitle_assembler_enabled" type="checkbox"
                      class="w-5 h-5 accent-blue-500 mt-0.5" />
                    <span>
                      <span class="block text-white font-medium">字幕組句器</span>
                      <span class="block text-white/50 text-sm mt-1">不完整句短暫等待下一個 ASR 片段，再一起翻譯。</span>
                    </span>
                  </label>
                </div>

                <template v-if="localConfig.translation.subtitle_assembler_enabled">
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">組句等待上限 (ms)</label>
                    <input v-model.number="localConfig.translation.subtitle_assembler_wait_ms" type="number"
                      min="0" max="2000" step="50"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  </div>
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">組句最大音訊跨度 (秒)</label>
                    <input v-model.number="localConfig.translation.subtitle_assembler_max_duration" type="number"
                      min="1" max="20" step="0.5"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  </div>
                  <div>
                    <label class="block text-white/70 font-semibold mb-2">可合併片段間隔 (秒)</label>
                    <input v-model.number="localConfig.translation.subtitle_assembler_gap_threshold" type="number"
                      min="0" max="5" step="0.1"
                      class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white focus:outline-none focus:border-blue-400" />
                  </div>
                </template>

                <div class="md:col-span-2">
                  <label class="block text-white/70 font-semibold mb-2 flex items-center gap-1.5">
                    處理代理伺服器 <span class="text-white/40 text-xs">(選填)</span>
                    <span class="tooltip-container text-white/40 hover:text-blue-300 transition text-sm">
                      ⓘ
                      <span class="tooltip-text">
                        為 Whisper 和 GPT API 的呼叫設定 HTTP/S 代理伺服器（Google Gemini API 目前不支援此代理設定）。
                      </span>
                    </span>
                  </label>
                  <input v-model="localConfig.translation.processing_proxy" type="text" placeholder="http://127.0.0.1:7890"
                    class="w-full px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400" />
                </div>

              </div>
              <section class="mt-5"><h4 class="commercial-section-title mb-3">提示詞設定</h4>
              <div class="space-y-4">
                <label class="flex items-center gap-3 p-3 bg-white/5 rounded-lg border border-white/10 cursor-pointer hover:bg-white/10 transition">
                  <input v-model="localConfig.translation.use_smart_prompt" type="checkbox" class="w-5 h-5 accent-blue-500" />
                  <div class="flex-1">
                    <span class="text-white font-medium">啟用智能提示詞</span>
                    <p class="text-white/50 text-sm mt-1">使用系統預設的智能提示詞進行翻譯優化</p>
                  </div>
                </label>

                <!-- 自訂翻譯提示詞（當關閉智能提示詞時顯示） -->
                <div v-if="!localConfig.translation.use_smart_prompt" class="pt-2">
                  <label class="block text-white/70 font-semibold mb-2">自訂翻譯提示詞</label>
                  <textarea v-model="localConfig.translation.translation_prompt" placeholder='例如: "Translate from Japanese to Traditional Chinese"' rows="5"
                    class="w-full px-4 py-3 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-blue-400 font-mono text-sm"></textarea>
                  <p class="text-white/40 text-sm mt-2">關閉智能提示詞時，將使用此提示詞進行翻譯。</p>
                </div>
              </div>
              </section>
            </div></details>

          </div>
</template>

<style scoped src="./settings-shared.css"></style>
