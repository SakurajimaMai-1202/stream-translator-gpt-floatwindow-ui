import type { AsrModelCapability } from '../services/api';
import type { UiSelectOption } from '../components/UiSelect.vue';

export const ASR_LANGUAGE_OPTIONS: UiSelectOption[] = [
  { value: 'auto', label: '自動偵測' },
  { value: 'zh-tw', label: '中文（繁體）' },
  { value: 'zh-cn', label: '中文（簡體）' },
  { value: 'yue', label: '粵語' },
  { value: 'en', label: '英文' },
  { value: 'ja', label: '日文' },
  { value: 'ko', label: '韓文' },
  { value: 'ar', label: '阿拉伯文' },
  { value: 'de', label: '德文' },
  { value: 'fr', label: '法文' },
  { value: 'es', label: '西班牙文' },
  { value: 'pt', label: '葡萄牙文' },
  { value: 'id', label: '印尼文' },
  { value: 'it', label: '義大利文' },
  { value: 'ru', label: '俄文' },
  { value: 'th', label: '泰文' },
  { value: 'vi', label: '越南文' },
  { value: 'tr', label: '土耳其文' },
  { value: 'hi', label: '印地文' },
  { value: 'ms', label: '馬來文' },
  { value: 'nl', label: '荷蘭文' },
  { value: 'sv', label: '瑞典文' },
  { value: 'da', label: '丹麥文' },
  { value: 'fi', label: '芬蘭文' },
  { value: 'pl', label: '波蘭文' },
  { value: 'cs', label: '捷克文' },
  { value: 'fil', label: '菲律賓文' },
  { value: 'fa', label: '波斯文' },
  { value: 'el', label: '希臘文' },
  { value: 'ro', label: '羅馬尼亞文' },
  { value: 'hu', label: '匈牙利文' },
  { value: 'mk', label: '馬其頓文' },
  { value: 'bg', label: '保加利亞文' },
  { value: 'hr', label: '克羅埃西亞文' },
  { value: 'et', label: '愛沙尼亞文' },
  { value: 'ga', label: '愛爾蘭文' },
  { value: 'lv', label: '拉脫維亞文' },
  { value: 'lt', label: '立陶宛文' },
  { value: 'mt', label: '馬爾他文' },
  { value: 'sk', label: '斯洛伐克文' },
  { value: 'sl', label: '斯洛維尼亞文' },
];

export function normalizeAsrLanguage(language: string | number | null | undefined): string {
  const normalized = String(language || 'auto').trim().toLowerCase();
  if (['zh-tw', 'zh-hant', 'zh-cn', 'zh-hans'].includes(normalized)) return 'zh';
  if (normalized === 'tl') return 'fil';
  return normalized || 'auto';
}

export function findAsrCapability(
  capabilities: AsrModelCapability[] | undefined,
  modelId: string,
): AsrModelCapability | undefined {
  return capabilities?.find((item) => item.model_id === modelId);
}

export function languageOptionsForModel(
  capabilities: AsrModelCapability[] | undefined,
  modelId: string,
): UiSelectOption[] {
  const capability = findAsrCapability(capabilities, modelId);
  if (!capability) return ASR_LANGUAGE_OPTIONS;
  const allowed = new Set(capability.supported_languages);
  return ASR_LANGUAGE_OPTIONS.filter((option) => {
    if (option.value === 'auto') return capability.language_mode !== 'fixed';
    return allowed.has(normalizeAsrLanguage(option.value));
  });
}

export function coerceLanguageForModel(
  capabilities: AsrModelCapability[] | undefined,
  modelId: string,
  language: string,
): string {
  const capability = findAsrCapability(capabilities, modelId);
  if (!capability) return language;
  if (capability.language_mode === 'fixed') return capability.default_language;
  return language;
}

export function isModelLanguageCompatible(
  capabilities: AsrModelCapability[] | undefined,
  modelId: string,
  language: string,
): boolean {
  const capability = findAsrCapability(capabilities, modelId);
  const normalized = normalizeAsrLanguage(language);
  if (!capability || normalized === 'auto') return true;
  return capability.supported_languages.includes(normalized);
}
