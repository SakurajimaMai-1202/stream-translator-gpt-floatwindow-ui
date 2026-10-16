<script setup lang="ts">
import { computed } from 'vue';
import UiSelect from '../UiSelect.vue';
import { useSettingsTabBindings } from '../../composables/settings/settingsContext';
const {
  GLOSSARY_PAGE_SIZE, LARGE_LIST_BATCH_SIZE, addAsrCorrection, addGlossaryScope, addTerm, applySelectedGlossaryScope, asrCorrectionRenderLimit, asrCorrectionSearchQuery, asrCorrectionsImporting, bulkGlossaryScope, customGlossaryScopes, customizePresetTerm, editingGlossaryScope, editingGlossaryScopeName, effectiveGlossaryCount, expandedGlossaryTerm, exportAsrCorrections, exportGlossary, filteredAsrCorrections, filteredGlossary, glossaryEntryForm, glossaryImporting, glossaryListMode, glossaryRenderLimit, glossaryScopeOptions, glossaryUserList, importAsrCorrections, importGlossary, localConfig, newAsrAliases, newAsrCanonical, newGlossaryScopeName, newTermAliases, newTermOriginal, newTermScope, newTermTranslated, removeAsrCorrection, removeGlossaryScope, removeTermEntry, removedGlossaryTerm, renameGlossaryScope, selectVisibleGlossaryTerms, selectedGlossaryTerms, selectedPresetPreview, setTermAliases, setTermScope, termSearchQuery, terminologySubTab, toggleGlossarySelection, undoRemovedGlossaryTerm, userGlossaryBySource, visibleAsrCorrections, visibleGlossary, optimizerEffective
} = useSettingsTabBindings();

// Mirrors ASR_PROMPT_BACKENDS in backend/core/hy_mt2_glossary_presets.py.
const asrPromptSupport = computed(() => {
  const t = localConfig.value.transcription || {};
  if (t.use_fun_asr) return { name: 'Fun-ASR-Nano', prompted: true };
  if (t.use_sensevoice_asr) return { name: 'SenseVoice', prompted: false };
  if (t.use_nemo_asr) return { name: 'Parakeet', prompted: false };
  if (t.use_qwen3_asr) return { name: 'Qwen3-ASR', prompted: false };
  if (t.use_openai_transcription_api) return { name: 'OpenAI 轉錄 API', prompted: true };
  const backend = String(t.backend || '').toLowerCase();
  const backends: Record<string, { name: string; prompted: boolean }> = {
    'fun-asr-nano': { name: 'Fun-ASR-Nano', prompted: true },
    sensevoice: { name: 'SenseVoice', prompted: false },
    'parakeet-ctc-ja': { name: 'Parakeet', prompted: false },
    'qwen3-asr': { name: 'Qwen3-ASR', prompted: false },
    'openai-api': { name: 'OpenAI 轉錄 API', prompted: true },
  };
  if (backends[backend]) return backends[backend];
  const model = String(t.model || '').toLowerCase();
  for (const [key, backend] of [['sensevoice', 'sensevoice'], ['parakeet', 'parakeet-ctc-ja'], ['fun-asr', 'fun-asr-nano'], ['qwen3-asr', 'qwen3-asr']]) {
    if (model.includes(key)) return backends[backend];
  }
  return { name: 'Whisper', prompted: true };
});
const glossaryAliasCount = computed(() => (localConfig.value.terminology?.glossary_list || [])
  .filter((term: any) => (Array.isArray(term.aliases) ? term.aliases.length : String(term.aliases || '').trim())).length);
</script>

<template>
          <div class="settings-paint-section apple-settings">
            <header class="apple-page-header"><h2>術語表</h2><p>管理辨識修正、翻譯詞條與使用情境。</p></header>
            <div class="grid grid-cols-2 gap-2 rounded-xl border border-white/10 bg-black/20 p-1" role="tablist" aria-label="術語設定種類">
              <button type="button" role="tab" :aria-selected="terminologySubTab === 'translation'" :class="terminologySubTab === 'translation' ? 'bg-purple-500/25 text-purple-100' : 'text-white/60 hover:bg-white/5'" class="rounded-lg px-4 py-3 font-semibold" @click="terminologySubTab = 'translation'">翻譯詞條</button>
              <button type="button" role="tab" :aria-selected="terminologySubTab === 'asr'" :class="terminologySubTab === 'asr' ? 'bg-cyan-500/25 text-cyan-100' : 'text-white/60 hover:bg-white/5'" class="rounded-lg px-4 py-3 font-semibold" @click="terminologySubTab = 'asr'">ASR 辨識修正</button>
            </div>

            <div v-if="terminologySubTab === 'translation'" class="rounded-xl border border-blue-400/25 bg-blue-400/5 p-5 space-y-4">
              <div>
                <h3 class="text-lg font-semibold text-blue-200">這次要看的內容</h3>
                <p class="mt-1 text-sm text-white/60">切換情境後，下面會顯示這次生效的個人詞條與內建詞條。選擇不會改動已存的詞條；重新開始翻譯工作階段後生效。</p>
              </div>
              <UiSelect v-model="localConfig.translation.translation_glossary_scope" aria-label="這次觀看的情境" :options="[
                { value: '', label: '不加情境詞表（只用我的全域詞條）' },
                ...glossaryScopeOptions.filter((option: { value: string; label: string }) => option.value !== 'all')
              ]" />
              <details class="rounded-lg border border-white/10 bg-black/15 p-3">
                <summary class="cursor-pointer text-sm font-semibold text-white/80">管理自訂情境（{{ customGlossaryScopes.length }} 個）</summary>
                <div class="mt-3 space-y-3">
                <div class="flex flex-wrap gap-2">
                  <input v-model="newGlossaryScopeName" maxlength="40" type="text" aria-label="新情境名稱" placeholder="例如：星街彗星雜談" class="min-w-[200px] flex-1 rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-white" @keyup.enter="addGlossaryScope" />
                  <button type="button" :disabled="!newGlossaryScopeName.trim()" class="rounded-lg bg-blue-600 px-4 py-2 font-semibold text-white disabled:opacity-40" @click="addGlossaryScope">新增情境</button>
                </div>
                <p class="text-xs text-white/50">自訂情境使用你的全域詞條與該情境詞條；建立後可在下方新增詞條。</p>
                <div v-for="scope in customGlossaryScopes" :key="scope.value" class="flex flex-wrap items-center gap-2 rounded-lg bg-white/5 px-3 py-2 text-sm">
                  <template v-if="editingGlossaryScope === scope.value">
                    <input v-model="editingGlossaryScopeName" maxlength="40" :aria-label="`重新命名 ${scope.label}`" class="min-w-[180px] flex-1 rounded border border-white/20 bg-black/20 px-2 py-1 text-white" @keyup.enter="renameGlossaryScope(scope)" />
                    <button type="button" class="text-blue-300" @click="renameGlossaryScope(scope)">完成</button>
                    <button type="button" class="text-white/60" @click="editingGlossaryScope = ''">取消</button>
                  </template>
                  <template v-else>
                    <span class="min-w-0 flex-1 text-white/80">{{ scope.label }}（{{ (localConfig.terminology.glossary_list || []).filter((term: any) => term.scope === scope.value).length }} 筆）</span>
                    <button type="button" class="text-blue-300" :aria-label="`重新命名 ${scope.label}`" @click="editingGlossaryScope = scope.value; editingGlossaryScopeName = scope.label">改名</button>
                    <button type="button" class="text-red-300" :aria-label="`刪除 ${scope.label}`" @click="removeGlossaryScope(scope)">刪除</button>
                  </template>
                </div>
                </div>
              </details>
              <p class="text-sm text-white/70">{{ optimizerEffective ? '下次翻譯會使用' : '啟用家族優化後可使用' }}約 {{ effectiveGlossaryCount }} 個原詞：我的詞條 {{ userGlossaryBySource.size }} 個、內建 {{ selectedPresetPreview.length }} 個；同名時以我的譯法為準。</p>
              <p v-if="localConfig.translation.hy_mt2_glossary_folder" class="text-xs text-white/45">JSON 資料夾的詞條仍會加入翻譯，但不包含在此處的預覽與數量中。</p>
              <details v-if="selectedPresetPreview.length" class="rounded-lg border border-white/10 bg-black/15 p-3">
                <summary class="cursor-pointer text-sm font-semibold text-white/80">查看內建詞條（{{ selectedPresetPreview.length }} 筆）</summary>
                <p class="my-2 text-xs text-white/55">內建詞條已包含在下方「這次生效」清單；按「自訂譯法」可新增個人版本。</p>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-x-5 gap-y-1 text-sm max-h-48 overflow-y-auto">
                  <div v-for="term in selectedPresetPreview" :key="term.source" class="flex flex-wrap gap-1 text-white/65">
                    <span>{{ term.source }} → {{ term.override || term.target }}</span>
                    <span v-if="term.override && term.override !== term.target" class="text-amber-200">（我的譯法；預設 {{ term.target }}）</span>
                    <span v-else-if="term.override" class="text-blue-200">（我的詞條優先）</span>
                    <button type="button" class="text-blue-300 underline ml-1" @click="customizePresetTerm(term.source, term.target, !!term.override)">{{ term.override ? '查看我的詞條' : '自訂譯法' }}</button>
                  </div>
                </div>
              </details>
            </div>

            <div v-if="terminologySubTab === 'asr'" class="bg-gradient-to-br from-cyan-500/10 to-blue-500/10 rounded-xl p-5 border border-cyan-500/20">
              <div class="flex items-center justify-between gap-4">
                <div>
                  <h3 class="text-lg font-semibold text-cyan-300 mb-2">ASR 人名／專有名詞修正</h3>
                  <p class="text-white/60 text-sm">辨識完成後、翻譯之前，將常見誤辨統一成標準原文。長詞優先且不會連鎖替換。</p>
                </div>
                <label class="flex items-center gap-3 cursor-pointer shrink-0">
                  <input v-model="localConfig.transcription.asr_corrections_enabled" type="checkbox" class="w-6 h-6 accent-cyan-500" />
                  <span class="text-white font-semibold">{{ localConfig.transcription.asr_corrections_enabled ? '已啟用' : '已停用' }}</span>
                </label>
              </div>

              <label class="flex items-center gap-2 cursor-pointer mt-4 text-sm text-white/70">
                <input v-model="localConfig.transcription.asr_corrections_case_sensitive" type="checkbox" class="w-4 h-4 accent-cyan-500" />
                英文別名區分大小寫
              </label>

              <label class="flex items-center gap-2 cursor-pointer mt-3 text-sm text-white/70">
                <input v-model="localConfig.transcription.asr_correction_log_enabled" type="checkbox" class="w-4 h-4 accent-cyan-500" />
                記錄已套用的 ASR 修正（app/logs/asr_corrections.log）
              </label>

              <label class="flex items-center gap-2 cursor-pointer mt-3 text-sm text-white/70">
                <input v-model="localConfig.transcription.asr_correction_learning_enabled" type="checkbox" class="w-4 h-4 accent-cyan-500" />
                收集未命中詞與 alias 建議（app/logs/asr_correction_suggestions.json）
              </label>
            </div>

            <div v-if="terminologySubTab === 'asr'" class="rounded-xl p-5 border border-white/10 bg-white/[0.03] space-y-3">
              <h3 class="text-lg font-semibold text-cyan-300">同步翻譯詞條</h3>
              <p class="text-white/60 text-sm">翻譯詞條的「日文原詞」是正確寫法，「別名／常見誤辨」是 ASR 常聽錯的寫法；同一份詞條可同時用於辨識。只套用這次情境生效的詞條，且需啟用「我的詞條」。</p>
              <label class="flex items-start gap-2 cursor-pointer text-sm text-white/80">
                <input v-model="localConfig.terminology.glossary_to_asr_corrections" type="checkbox" class="mt-0.5 w-4 h-4 accent-cyan-500" />
                <span>把別名當作誤辨修正成原詞（所有 ASR 都適用；目前 {{ glossaryAliasCount }} 筆詞條有別名；需啟用上方修正）</span>
              </label>
              <label class="flex items-start gap-2 cursor-pointer text-sm text-white/80">
                <input v-model="localConfig.terminology.glossary_to_asr_prompt" type="checkbox" class="mt-0.5 w-4 h-4 accent-cyan-500" />
                <span>把原詞加入 ASR 提示詞（Whisper、faster-whisper、SimulStreaming、OpenAI 轉錄 API、Fun-ASR-Nano）</span>
              </label>
              <p class="text-xs" :class="asrPromptSupport.prompted ? 'text-cyan-200/80' : 'text-amber-200/80'">
                目前的 ASR：{{ asrPromptSupport.name }} —
                {{ asrPromptSupport.prompted ? '會收到提示詞，並套用誤辨修正。' : asrPromptSupport.name === 'Qwen3-ASR' ? '不送提示詞（雜音或唱歌時會把提示詞當成辨識結果輸出），只套用誤辨修正。' : '不支援提示詞，只套用誤辨修正。' }}
              </p>
            </div>

            <div v-if="terminologySubTab === 'asr'" class="rounded-xl p-5 border border-white/10 bg-white/[0.03] space-y-4">
              <div class="grid grid-cols-1 lg:grid-cols-[minmax(180px,0.8fr)_minmax(260px,1.4fr)_auto] gap-3">
                <input v-model="newAsrCanonical" type="text" placeholder="標準名稱，例如：桜島麻衣"
                  class="px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-cyan-400" />
                <input v-model="newAsrAliases" type="text" placeholder="常見誤辨，以逗號分隔：櫻島舞衣, 桜島舞衣"
                  class="px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-cyan-400"
                  @keyup.enter="addAsrCorrection" />
                <button @click="addAsrCorrection" class="bg-cyan-600 hover:bg-cyan-700 text-white font-semibold py-2 px-4 rounded-lg transition">
                  + 新增修正
                </button>
              </div>

              <div class="flex flex-wrap gap-3">
                <input v-model="asrCorrectionSearchQuery" type="text" placeholder="搜尋標準名稱或誤辨文字..."
                  class="flex-1 min-w-[220px] px-4 py-2 bg-white/5 border border-white/20 rounded-lg text-white placeholder-white/30 focus:outline-none focus:border-cyan-400" />
                <button type="button" @click="importAsrCorrections" :disabled="asrCorrectionsImporting"
                  class="bg-white/10 hover:bg-white/20 disabled:opacity-50 disabled:cursor-wait text-white font-semibold py-2 px-4 rounded-lg transition border border-white/20">
                  {{ asrCorrectionsImporting ? '匯入並儲存中…' : '匯入 CSV' }}
                </button>
                <button type="button" @click="exportAsrCorrections" class="bg-white/10 hover:bg-white/20 text-white font-semibold py-2 px-4 rounded-lg transition border border-white/20">
                  匯出 CSV
                </button>
              </div>

              <div class="max-h-80 overflow-y-auto space-y-2">
                <div v-for="rule in visibleAsrCorrections" :key="`${rule.canonical}-${(rule.aliases || []).join('|')}`"
                  class="flex items-center justify-between gap-4 p-3 bg-white/5 rounded-lg border border-white/10">
                  <div class="min-w-0">
                    <div class="text-cyan-300 font-semibold">{{ rule.canonical }}</div>
                    <div class="text-white/55 text-sm break-words mt-1">誤辨：{{ (rule.aliases || []).join('、') }}</div>
                  </div>
                  <button @click="removeAsrCorrection(rule)" class="text-red-400 hover:text-red-300 shrink-0">刪除</button>
                </div>
                <div v-if="filteredAsrCorrections.length === 0" class="text-white/40 text-center py-6">
                  {{ (localConfig.transcription?.asr_correction_rules?.length || 0) === 0 ? '尚未新增 ASR 修正規則' : '沒有符合搜尋的規則' }}
                </div>
                <button
                  v-if="visibleAsrCorrections.length < filteredAsrCorrections.length"
                  @click="asrCorrectionRenderLimit += LARGE_LIST_BATCH_SIZE"
                  class="w-full py-2 text-sm text-cyan-300 hover:text-cyan-200 bg-white/5 hover:bg-white/10 rounded-lg"
                >
                  顯示更多（尚有 {{ filteredAsrCorrections.length - visibleAsrCorrections.length }} 筆）
                </button>
              </div>

              <div class="text-white/40 text-sm">共 {{ localConfig.transcription?.asr_correction_rules?.length || 0 }} 筆修正規則</div>
            </div>

            <div v-if="terminologySubTab === 'translation'" class="space-y-5">
            <h3 class="text-lg font-semibold text-purple-300 pt-4">翻譯術語表</h3>

            <!-- 啟用術語表開關 -->
            <div class="bg-gradient-to-br from-purple-500/10 to-blue-500/10 rounded-xl p-5 border border-purple-500/20 mb-6">
              <div class="flex items-center justify-between">
                <div class="flex-1">
                  <h3 class="text-lg font-semibold text-purple-300 mb-2">我的詞條</h3>
                  <p class="text-white/60 text-sm">
                    原有詞條維持「所有直播」適用。關閉這個開關只停用我的詞條，不會停用所選的內建情境詞表。
                  </p>
                </div>
                <label class="flex items-center gap-3 cursor-pointer ml-6">
                  <input v-model="localConfig.terminology.use_terminology_glossary" type="checkbox" class="w-6 h-6 accent-purple-500" />
                  <span class="text-white font-semibold">{{ localConfig.terminology.use_terminology_glossary ? '已啟用' : '已停用' }}</span>
                </label>
              </div>
              <label class="flex items-center gap-2 cursor-pointer mt-4 text-sm text-white/70">
                <input v-model="localConfig.terminology.translation_glossary_audit_enabled" type="checkbox" class="w-4 h-4 accent-purple-500" />
                記錄術語遵循狀況與重複未命中（app/logs/translation_glossary_audit.log、translation_glossary_issues.json）
              </label>
              <p v-if="Object.keys(localConfig.terminology?.terminology_glossary || {}).length" class="mt-3 text-xs text-amber-200">設定檔仍含舊版術語字典；它目前優先於下方個人詞條列表。若修改列表後沒有生效，請先匯出備份並整理舊版字典。</p>
            </div>

            <!-- 新增術語 -->
            <div :ref="(el: any) => (glossaryEntryForm = el)" class="rounded-xl border border-white/10 bg-white/[0.03] p-4 space-y-3">
              <h4 class="font-semibold text-white/85">新增個人詞條</h4>
              <p v-if="newTermOriginal.trim()" class="text-sm text-blue-200">「{{ newTermOriginal }}」目前只填入表單；按「新增詞條」後才會成為你的詞條。</p>
              <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                <label class="text-sm text-white/70">日文原詞
                  <input v-model="newTermOriginal" type="text" placeholder="例如：すいちゃん" class="mt-1 w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                </label>
                <label class="text-sm text-white/70">繁中譯法
                  <input v-model="newTermTranslated" type="text" placeholder="例如：Sui醬" class="mt-1 w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                </label>
                <label class="text-sm text-white/70">別名／常見誤辨（可留空，逗號分隔）
                  <input v-model="newTermAliases" type="text" placeholder="例如：スイちゃん" class="mt-1 w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
                </label>
                <div class="text-sm text-white/70">適用情境
                  <UiSelect v-model="newTermScope" aria-label="新詞條適用情境" :options="glossaryScopeOptions" button-class="mt-1" />
                </div>
              </div>
              <div class="flex justify-end">
                <button type="button" @click="addTerm" :disabled="!newTermOriginal.trim() || !newTermTranslated.trim()" class="bg-blue-600 hover:bg-blue-700 disabled:opacity-40 text-white font-semibold px-5 py-2 rounded-lg transition">新增詞條</button>
              </div>
            </div>

            <!-- 搜尋 & 匯入匯出 -->
            <h4 class="text-base font-semibold text-purple-200">詞條清單 <span class="ml-2 text-sm font-normal text-white/55">預設顯示本次生效的個人與內建詞條</span></h4>
            <div class="flex flex-wrap items-end gap-3 mb-4">
              <div class="min-w-[215px]">
                <UiSelect :model-value="glossaryListMode" :options="[
                  { value: 'active', label: '這次生效：個人＋內建' },
                  { value: 'global', label: '待分類：所有直播' },
                  { value: 'all', label: '查看所有我的詞條' }
                ]" aria-label="詞條顯示範圍" @update:model-value="glossaryListMode = $event === 'all' ? 'all' : $event === 'global' ? 'global' : 'active'" />
              </div>
              <label class="flex-1 min-w-[200px] text-sm text-white/70">搜尋詞條
                <input v-model="termSearchQuery" type="text" placeholder="輸入日文原詞或譯法" class="mt-1 w-full px-3 py-2 bg-white/5 border border-white/20 rounded-lg text-white" />
              </label>
              <button type="button" @click="importGlossary" :disabled="glossaryImporting"
                class="bg-white/10 hover:bg-white/20 disabled:opacity-50 disabled:cursor-wait text-white font-semibold py-2 px-4 rounded-lg transition border border-white/20">
                {{ glossaryImporting ? '📂 匯入並儲存中…' : '📂 匯入 CSV' }}
              </button>
              <button type="button" @click="exportGlossary" class="bg-white/10 hover:bg-white/20 text-white font-semibold py-2 px-4 rounded-lg transition border border-white/20">
                💾 匯出 CSV
              </button>
            </div>

            <div v-if="(localConfig.terminology?.glossary_list || []).some((term: any) => String(term.scope || 'all') === 'all')" class="rounded-lg border border-amber-400/20 bg-amber-400/5 p-3 text-sm text-white/70">
              目前有 {{ (localConfig.terminology?.glossary_list || []).filter((term: any) => String(term.scope || 'all') === 'all').length }} 筆全域詞條。人名、作品名可移到 Hololive／VTuber；一般直播用語可維持全域。請先篩選、勾選，再批次調整；現有詞條不會自動改寫。
            </div>
            <div class="flex flex-wrap items-center gap-2 text-sm">
              <button type="button" class="rounded-lg bg-white/10 px-3 py-2 text-white hover:bg-white/20" @click="selectVisibleGlossaryTerms">選取本頁個人詞條</button>
              <button type="button" :disabled="!selectedGlossaryTerms.length" class="rounded-lg bg-white/10 px-3 py-2 text-white disabled:opacity-40" @click="selectedGlossaryTerms = []">清除選取</button>
              <span class="text-white/60">已選 {{ selectedGlossaryTerms.length }} 筆</span>
              <div class="min-w-[190px] ml-auto"><UiSelect v-model="bulkGlossaryScope" aria-label="批次適用情境" :options="glossaryScopeOptions" /></div>
              <button type="button" :disabled="!selectedGlossaryTerms.length" class="rounded-lg bg-purple-600 px-3 py-2 font-semibold text-white disabled:opacity-40" @click="applySelectedGlossaryScope">套用情境</button>
            </div>
            <div v-if="removedGlossaryTerm" class="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-white/70">
              已移除「{{ removedGlossaryTerm.term.original }}」。<button type="button" class="ml-2 text-blue-300 underline" @click="undoRemovedGlossaryTerm">還原</button>
            </div>

            <!-- 精簡清單：只有選中的一筆展開編輯 -->
            <div :ref="(el: any) => (glossaryUserList = el)" class="space-y-2">
              <div v-for="term in visibleGlossary" :key="`${term.original}-${term.scope || 'all'}`"
                class="rounded-lg border border-white/10 bg-white/[0.03]">
                <div class="flex items-center gap-3 px-3 py-2">
                  <input v-if="!term.builtin && !term.legacy" type="checkbox" :checked="selectedGlossaryTerms.includes(term)" :aria-label="`選取 ${term.original}`" @change="toggleGlossarySelection(term, ($event.target as HTMLInputElement).checked)" />
                  <span v-else class="w-[13px] shrink-0" aria-hidden="true"></span>
                  <button type="button" :disabled="term.builtin || term.legacy" class="min-w-0 flex-1 grid grid-cols-1 sm:grid-cols-[minmax(110px,1fr)_minmax(130px,1fr)] gap-1 text-left disabled:cursor-default" :aria-expanded="!term.builtin && !term.legacy && expandedGlossaryTerm === term" @click="expandedGlossaryTerm = expandedGlossaryTerm === term ? null : term">
                    <span class="truncate text-white">{{ term.original }}</span>
                    <span class="truncate text-yellow-200">→ {{ term.translated }}</span>
                  </button>
                  <span class="hidden md:inline shrink-0 rounded bg-white/10 px-2 py-1 text-xs text-white/60">{{ term.builtin ? '內建' : term.legacy ? '舊版詞條' : `我的詞條 · ${glossaryScopeOptions.find((option: { value: string; label: string }) => option.value === (term.scope || 'all'))?.label || '所有直播'}` }}</span>
                  <button v-if="term.builtin" type="button" class="shrink-0 text-sm text-blue-300" :aria-label="`自訂 ${term.original} 譯法`" @click="customizePresetTerm(term.original, term.translated, false)">自訂譯法</button>
                  <span v-else-if="term.legacy" class="text-xs text-amber-200">由舊版設定管理</span>
                  <button v-else type="button" class="shrink-0 text-sm text-blue-300" :aria-label="`${expandedGlossaryTerm === term ? '收合' : '編輯'} ${term.original}`" @click="expandedGlossaryTerm = expandedGlossaryTerm === term ? null : term">{{ expandedGlossaryTerm === term ? '收合' : '編輯' }}</button>
                </div>
                <div v-if="!term.builtin && !term.legacy && expandedGlossaryTerm === term" class="grid grid-cols-1 md:grid-cols-2 gap-3 border-t border-white/10 p-3">
                  <label class="text-sm text-white/70">繁中譯法
                    <input v-model="term.translated" class="mt-1 w-full rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-yellow-200" />
                  </label>
                  <div class="text-sm text-white/70">適用情境
                    <UiSelect :model-value="term.scope || 'all'" :options="glossaryScopeOptions" :aria-label="`${term.original} 的適用情境`" button-class="mt-1" @update:model-value="setTermScope(term, $event)" />
                  </div>
                  <label class="text-sm text-white/70 md:col-span-2">別名／常見誤辨（可留空，逗號分隔）
                    <input :value="Array.isArray(term.aliases) ? term.aliases.join(', ') : (term.aliases || '')" @change="setTermAliases(term, $event)" class="mt-1 w-full rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-white" />
                  </label>
                  <div class="md:col-span-2 flex justify-end"><button type="button" class="text-sm text-red-300 hover:text-red-200" @click="removeTermEntry(term)">刪除此詞條</button></div>
                </div>
              </div>
              <div v-if="filteredGlossary.length === 0" class="text-white/40 text-center py-8">
                {{ termSearchQuery.trim() ? '沒有符合搜尋的詞條' : '目前沒有適用詞條' }}
              </div>
              <button
                v-if="visibleGlossary.length < filteredGlossary.length"
                @click="glossaryRenderLimit += GLOSSARY_PAGE_SIZE"
                class="w-full py-2 text-sm text-purple-300 hover:text-purple-200 bg-white/5 hover:bg-white/10 rounded-lg"
              >
                顯示接下來 {{ Math.min(GLOSSARY_PAGE_SIZE, filteredGlossary.length - visibleGlossary.length) }} 筆（尚有 {{ filteredGlossary.length - visibleGlossary.length }} 筆）
              </button>
            </div>

            <div class="text-white/40 text-sm mt-4">
              目前清單 {{ filteredGlossary.length }} 筆；我的詞條總數 {{ localConfig.terminology?.glossary_list?.length || 0 }} 筆
            </div>
            </div>
          </div>
</template>

<style scoped src="./settings-shared.css"></style>

