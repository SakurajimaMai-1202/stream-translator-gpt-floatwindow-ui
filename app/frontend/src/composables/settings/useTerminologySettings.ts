import { ref, computed, watch, nextTick, toRaw, type Ref } from 'vue';
import type { useTranslationStore } from '../../stores/translation';

export function useTerminologySettings(localConfig: Ref<any>, store: ReturnType<typeof useTranslationStore>, saveBulkImport: (section: 'terminology' | 'transcription', applyImport: () => void) => Promise<void>) {
  const glossaryImporting = ref(false);
  const asrCorrectionsImporting = ref(false);
  const newTermOriginal = ref('');
  const newTermTranslated = ref('');
  const newTermAliases = ref('');
  const newTermScope = ref('all');
  const glossaryEntryForm = ref<HTMLElement | null>(null);
  const glossaryUserList = ref<HTMLElement | null>(null);
  const termSearchQuery = ref('');
  const terminologySubTab = ref<'translation' | 'asr'>('translation');
  const expandedGlossaryTerm = ref<any | null>(null);
  const selectedGlossaryTerms = ref<any[]>([]);
  const bulkGlossaryScope = ref('hololive_vtuber');
  const removedGlossaryTerm = ref<{ term: any; index: number } | null>(null);
  const glossaryListMode = ref<'active' | 'all' | 'global'>('active');
  const presetGlossaries = ref<Record<string, Record<string, string>>>({});
  const builtinGlossaryScopeOptions = [
    { value: 'all', label: '所有直播' },
    { value: 'general_chat', label: '日文雜談' },
    { value: 'hololive_vtuber', label: 'Hololive／VTuber 雜談' },
    { value: 'cosplay', label: 'Cosplay 雜談' },
  ];
  const customGlossaryScopes = computed<{ value: string; label: string }[]>(() =>
    Array.isArray(localConfig.value.terminology?.custom_glossary_scopes)
      ? localConfig.value.terminology.custom_glossary_scopes.filter((scope: any) =>
        typeof scope?.value === 'string' && scope.value.startsWith('custom_') && typeof scope?.label === 'string')
      : []);
  const glossaryScopeOptions = computed(() => [...builtinGlossaryScopeOptions, ...customGlossaryScopes.value]);
  const newGlossaryScopeName = ref('');
  const editingGlossaryScope = ref('');
  const editingGlossaryScopeName = ref('');
  const selectedGlossaryPreset = computed(() => String(localConfig.value.translation?.translation_glossary_scope ?? localConfig.value.translation?.hy_mt2_glossary_preset ?? ''));
  const selectedGlossaryPresetLabel = computed(() => glossaryScopeOptions.value.find(option => option.value === selectedGlossaryPreset.value)?.label || '不加情境詞表');
  const activeUserGlossaryRows = computed<any[]>(() => {
    const rows: any[] = localConfig.value.terminology?.glossary_list || [];
    const globalRows = rows.filter(row => String(row?.scope || 'all') === 'all');
    const scopedRows = rows.filter(row => selectedGlossaryPreset.value && row?.scope === selectedGlossaryPreset.value);
    return [...globalRows, ...scopedRows];
  });
  const userGlossaryBySource = computed(() => {
    const values = new Map<string, string>();
    if (!localConfig.value.terminology?.use_terminology_glossary) return values;
    const legacy = localConfig.value.terminology?.terminology_glossary || {};
    if (Object.keys(legacy).length > 0) {
      for (const [source, target] of Object.entries(legacy)) values.set(source, String(target));
    } else {
      for (const row of activeUserGlossaryRows.value) {
        if (row.original?.trim() && row.translated?.trim()) values.set(row.original.trim(), row.translated.trim());
      }
    }
    return values;
  });
  const selectedPresetPreview = computed(() => Object.entries(presetGlossaries.value[selectedGlossaryPreset.value] || {}).map(([source, target]) => ({
    source, target, override: userGlossaryBySource.value.get(source),
  })));
  const activeGlossaryRows = computed<any[]>(() => {
    const legacy = localConfig.value.terminology?.terminology_glossary || {};
    const userRows = !localConfig.value.terminology?.use_terminology_glossary ? []
      : Object.keys(legacy).length
        ? Object.entries(legacy).map(([original, translated]) => ({ original, translated: String(translated), legacy: true }))
        : [...new Map(activeUserGlossaryRows.value.map(row => [row.original?.trim(), row])).values()];
    const userSources = new Set(userRows.map(row => row.original?.trim()));
    const builtinRows = selectedPresetPreview.value
      .filter(term => !userSources.has(term.source))
      .map(term => ({ original: term.source, translated: term.target, scope: selectedGlossaryPreset.value, builtin: true }));
    return [...userRows, ...builtinRows];
  });
  const effectiveGlossaryCount = computed(() => {
    const sources = new Set(userGlossaryBySource.value.keys());
    for (const term of selectedPresetPreview.value) sources.add(term.source);
    return sources.size;
  });
  const newAsrCanonical = ref('');
  const newAsrAliases = ref('');
  const asrCorrectionSearchQuery = ref('');
  const LARGE_LIST_BATCH_SIZE = 100;
  const GLOSSARY_PAGE_SIZE = 20;
  const glossaryRenderLimit = ref(GLOSSARY_PAGE_SIZE);
  const asrCorrectionRenderLimit = ref(LARGE_LIST_BATCH_SIZE);

  // 過濾後的術語表
  const filteredGlossary = computed(() => {
    const allRows = localConfig.value.terminology?.glossary_list || [];
    const list = glossaryListMode.value === 'active' ? activeGlossaryRows.value
      : glossaryListMode.value === 'global' ? allRows.filter((row: any) => String(row?.scope || 'all') === 'all')
      : allRows;
    if (!termSearchQuery.value.trim()) return list;
    const query = termSearchQuery.value.toLowerCase();
    return list.filter((item: any) => 
      item.original?.toLowerCase().includes(query) ||
      item.translated?.toLowerCase().includes(query)
    );
  });

  const filteredAsrCorrections = computed(() => {
    const rules = localConfig.value.transcription?.asr_correction_rules || [];
    const query = asrCorrectionSearchQuery.value.trim().toLowerCase();
    if (!query) return rules;
    return rules.filter((rule: any) =>
      rule.canonical?.toLowerCase().includes(query) ||
      (rule.aliases || []).some((alias: string) => alias.toLowerCase().includes(query))
    );
  });

  const visibleGlossary = computed(() => filteredGlossary.value.slice(0, glossaryRenderLimit.value));
  const visibleAsrCorrections = computed(() => filteredAsrCorrections.value.slice(0, asrCorrectionRenderLimit.value));

  watch(termSearchQuery, () => {
    glossaryRenderLimit.value = GLOSSARY_PAGE_SIZE;
  });
  watch(selectedGlossaryPreset, (preset) => {
    newTermScope.value = preset || 'all';
    glossaryRenderLimit.value = GLOSSARY_PAGE_SIZE;
  });
  watch(glossaryListMode, () => {
    glossaryRenderLimit.value = GLOSSARY_PAGE_SIZE;
  });
  watch(asrCorrectionSearchQuery, () => {
    asrCorrectionRenderLimit.value = LARGE_LIST_BATCH_SIZE;
  });
  function addGlossaryScope() {
    const label = newGlossaryScopeName.value.trim();
    if (!label) return;
    if (glossaryScopeOptions.value.some(scope => scope.label.toLocaleLowerCase() === label.toLocaleLowerCase())) {
      store.statusMessage = '已有同名情境，請換一個名稱';
      return;
    }
    const value = `custom_${crypto.randomUUID()}`;
    if (!Array.isArray(localConfig.value.terminology.custom_glossary_scopes)) {
      localConfig.value.terminology.custom_glossary_scopes = [];
    }
    localConfig.value.terminology.custom_glossary_scopes.push({ value, label });
    localConfig.value.translation.translation_glossary_scope = value;
    newGlossaryScopeName.value = '';
    store.statusMessage = `已建立「${label}」，儲存設定後可在翻譯時使用`;
  }

  function renameGlossaryScope(scope: { value: string; label: string }) {
    const label = editingGlossaryScopeName.value.trim();
    if (!label) return;
    if (glossaryScopeOptions.value.some(other => other.value !== scope.value && other.label.toLocaleLowerCase() === label.toLocaleLowerCase())) {
      store.statusMessage = '已有同名情境，請換一個名稱';
      return;
    }
    scope.label = label;
    editingGlossaryScope.value = '';
  }

  function removeGlossaryScope(scope: { value: string; label: string }) {
    const count = (localConfig.value.terminology.glossary_list || []).filter((term: any) => term.scope === scope.value).length;
    if (count) {
      store.statusMessage = `「${scope.label}」還有 ${count} 筆詞條，請先將詞條移到其他情境`;
      glossaryListMode.value = 'all';
      return;
    }
    localConfig.value.terminology.custom_glossary_scopes = customGlossaryScopes.value.filter(item => item.value !== scope.value);
    if (selectedGlossaryPreset.value === scope.value) localConfig.value.translation.translation_glossary_scope = '';
    if (newTermScope.value === scope.value) newTermScope.value = 'all';
    if (bulkGlossaryScope.value === scope.value) bulkGlossaryScope.value = 'all';
    editingGlossaryScope.value = '';
  }

  function addTerm() {
    if (!newTermOriginal.value.trim() || !newTermTranslated.value.trim()) return;
    if (!localConfig.value.terminology.glossary_list) {
      localConfig.value.terminology.glossary_list = [];
    }
    const original = newTermOriginal.value.trim();
    if (localConfig.value.terminology.glossary_list.some((term: any) =>
      term.original?.trim() === original && String(term.scope || 'all') === newTermScope.value)) {
      store.statusMessage = `「${original}」已在此情境存在；請直接編輯下方詞條`;
      glossaryListMode.value = 'all';
      termSearchQuery.value = original;
      return;
    }
    const created = {
      original,
      translated: newTermTranslated.value.trim(),
      aliases: newTermAliases.value.split(',').map(s => s.trim()).filter(Boolean),
      scope: newTermScope.value,
    };
    localConfig.value.terminology.glossary_list.push(created);
    expandedGlossaryTerm.value = created;
    termSearchQuery.value = original;
    if (newTermScope.value !== 'all' && newTermScope.value !== selectedGlossaryPreset.value) glossaryListMode.value = 'all';
    newTermOriginal.value = '';
    newTermTranslated.value = '';
    newTermAliases.value = '';
  }

  function removeTerm(index: number) {
    localConfig.value.terminology.glossary_list.splice(index, 1);
  }

  function removeTermEntry(term: any) {
    const list = localConfig.value.terminology.glossary_list || [];
    const index = list.indexOf(term);
    if (index < 0) return;
    removedGlossaryTerm.value = { term: structuredClone(toRaw(term)), index };
    removeTerm(index);
    selectedGlossaryTerms.value = selectedGlossaryTerms.value.filter(item => item !== term);
    if (expandedGlossaryTerm.value === term) expandedGlossaryTerm.value = null;
  }

  function undoRemovedGlossaryTerm() {
    const removed = removedGlossaryTerm.value;
    if (!removed) return;
    localConfig.value.terminology.glossary_list.splice(removed.index, 0, removed.term);
    removedGlossaryTerm.value = null;
  }

  function toggleGlossarySelection(term: any, checked: boolean) {
    selectedGlossaryTerms.value = checked
      ? [...selectedGlossaryTerms.value.filter(item => item !== term), term]
      : selectedGlossaryTerms.value.filter(item => item !== term);
  }

  function selectVisibleGlossaryTerms() {
    selectedGlossaryTerms.value = [...new Set([...selectedGlossaryTerms.value, ...visibleGlossary.value.filter((term: any) => !term.builtin && !term.legacy)])];
  }

  function applySelectedGlossaryScope() {
    const rows = localConfig.value.terminology.glossary_list || [];
    let changed = 0;
    let conflicts = 0;
    for (const term of selectedGlossaryTerms.value) {
      if (!rows.includes(term) || String(term.scope || 'all') === bulkGlossaryScope.value) continue;
      const duplicate = rows.some((other: any) => other !== term
        && other.original?.trim() === term.original?.trim()
        && String(other.scope || 'all') === bulkGlossaryScope.value);
      if (duplicate) { conflicts += 1; continue; }
      term.scope = bulkGlossaryScope.value;
      changed += 1;
    }
    selectedGlossaryTerms.value = [];
    store.statusMessage = `已調整 ${changed} 筆詞條${conflicts ? `；${conflicts} 筆因同情境已有相同原詞而略過` : ''}`;
  }

  function setTermScope(term: any, value: string | number | null) {
    const scope = String(value || 'all');
    const duplicate = (localConfig.value.terminology.glossary_list || []).some((other: any) =>
      other !== term && other.original?.trim() === term.original?.trim() && String(other.scope || 'all') === scope);
    if (duplicate) {
      store.statusMessage = `「${term.original}」在此情境已有譯法；請先處理重複詞條`;
      return;
    }
    term.scope = scope;
  }

  function setTermAliases(term: any, event: Event) {
    term.aliases = (event.target as HTMLInputElement).value.split(/[,，]/).map(value => value.trim()).filter(Boolean);
  }

  function customizePresetTerm(source: string, target: string, hasOverride: boolean) {
    if (hasOverride) {
      glossaryListMode.value = 'active';
      termSearchQuery.value = source;
      expandedGlossaryTerm.value = Object.keys(localConfig.value.terminology?.terminology_glossary || {}).length
        ? null : activeUserGlossaryRows.value.find(row => row.original?.trim() === source) || null;
      void nextTick(() => glossaryUserList.value?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
      return;
    }
    newTermOriginal.value = source;
    newTermTranslated.value = target;
    newTermAliases.value = '';
    newTermScope.value = selectedGlossaryPreset.value || 'all';
    void nextTick(() => glossaryEntryForm.value?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  }

  /**
   * Parse the two-column files accepted by the settings page.
   *
   * The old implementation used `split(',')`, which made an exported glossary
   * unusable as soon as a term contained a comma, a quote, or a line break.  A
   * small RFC-4180 compatible parser keeps this dependency-free and also accepts
   * tab-separated text exported by spreadsheet applications.
   */
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

  function isGlossaryHeader(row: string[]): boolean {
    const original = (row[0] || '').trim().toLowerCase();
    const translated = (row[1] || '').trim().toLowerCase();
    return ['original', 'source', '原文', '來源'].includes(original)
      && ['translated', 'translation', 'target', '翻譯', '譯文'].includes(translated);
  }

  function isAsrCorrectionHeader(row: string[]): boolean {
    const canonical = (row[0] || '').trim().toLowerCase();
    return ['canonical', 'standard', 'name', '標準', '標準名稱', '正確名稱'].includes(canonical);
  }

  function csvField(value: unknown): string {
    const text = String(value ?? '');
    return /[",\r\n\t]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  }

  function glossaryExportRows(): string[][] {
    const terminology = localConfig.value.terminology || {};
    const rows: string[][] = [];
    const seen = new Set<string>();
    const add = (original: unknown, translated: unknown, scope: unknown = 'all', aliases: unknown = []) => {
      const source = String(original ?? '').trim();
      const target = String(translated ?? '').trim();
      const termScope = String(scope || 'all');
      if (!source || !target) return;
      const key = `${source}\u0000${termScope}`;
      if (seen.has(key)) return;
      seen.add(key);
      const aliasList = Array.isArray(aliases) ? aliases : String(aliases || '').split(/[,，]/);
      rows.push([source, target, termScope, aliasList.map(value => String(value).trim()).filter(Boolean).join(', ')]);
    };

    if (terminology.terminology_glossary && typeof terminology.terminology_glossary === 'object') {
      for (const [original, translated] of Object.entries(terminology.terminology_glossary)) {
        add(original, translated);
      }
    }
    if (Array.isArray(terminology.glossary_list)) {
      for (const term of terminology.glossary_list) add(term?.original, term?.translated, term?.scope, term?.aliases);
    }
    // Older configurations used `glossary` as either a JSON object or a small
    // delimited text block. Include it as well so export always means *all*.
    if (typeof terminology.glossary === 'string' && terminology.glossary.trim()) {
      const legacy = terminology.glossary.trim();
      try {
        const parsed = JSON.parse(legacy);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          for (const [original, translated] of Object.entries(parsed)) add(original, translated);
        }
      } catch {
        for (const row of parseDelimitedRows(legacy)) {
          if (row.length >= 2 && !isGlossaryHeader(row)) add(row[0], row[1]);
        }
      }
    }
    const scopeRows = customGlossaryScopes.value.map(scope => ['#context', scope.value, scope.label, '']);
    return rows.length || scopeRows.length ? [...scopeRows, ['original', 'translated', 'scope', 'aliases'], ...rows] : [];
  }

  function asrCorrectionExportRows(): string[][] {
    const rawRules = localConfig.value.transcription?.asr_correction_rules;
    let rules: any[] = Array.isArray(rawRules) ? rawRules : [];
    if (typeof rawRules === 'string' && rawRules.trim()) {
      try {
        const parsed = JSON.parse(rawRules);
        if (Array.isArray(parsed)) rules = parsed;
        else if (parsed && typeof parsed === 'object') {
          rules = Object.entries(parsed).map(([canonical, aliases]) => ({ canonical, aliases }));
        }
      } catch {
        rules = parseDelimitedRows(rawRules).map(row => ({ canonical: row[0], aliases: row.slice(1) }));
      }
    }

    const rows: string[][] = [];
    const seen = new Set<string>();
    for (const rule of rules) {
      const canonical = String(rule?.canonical ?? rule?.original ?? '').trim();
      const aliases = Array.isArray(rule?.aliases)
        ? rule.aliases
        : String(rule?.aliases ?? '').split(/[,，\t\r\n]/);
      const values = [canonical, ...aliases.map((value: unknown) => String(value ?? '').trim())]
        .filter((value, index, all) => value && (index === 0 || value !== canonical) && all.indexOf(value) === index);
      if (values.length < 2) continue;
      const key = values.join('\u0000');
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push(values);
    }
    return rows;
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
    input.type = 'file';
    input.accept = '.txt,.csv';
    input.onchange = async (e: any) => {
      const file = e.target.files[0];
      if (!file) return;
      glossaryImporting.value = true;
      try {
        const rows = parseDelimitedRows(await file.text());
        const importedScopes = rows.filter(row => row[0]?.trim() === '#context').map(row => ({
          value: row[1]?.trim() || '', label: row[2]?.trim() || '',
        }));
        const existingScopeIds = new Set(glossaryScopeOptions.value.map(option => option.value));
        const importedIds = new Set<string>();
        const importedNames = new Set<string>();
        for (const scope of importedScopes) {
          const normalizedName = scope.label.toLocaleLowerCase();
          if (!/^custom_[0-9a-f-]{36}$/i.test(scope.value) || !scope.label || scope.label.length > 40 || importedIds.has(scope.value) || importedNames.has(normalizedName)) {
            throw new Error('CSV 中的自訂情境資料無效或重複');
          }
          const existing = glossaryScopeOptions.value.find(item => item.value === scope.value);
          if (existing && existing.label !== scope.label) throw new Error(`情境 ID 衝突：${scope.value}`);
          if (!existing && glossaryScopeOptions.value.some(item => item.label.toLocaleLowerCase() === normalizedName)) {
            throw new Error(`已有同名情境：${scope.label}`);
          }
          importedIds.add(scope.value);
          importedNames.add(normalizedName);
        }
        const allowedScopes = new Set([...existingScopeIds, ...importedIds]);
        const newTerms: any[] = rows
          .filter(row => row.length >= 2 && row[0]?.trim() !== '#context' && !isGlossaryHeader(row))
          .map(row => {
            const scope = (row[2] || 'all').trim();
            if (!allowedScopes.has(scope)) throw new Error(`未知適用情境：${scope}`);
            return {
              original: row[0].trim(), translated: row[1].trim(), scope,
              ...(row.length >= 4 ? { aliases: row[3].split(/[,，]/).map(value => value.trim()).filter(Boolean) } : {}),
            };
          })
          .filter(term => term.original && term.translated);
        let mergedCount = localConfig.value.terminology.glossary_list?.length || 0;
        await saveBulkImport('terminology', () => {
          const currentScopes = Array.isArray(localConfig.value.terminology.custom_glossary_scopes)
            ? localConfig.value.terminology.custom_glossary_scopes : [];
          localConfig.value.terminology.custom_glossary_scopes = [
            ...currentScopes, ...importedScopes.filter(scope => !existingScopeIds.has(scope.value)),
          ];
          const merged = mergeGlossaryTerms(localConfig.value.terminology.glossary_list || [], newTerms);
          mergedCount = merged.length;
          localConfig.value.terminology.glossary_list = merged;
        });
        store.statusMessage = `詞語表匯入完成：讀取 ${newTerms.length} 筆，合併後共 ${mergedCount} 筆`;
      } catch (error: any) {
        store.errorMessage = `詞語表匯入失敗：${error?.message || '未知錯誤'}`;
      } finally {
        glossaryImporting.value = false;
      }
    };
    input.click();
  }

  function exportGlossary() {
    void downloadCsv('glossary.csv', glossaryExportRows(), '術語');
  }

  function mergeGlossaryTerms(existing: any[], imported: any[]): any[] {
    const merged = new Map<string, any>();
    for (const term of [...existing, ...imported]) {
      const original = String(term?.original || '').trim();
      const translated = String(term?.translated || '').trim();
      const scope = String(term?.scope || 'all');
      if (original && translated) {
        const key = `${original}\u0000${scope}`;
        merged.set(key, { ...(merged.get(key) || {}), ...term, original, translated, scope });
      }
    }
    return [...merged.values()];
  }

  function mergeAsrCorrectionRules(existing: any[], imported: any[]): any[] {
    const merged = new Map<string, Set<string>>();
    for (const rule of [...existing, ...imported]) {
      const canonical = String(rule?.canonical || '').trim();
      if (!canonical) continue;
      const aliases = merged.get(canonical) || new Set<string>();
      for (const value of rule?.aliases || []) {
        const alias = String(value || '').trim();
        if (alias && alias !== canonical) aliases.add(alias);
      }
      if (aliases.size > 0) merged.set(canonical, aliases);
    }
    return [...merged.entries()].map(([canonical, aliases]) => ({ canonical, aliases: [...aliases] }));
  }

  function addAsrCorrection() {
    const canonical = newAsrCanonical.value.trim();
    const aliases = newAsrAliases.value
      .split(/[,，\n]/)
      .map(value => value.trim())
      .filter((value, index, values) => value && value !== canonical && values.indexOf(value) === index);
    if (!canonical || aliases.length === 0) return;
    if (!localConfig.value.transcription.asr_correction_rules) {
      localConfig.value.transcription.asr_correction_rules = [];
    }
    localConfig.value.transcription.asr_correction_rules.push({ canonical, aliases });
    newAsrCanonical.value = '';
    newAsrAliases.value = '';
  }

  function removeAsrCorrection(rule: any) {
    const rules = localConfig.value.transcription.asr_correction_rules || [];
    const index = rules.indexOf(rule);
    if (index >= 0) rules.splice(index, 1);
  }

  function importAsrCorrections() {
    if (asrCorrectionsImporting.value) return;
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.txt,.csv';
    input.onchange = async (event: any) => {
      const file = event.target.files[0];
      if (!file) return;
      asrCorrectionsImporting.value = true;
      try {
        const imported = parseDelimitedRows(await file.text())
          .filter(row => row.length >= 2 && !isAsrCorrectionHeader(row))
          .map(row => {
            const canonical = row[0].trim();
            const aliases = row.slice(1)
              .map(value => value.trim())
              .filter((value, index, values) => value && value !== canonical && values.indexOf(value) === index);
            return { canonical, aliases };
          })
          .filter(rule => rule.canonical && rule.aliases.length > 0);
        let mergedCount = localConfig.value.transcription.asr_correction_rules?.length || 0;
        await saveBulkImport('transcription', () => {
          const merged = mergeAsrCorrectionRules(
            localConfig.value.transcription.asr_correction_rules || [],
            imported,
          );
          mergedCount = merged.length;
          localConfig.value.transcription.asr_correction_rules = merged;
        });
        store.statusMessage = `ASR 校正表匯入完成：讀取 ${imported.length} 筆，合併後共 ${mergedCount} 筆`;
      } catch (error: any) {
        store.errorMessage = `ASR 校正表匯入失敗：${error?.message || '未知錯誤'}`;
      } finally {
        asrCorrectionsImporting.value = false;
      }
    };
    input.click();
  }

  function exportAsrCorrections() {
    void downloadCsv('asr-name-corrections.csv', asrCorrectionExportRows(), 'ASR 修正規則');
  }


  return {
    glossaryImporting,
    asrCorrectionsImporting,
    newTermOriginal,
    newTermTranslated,
    newTermAliases,
    newTermScope,
    glossaryEntryForm,
    glossaryUserList,
    termSearchQuery,
    terminologySubTab,
    expandedGlossaryTerm,
    selectedGlossaryTerms,
    bulkGlossaryScope,
    removedGlossaryTerm,
    glossaryListMode,
    presetGlossaries,
    customGlossaryScopes,
    glossaryScopeOptions,
    newGlossaryScopeName,
    editingGlossaryScope,
    editingGlossaryScopeName,
    selectedGlossaryPresetLabel,
    userGlossaryBySource,
    selectedPresetPreview,
    effectiveGlossaryCount,
    newAsrCanonical,
    newAsrAliases,
    asrCorrectionSearchQuery,
    LARGE_LIST_BATCH_SIZE,
    GLOSSARY_PAGE_SIZE,
    glossaryRenderLimit,
    asrCorrectionRenderLimit,
    filteredGlossary,
    filteredAsrCorrections,
    visibleGlossary,
    visibleAsrCorrections,
    addGlossaryScope,
    renameGlossaryScope,
    removeGlossaryScope,
    addTerm,
    removeTermEntry,
    undoRemovedGlossaryTerm,
    toggleGlossarySelection,
    selectVisibleGlossaryTerms,
    applySelectedGlossaryScope,
    setTermScope,
    setTermAliases,
    customizePresetTerm,
    importGlossary,
    exportGlossary,
    addAsrCorrection,
    removeAsrCorrection,
    importAsrCorrections,
    exportAsrCorrections,
  };
}
