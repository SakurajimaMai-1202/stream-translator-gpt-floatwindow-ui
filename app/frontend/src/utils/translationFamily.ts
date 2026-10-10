// Keep browser display aligned with translation_policy.resolve_model_family.
export function resolveTranslationFamily(t: any): string {
  const requested = String(t.translation_model_family || 'auto').trim().toLowerCase().replace(/-/g, '_');
  const aliases: Record<string, string> = {hymt2: 'hy_mt2', hy_mt: 'hy_mt2', generic: 'generic_chat', chat: 'generic_chat', structured: 'structured_api', index: 'index_translate', indextranslate: 'index_translate'};
  const family = aliases[requested] || requested;
  if (['hy_mt2', 'index_translate', 'generic_chat', 'structured_api'].includes(family)) return family;
  const custom = (t.custom_models || []).find((m: any) => `custom:${m.name}` === t.backend);
  const model = String(custom?.model_name || t.gpt_model || '').toLowerCase();
  if (/index[-_ ]?translate(?:[-_/ .]|$)/.test(model)) return 'index_translate';
  if (model.includes('hy-mt2') || model.includes('hymt2')) return 'hy_mt2';
  if (t.hy_mt2_optimizer_enabled && ['lm_studio', 'llama_cpp'].includes(t.hy_mt2_provider)) return 'hy_mt2';
  return ['gpt', 'gemini'].includes(t.backend) ? 'structured_api' : 'generic_chat';
}

export function usesExternalFamilyEndpoint(t: any): boolean {
  const family = resolveTranslationFamily(t);
  return ['hy_mt2', 'index_translate'].includes(family)
    && ['lm_studio', 'llama_cpp'].includes(t[family + '_provider']);
}
