import { watch } from 'vue';

interface TranscriptionConfig {
  use_faster_whisper?: boolean;
  use_simul_streaming?: boolean;
  use_openai_transcription_api?: boolean;
  use_qwen3_asr?: boolean;
}

/**
 * 維持轉錄引擎互斥規則：
 * - OpenAI API 與其他選項互斥
 * - Qwen3-ASR 與其他選項互斥
 * - Faster-Whisper 與 SimulStreaming 可同時啟用
 */
export function useTranscriptionMutex(getTranscription: () => TranscriptionConfig) {
  let isApplying = false;

  watch(
    getTranscription,
    (cfg) => {
      if (!cfg || isApplying) return;

      isApplying = true;
      try {
        if (cfg.use_openai_transcription_api) {
          cfg.use_faster_whisper = false;
          cfg.use_simul_streaming = false;
          cfg.use_qwen3_asr = false;
          return;
        }

        if (cfg.use_qwen3_asr) {
          cfg.use_faster_whisper = false;
          cfg.use_simul_streaming = false;
          cfg.use_openai_transcription_api = false;
          return;
        }

        if (cfg.use_faster_whisper || cfg.use_simul_streaming) {
          cfg.use_openai_transcription_api = false;
          cfg.use_qwen3_asr = false;
        }
      } finally {
        isApplying = false;
      }
    },
    { deep: true }
  );
}
