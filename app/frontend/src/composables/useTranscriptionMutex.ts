import { watch } from 'vue';

interface TranscriptionConfig {
  use_faster_whisper?: boolean;
  use_simul_streaming?: boolean;
  use_openai_transcription_api?: boolean;
  use_qwen3_asr?: boolean;
  use_sensevoice_asr?: boolean;
  use_nemo_asr?: boolean;
}

/**
 * 維持轉錄引擎互斥規則：
 * - OpenAI API 與其他選項互斥
 * - Qwen3-ASR 與其他選項互斥
 * - Faster-Whisper 與 SimulStreaming 可同時啟用
 */
export function useTranscriptionMutex(getTranscription: () => TranscriptionConfig) {
  let isApplying = false;

  function clearExclusiveEngines(cfg: TranscriptionConfig) {
    cfg.use_openai_transcription_api = false;
    cfg.use_qwen3_asr = false;
    cfg.use_sensevoice_asr = false;
    cfg.use_nemo_asr = false;
  }

  function selectExclusiveEngine(cfg: TranscriptionConfig, engine: 'openai' | 'qwen3' | 'sensevoice' | 'nemo') {
    cfg.use_faster_whisper = false;
    cfg.use_simul_streaming = false;
    cfg.use_openai_transcription_api = engine === 'openai';
    cfg.use_qwen3_asr = engine === 'qwen3';
    cfg.use_sensevoice_asr = engine === 'sensevoice';
    cfg.use_nemo_asr = engine === 'nemo';
  }

  watch(
    getTranscription,
    (cfg) => {
      if (!cfg || isApplying) return;

      isApplying = true;
      try {
        if (cfg.use_sensevoice_asr) {
          selectExclusiveEngine(cfg, 'sensevoice');
          return;
        }

        if (cfg.use_nemo_asr) {
          selectExclusiveEngine(cfg, 'nemo');
          return;
        }

        if (cfg.use_qwen3_asr) {
          selectExclusiveEngine(cfg, 'qwen3');
          return;
        }

        if (cfg.use_openai_transcription_api) {
          selectExclusiveEngine(cfg, 'openai');
          return;
        }

        if (cfg.use_faster_whisper || cfg.use_simul_streaming) {
          clearExclusiveEngines(cfg);
        }
      } finally {
        isApplying = false;
      }
    },
    { deep: true, immediate: true }
  );
}
