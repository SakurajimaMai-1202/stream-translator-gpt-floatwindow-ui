export function validateAudioSlicing(audio: Record<string, unknown>): string {
  const labels: Record<string, string> = {
    min_audio_length: '最小音訊長度',
    target_audio_length: '目標音訊長度',
    max_audio_length: '最大音訊長度',
    omnivad_max_audio_length: '原生模式最大音訊長度',
    continuous_no_speech_threshold: '句尾連續靜音',
    prefix_retention_length: '前綴重疊長度',
    vad_threshold: '目前切段語音閾值',
    omnivad_threshold: 'OmniStreamVAD 語音閾值',
    vad_every_n_frames: 'VAD 計算頻率',
    omnivad_smooth_window_size: '平滑視窗（10 ms frame）',
    omnivad_pad_start_frame: '起音回溯 frame',
    omnivad_min_speech_frame: '最短語音 frame',
    omnivad_max_speech_frame: '最長語音 frame',
    omnivad_min_silence_frame: '句尾靜音 frame',
  };
  const native = audio.slicing_mode === 'omnivad_native';
  const legacy = !native;
  const fields = legacy ? ['min_audio_length', 'target_audio_length', 'max_audio_length']
    : ['min_audio_length', 'omnivad_max_audio_length'];
  const numericKeys = [...fields, 'prefix_retention_length'];
  if (legacy) numericKeys.push('continuous_no_speech_threshold');
  if (audio.vad_enabled) {
    numericKeys.push(...(legacy ? ['vad_threshold', 'vad_every_n_frames'] : ['omnivad_threshold']));
    if (native) {
      numericKeys.push('omnivad_smooth_window_size', 'omnivad_pad_start_frame',
        'omnivad_min_speech_frame', 'omnivad_max_speech_frame', 'omnivad_min_silence_frame');
    }
  }
  for (const key of numericKeys) {
    const value = audio[key];
    if (key in audio && (typeof value !== 'number' || !Number.isFinite(value))) {
      return `${labels[key]}不可空白`;
    }
  }
  for (const key of fields) {
    if (!(key in audio)) continue;
    const label = labels[key];
    const value = audio[key];
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
      return `${label}必須是大於 0 的數字`;
    }
  }
  const maximum = legacy ? 'max_audio_length' : 'omnivad_max_audio_length';
  const min = audio.min_audio_length as number;
  const max = audio[maximum] as number;
  const target = audio.target_audio_length as number;
  if (min > max) return `最小音訊長度（${min} 秒）不可大於${labels[maximum]}（${max} 秒）`;
  if (legacy && (target < min || target > max)) {
    return `目標音訊長度（${target} 秒）必須介於最小音訊長度（${min} 秒）與最大音訊長度（${max} 秒）之間`;
  }
  return '';
}
