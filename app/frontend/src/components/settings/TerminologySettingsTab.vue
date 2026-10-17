<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue';
import UiSelect from '../UiSelect.vue';
import { useSettingsTabBindings } from '../../composables/settings/settingsContext';
const { aliasSuggestions, suggestionsError, addonError, readingAddon, suggestionActionBusy, addonActionBusy, addonRunning, suggestionsVisible, startSuggestionReview, stopSuggestionReview, refreshAliasSuggestions, refreshReadingAddon, changeReadingAddon, acceptAliasSuggestion, ignoreAliasSuggestion, clearAliasSuggestions, localConfig, presetLoadError, glossaryImporting, newTermOriginal, newTermTranslated, newTermAliases, newTermScope, newGlossaryScopeName, termSearchQuery, glossaryListMode, editingGlossaryScope, editingGlossaryScopeName, deletingScope, highlightedTerm, removedGlossaryTerm, expandedGroups, groupLimits, glossaryScopeOptions, groups, categoryCounts, isActive, isBuiltinEnabled, toggleCategory, toggleBuiltin, addGlossaryScope, renameGlossaryScope, removeGlossaryScope, addTerm, setTermOriginal, setTermScope, setTermAliases, registerTermRow, customizePresetTerm, removeTermEntry, undoRemovedGlossaryTerm, importGlossary, exportGlossary, normalizeTermAliases } = useSettingsTabBindings();
const suggestionsExpanded = ref(false);
// Records collected before the reading add-on (or without it) carry no reading
// verdict; they are glyph matches and often false positives (お姉ちゃん ↔ 水ちゃん).
const isLegacySuggestion = (suggestion: { reading_match: boolean | null }) =>
  !!readingAddon.value?.installed && suggestion.reading_match === null;
const legacySuggestionCount = computed(() => aliasSuggestions.value.filter(isLegacySuggestion).length);
onMounted(async () => {
  await startSuggestionReview();
  suggestionsExpanded.value = aliasSuggestions.value.length > 0;
});
onUnmounted(stopSuggestionReview);
function exampleParts(sentence: string, alias: string) {
  if (!alias) return [{ text: sentence, highlight: false }];
  return sentence.split(alias).flatMap((text, index) => index
    ? [{ text: alias, highlight: true }, { text, highlight: false }]
    : [{ text, highlight: false }]);
}
const termIds = new WeakMap<object, number>();
let nextTermId = 0;
function termKey(term: object & { original: string; scope: string }, builtin: boolean) {
  if (builtin) return `builtin:${term.scope}:${term.original}`;
  if (!termIds.has(term)) termIds.set(term, ++nextTermId);
  return `user:${termIds.get(term)}`;
}
function categoryCount(id: string) {
  const counts = categoryCounts.value[id];
  return glossaryListMode.value === 'mine' ? counts?.mine || 0 : counts?.applicable || 0;
}
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
</script>

<template>
  <div class="settings-paint-section apple-settings terminology-page">
    <header class="apple-page-header"><h2>術語表</h2><p>同一個詞只要建一次：寫對的寫法、想要的譯法，以及語音辨識常聽錯的寫法。</p></header>
    <div v-if="localConfig.terminology.use_terminology_glossary === false" class="term-notice" role="status">
      <span>翻譯時不會套用你的詞條</span><button type="button" @click="localConfig.terminology.use_terminology_glossary = true">開啟</button>
    </div>
    <div v-if="localConfig.transcription.asr_corrections_enabled === false" class="term-notice" role="status">
      <span>常見誤辨目前不會修正辨識結果</span><button type="button" @click="localConfig.transcription.asr_corrections_enabled = true">開啟</button>
    </div>
    <section class="commercial-panel term-panel">
      <h3>這次直播使用的分類</h3>
      <p v-if="presetLoadError" role="alert">內建分類讀取失敗，請重新整理後再試。</p>
      <div class="term-wrap">
        <label v-for="category in glossaryScopeOptions" :key="category.value" class="category-chip" :title="category.value === 'all' ? '永遠套用' : undefined">
          <input type="checkbox" :checked="isActive(category.value)" :disabled="category.value === 'all'" @change="toggleCategory(category.value, ($event.target as HTMLInputElement).checked)" />
          {{ category.label }}（{{ categoryCount(category.value) }}）
        </label>
      </div>
      <form class="term-wrap" @submit.prevent="addGlossaryScope">
        <input v-model="newGlossaryScopeName" maxlength="40" aria-label="新增分類名稱" placeholder="分類名稱" class="category-name" />
        <button type="submit" :disabled="!newGlossaryScopeName.trim()">＋ 新增分類</button>
      </form>
    </section>
    <section class="commercial-panel term-panel">
      <h3>新增詞條</h3>
      <form class="term-grid" @submit.prevent="addTerm">
        <label>正確寫法<input v-model="newTermOriginal" required placeholder="例如：すいちゃん" /></label>
        <label>譯法<input v-model="newTermTranslated" placeholder="留空＝只修正辨識" /></label>
        <label>常見誤辨<input v-model="newTermAliases" placeholder="以逗號或、分隔" /></label>
        <label>分類<UiSelect v-model="newTermScope" aria-label="新增詞條分類" :options="glossaryScopeOptions" /></label>
        <button type="submit" :disabled="!newTermOriginal.trim()">新增</button>
      </form>
    </section>
    <div class="term-toolbar">
      <input v-model="termSearchQuery" aria-label="搜尋詞條" placeholder="搜尋寫法、譯法或誤辨" />
      <UiSelect v-model="glossaryListMode" aria-label="篩選詞條" :options="[{ value: 'all', label: '全部' }, { value: 'active', label: '這次使用的' }, { value: 'mine', label: '只看我的' }]" />
      <button type="button" :disabled="glossaryImporting" @click="importGlossary">{{ glossaryImporting ? '匯入並儲存中…' : '匯入 CSV' }}</button>
      <button type="button" @click="exportGlossary">匯出 CSV</button>
    </div>
    <p v-if="suggestionsError && !suggestionsVisible" class="suggestion-error" role="status">{{ suggestionsError }} <button type="button" @click="refreshAliasSuggestions">重試</button></p>
    <section v-if="suggestionsVisible" class="commercial-panel term-panel suggestion-panel">
      <button type="button" class="suggestion-heading" :aria-expanded="suggestionsExpanded" aria-controls="alias-suggestion-content" @click="suggestionsExpanded = !suggestionsExpanded">{{ suggestionsExpanded ? '▾' : '▸' }} 建議的常見誤辨（{{ aliasSuggestions.length }}）</button>
      <div v-if="suggestionsExpanded" id="alias-suggestion-content" class="suggestion-content">
        <div v-if="!localConfig.transcription.asr_correction_learning_enabled" class="term-wrap">
          <p>開啟「收集未命中詞」後，直播時會自動記錄可能的誤辨</p>
          <button type="button" @click="localConfig.transcription.asr_correction_learning_enabled = true">開啟</button>
        </div>
        <div class="suggestion-addon">
          <div v-if="readingAddon" class="term-wrap">
            <template v-if="readingAddon.installed">
              <p>讀音比對：已啟用</p>
              <button type="button" class="addon-remove" :disabled="addonActionBusy || addonRunning" @click="changeReadingAddon(false)">移除</button>
            </template>
            <template v-else>
              <p>安裝讀音比對元件（約 20 MB 下載），可分辨同音字、減少誤報</p>
              <button type="button" :disabled="addonActionBusy || addonRunning" @click="changeReadingAddon(true)">{{ addonRunning ? (readingAddon.state === 'installing' ? '安裝中…' : '下載中…') : addonActionBusy ? '處理中…' : '安裝' }}</button>
            </template>
            <template v-if="addonRunning">
              <progress :value="Math.min(1, Math.max(0, readingAddon.progress))" max="1" aria-label="讀音元件安裝進度"></progress>
              <span>{{ Math.round(Math.min(1, Math.max(0, readingAddon.progress)) * 100) }}%</span>
            </template>
          </div>
          <p v-if="addonError" class="suggestion-error" role="status">{{ addonError }} <button type="button" :disabled="addonActionBusy" @click="refreshReadingAddon">重試</button></p>
        </div>
        <p v-if="suggestionsError" class="suggestion-error" role="status">{{ suggestionsError }} <button type="button" @click="refreshAliasSuggestions">重試</button></p>
        <p v-if="!aliasSuggestions.length">目前沒有建議。</p>
        <p v-if="legacySuggestionCount" class="suggestion-error" role="status">有 {{ legacySuggestionCount }} 筆是安裝讀音比對前收集的，可能有誤報；建議「清除全部建議」後重新收集。</p>
        <article v-for="suggestion in aliasSuggestions" :key="JSON.stringify([suggestion.alias, suggestion.canonical])" class="suggestion-row">
          <div class="term-wrap">
            <strong>{{ suggestion.alias }} → {{ suggestion.canonical }}</strong>
            <span>{{ suggestion.count }} 次</span><span v-if="suggestion.reading_match" class="active-badge">同音</span><span v-else-if="isLegacySuggestion(suggestion)" class="legacy-badge">舊方法</span>
          </div>
          <p v-for="(example, index) in suggestion.examples.slice(0, 3)" :key="index" class="suggestion-example"><template v-for="(part, partIndex) in exampleParts(example, suggestion.alias)" :key="partIndex"><mark v-if="part.highlight">{{ part.text }}</mark><template v-else>{{ part.text }}</template></template></p>
          <div class="term-wrap">
            <button type="button" :disabled="suggestionActionBusy" @click="acceptAliasSuggestion(suggestion)">加入為誤辨</button>
            <button type="button" :disabled="suggestionActionBusy" @click="ignoreAliasSuggestion(suggestion)">忽略</button>
          </div>
        </article>
        <button v-if="aliasSuggestions.length" type="button" :disabled="suggestionActionBusy" @click="clearAliasSuggestions">清除全部建議</button>
      </div>
    </section>
    <p v-if="removedGlossaryTerm" role="status">已刪除「{{ removedGlossaryTerm.term.original }}」 <button type="button" @click="undoRemovedGlossaryTerm">復原</button></p>
    <p v-if="!groups.length">沒有符合的詞條。</p>
    <section v-for="group in groups" :key="group.value" class="commercial-panel term-panel">
      <div class="term-wrap group-header">
        <button type="button" :aria-expanded="!!expandedGroups[group.value]" @click="expandedGroups[group.value] = !expandedGroups[group.value]">{{ expandedGroups[group.value] ? '▾' : '▸' }} {{ group.label }}（{{ group.count }}）</button>
        <span v-if="isActive(group.value)" class="active-badge">使用中</span>
        <template v-if="group.value.startsWith('custom_')">
          <template v-if="editingGlossaryScope === group.value">
            <input v-model="editingGlossaryScopeName" maxlength="40" aria-label="分類新名稱" @keydown.enter.prevent="renameGlossaryScope(group.value)" />
            <button type="button" @click="renameGlossaryScope(group.value)">完成</button>
            <button type="button" @click="editingGlossaryScope = ''">取消</button>
          </template>
          <template v-else>
            <button type="button" @click="editingGlossaryScope = group.value; editingGlossaryScopeName = group.label">改名</button>
            <button type="button" @click="deletingScope = group.value">刪除分類</button>
          </template>
        </template>
      </div>
      <div v-if="deletingScope === group.value" class="term-panel" role="group" aria-label="刪除分類確認">
        <p>刪除「{{ group.label }}」後，詞條要如何處理？移到一般時，同名詞保留一般的譯法並合併誤辨。</p>
        <div class="term-wrap">
          <button type="button" @click="removeGlossaryScope(group.value, true)">移到一般</button>
          <button type="button" @click="removeGlossaryScope(group.value, false)">連同詞條刪除</button>
          <button type="button" @click="deletingScope = ''">取消</button>
        </div>
      </div>
      <div v-if="expandedGroups[group.value]" class="term-rows">
        <div v-if="group.entries.length" class="term-grid term-column-header" aria-hidden="true">
          <span>正確寫法</span><span>譯法</span><span>常見誤辨</span><span>分類</span><span></span>
        </div>
        <div v-for="entry in group.visible" :key="termKey(entry.term, entry.builtin)" :ref="el => !entry.builtin && registerTermRow(entry.term, el)" class="term-grid term-row" :class="{ highlighted: highlightedTerm === entry.term }">
          <template v-if="!entry.builtin">
            <label><span class="term-field-label">正確寫法</span><input :value="entry.term.original" required @change="setTermOriginal(entry.term, $event)" /></label>
            <label><span class="term-field-label">譯法</span><input v-model="entry.term.translated" placeholder="留空＝只修正辨識" /></label>
            <label><span class="term-field-label">常見誤辨</span><input :value="normalizeTermAliases(entry.term.aliases).join('、')" placeholder="以逗號或、分隔" @change="setTermAliases(entry.term, $event)" /></label>
            <label><span class="term-field-label">分類</span><UiSelect :model-value="entry.term.scope || 'all'" :options="glossaryScopeOptions" aria-label="詞條分類" @update:model-value="setTermScope(entry.term, $event)" /></label>
            <button type="button" :aria-label="`刪除 ${entry.term.original}`" @click="removeTermEntry(entry.term)">刪除</button>
          </template>
          <template v-else>
            <label><span class="term-field-label">正確寫法</span><span>{{ entry.term.original }}</span></label>
            <label><span class="term-field-label">譯法</span><span>{{ entry.term.translated || '只修正辨識' }}</span></label>
            <label><span class="term-field-label">常見誤辨</span><span>{{ entry.term.aliases.join('、') || '—' }}</span></label>
            <div><span class="term-field-label">分類</span><span class="builtin-category">{{ group.label }}</span><label class="builtin-switch"><input type="checkbox" role="switch" :aria-label="`啟用 ${entry.term.original}`" :checked="isBuiltinEnabled(group.value, entry.term.original)" @change="toggleBuiltin(group.value, entry.term.original, ($event.target as HTMLInputElement).checked)" />啟用</label></div>
            <button type="button" @click="customizePresetTerm(entry.term)">改譯法</button>
          </template>
        </div>
        <p v-if="!group.entries.length">{{ glossaryListMode === 'mine' ? '還沒有自己的詞條。' : '這個分類還沒有詞條。' }}</p>
        <button v-if="group.visible.length < group.entries.length" type="button" @click="groupLimits[group.value] = (groupLimits[group.value] || 50) + 50">顯示更多（還有 {{ group.entries.length - group.visible.length }} 個）</button>
      </div>
    </section>
    <details class="commercial-panel term-panel">
      <summary>進階設定</summary>
      <div class="advanced-options">
        <label><input v-model="localConfig.terminology.use_terminology_glossary" type="checkbox" />啟用我的詞條</label>
        <label><input v-model="localConfig.transcription.asr_corrections_enabled" type="checkbox" />語音辨識修正</label>
        <p>將誤辨改成正確寫法。需啟用語音辨識修正。</p>
        <label><input v-model="localConfig.terminology.glossary_to_asr_prompt" type="checkbox" />把正確寫法加入 ASR 提示詞</label>
        <p>支援 Whisper、faster-whisper、SimulStreaming、OpenAI 轉錄 API、Fun-ASR-Nano。預設關閉：Whisper 遇到 BGM 或靜音時可能把提示詞當成字幕輸出。</p>
        <p>目前的 ASR：{{ asrPromptSupport.name }} — {{ asrPromptSupport.prompted ? '支援提示詞；開啟後才會送出。' : asrPromptSupport.name === 'Qwen3-ASR' ? '不送提示詞，避免雜音或唱歌時誤輸出；可套用誤辨修正。' : '不支援提示詞；可套用誤辨修正。' }}</p>
        <label><input v-model="localConfig.transcription.asr_corrections_case_sensitive" type="checkbox" />英文區分大小寫</label>
        <label><input v-model="localConfig.transcription.asr_correction_log_enabled" type="checkbox" />記錄修正 log</label>
        <label><input v-model="localConfig.transcription.asr_correction_learning_enabled" type="checkbox" />收集未命中詞</label>
        <label><input v-model="localConfig.terminology.translation_glossary_audit_enabled" type="checkbox" />記錄術語遵循狀況</label>
      </div>
    </details>
  </div>
</template>

<style scoped src="./settings-shared.css"></style>
<style scoped>
.suggestion-content { display: grid; gap: 10px; min-width: 0; }
.suggestion-panel .suggestion-heading { text-align: left; font-weight: 600; }
.suggestion-addon { padding: 10px; border-radius: 8px; background: #ffffff05; min-width: 0; }
.suggestion-row { display: grid; gap: 6px; min-width: 0; padding-top: 10px; border-top: 1px solid #ffffff15; }
.suggestion-panel p, .suggestion-row span { font-size: 12px; }
.suggestion-example { white-space: pre-wrap; overflow-wrap: anywhere; }
.suggestion-example mark { color: #fef3c7; background: #f59e0b35; border-radius: 2px; }
.suggestion-error { font-size: 12px; color: #fcd34d; }
.legacy-badge { margin-left: 6px; padding: 0 6px; border-radius: 999px; font-size: 11px; color: #cbd5e1; background: #ffffff12; }
.suggestion-addon progress { width: 120px; max-width: 100%; }
.suggestion-addon .addon-remove { padding: 0; background: transparent; text-decoration: underline; }
.suggestion-panel .term-wrap > * { min-width: 0; max-width: 100%; overflow-wrap: anywhere; }
.terminology-page { min-width: 0; overflow-wrap: anywhere; }
.term-panel { padding: 16px; display: grid; gap: 12px; min-width: 0; }
h3 { font-weight: 600; }
.term-wrap { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; min-width: 0; }
.category-chip { display: flex; align-items: center; gap: 6px; padding: 8px 10px; border: 1px solid #ffffff25; border-radius: 20px; max-width: 100%; }
.terminology-page input:not([type=checkbox]) { width: 100%; min-width: 0; box-sizing: border-box; background: #ffffff08; border: 1px solid #ffffff30; border-radius: 8px; padding: 8px 10px; color: inherit; }
.terminology-page input.category-name { flex: 1 1 140px; width: auto; }
.terminology-page button { padding: 8px 10px; border-radius: 8px; background: #ffffff0d; color: #bfdbfe; white-space: normal; }
.terminology-page button:disabled { opacity: .4; }
.terminology-page :is(button,input):focus-visible { outline: 2px solid #93c5fd; outline-offset: 2px; }
.term-grid { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr) minmax(0,1.2fr) minmax(0,1fr) auto; gap: 10px; align-items: end; }
.term-grid > * { min-width: 0; }
.term-grid label { display: grid; gap: 5px; font-size: 12px; color: #ffffffaa; }
.term-grid label span { font-size: 14px; color: #ffffffe0; padding: 8px 0; }
.term-toolbar { display: flex; flex-wrap: wrap; gap: 8px; min-width: 0; }
.term-toolbar > input { flex: 1 1 200px; }
.term-toolbar > * { min-width: 0; max-width: 100%; }
.term-rows { display: grid; gap: 10px; min-width: 0; }
.term-row { border-top: 1px solid #ffffff15; padding: 12px 4px; }
.term-row.highlighted { outline: 2px solid #60a5fa; border-radius: 8px; }
.term-grid .builtin-switch { display: flex; align-items: center; gap: 8px; padding: 8px 0; }
.active-badge { color: #a7f3d0; font-size: 12px; }
.advanced-options { display: grid; gap: 12px; margin-top: 16px; }
.advanced-options label { display: flex; align-items: start; gap: 8px; }
.advanced-options input { margin-top: 4px; flex-shrink: 0; }
.advanced-options p { font-size: 12px; color: #ffffff99; }
summary { cursor: pointer; }
.term-notice { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 8px 12px; border: 1px solid #f59e0b66; border-radius: 8px; background: #f59e0b15; color: #fcd34d; font-size: 13px; }
.term-column-header { display: none; }
.builtin-category { display: block; padding-top: 8px; }
@media (min-width: 768px) {
  .term-rows .term-grid { grid-template-columns: minmax(0,1fr) minmax(0,1fr) minmax(0,1.2fr) minmax(0,1fr) 70px; }
  .term-column-header { display: grid; padding: 0 4px; font-size: 12px; color: #ffffffaa; }
  .term-row .term-field-label { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
}
@media (max-width: 1000px) { .term-grid { grid-template-columns: repeat(2,minmax(0,1fr)); } }
@media (max-width: 540px) { .term-grid { grid-template-columns: minmax(0,1fr); } .term-panel { padding: 12px; } .term-toolbar > * { flex: 1 1 100%; } }
</style>
