import { ref, computed, toRaw, type Ref } from 'vue';
import axios from 'axios';
import type { UiSelectOption } from '../../components/UiSelect.vue';
import { resolveTranslationFamily } from '../../utils/translationFamily';

export function useTranslationSettings(localConfig: Ref<any>, sectionSaveTimers: Map<string, ReturnType<typeof setTimeout>>, saveSectionNow: (section: string) => Promise<void>) {
  const hyMt2HealthChecking = ref(false);
  const hyMt2HealthResult = ref('');
  const translationModelFamilyOptions: UiSelectOption[] = [
    { value: 'auto', label: '自動判斷' },
    { value: 'hy_mt2', label: 'Hy-MT2 專用翻譯模型' },
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
      { value: 'llama', label: '🦙 Llama (本地)' },
    ];
    const customModels: any[] = localConfig.value?.translation?.custom_models || [];
    const customOptions: UiSelectOption[] = customModels.map((m: any) => ({
      value: `custom:${m.name}`,
      label: m.name,
      group: '自訂模型',
    }));
    return [...base, ...customOptions];
  });

  const activeTranslationFamily = computed(() => resolveTranslationFamily(localConfig.value.translation));
  const familySettings = computed(() => activeTranslationFamily.value === 'index_translate' ? 'index_translate' : 'hy_mt2');
  const familyLabel = computed(() => activeTranslationFamily.value === 'index_translate' ? 'Index-Translate' : 'HY-MT2');
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
    const custom = (t.custom_models || []).find((m: any) => `custom:${m.name}` === selected);
    return `目前模型 · ${custom?.model_name || t.gpt_model || selected}`;
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
    familySettings,
    familyLabel,
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
