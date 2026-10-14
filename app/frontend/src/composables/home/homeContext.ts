import { inject, provide, type ComputedRef, type InjectionKey, type Ref } from 'vue';
import type { Router } from 'vue-router';
import type { useTranslationStore } from '../../stores/translation';
import type { useLlamaStore } from '../../stores/llama';
import type { useInterfaceModeStore } from '../../stores/interfaceMode';
import type { useModelDownloadStore } from '../../stores/modelDownload';
import type { UiSelectOption } from '../../components/UiSelect.vue';
import type { AppUpdateStatus, AudioSource, AudioDevice, ProcessAudioTarget, SourceCheckResult, ModelEngine, ModelComputeBackend } from '../../services/api';

interface PyQtClipboardBridge {
  copyToClipboard?: (text: string, callback?: (result: boolean) => void) => void;
  chooseLocalFile?: (callback: (path: string) => void) => void;
  updateNativeRecordingState?: (isRecording: boolean) => void;
}

export type WindowWithPyQt = Window & {
  pyqt?: PyQtClipboardBridge;
};

// 配置狀態檢查
interface ConfigWarning {
  level: 'warning' | 'error';
  message: string;
  page?: string;
  actionLabel?: string;
}

export interface HomeContext {
  router: Router;
  store: ReturnType<typeof useTranslationStore>;
  configWarnings: ComputedRef<ConfigWarning[]>;
  hasErrors: ComputedRef<boolean>;
  availableAppUpdate: Ref<AppUpdateStatus | null>;
  appUpdateNoticeDismissed: Ref<boolean>;
  openAppUpdateSettings: () => void;
  ffmpegWarningDismissed: Ref<boolean>;
  interfaceMode: ReturnType<typeof useInterfaceModeStore>;
  readinessItems: ComputedRef<{ label: string; status: string; detail: string }[]>;
  goToWarningPage: (page?: string) => void;
  urlInput: Ref<string>;
  urlInputRef: Ref<HTMLInputElement | null>;
  localFileInputRef: Ref<HTMLInputElement | null>;
  isLoading: Ref<boolean>;
  isPreparingAsrModel: Ref<boolean>;
  audioSource: Ref<AudioSource>;
  availableDevices: Ref<AudioDevice[]>;
  selectedDeviceIndex: Ref<number | null>;
  isLoadingDevices: Ref<boolean>;
  sourceCheck: Ref<SourceCheckResult | null>;
  isCheckingSource: Ref<boolean>;
  sourceControlsLocked: ComputedRef<boolean>;
  processAudioTargets: Ref<ProcessAudioTarget[]>;
  selectedProcessTargetKey: Ref<string | number | null>;
  processAudioSupported: Ref<boolean>;
  processAudioMessage: Ref<string>;
  isLoadingProcessTargets: Ref<boolean>;
  processTargetKey: (target: ProcessAudioTarget) => string;
  selectedProcessTarget: ComputedRef<ProcessAudioTarget | undefined>;
  loadProcessAudioTargets: () => Promise<void>;
  addLog: (message: string) => void;
  loadDevices: () => Promise<void>;
  onAudioSourceChange: () => Promise<void>;
  whisperModels: string[];
  qwen3AsrModels: { value: string; label: string }[];
  parakeetModels: { value: string; label: string }[];
  allFunAsrModelOptions: UiSelectOption[];
  selectedAsrModelId: ComputedRef<string>;
  selectedAsrCapability: ComputedRef<NonNullable<NonNullable<HomeContext['runtimeCapabilities']['value']>['asr_model_capabilities']>[number] | undefined>;
  selectedTranscriptionEngine: Ref<string>;
  selectedAsrComputeBackend: Ref<string>;
  selectedWhisperModel: Ref<string>;
  selectedQwen3AsrModel: Ref<string>;
  selectedSenseVoiceModel: Ref<string>;
  selectedFunAsrModel: Ref<string>;
  selectedParakeetModel: Ref<string>;
  selectedOpenAiTranscriptionModel: Ref<string>;
  selectedInputLanguage: Ref<string>;
  selectedOutputLanguage: Ref<string>;
  selectedBackend: Ref<string>;
  translationEnabled: Ref<boolean>;
  sameLanguageSelected: ComputedRef<boolean>;
  runtimeCapabilities: ComputedRef<NonNullable<ReturnType<typeof useTranslationStore>['runtimeStatus']>['asr_capabilities'] | null>;
  allowedTranscriptionEngines: ComputedRef<string[]>;
  allowedFasterWhisperModels: ComputedRef<string[]>;
  allowedQwen3AsrModels: ComputedRef<string[]>;
  allowedParakeetModels: ComputedRef<string[]>;
  modelDownloadStore: ReturnType<typeof useModelDownloadStore>;
  selectedDownloadEngine: ComputedRef<ModelEngine | null>;
  selectedModelComputeBackend: ComputedRef<ModelComputeBackend>;
  selectedAsrDownloadTask: ComputedRef<ReturnType<ReturnType<typeof useModelDownloadStore>['getTask']>>;
  selectedAsrModelDownloaded: ComputedRef<boolean>;
  isConfigReady: ComputedRef<boolean>;
  handleStart: () => Promise<void>;
  handleStop: () => Promise<void>;
  openSubtitleWindow: () => void;
  llamaStore: ReturnType<typeof useLlamaStore>;
  externalFamilyEndpoint: ComputedRef<boolean>;
  logs: Ref<string[]>;
  logContainer: Ref<HTMLElement | null>;
  publicPort: Ref<number>;
  activeCopyPath: Ref<string | null>;
  subtitleSharingEnabled: Ref<boolean>;
  subtitleSharingStatusKnown: Ref<boolean>;
  isUpdatingSubtitleSharing: Ref<boolean>;
  getPublicBase: () => string;
  copyLink: (path: string) => Promise<void>;
  toggleSubtitleSharing: () => Promise<void>;
}

export const homeContextKey: InjectionKey<HomeContext> = Symbol('HomeContext');

export function provideHomeContext(context: HomeContext): void {
  provide(homeContextKey, context);
}

export function useHomeContext(): HomeContext {
  const context = inject(homeContextKey);
  if (!context) throw new Error('useHomeContext requires provideHomeContext in an ancestor component');
  return context;
}
