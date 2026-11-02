import { asrModelLabel } from '../../utils/asrModelLabels';
import { computed, type Ref } from 'vue';
import type { useTranslationStore } from '../../stores/translation';
import type { UiSelectOption } from '../../components/UiSelect.vue';
import { ASR_LANGUAGE_OPTIONS, HAAS_MODEL_ID, isModelLanguageCompatible, languageOptionsForModel } from '../../utils/asrCapabilities';

export function useTranscriptionSettings(localConfig: Ref<any>, store: ReturnType<typeof useTranslationStore>) {
  const allQwenModels = ['Qwen/Qwen3-ASR-0.6B', 'Qwen/Qwen3-ASR-1.7B', 'jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame'];
  const legacyQwen3JaModel = 'neosophie/Qwen3-ASR-1.7B-JA';
  const qwen3AnimeModel = 'jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame';
  const allFasterWhisperModels = ['tiny', 'base', 'small', 'medium', 'large-v2', 'large-v3', 'large-v3-turbo'];
  const allSenseVoiceModels = ['iic/SenseVoiceSmall'];
  const allFunAsrModels = ['FunAudioLLM/Fun-ASR-Nano-2512', 'FunAudioLLM/Fun-ASR-MLT-Nano-2512'];
  const allParakeetModels = [
    'nvidia/parakeet-tdt-0.6b-v3',
    'nvidia/parakeet-tdt_ctc-0.6b-ja',
    'oboroge0/Haas-ja-v1.0-onnx-quantized',
    'nvidia/parakeet-tdt_ctc-1.1b',
    'grider-transwithai/parakeet-ctc-1.1b-ja',
  ];

  const whisperModelSelectOptions = computed<UiSelectOption[]>(() =>
    allFasterWhisperModels
      .filter(m => allowedFasterWhisperModels.value.includes(m))
      .map(m => ({ value: m, label: asrModelLabel(m) }))
  );
  const allQwen3AsrModelOptions: UiSelectOption[] = [
    { value: 'Qwen/Qwen3-ASR-1.7B', label: asrModelLabel('Qwen/Qwen3-ASR-1.7B') },
    { value: 'Qwen/Qwen3-ASR-0.6B', label: asrModelLabel('Qwen/Qwen3-ASR-0.6B') },
    { value: 'jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame', label: asrModelLabel('jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame') },
  ];
  const qwen3AsrModelOptions = computed<UiSelectOption[]>(() =>
    allQwen3AsrModelOptions
      .filter(option => allowedQwen3AsrModels.value.includes(String(option.value)))
      .map(option => ({
        ...option,
        disabled: selectedSettingsAsrCapability.value?.language_mode !== 'fixed'
          && !isModelLanguageCompatible(
            runtimeCapabilities.value?.asr_model_capabilities,
            String(option.value),
            localConfig.value.transcription.language,
          ),
      }))
  );
  const senseVoiceModelOptions = computed<UiSelectOption[]>(() =>
    allSenseVoiceModels
      .filter(model => allowedSenseVoiceModels.value.includes(model))
      .map(model => ({
        value: model,
        label: asrModelLabel(model),
        disabled: selectedSettingsAsrCapability.value?.language_mode !== 'fixed'
          && !isModelLanguageCompatible(
            runtimeCapabilities.value?.asr_model_capabilities,
            model,
            localConfig.value.transcription.language,
          ),
      }))
  );
  const parakeetModelOptions = computed<UiSelectOption[]>(() => {
    // Haas is CPU-sidecar only, so a GPU runtime leaves it out of the backend
    // capability list.  Show it disabled with the reason instead of hiding it.
    const allowed = allowedParakeetModels.value;
    const showHaasDisabled = allowed.length > 0
      && !allowed.includes(HAAS_MODEL_ID)
      && allowedLocalAsrEngines.value.includes('parakeet-ctc-ja');
    return allParakeetModels
      .filter(model => allowed.includes(model)
        || (showHaasDisabled && model === HAAS_MODEL_ID))
      .map(model => {
        const needsCpuBackend = showHaasDisabled && model === HAAS_MODEL_ID;
        const baseLabel = asrModelLabel(model);
        return {
          value: model,
          label: needsCpuBackend ? `${baseLabel} · 請先把 ASR 運算模式切到 CPU` : baseLabel,
          disabled: needsCpuBackend,
        };
      });
  });
  const parakeetDecodingOptions: UiSelectOption[] = [
    { value: 'tdt', label: 'TDT（建議）' },
    { value: 'ctc', label: 'CTC' },
  ];
  const qwen3DtypeOptions: UiSelectOption[] = [
    { value: 'bfloat16', label: 'BF16（建議，速度快、顯存較低）' },
    { value: 'float32', label: 'FP32（相容性高、顯存約兩倍）' },
  ];
  const asrComputeBackendOptions = computed<UiSelectOption[]>(() => {
    const profile = String(runtimeStatus.value?.profile || localConfig.value.runtime?.profile || 'cuda').toLowerCase();
    const gpuLabel = profile === 'rocm' ? 'ROCm GPU 原生 ASR' : 'CUDA GPU 原生 ASR';
    return [
      { value: 'auto', label: `自動（${profile === 'cpu' ? 'CPU' : profile.toUpperCase()}）` },
      { value: 'gpu', label: gpuLabel, disabled: profile === 'cpu' },
      { value: 'cpu', label: 'CPU · Sherpa-ONNX INT8' },
    ];
  });
  const runtimeDevicePolicyOptions: UiSelectOption[] = [
    { value: 'auto_discrete', label: 'Auto discrete GPU' },
    { value: 'auto_any', label: 'Auto any GPU' },
    { value: 'manual', label: 'Manual' },
    { value: 'cpu', label: 'CPU' },
  ];
  const fallbackTranscriptionLanguageOptions = ASR_LANGUAGE_OPTIONS;
  const funAsrModelOptions = computed<UiSelectOption[]>(() =>
    allFunAsrModels
      .filter(model => allowedFunAsrModels.value.includes(model))
      .map(model => ({
        value: model,
        label: asrModelLabel(model),
        disabled: selectedSettingsAsrCapability.value?.language_mode !== 'fixed'
          && !isModelLanguageCompatible(
            runtimeCapabilities.value?.asr_model_capabilities,
            model,
            localConfig.value.transcription.language,
          ),
      }))
  );
  const runtimeStatus = computed(() => store.runtimeStatus);
  const asrComputeBackendLocked = computed(() => runtimeStatus.value?.profile === 'cpu');
  const runtimeCapabilities = computed(() => runtimeStatus.value?.asr_capabilities || runtimeStatus.value?.capabilities || null);
  const effectiveAsrComputeBackend = computed(() =>
    runtimeStatus.value?.effective_asr_compute_backend
      || (localConfig.value.transcription?.asr_compute_backend === 'cpu' ? 'cpu' : 'gpu')
  );
  const isSherpaOnnxMode = computed(() => effectiveAsrComputeBackend.value === 'cpu');
  const effectiveRuntimeKind = computed(() => {
    if (isSherpaOnnxMode.value) return 'CPU';
    return String(runtimeStatus.value?.profile || localConfig.value.runtime?.profile || 'cuda').toUpperCase() === 'ROCM'
      ? 'ROCm'
      : 'CUDA';
  });
  const effectiveAsrRuntimeLabel = computed(() =>
    isSherpaOnnxMode.value ? 'CPU · Sherpa-ONNX INT8' : `${effectiveRuntimeKind.value} · GPU 原生 ASR`
  );
  const packageProfileLabel = computed(() => {
    const profile = String(runtimeStatus.value?.profile || localConfig.value.runtime?.profile || 'unknown').toLowerCase();
    if (profile === 'cuda') return 'CUDA 套件';
    if (profile === 'rocm') return 'ROCm 套件（Experimental）';
    if (profile === 'cpu') return 'CPU 套件';
    return profile.toUpperCase();
  });
  const cpuAsrRuntimeAvailable = computed(() => Boolean(runtimeStatus.value?.cpu_asr_runtime?.available));
  const selectedSettingsAsrModelId = computed<string>(() => {
    const transcription = localConfig.value.transcription;
    if (transcription.use_qwen3_asr) return transcription.qwen3_asr_model;
    if (transcription.use_sensevoice_asr) return transcription.sensevoice_model;
    if (transcription.use_fun_asr) return transcription.fun_asr_model;
    if (transcription.use_nemo_asr) return transcription.nemo_asr_model;
    return transcription.model;
  });
  const selectedSettingsAsrCapability = computed(() =>
    runtimeCapabilities.value?.asr_model_capabilities?.find(
      (item) => item.model_id === selectedSettingsAsrModelId.value
    )
  );
  const transcriptionLanguageOptions = computed<UiSelectOption[]>(() => {
    const options = languageOptionsForModel(
      runtimeCapabilities.value?.asr_model_capabilities,
      selectedSettingsAsrModelId.value,
    );
    return options.length > 0 ? options : fallbackTranscriptionLanguageOptions;
  });
  const isTranscriptionLanguageLocked = computed(
    () => selectedSettingsAsrCapability.value?.language_mode === 'fixed'
  );
  const allowedLocalAsrEngines = computed<string[]>(() =>
    runtimeCapabilities.value?.local_asr_engines?.length
      ? runtimeCapabilities.value.local_asr_engines
      : ['faster-whisper', 'simul-streaming', 'faster-whisper-simul', 'qwen3-asr', 'sensevoice', 'fun-asr-nano', 'parakeet-ctc-ja']
  );
  const allowedRemoteAsrEngines = computed<string[]>(() =>
    runtimeCapabilities.value?.remote_asr_engines?.length
      ? runtimeCapabilities.value.remote_asr_engines
      : ['openai-api']
  );
  const canUseFasterWhisper = computed(() => allowedLocalAsrEngines.value.includes('faster-whisper'));
  const canUseSimulStreaming = computed(() => allowedLocalAsrEngines.value.includes('simul-streaming'));
  const canUseFasterWhisperSimul = computed(() => allowedLocalAsrEngines.value.includes('faster-whisper-simul'));
  const canUseQwen3Asr = computed(() => allowedLocalAsrEngines.value.includes('qwen3-asr'));
  const canUseSenseVoice = computed(() => allowedLocalAsrEngines.value.includes('sensevoice'));
  const canUseFunAsr = computed(() => allowedLocalAsrEngines.value.includes('fun-asr-nano'));
  const canUseParakeet = computed(() => allowedLocalAsrEngines.value.includes('parakeet-ctc-ja'));
  const canUseOpenAiAsr = computed(() => allowedRemoteAsrEngines.value.includes('openai-api'));
  const allowedFasterWhisperModels = computed<string[]>(() =>
    runtimeCapabilities.value?.faster_whisper_model_ids?.length
      ? runtimeCapabilities.value.faster_whisper_model_ids
      : allFasterWhisperModels
  );
  const allowedQwen3AsrModels = computed<string[]>(() =>
    runtimeCapabilities.value?.qwen3_asr_model_ids?.length
      ? runtimeCapabilities.value.qwen3_asr_model_ids
      : allQwenModels
  );
  const allowedSenseVoiceModels = computed<string[]>(() =>
    runtimeCapabilities.value?.sensevoice_model_ids?.length
      ? runtimeCapabilities.value.sensevoice_model_ids
      : allSenseVoiceModels
  );
  const allowedFunAsrModels = computed<string[]>(() =>
    runtimeCapabilities.value?.fun_asr_model_ids?.length
      ? runtimeCapabilities.value.fun_asr_model_ids
      : allFunAsrModels
  );
  const allowedParakeetModels = computed<string[]>(() =>
    runtimeCapabilities.value?.parakeet_model_ids?.length
      ? runtimeCapabilities.value.parakeet_model_ids
      : allParakeetModels.filter(model => isSherpaOnnxMode.value || model !== 'oboroge0/Haas-ja-v1.0-onnx-quantized')
  );

  const runtimeSelection = computed(() => runtimeStatus.value?.selection || null);
  const selectedRuntimeDevice = computed(() => runtimeSelection.value?.device || null);
  const ignoredRuntimeDevices = computed(() => runtimeSelection.value?.ignored_devices || []);
  const runtimeStatusLabel = computed(() => {
    const status = runtimeStatus.value?.status || 'unknown';
    if (status === 'official') return 'Official';
    if (status === 'compatibility') return 'Compatibility';
    if (status === 'experimental') return 'Experimental';
    return status;
  });
  const runtimeDiagnosticNotice = computed(() => {
    const profile = runtimeStatus.value?.profile || localConfig.value?.runtime?.profile;
    if (profile !== 'rocm') return '';
    if (runtimeSelection.value?.kind === 'gpu') {
      return 'ROCm package/profile is selected. Export the Runtime diagnostics report on an AMD GPU machine and run an ASR sample to confirm HIP execution; package validation alone does not verify inference.';
    }
    return 'ROCm package/profile is selected, but no suitable AMD discrete GPU is selected on this machine. Package validation can still pass; ROCm GPU inference remains unverified until an AMD machine exports diagnostics and passes an ASR sample.';
  });

  function formatRuntimeMemory(memoryMb: number | null | undefined): string {
    if (!memoryMb) return 'unknown VRAM';
    if (memoryMb >= 1024) return `${(memoryMb / 1024).toFixed(1)} GB VRAM`;
    return `${memoryMb} MB VRAM`;
  }

  function runtimeDeviceLine(device: any): string {
    if (!device) return 'None';
    const integrated = device.is_integrated ? 'integrated' : 'discrete';
    const details = [formatRuntimeMemory(device.memory_mb), integrated];
    if (device.arch_name) details.push(device.arch_name);
    if (device.is_supported_by_torch === false) details.push('unsupported by torch');
    if (device.is_supported_by_torch === true) details.push('torch supported');
    if (device.is_supported_by_torch === null || device.is_supported_by_torch === undefined) details.push('torch support unknown');
    if (device.source === 'runtime_python') details.push('runtime probe');
    if (device.source === 'win32_video_controller') details.push('Windows estimate');
    return `${device.name} (${details.join(', ')})`;
  }

  function coerceAsrSettingsForRuntime() {
    const transcription = localConfig.value.transcription || {};
    if (!canUseFasterWhisper.value) {
      transcription.use_faster_whisper = false;
    }
    if (!canUseSimulStreaming.value && !canUseFasterWhisperSimul.value) {
      transcription.use_simul_streaming = false;
    }
    if (!canUseQwen3Asr.value) {
      transcription.use_qwen3_asr = false;
    }
    if (!canUseSenseVoice.value) {
      transcription.use_sensevoice_asr = false;
    }
    if (!canUseParakeet.value) {
      transcription.use_nemo_asr = false;
    }
    if (!canUseOpenAiAsr.value) {
      transcription.use_openai_transcription_api = false;
    }
    if (!allowedFasterWhisperModels.value.includes(transcription.model)) {
      transcription.model = allowedFasterWhisperModels.value[0] || 'small';
    }
    if (transcription.qwen3_asr_model === legacyQwen3JaModel) {
      transcription.qwen3_asr_model = qwen3AnimeModel;
    }
    if (!canUseFunAsr.value) {
      transcription.use_fun_asr = false;
    }
    if (!allowedQwen3AsrModels.value.includes(transcription.qwen3_asr_model)) {
      transcription.qwen3_asr_model = allowedQwen3AsrModels.value[0] || 'Qwen/Qwen3-ASR-0.6B';
    }
    if (!allowedSenseVoiceModels.value.includes(transcription.sensevoice_model)) {
      transcription.sensevoice_model = allowedSenseVoiceModels.value[0] || 'iic/SenseVoiceSmall';
    }
    if (!allowedFunAsrModels.value.includes(transcription.fun_asr_model)) {
      transcription.fun_asr_model = allowedFunAsrModels.value[0] || 'FunAudioLLM/Fun-ASR-Nano-2512';
    }
    if (!allowedParakeetModels.value.includes(transcription.nemo_asr_model)) {
      transcription.nemo_asr_model = allowedParakeetModels.value[0] || 'nvidia/parakeet-tdt_ctc-0.6b-ja';
    }
    if (transcription.use_nemo_asr && transcription.nemo_asr_model === 'oboroge0/Haas-ja-v1.0-onnx-quantized') transcription.language = 'ja';
    normalizeAsrEngineSelection();
    if (
      !transcription.use_faster_whisper &&
      !transcription.use_simul_streaming &&
      !transcription.use_qwen3_asr &&
      !transcription.use_sensevoice_asr &&
      !transcription.use_fun_asr &&
      !transcription.use_nemo_asr &&
      !transcription.use_openai_transcription_api
    ) {
      if (canUseQwen3Asr.value) {
        transcription.use_qwen3_asr = true;
      } else if (canUseSenseVoice.value) {
        transcription.use_sensevoice_asr = true;
      } else if (canUseFasterWhisper.value) {
        transcription.use_faster_whisper = true;
      } else if (canUseOpenAiAsr.value) {
        transcription.use_openai_transcription_api = true;
      }
    }
  }

  type AsrEngine =
    | 'faster_whisper'
    | 'simul_streaming'
    | 'openai'
    | 'qwen3'
    | 'sensevoice'
    | 'fun_asr'
    | 'parakeet';

  function clearExclusiveAsrEngines(transcription: any) {
    transcription.use_openai_transcription_api = false;
    transcription.use_qwen3_asr = false;
    transcription.use_sensevoice_asr = false;
    transcription.use_fun_asr = false;
    transcription.use_nemo_asr = false;
  }

  function clearAllAsrEngines(transcription: any) {
    transcription.use_faster_whisper = false;
    transcription.use_simul_streaming = false;
    clearExclusiveAsrEngines(transcription);
  }

  function normalizeAsrEngineSelection() {
    const transcription = localConfig.value.transcription || {};
    const selectedExclusive = [
      transcription.use_fun_asr ? 'fun_asr' : '',
      transcription.use_sensevoice_asr ? 'sensevoice' : '',
      transcription.use_nemo_asr ? 'parakeet' : '',
      transcription.use_qwen3_asr ? 'qwen3' : '',
      transcription.use_openai_transcription_api ? 'openai' : '',
    ].filter(Boolean);

    if (selectedExclusive.length > 0) {
      const selected = selectedExclusive[0];
      transcription.use_faster_whisper = false;
      transcription.use_simul_streaming = false;
      transcription.use_sensevoice_asr = selected === 'sensevoice';
      transcription.use_fun_asr = selected === 'fun_asr';
      transcription.use_nemo_asr = selected === 'parakeet';
      transcription.use_qwen3_asr = selected === 'qwen3';
      transcription.use_openai_transcription_api = selected === 'openai';
    }
  }

  function isAsrEngineSelected(engine: AsrEngine): boolean {
    const transcription = localConfig.value.transcription || {};
    if (engine === 'faster_whisper') return !!transcription.use_faster_whisper;
    if (engine === 'simul_streaming') return !!transcription.use_simul_streaming;
    if (engine === 'openai') return !!transcription.use_openai_transcription_api;
    if (engine === 'qwen3') return !!transcription.use_qwen3_asr;
    if (engine === 'sensevoice') return !!transcription.use_sensevoice_asr;
    if (engine === 'fun_asr') return !!transcription.use_fun_asr;
    if (engine === 'parakeet') return !!transcription.use_nemo_asr;
    return false;
  }

  function selectAsrEngine(engine: AsrEngine) {
    const transcription = localConfig.value.transcription || {};

    if (engine === 'faster_whisper') {
      clearExclusiveAsrEngines(transcription);
      transcription.use_faster_whisper = !transcription.use_faster_whisper;
      return;
    }

    if (engine === 'simul_streaming') {
      clearExclusiveAsrEngines(transcription);
      transcription.use_simul_streaming = !transcription.use_simul_streaming;
      return;
    }

    clearAllAsrEngines(transcription);
    if (engine === 'openai') transcription.use_openai_transcription_api = true;
    if (engine === 'qwen3') transcription.use_qwen3_asr = true;
    if (engine === 'sensevoice') transcription.use_sensevoice_asr = true;
    if (engine === 'fun_asr') transcription.use_fun_asr = true;
    if (engine === 'parakeet') transcription.use_nemo_asr = true;
  }


  return {
    allQwenModels,
    allFasterWhisperModels,
    allSenseVoiceModels,
    allFunAsrModels,
    allParakeetModels,
    whisperModelSelectOptions,
    qwen3AsrModelOptions,
    senseVoiceModelOptions,
    parakeetModelOptions,
    parakeetDecodingOptions,
    qwen3DtypeOptions,
    asrComputeBackendOptions,
    runtimeDevicePolicyOptions,
    funAsrModelOptions,
    runtimeStatus,
    asrComputeBackendLocked,
    runtimeCapabilities,
    effectiveAsrComputeBackend,
    isSherpaOnnxMode,
    effectiveAsrRuntimeLabel,
    packageProfileLabel,
    cpuAsrRuntimeAvailable,
    selectedSettingsAsrModelId,
    transcriptionLanguageOptions,
    isTranscriptionLanguageLocked,
    canUseFasterWhisper,
    canUseSimulStreaming,
    canUseFasterWhisperSimul,
    canUseQwen3Asr,
    canUseSenseVoice,
    canUseFunAsr,
    canUseParakeet,
    canUseOpenAiAsr,
    allowedFasterWhisperModels,
    allowedQwen3AsrModels,
    allowedSenseVoiceModels,
    allowedFunAsrModels,
    allowedParakeetModels,
    runtimeSelection,
    selectedRuntimeDevice,
    ignoredRuntimeDevices,
    runtimeStatusLabel,
    runtimeDiagnosticNotice,
    runtimeDeviceLine,
    coerceAsrSettingsForRuntime,
    isAsrEngineSelected,
    selectAsrEngine,
  };
}
