export function validateAudioSlicing(audio: Record<string, unknown>): string {
  const labels: Record<string, string> = {
    min_audio_length: '最小音訊長度',
    target_audio_length: '目標音訊長度',
    max_audio_length: '最大音訊長度',
    omnivad_max_audio_length: '原生模式最大音訊長度',
  };
  const numericKeys = [
    'min_audio_length', 'target_audio_length', 'max_audio_length',
    'omnivad_max_audio_length', 'continuous_no_speech_threshold',
    'prefix_retention_length', 'vad_threshold', 'omnivad_threshold',
    'vad_every_n_frames', 'omnivad_smooth_window_size', 'omnivad_pad_start_frame',
    'omnivad_min_speech_frame', 'omnivad_max_speech_frame', 'omnivad_min_silence_frame',
  ];
  for (const key of numericKeys) {
    const value = audio[key];
    if (key in audio && (typeof value !== 'number' || !Number.isFinite(value))) {
      return '欄位不可空白';
    }
  }
  const native = audio.slicing_mode === 'omnivad_native';
  const fields = native ? ['min_audio_length', 'omnivad_max_audio_length']
    : ['min_audio_length', 'target_audio_length', 'max_audio_length'];
  for (const key of fields) {
    if (!(key in audio)) continue;
    const label = labels[key];
    const value = audio[key];
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
      return `${label}必須是大於 0 的數字`;
    }
  }
  const maximum = native ? 'omnivad_max_audio_length' : 'max_audio_length';
  const min = audio.min_audio_length as number;
  const max = audio[maximum] as number;
  const target = audio.target_audio_length as number;
  if (min > max) return `最小音訊長度（${min} 秒）不可大於${labels[maximum]}（${max} 秒）`;
  if (!native && (target < min || target > max)) {
    return `目標音訊長度（${target} 秒）必須介於最小音訊長度（${min} 秒）與最大音訊長度（${max} 秒）之間`;
  }
  return '';
}
