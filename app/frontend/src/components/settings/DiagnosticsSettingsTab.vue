<script setup lang="ts">
import { useSettingsContext } from '../../composables/settings/settingsContext';
import { useTranslationStore } from '../../stores/translation';
import { runtimeApi } from '../../services/api';

const { diagnosticsBusy } = useSettingsContext();
const store = useTranslationStore();

async function exportRuntimeDiagnostics() {
  if (diagnosticsBusy.value) return;
  diagnosticsBusy.value = true;
  store.errorMessage = '';
  try {
    const report = await runtimeApi.getDiagnostics();
    const content = JSON.stringify(report, null, 2);
    const filename = `stream-translator-diagnostics-${new Date().toISOString().replace(/[:.]/g, '-')}.json`;
    const bridge = (window as any).pyqt;
    if (bridge?.saveTextFile) {
      const savedPath = await new Promise<string>((resolve) => {
        bridge.saveTextFile(filename, content, (result: string) => resolve(result || ''));
      });
      if (!savedPath) {
        store.statusMessage = '已取消儲存診斷報告';
        return;
      }
      if (savedPath.startsWith('ERROR:')) throw new Error(savedPath.slice(6));
      store.statusMessage = `診斷報告已儲存：${savedPath}`;
      return;
    }
    const blob = new Blob([content], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    window.setTimeout(() => {
      anchor.remove();
      URL.revokeObjectURL(url);
    }, 10_000);
    store.statusMessage = `診斷報告已下載：${filename}`;
  } catch (error: any) {
    store.errorMessage = `匯出 Runtime 診斷報告失敗：${error?.response?.data?.detail || error?.message || '未知錯誤'}`;
  } finally {
    diagnosticsBusy.value = false;
  }
}
</script>

<template>
          <div class="settings-paint-section apple-settings">
            <header class="apple-page-header"><h2>進階設定／疑難排解</h2><p>檢查目前環境與診斷資訊。</p></header>
            <div class="rounded-xl border border-white/10 bg-white/5 p-5">
              <h3 class="text-lg font-semibold text-cyan-300">Runtime 診斷報告</h3>
              <p class="mt-2 text-sm leading-6 text-white/60">
                匯出程式版本、CPU／GPU Runtime、CPU ASR Sidecar、模型儲存位置及 llama.cpp 路徑，供啟動失敗或 GPU 未被使用時分析。
              </p>
              <p class="mt-2 text-xs leading-5 text-white/40">報告不包含 API Key、Cookie 或字幕內容，也不會下載模型或修改設定。</p>
              <button type="button" @click="exportRuntimeDiagnostics" :disabled="diagnosticsBusy" class="mt-4 px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 text-white font-semibold">
                {{ diagnosticsBusy ? '正在建立報告…' : '匯出 Runtime 診斷報告' }}
              </button>
            </div>
          </div>
</template>

<style scoped src="./settings-shared.css"></style>
