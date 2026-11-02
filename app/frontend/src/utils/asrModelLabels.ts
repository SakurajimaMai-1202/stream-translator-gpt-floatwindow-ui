const ASR_MODEL_LABELS = new Map<string, string>([
  ['tiny', 'tiny（最快，準確度最低）'],
  ['base', 'base（很快，準確度較低）'],
  ['small', 'small（快，準確度普通）'],
  ['medium', 'medium（速度中等，準確度不錯）'],
  ['large-v2', 'large-v2（較慢，準確度高）'],
  ['large-v3', 'large-v3（較慢，準確度最高）'],
  ['large-v3-turbo', 'large-v3-turbo（比 large-v3 快，準確度接近）'],
  ['Qwen/Qwen3-ASR-1.7B', 'Qwen3 標準版（多語言，推薦）'],
  ['Qwen/Qwen3-ASR-0.6B', 'Qwen3 輕量版（多語言，較快）'],
  ['jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame', 'Qwen3 日文動畫／遊戲專用'],
  ['iic/SenseVoiceSmall', 'SenseVoice（中文／粵語／英文／日文／韓文）'],
  ['FunAudioLLM/Fun-ASR-Nano-2512', 'Fun-ASR 標準版（中文／英文／日文）'],
  ['FunAudioLLM/Fun-ASR-MLT-Nano-2512', 'Fun-ASR 多語言版（31 種語言）'],
  ['nvidia/parakeet-tdt-0.6b-v3', 'Parakeet 多語言版（25 種歐洲語言）'],
  ['nvidia/parakeet-tdt_ctc-0.6b-ja', 'Parakeet 日文版（CPU／NVIDIA GPU）'],
  ['oboroge0/Haas-ja-v1.0-onnx-quantized', 'Haas 日文（較準確，僅限 CPU）'],
  ['nvidia/parakeet-tdt_ctc-1.1b', 'Parakeet 英文版'],
  ['grider-transwithai/parakeet-ctc-1.1b-ja', 'Parakeet 日文舊版（不建議）'],
]);

export function asrModelLabel(modelId: string): string {
  return ASR_MODEL_LABELS.get(modelId) ?? modelId;
}
