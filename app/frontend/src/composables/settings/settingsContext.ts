import type { useTranslationStore } from '../../stores/translation';
import type { useModelDownloadStore } from '../../stores/modelDownload';
import type { useTranscriptionSettings } from './useTranscriptionSettings';
import type { useTerminologySettings } from './useTerminologySettings';
import type { useTranslationSettings } from './useTranslationSettings';
import type { useAsrModelManagement } from './useAsrModelManagement';
import { inject, provide, type ComputedRef, type InjectionKey, type Ref } from 'vue';
import type { AppUpdateStatus } from '../../services/api';

export interface SettingsContext {
  localConfig: Ref<any>;
  audioValidationMessage: ComputedRef<string>;
  sharingLanAddresses: Ref<string[]>;
  copiedSharingUrl: Ref<string>;
  appUpdateStatus: Ref<AppUpdateStatus | null>;
  appUpdateBusy: ComputedRef<boolean>;
  checkAppUpdate: () => Promise<void>;
  downloadAppUpdate: () => Promise<void>;
  cancelAppUpdate: () => Promise<void>;
  applyAppUpdate: () => Promise<void>;
  testingGpt: Ref<boolean>;
  testingGemini: Ref<boolean>;
  testConnection: (backend: 'gpt' | 'gemini') => Promise<void>;
  diagnosticsBusy: Ref<boolean>;
  cookiePlatform: Ref<string>;
  cookieBrowser: Ref<string>;
  cookieBrowserProfile: Ref<string>;
  cookieImporting: Ref<boolean>;
  cookieFileInput: Ref<HTMLInputElement | null>;
  cookieImportResult: Ref<{ type: 'success' | 'error'; message: string } | null>;
}

export const settingsContextKey: InjectionKey<SettingsContext> = Symbol('SettingsContext');

export function provideSettingsContext(ctx: SettingsContext): void {
  provide(settingsContextKey, ctx);
}

export function useSettingsContext(): SettingsContext {
  const ctx = inject(settingsContextKey);
  if (!ctx) throw new Error('useSettingsContext requires provideSettingsContext in an ancestor component');
  return ctx;
}

// Tab state is instantiated once by SettingsView and shared through typed bindings.
export interface SettingsTabBindings extends ReturnType<typeof useTranscriptionSettings>, ReturnType<typeof useTerminologySettings>, ReturnType<typeof useTranslationSettings>, ReturnType<typeof useAsrModelManagement> {
  activeTab: Ref<string>;
  deleteCustomModel: (index: number) => void;
  localConfig: Ref<any>;
  modelDownloadStore: ReturnType<typeof useModelDownloadStore>;
  openCustomModelDialog: (index?: number) => void;
  store: ReturnType<typeof useTranslationStore>;
  testConnection: (backend: 'gpt' | 'gemini') => Promise<void>;
  testOpenAiAsrConnection: () => Promise<void>;
  testingGemini: Ref<boolean>;
  testingGpt: Ref<boolean>;
}

export const settingsTabBindingsKey: InjectionKey<SettingsTabBindings> = Symbol('SettingsTabBindings');

export function provideSettingsTabBindings(bindings: SettingsTabBindings): void {
  provide(settingsTabBindingsKey, bindings);
}

export function useSettingsTabBindings(): SettingsTabBindings {
  const bindings = inject(settingsTabBindingsKey);
  if (!bindings) throw new Error('useSettingsTabBindings requires provideSettingsTabBindings in an ancestor component');
  return bindings;
}
