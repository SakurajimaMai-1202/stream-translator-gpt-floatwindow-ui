import { ASR_LANGUAGE_OPTIONS, normalizeAsrLanguage } from './asrCapabilities';

// Keep aligned with backend/core/asr_model_capabilities.py PARAKEET_V3_LANGUAGES.
export const SIMPLE_V3_LANGUAGES = new Set('bg hr cs da nl en et fi fr de el hu it lv lt mt pl pt ro sk sl es sv ru uk'.split(' '));
export function simpleAsrModel(language: string): string | null {
  const normalized = normalizeAsrLanguage(language);
  if (normalized === 'zh') return 'iic/SenseVoiceSmall';
  if (normalized === 'ja') return 'nvidia/parakeet-tdt_ctc-0.6b-ja';
  return SIMPLE_V3_LANGUAGES.has(normalized) ? 'nvidia/parakeet-tdt-0.6b-v3' : null;
}
export const simpleAsrLanguages = [
  ...ASR_LANGUAGE_OPTIONS.filter(option => simpleAsrModel(String(option.value))),
  { value: 'uk', label: '烏克蘭文' },
];
