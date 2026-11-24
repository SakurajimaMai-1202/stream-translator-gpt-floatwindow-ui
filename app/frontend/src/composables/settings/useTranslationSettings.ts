import { ref, computed, toRaw, watch, onBeforeUnmount, type Ref } from 'vue';
import axios from 'axios';
import type { UiSelectOption } from '../../components/UiSelect.vue';
import { resolveTranslationFamily } from '../../utils/translationFamily';
import { useLlamaStore } from '../../stores/llama';

export function useTranslationSettings(localConfig: Ref<any>, sectionSaveTimers: Map<string, ReturnType<typeof setTimeout>>, saveSectionNow: (section: string) => Promise<void>) {
  const hyMt2HealthChecking = ref(false);
  const hyMt2HealthResult = ref('');
  const translationModelFamilyOptions: UiSelectOption[] = [
    { value: 'auto', label: '自動判斷' },
    { value: 'hy_mt2', label: 'Hy-MT 專用翻譯模型（Hy-MT2／Hy-MT3）' },
    { value: 'index_translate', label: 'Index-Translate 專用翻譯模型' },
    { value: 'generic_chat', label: '通用聊天模型（Gemma 等）' },
    { value: 'structured_api', label: '結構化 API（OpenAI / Gemini）' },
  ];
  const translationOutputFormatOptions: UiSelectOption[] = [
    { value: 'auto', label: '自動' },
    { value: 'text', label: '純文字' },
    { value: 'json', label: 'JSON' },
  ];
  const targetLanguageOptions: UiSelectOption[] = [
    { value: 'Traditional Chinese', label: '繁體中文' },
    { value: 'Simplified Chinese', label: '簡體中文' },
    { value: 'Japanese', label: '日文' },
    { value: 'English', label: '英文' },
    { value: 'Korean', label: '韓文' },
  ];

  const translationBackendOptions = computed<UiSelectOption[]>(() => {
    const base: UiSelectOption[] = [
      { value: 'none', label: '不翻譯' },
      { value: 'gpt', label: 'OpenAI GPT' },
      { value: 'gemini', label: 'Google Gemini' },
      { value: 'llama', label: '本機模型（llama.cpp）' },
    ];
    const customModels: any[] = localConfig.value?.translation?.custom_models || [];
    const customOptions: UiSelectOption[] = customModels.map((m: any) => ({
      value: `custom:${m.name}`,
      label: m.name,
      group: '自訂模型',
    }));
    return [...base, ...customOptions];
  });

  // A local alias such as "localllm" hides the family, so ask the backend which
  // model the server really serves when the name alone gives no hint.
  const detectedFamily = ref('');
  const servedModels = ref<string[]>([]);
  const familyDetecting = ref(false);
  let detectTimer: ReturnType<typeof setTimeout> | undefined;
  let detectSeq = 0;
  const nameFamily = computed(() => resolveTranslationFamily(localConfig.value?.translation || {}));
  const familyNeedsServerProbe = computed(() => {
    const t = localConfig.value?.translation || {};
    return String(t.translation_model_family || 'auto') === 'auto'
      && !['hy_mt2', 'index_translate'].includes(nameFamily.value)
      && String(t.backend || 'none') !== 'none';
  });
  async function detectServedFamily() {
    const seq = ++detectSeq;
    familyDetecting.value = true;
    try {
      const response = await axios.post('/api/translation/detect-family', {config: {translation: toRaw(localConfig.value.translation), llama: toRaw(localConfig.value.llama)}});
      if (seq !== detectSeq) return;
      detectedFamily.value = String(response.data?.family || '');
      servedModels.value = Array.isArray(response.data?.served_models) ? response.data.served_models : [];
    } catch {
      if (seq === detectSeq) { detectedFamily.value = ''; servedModels.value = []; }
    } finally {
      if (seq === detectSeq) familyDetecting.value = false;
    }
  }
  const llamaStore = useLlamaStore();
  // Opening settings first leaves the llama store empty; load it to name the selected model.
  if (!llamaStore.selectedModelPath) void llamaStore.loadConfig().catch(() => {});
  function scheduleFamilyDetection() {
    if (detectTimer) clearTimeout(detectTimer);
    detectSeq++;
    if (familyNeedsServerProbe.value) {
      familyDetecting.value = true;
      detectTimer = setTimeout(detectServedFamily, 400);
    } else {
      familyDetecting.value = false;
      detectedFamily.value = '';
      servedModels.value = [];
    }
  }
  // Switching models restarts the server without touching translation settings.
  watch(() => [llamaStore.isServerRunning, llamaStore.currentModel], scheduleFamilyDetection);
  watch(() => {
    const t = localConfig.value?.translation || {};
    return JSON.stringify([t.backend, t.gpt_model, t.translation_model_family, t.index_translate_provider, t.hy_mt2_provider,
      (t.custom_models || []).map((m: any) => [m.name, m.base_url || m.api_url, m.model_name]),
      localConfig.value?.llama?.model_path, localConfig.value?.llama?.host, localConfig.value?.llama?.port]);
  }, () => {
    if (detectTimer) clearTimeout(detectTimer);
    detectSeq++;
    detectedFamily.value = '';
    servedModels.value = [];
    if (familyNeedsServerProbe.value) {
      familyDetecting.value = true;
      detectTimer = setTimeout(detectServedFamily, 400);
    } else {
      familyDetecting.value = false;
    }
  }, {immediate: true});
  onBeforeUnmount(() => { if (detectTimer) clearTimeout(detectTimer); });
  const activeTranslationFamily = computed(() => (
    familyNeedsServerProbe.value && ['hy_mt2', 'index_translate'].includes(detectedFamily.value)
      ? detectedFamily.value : nameFamily.value));
  const familySettings = computed(() => activeTranslationFamily.value === 'index_translate' ? 'index_translate' : 'hy_mt2');
  const familyLabel = computed(() => activeTranslationFamily.value === 'index_translate' ? 'Index-Translate' : 'HY-MT');
  const optimizerEffective = computed(() => String(localConfig.value.translation.backend || 'none') !== 'none' && ['hy_mt2', 'index_translate'].includes(activeTranslationFamily.value) && (localConfig.value.translation.family_optimizer_auto === true || localConfig.value.translation[familySettings.value + '_optimizer_enabled'] === true));
  const previewText = ref('今日はすいちゃんと一緒にゲームをします。');
  const previewContext = ref('');
  const previewBusy = ref(false);
  const previewError = ref('');
  const previewResult = ref<any>(null);
  function previewValidationStatus(result: any): string {
    const reasons = Array.isArray(result?.validation)
      ? result.validation.map((issue: any) => issue.code).filter(Boolean).join('、') : '';
    if (result?.error) return reasons ? `未通過：${reasons}` : '未完成：翻譯請求失敗';
    if (!String(result?.translation || '').trim()) return reasons ? `未通過：${reasons}` : '未通過：空白譯文';
    return reasons ? `未通過：${reasons}` : '通過';
  }
  function previewLatencyLabel(value: unknown): string {
    const milliseconds = Number(value);
    return Number.isFinite(milliseconds) && milliseconds >= 0 ? `${Math.round(milliseconds)} ms` : '未取得';
  }

  async function runTranslationPreview() {
    previewBusy.value = true;
    previewError.value = '';
    previewResult.value = null;
    try {
      const response = await axios.post('/api/translation/preview', {
        text: previewText.value,
        context: previewContext.value.split('\n').filter(Boolean).map(source => ({source, target: ''})),
        config: { translation: toRaw(localConfig.value.translation), terminology: toRaw(localConfig.value.terminology), transcription: {language: localConfig.value.transcription.language} },
      });
      previewResult.value = response.data;
    } catch (e: any) {
      previewError.value = e?.response?.data?.detail || '試譯失敗，請檢查端點與模型 ID。';
    } finally { previewBusy.value = false; }
  }

  const hyMt2EffectiveBackend = computed(() => {
    const t = localConfig.value.translation;
    const provider = t[familySettings.value + '_provider'];
    if (['lm_studio', 'llama_cpp'].includes(provider)) {
      return `${provider === 'lm_studio' ? 'LM Studio' : 'llama.cpp'} · ${t[familySettings.value + '_' + provider + '_model'] || '尚未填模型 ID'}`;
    }
    const selected = String(t.backend || 'none');
    if (servedModels.value.length) return servedModels.value[0];
    if (['llama', 'localllm'].includes(selected)) {
      // The settings page's localConfig has no llama section; the llama store holds the selected GGUF.
      const modelPath = String(llamaStore.selectedModelPath || localConfig.value.llama?.model_path || '');
      const modelFile = modelPath.split(/[\\/]/).pop() || '';
      return modelFile || t.gpt_model;
    }
    const custom = (t.custom_models || []).find((m: any) => `custom:${m.name}` === selected);
    if (selected.startsWith('custom:')) return custom?.model_name || custom?.name || t.gpt_model;
    return t.gpt_model || selected;
  });

  async function checkHyMt2Backend() {
    hyMt2HealthChecking.value = true;
    hyMt2HealthResult.value = '';
    try {
      const pendingSave = sectionSaveTimers.get('translation');
      if (pendingSave) clearTimeout(pendingSave);
      sectionSaveTimers.delete('translation');
      await saveSectionNow('translation');
      const response = await axios.post('/api/translation/health', {config: {translation: toRaw(localConfig.value.translation), terminology: toRaw(localConfig.value.terminology)}});
      const result = response.data;
      hyMt2HealthResult.value = `已連線 ${result.model}；測試回應「${result.sample}」（${result.latency_ms} ms）`;
    } catch (error: any) {
      hyMt2HealthResult.value = `連線失敗：${error?.response?.data?.detail || error?.message || '未知錯誤'}`;
    } finally {
      hyMt2HealthChecking.value = false;
    }
  }


  return {
    hyMt2HealthChecking,
    hyMt2HealthResult,
    translationModelFamilyOptions,
    translationOutputFormatOptions,
    targetLanguageOptions,
    translationBackendOptions,
    activeTranslationFamily,
    servedModels,
    familyDetecting,
    scheduleFamilyDetection,
    familySettings,
    familyLabel,
    optimizerEffective,
    previewText,
    previewContext,
    previewBusy,
    previewError,
    previewResult,
    previewValidationStatus,
    previewLatencyLabel,
    runTranslationPreview,
    hyMt2EffectiveBackend,
    checkHyMt2Backend,
  };
}

