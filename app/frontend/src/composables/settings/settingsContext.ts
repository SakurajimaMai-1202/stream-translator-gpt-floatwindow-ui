import { inject, provide, type ComputedRef, type InjectionKey, type Ref } from 'vue';
import type { AppUpdateStatus } from '../../services/api';

export interface SettingsContext {
  localConfig: Ref<any>;
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
