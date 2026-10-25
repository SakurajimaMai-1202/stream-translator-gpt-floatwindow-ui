import { ref, computed, watch, nextTick, onScopeDispose, type Ref } from 'vue';
import type { useTranslationStore } from '../../stores/translation';

import { terminologyApi, type AliasSuggestion, type ReadingAddonStatus } from '../../services/api';

type Term = { original: string; translated: string; aliases: string[]; scope: string };
type Category = { id: string; label: string; terms: Record<string, string>; asr_variants: Record<string, string[]> };
export function normalizeTermAliases(value: unknown): string[] {
  return [...new Set((Array.isArray(value) ? value : String(value || '').split(/[,，、\n]/)).map(value => String(value).trim()).filter(Boolean))];
}
export function useTerminologySettings(localConfig: Ref<any>, store: ReturnType<typeof useTranslationStore>, saveBulkImport: (section: 'terminology' | 'transcription', applyImport: () => void) => Promise<void>) {
  const aliasSuggestions = ref<AliasSuggestion[]>([]);
  const suggestionsError = ref('');
  const addonError = ref('');
  const readingAddon = ref<ReadingAddonStatus | null>(null);
  const suggestionActionBusy = ref(false);
  const addonActionBusy = ref(false);
  const addonRunning = computed(() => ['downloading', 'installing'].includes(readingAddon.value?.state || ''));
  const suggestionsVisible = computed(() => !!localConfig.value.transcription.asr_correction_learning_enabled || aliasSuggestions.value.length > 0);
  let pollTimer: ReturnType<typeof setTimeout> | undefined;
  let disposed = false;
  function scheduleAddonPoll() {
    clearTimeout(pollTimer);
    if (!disposed && addonRunning.value) pollTimer = setTimeout(() => { void refreshReadingAddon(); }, 1000);
  }
  async function refreshReadingAddon() {
    try {
      const status = await terminologyApi.getReadingAddon();
      if (disposed) return;
      readingAddon.value = status;
      addonError.value = status.state === 'error' ? '讀音元件安裝失敗，請重試。' : '';
    } catch {
      if (!disposed) addonError.value = '無法讀取讀音元件狀態，請重試。';
    }
    finally { scheduleAddonPoll(); }
  }
  async function refreshAliasSuggestions() {
    try {
      const result = await terminologyApi.getAliasSuggestions();
      if (disposed) return;
      aliasSuggestions.value = result.suggestions.filter(suggestion =>
        !rows.value.some(row => row.original === suggestion.canonical && normalizeTermAliases(row.aliases).includes(suggestion.alias)) &&
        !(localConfig.value.terminology.ignored_alias_suggestions || []).some((item: { alias: string; canonical: string }) => item.alias === suggestion.alias && item.canonical === suggestion.canonical));
      suggestionsError.value = '';
    } catch {
      if (!disposed) suggestionsError.value = '無法讀取建議，請稍後重試。';
    }
  }
  async function startSuggestionReview() {
    disposed = false;
    await Promise.allSettled([refreshAliasSuggestions(), refreshReadingAddon()]);
  }
  function stopSuggestionReview() {
    disposed = true;
    clearTimeout(pollTimer);
  }
  onScopeDispose(stopSuggestionReview);
  async function changeReadingAddon(install: boolean) {
    if (addonActionBusy.value || addonRunning.value) return;
    addonActionBusy.value = true;
    addonError.value = '';
    try {
      if (install) {
        readingAddon.value = await terminologyApi.installReadingAddon();
        if (readingAddon.value.state === 'error') addonError.value = '讀音元件安裝失敗，請重試。';
        scheduleAddonPoll();
      } else {
        await terminologyApi.removeReadingAddon();
        await refreshReadingAddon();
      }
    } catch { addonError.value = install ? '無法安裝讀音元件，請重試。' : '無法移除讀音元件，請重試。'; }
    finally { addonActionBusy.value = false; }
  }
  function dismissAliasSuggestion(suggestion: AliasSuggestion) {
    aliasSuggestions.value = aliasSuggestions.value.filter(item => item.alias !== suggestion.alias || item.canonical !== suggestion.canonical);
  }
  function acceptAliasSuggestion(suggestion: AliasSuggestion) {
    const matches = rows.value.filter(row => row.original === suggestion.canonical);
    if (matches.length) for (const row of matches) row.aliases = normalizeTermAliases([...normalizeTermAliases(row.aliases), suggestion.alias]);
    else localConfig.value.terminology.glossary_list = [...rows.value, { original: suggestion.canonical, translated: '', aliases: [suggestion.alias], scope: 'all' }];
    dismissAliasSuggestion(suggestion);
  }
  function ignoreAliasSuggestion(suggestion: AliasSuggestion) {
    const ignored = localConfig.value.terminology.ignored_alias_suggestions || [];
    if (!ignored.some((item: { alias: string; canonical: string }) => item.alias === suggestion.alias && item.canonical === suggestion.canonical)) {
      localConfig.value.terminology.ignored_alias_suggestions = [...ignored, { alias: suggestion.alias, canonical: suggestion.canonical }];
    }
    dismissAliasSuggestion(suggestion);
  }
  async function clearAliasSuggestions() {
    if (suggestionActionBusy.value || !window.confirm('確定清除全部建議？')) return;
    suggestionActionBusy.value = true;
    try {
      await terminologyApi.clearAliasSuggestions();
      aliasSuggestions.value = [];
      suggestionsError.value = '';
    } catch { suggestionsError.value = '無法清除建議，請重試。'; }
    finally { suggestionActionBusy.value = false; }
  }
  const presetCategories = ref<Category[]>([]);
  const presetLoadError = ref(false);
  const glossaryImporting = ref(false);
  const newTermOriginal = ref('');
  const newTermTranslated = ref('');
  const newTermAliases = ref('');
  const newTermScope = ref('all');
  const newGlossaryScopeName = ref('');
  const termSearchQuery = ref('');
  const glossaryListMode = ref('all');
  const editingGlossaryScope = ref('');
  const editingGlossaryScopeName = ref('');
  const deletingScope = ref('');
  const highlightedTerm = ref<Term | null>(null);
  const removedGlossaryTerm = ref<{ term: Term; index: number } | null>(null);
  const expandedGroups = ref<Record<string, boolean>>({});
  const groupLimits = ref<Record<string, number>>({});
  const rowElements = new WeakMap<Term, HTMLElement>();
  const rows = computed<Term[]>(() => localConfig.value.terminology.glossary_list || []);
  const customGlossaryScopes = computed<{ value: string; label: string }[]>(() => localConfig.value.terminology.custom_glossary_scopes || []);
  // Fallback labels keep 翻譯選項 truthful if the preset request fails.
  const builtinFallback = [{ value: 'general_chat', label: '一般直播' }, { value: 'hololive_vtuber', label: 'Hololive／VTuber' }, { value: 'cosplay', label: 'Cosplay' }];
  const glossaryScopeOptions = computed(() => [{ value: 'all', label: '一般' },
    ...(presetCategories.value.length ? presetCategories.value.map(c => ({ value: c.id, label: c.label })) : builtinFallback),
    ...customGlossaryScopes.value]);
  const activeCategories = computed<string[]>(() => ['all', ...(localConfig.value.terminology.active_categories || [])]);
  const activeCategoryLabels = computed(() => glossaryScopeOptions.value.filter(c => activeCategories.value.includes(c.value)).map(c => c.label).join('、'));
  const isActive = (id: string) => activeCategories.value.includes(id);
  const isBuiltinEnabled = (category: string, source: string) => !(localConfig.value.terminology.builtin_disabled || []).some((entry: any) => entry.category === category && entry.source === source);
  const effectiveGlossaryCount = computed(() => {
    const sources = new Set<string>();
    const userOn = localConfig.value.terminology.use_terminology_glossary;
    // Mirrors session_vocabulary: a blank 譯法 in the same built-in category drops it.
    const blanked = (category: string, source: string) => userOn && rows.value.some(row =>
      (row.scope || 'all') === category && row.original.trim() === source && !row.translated.trim());
    for (const c of presetCategories.value.filter(c => isActive(c.id))) {
      for (const source of Object.keys(c.terms)) if (isBuiltinEnabled(c.id, source) && !blanked(c.id, source)) sources.add(source);
    }
    if (localConfig.value.terminology.use_terminology_glossary) {
      for (const row of rows.value) if (isActive(row.scope || 'all') && row.original.trim() && row.translated.trim()) sources.add(row.original.trim());
    }
    return sources.size;
  });
  const groups = computed(() => glossaryScopeOptions.value.map(category => {
    const preset = presetCategories.value.find(c => c.id === category.value);
    const users = rows.value.filter(row => (row.scope || 'all') === category.value);
    // A user row overrides (and hides) a built-in only while 我的詞條 is on; the
    // backend falls back to the built-in otherwise.
    const overrides = localConfig.value.terminology.use_terminology_glossary ? users : [];
    const builtins = preset ? [...new Set([...Object.keys(preset.terms), ...Object.keys(preset.asr_variants || {})])].filter(original => !overrides.some(row => row.original.trim() === original)).map(original => ({ original, translated: preset.terms[original] || '', aliases: preset.asr_variants?.[original] || [], scope: category.value })) : [];
    const query = termSearchQuery.value.trim().toLocaleLowerCase();
    const matches = (row: Term) => [row.original, row.translated, ...normalizeTermAliases(row.aliases)].some(value => value.toLocaleLowerCase().includes(query));
    const entries = [...users.map(term => ({ term, builtin: false })), ...(glossaryListMode.value === 'mine' ? [] : builtins.map(term => ({ term, builtin: true })))].filter(entry => matches(entry.term));
    return { ...category, count: entries.length, applicableCount: entries.filter(entry => entry.builtin ? isBuiltinEnabled(category.value, entry.term.original) : localConfig.value.terminology.use_terminology_glossary).length, entries, visible: entries.slice(0, groupLimits.value[category.value] || 50) };
  }).filter(group => (glossaryListMode.value !== 'active' || isActive(group.value)) && (!termSearchQuery.value.trim() || group.entries.length)));
  // Chip counts ignore the list's search and filter: a chip must show what the
  // category holds even while its group is hidden from the list.
  const categoryCounts = computed(() => Object.fromEntries(glossaryScopeOptions.value.map(category => {
    const preset = presetCategories.value.find(c => c.id === category.value);
    const users = rows.value.filter(row => (row.scope || 'all') === category.value && row.original.trim());
    const overridden = new Set(localConfig.value.terminology.use_terminology_glossary ? users.map(row => row.original.trim()) : []);
    const builtins = preset ? [...new Set([...Object.keys(preset.terms), ...Object.keys(preset.asr_variants || {})])]
      .filter(original => !overridden.has(original) && isBuiltinEnabled(category.value, original)) : [];
    return [category.value, { mine: users.length, applicable: builtins.length + (localConfig.value.terminology.use_terminology_glossary ? users.length : 0) }];
  })) as Record<string, { mine: number; applicable: number }>);
  watch(activeCategories, active => {
    newTermScope.value = active.find(id => customGlossaryScopes.value.some(c => c.value === id)) || 'all';
    for (const id of active) expandedGroups.value[id] = true;
  }, { immediate: true });
  watch([termSearchQuery, glossaryListMode], () => {
    groupLimits.value = {};
    if (termSearchQuery.value.trim()) for (const c of glossaryScopeOptions.value) expandedGroups.value[c.value] = true;
  });
  function toggleCategory(id: string, enabled: boolean) {
    if (id === 'all') return;
    localConfig.value.terminology.active_categories = [...new Set(activeCategories.value.filter(value => value !== 'all' && value !== id).concat(enabled ? [id] : []))];
  }
  function toggleBuiltin(category: string, source: string, enabled: boolean) {
    const entries = (localConfig.value.terminology.builtin_disabled || []).filter((entry: any) => entry.category !== category || entry.source !== source);
    localConfig.value.terminology.builtin_disabled = enabled ? entries : [...entries, { category, source }];
  }
  function addGlossaryScope() {
    const label = newGlossaryScopeName.value.trim();
    if (!label) return;
    if (glossaryScopeOptions.value.some(c => c.label.toLocaleLowerCase() === label.toLocaleLowerCase())) { store.statusMessage = '已有同名分類'; return; }
    const value = `custom_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    localConfig.value.terminology.custom_glossary_scopes = [...customGlossaryScopes.value, { value, label }];
    toggleCategory(value, true);
    newGlossaryScopeName.value = '';
  }
  function renameGlossaryScope(id: string) {
    const label = editingGlossaryScopeName.value.trim();
    if (!label) return;
    if (glossaryScopeOptions.value.some(c => c.value !== id && c.label.toLocaleLowerCase() === label.toLocaleLowerCase())) { store.statusMessage = '已有同名分類'; return; }
    const scope = customGlossaryScopes.value.find(c => c.value === id);
    if (scope) scope.label = label;
    editingGlossaryScope.value = '';
  }
  function removeGlossaryScope(id: string, move: boolean) {
    const remaining = rows.value.filter(row => row.scope !== id);
    if (move) for (const row of rows.value.filter(row => row.scope === id)) {
      const existing = remaining.find(other => other.original === row.original && (other.scope || 'all') === 'all');
      if (existing) { existing.aliases = normalizeTermAliases([...normalizeTermAliases(existing.aliases), ...normalizeTermAliases(row.aliases)]); if (!existing.translated) existing.translated = row.translated; }
      else remaining.push({ ...row, scope: 'all' });
    }
    localConfig.value.terminology.glossary_list = remaining;
    localConfig.value.terminology.custom_glossary_scopes = customGlossaryScopes.value.filter(c => c.value !== id);
    toggleCategory(id, false);
    removedGlossaryTerm.value = null;
    deletingScope.value = '';
  }
  async function focusTerm(term: Term) {
    glossaryListMode.value = 'all';
    termSearchQuery.value = '';
    expandedGroups.value[term.scope || 'all'] = true;
    groupLimits.value[term.scope || 'all'] = Math.max(50, rows.value.filter(row => row.scope === term.scope).indexOf(term) + 1);
    highlightedTerm.value = term;
    await nextTick();
    const element = rowElements.get(term);
    element?.scrollIntoView({ block: 'center' });
    element?.querySelector('input')?.focus();
  }
  function addTerm() {
    const original = newTermOriginal.value.trim();
    if (!original) return;
    const existing = rows.value.find(row => row.original === original && (row.scope || 'all') === newTermScope.value);
    if (existing) { void focusTerm(existing); store.statusMessage = '已有同名詞條，請直接修改。'; return; }
    localConfig.value.terminology.glossary_list = [...rows.value, { original, translated: newTermTranslated.value.trim(), aliases: normalizeTermAliases(newTermAliases.value), scope: newTermScope.value }];
    void focusTerm(rows.value[rows.value.length - 1]!);
    newTermOriginal.value = ''; newTermTranslated.value = ''; newTermAliases.value = '';
  }
  function setTermIdentity(term: Term, original: string, scope: string) {
    original = original.trim();
    const existing = rows.value.find(row => row !== term && row.original === original && (row.scope || 'all') === scope);
    if (!original || existing) { store.statusMessage = existing ? '已有同名詞條，請直接修改。' : '資料不完整，請檢查寫法與分類'; if (existing) void focusTerm(existing); return; }
    term.original = original; term.scope = scope;
  }
  function setTermOriginal(term: Term, event: Event) {
    const input = event.target as HTMLInputElement;
    setTermIdentity(term, input.value, term.scope || 'all'); input.value = term.original;
  }
  function setTermScope(term: Term, value: string | number | null) { setTermIdentity(term, term.original, String(value || 'all')); }
  function setTermAliases(term: Term, event: Event) { term.aliases = normalizeTermAliases((event.target as HTMLInputElement).value); }
  function registerTermRow(term: Term, element: unknown) { if (element instanceof HTMLElement) rowElements.set(term, element); }
  function customizePresetTerm(term: Term) {
    const existing = rows.value.find(row => row.original === term.original && row.scope === term.scope);
    if (existing) { void focusTerm(existing); return; }
    localConfig.value.terminology.glossary_list = [...rows.value, { ...term, aliases: [...term.aliases] }];
    void focusTerm(rows.value[rows.value.length - 1]!);
  }
  function removeTermEntry(term: Term) {
    const index = rows.value.indexOf(term);
    if (index < 0) return;
    removedGlossaryTerm.value = { term: JSON.parse(JSON.stringify(term)), index };
    rows.value.splice(index, 1);
  }
  function undoRemovedGlossaryTerm() {
    const removed = removedGlossaryTerm.value;
    if (!removed) return;
    const existing = rows.value.find(row => row.original === removed.term.original && row.scope === removed.term.scope);
    if (existing) { void focusTerm(existing); store.statusMessage = '已有同名詞條，請直接修改。'; return; }
    rows.value.splice(removed.index, 0, removed.term);
    removedGlossaryTerm.value = null;
    void focusTerm(rows.value[removed.index]!);
  }
  function parseDelimitedRows(text: string): string[][] {
    const source = text.replace(/^\uFEFF/, '');
    const firstLine = source.split(/\r?\n/, 1)[0] || '';
    const delimiterCounts = { ',': 0, '\t': 0, '，': 0 } as Record<string, number>;
    let delimiterQuoted = false;
    for (let index = 0; index < firstLine.length; index += 1) {
      const character = firstLine[index];
      if (character === '"') {
        if (firstLine[index + 1] === '"') index += 1;
        else delimiterQuoted = !delimiterQuoted;
      } else if (!delimiterQuoted && character in delimiterCounts) {
        delimiterCounts[character] += 1;
      }
    }
    const delimiter = (Object.entries(delimiterCounts)
      .sort((left, right) => right[1] - left[1])[0]?.[1] || 0) > 0
      ? Object.entries(delimiterCounts).sort((left, right) => right[1] - left[1])[0][0]
      : ',';
    const rows: string[][] = [];
    let row: string[] = [];
    let field = '';
    let quoted = false;

    const pushRow = () => {
      // Keep quoted whitespace intact, but ignore the incidental whitespace
      // around unquoted values that is common in hand-written CSV files.
      row.push(field);
      if (row.some(value => value.trim())) rows.push(row);
      row = [];
      field = '';
    };

    for (let index = 0; index < source.length; index += 1) {
      const character = source[index];
      if (quoted) {
        if (character === '"') {
          if (source[index + 1] === '"') {
            field += '"';
            index += 1;
          } else {
            quoted = false;
          }
        } else {
          field += character;
        }
      } else if (character === '"' && field.trim() === '') {
        // Permit the common `  "quoted value"` spelling while avoiding the
        // incidental spaces becoming part of the parsed value.
        field = '';
        quoted = true;
      } else if (character === delimiter) {
        row.push(field.trim());
        field = '';
      } else if (character === '\n') {
        pushRow();
      } else if (character === '\r') {
        if (source[index + 1] === '\n') index += 1;
        pushRow();
      } else {
        field += character;
      }
    }
    if (field.length > 0 || row.length > 0) pushRow();
    return rows;
  }

  function csvField(value: unknown): string {
    const text = String(value ?? '');
    return /[",\r\n\t]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }
  async function downloadCsv(filename: string, rows: string[][], label: string): Promise<boolean> {
    if (rows.length === 0) {
      store.statusMessage = `沒有可匯出的${label}`;
      return false;
    }
    // UTF-8 BOM makes Traditional Chinese display correctly in Excel on
    // Windows.  CRLF is also the format Excel expects for a CSV file.
    const csv = `\uFEFF${rows.map(row => row.map(csvField).join(',')).join('\r\n')}\r\n`;
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });

    // Chromium supports a real Save As dialog in normal browser builds. Use it
    // when available; this also works around WebView builds that ignore a
    // synthetic download click.
    const saveFilePicker = (window as any).showSaveFilePicker;
    if (typeof saveFilePicker === 'function') {
      try {
        const handle = await saveFilePicker({
          suggestedName: filename,
          types: [{ description: 'CSV 檔案', accept: { 'text/csv': ['.csv'] } }],
        });
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        store.statusMessage = `已匯出 ${label} CSV`;
        return true;
      } catch (error: any) {
        // User cancellation is not an error. Other picker failures fall back to
        // the standard anchor download below.
        if (error?.name === 'AbortError') return false;
        console.warn('[SettingsView] Save As CSV 失敗，改用瀏覽器下載:', error);
      }
    }

    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    // Keep the anchor and object URL alive long enough for Qt WebEngine and
    // Chromium download handlers to receive the click.
    window.setTimeout(() => {
      anchor.remove();
      URL.revokeObjectURL(url);
    }, 10_000);
    store.statusMessage = `已匯出 ${label} CSV`;
    return true;
  }

  function importGlossary() {
    if (glossaryImporting.value) return;
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.csv,.txt';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      glossaryImporting.value = true;
      try {
        const data = parseDelimitedRows(await file.text());
        const scopes = customGlossaryScopes.value.map(scope => ({ ...scope }));
        for (const row of data.filter(row => row[0]?.trim().toLowerCase() === '#context')) {
          const value = row[1] || ''; const label = row[2] || '';
          if (!value.startsWith('custom_') || !label) throw new Error('資料不完整，請檢查寫法與分類');
          if (!scopes.some(c => c.value === value)) scopes.push({ value, label });
        }
        const options = [...glossaryScopeOptions.value, ...scopes];
        const header = data.find(row => row[0]?.trim().toLowerCase() !== '#context');
        const cells = header?.map(cell => cell.trim().toLowerCase()) || [];
        const newFormat = ['正確寫法,譯法,常見誤辨,分類', 'original,translated,aliases,category'].includes(cells.join(','));
        const legacy = ['original', 'source', '原文', '來源'].includes(cells[0] || '')
          && ['translated', 'translation', 'target', '翻譯', '譯文'].includes(cells[1] || '')
          && (cells.length === 2 || (cells[2] === 'scope' && (cells.length === 3 || (cells.length === 4 && cells[3] === 'aliases'))));
        const asr = ['canonical', 'standard', 'name', '標準', '標準名稱', '正確名稱'].includes(cells[0] || '')
          && cells.length >= 2 && cells.slice(1).every(cell => /^aliases?(?:[ _]?\d+)?$/.test(cell));
        if (!newFormat && !legacy && !asr) throw new Error('無法辨識 CSV 表頭，請使用術語表或舊版匯出格式');
        const imported: Term[] = [];
        for (const row of data) {
          if (row[0]?.trim().toLowerCase() === '#context' || row === header) continue;
          const original = (row[0] || '').trim();
          if (!original) continue;
          const category = asr ? 'all' : row[legacy ? 2 : 3]?.trim() || 'all';
          let scope = options.find(c => c.value === category || c.label === category);
          if (!scope) {
            scope = { value: category.startsWith('custom_') ? category : `custom_${Date.now()}_${scopes.length}`, label: category };
            scopes.push(scope); options.push(scope);
          }
          imported.push({ original, translated: asr ? '' : (row[1] || '').trim(), aliases: normalizeTermAliases(asr ? row.slice(1).flatMap(value => normalizeTermAliases(value)) : row[legacy ? 3 : 2]), scope: scope.value });
        }
        await saveBulkImport('terminology', () => {
          const merged = new Map<string, Term>();
          for (const term of [...rows.value, ...imported]) {
            const original = term.original.trim();
            const key = `${original}\0${term.scope || 'all'}`;
            const existing = merged.get(key);
            merged.set(key, { ...term, original, translated: term.translated.trim() || existing?.translated || '', aliases: normalizeTermAliases([...normalizeTermAliases(existing?.aliases), ...normalizeTermAliases(term.aliases)]) });
          }
          localConfig.value.terminology.custom_glossary_scopes = scopes;
          localConfig.value.terminology.glossary_list = [...merged.values()];
        });
        store.statusMessage = `已匯入並儲存 ${imported.length} 個詞條`;
      } catch (error: any) { store.errorMessage = `匯入失敗：${error?.message || '請檢查 CSV 格式'}`; }
      finally { glossaryImporting.value = false; }
    };
    input.click();
  }
  function exportGlossary() {
    void downloadCsv('glossary.csv', [['正確寫法', '譯法', '常見誤辨', '分類'], ...rows.value.map(term => [term.original, term.translated, normalizeTermAliases(term.aliases).join('、'), glossaryScopeOptions.value.find(c => c.value === (term.scope || 'all'))?.label || term.scope])], '術語表');
  }
  return { aliasSuggestions, suggestionsError, addonError, readingAddon, suggestionActionBusy, addonActionBusy, addonRunning, suggestionsVisible, startSuggestionReview, stopSuggestionReview, refreshAliasSuggestions, refreshReadingAddon, changeReadingAddon, acceptAliasSuggestion, ignoreAliasSuggestion, clearAliasSuggestions, presetCategories, presetLoadError, glossaryImporting, newTermOriginal, newTermTranslated, newTermAliases, newTermScope, newGlossaryScopeName, termSearchQuery, glossaryListMode, editingGlossaryScope, editingGlossaryScopeName, deletingScope, highlightedTerm, removedGlossaryTerm, expandedGroups, groupLimits, glossaryScopeOptions, activeCategoryLabels, effectiveGlossaryCount, groups, categoryCounts, isActive, isBuiltinEnabled, toggleCategory, toggleBuiltin, addGlossaryScope, renameGlossaryScope, removeGlossaryScope, addTerm, setTermOriginal, setTermScope, setTermAliases, registerTermRow, customizePresetTerm, removeTermEntry, undoRemovedGlossaryTerm, importGlossary, exportGlossary, normalizeTermAliases };
}
