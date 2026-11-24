import type { ServerConfig } from '../services/llamaApi';

type TranslationModelSettings = {
  backend?: string;
  gpt_model?: string;
  hy_mt2_provider?: string;
  hy_mt2_lm_studio_url?: string;
  hy_mt2_lm_studio_model?: string;
  hy_mt2_llama_cpp_url?: string;
  hy_mt2_llama_cpp_model?: string;
  custom_models?: { name: string; model_name?: string }[];
};

type MemoryOptions = Pick<ServerConfig, 'flash_attn' | 'no_mmap'>;

export function hyMtContextForcedOff(
  family: string,
  translation: TranslationModelSettings,
  servedModels: readonly string[],
  llamaModelPath: string | undefined,
  selectedLlamaModelPath?: string,
): boolean {
  if (family !== 'hy_mt2') return false;

  const smallHyMt3 = /hy[-_ ]?mt3[-_ .]*1[._]?8b/i;
  const provider = translation.hy_mt2_provider;
  if (provider === 'lm_studio' || provider === 'llama_cpp') {
    const url = String(translation[`hy_mt2_${provider}_url`] || '').trim();
    const model = String(translation[`hy_mt2_${provider}_model`] || '').trim();
    if (url && model) return smallHyMt3.test(model);
  }

  const backend = String(translation.backend || '');
  let configuredModel = '';
  if (backend === 'llama' || backend === 'localllm') {
    const modelPath = String(llamaModelPath || selectedLlamaModelPath || '');
    configuredModel = modelPath.split(/[\\/]/).pop() || '';
  } else if (backend.startsWith('custom:')) {
    const custom = (translation.custom_models || []).find(model => model.name === backend.slice(7));
    configuredModel = custom?.model_name || '';
  }
  return smallHyMt3.test(servedModels[0] || configuredModel || translation.gpt_model || '');
}

export function isHyMtForcedModelPath(modelPath: string): boolean {
  const compactName = (modelPath.split(/[\\/]/).pop() || '').toLowerCase().replace(/[-_]/g, '');
  return compactName.includes('hymt') && !compactName.includes('hymt3');
}

export function hyMtMemoryOptionsAfterSwitch(
  isHyMt: boolean,
  wasHyMt: boolean | undefined,
  current: MemoryOptions,
): MemoryOptions {
  if (isHyMt) return { flash_attn: 'off', no_mmap: true };

  const { flash_attn, no_mmap } = current;
  return {
    flash_attn: wasHyMt && flash_attn === 'off' ? 'auto' : flash_attn,
    no_mmap: wasHyMt && no_mmap === true ? false : no_mmap,
  };
}
