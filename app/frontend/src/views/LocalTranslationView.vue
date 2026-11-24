<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useInterfaceModeStore } from '../stores/interfaceMode';
import { cancelModelInstallWithRetry, isModelInstallBusy, useLocalTranslationSetup } from '../composables/useLocalTranslationSetup';
import { useNativePicker } from '../composables/useNativePicker';
import LlamaSettings from '../components/LlamaSettings.vue';
import { useLlamaStore } from '../stores/llama';
import { useTranslationStore } from '../stores/translation';
import { configApi } from '../services/api';
import { llamaApi, type ModelInstallStatus, type TranslationModelRecommendationInfo } from '../services/llamaApi';

const interfaceMode = useInterfaceModeStore();
const { available, pickFolder } = useNativePicker();
async function chooseModelFolder() {
  const path = await pickFolder('選擇模型資料夾', directory.value);
  // A download may have started while the dialog was open.
  if (!path || locked.value) return;
  directory.value = path;
  await scan();
}
function scrollToStep(id: string) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
const setup = useLocalTranslationSetup();
const { running: settingUp, progress: setupPercent, cancelled: setupCancelled } = setup;
const simpleReady = computed(() => !!llamaStore.serverStatus?.runtime?.installed && !!llamaStore.selectedModelPath);
const changingModel = ref(false);
const selectedOptionKey = ref('');
const setupOptions = computed(() => data.value?.simple_setup.options ?? []);
const selectedOption = computed(() => setupOptions.value.find(option => option.key === selectedOptionKey.value)
  ?? setupOptions.value.find(option => option.recommended));
function cancelModelChange() {
  changingModel.value = false;
  setupCancelled.value = false;
  error.value = '';
}
const modelName = computed(() => {
  const filename = llamaStore.selectedModelPath.split(/[\\/]/).pop() || '';
  const index = /index[-_. ]?translate[-_. ]?(2|9)b/i.exec(filename);
  if (index) return `Index-Translate ${index[1]}B`;
  const hyMt = /hy[-_]?mt([23])/i.exec(filename);
  if (hyMt) return `Hy-MT${hyMt[1]} ${/1[._]8b/i.test(filename) ? '1.8B' : '7B'}`;
  return filename.replace(/\.gguf$/i, '').replace(/[-_.]Q\d[^ ]*$/i, '').replace(/[-_]/g, ' ') || '翻譯模型';
});
const simpleStatus = computed(() => llamaStore.errorMessage || llamaStore.serverStatus?.last_error ? '錯誤'
  : llamaStore.isServerReady ? '已就緒' : actionBusy.value || llamaStore.isServerRunning ? '啟動中' : '未啟動');
const setupStep = computed(() => setupCancelled.value ? setup.setupMessage.value : settingUp.value
  ? setup.phase.value === 'model' ? setup.setupMessage.value : setup.phase.value === 'saving' ? '正在儲存設定…' : '正在準備翻譯引擎…' : '');
const testText = ref('');
const testResult = ref('');
const testing = ref(false);
async function startSetup() {
  error.value = '';
  try {
    // A running server would keep serving the old model under the new model's settings.
    if (changingModel.value && llamaStore.isServerRunning) await llamaStore.stopServer();
    await setup.run(data.value, undefined, selectedOption.value);
    if (!setupCancelled.value) { await llamaStore.loadConfig(); backend.value = 'llama'; changingModel.value = false; }
  } catch { if (!setupCancelled.value) error.value = '設定失敗，請檢查網路與磁碟空間後重試。'; }
}
async function cancelSetup() {
  try { await setup.cancel(); }
  catch { error.value = '取消失敗，請再試一次。'; }
}
async function toggleSimpleServer() {
  actionBusy.value = true;
  error.value = '';
  try {
    if (llamaStore.isServerRunning) await llamaStore.stopServer();
    else {
      await switchBackend();
      if (backend.value === 'llama') await llamaStore.startServer();
    }
  } catch { error.value = '無法啟動或停止翻譯，請再試一次。'; }
  finally { actionBusy.value = false; }
}
async function testSimpleTranslation() {
  if (!testText.value.trim() || testing.value) return;
  testing.value = true;
  error.value = '';
  testResult.value = '';
  try { testResult.value = await llamaStore.translate(testText.value.trim(), 'auto', 'Traditional Chinese'); }
  catch { error.value = '試譯失敗，請確認翻譯已啟動後再試。'; }
  finally { testing.value = false; }
}

type CatalogModel = TranslationModelRecommendationInfo['models'][number];
const llamaStore = useLlamaStore();
const translationStore = useTranslationStore();
const ready = ref(false);
const statusReady = ref(false);
const tab = ref('recommended');
const filter = ref('recommended');
const data = ref<TranslationModelRecommendationInfo | null>(null);
const loading = ref(false);
const error = ref('');
const directory = ref('');
const search = ref('');
const actionBusy = ref(false);
const switching = ref(false);
const backend = ref<string | null>(null);
const install = ref<ModelInstallStatus | null>(null);
const busy = computed(() => isModelInstallBusy(interfaceMode.localModelInstallStatus || install.value));
watch(() => settingUp.value || setup.runtimeBackgroundBusy.value || busy.value || actionBusy.value,
  value => { interfaceMode.localViewJobBusy = value; }, { immediate: true, flush: 'sync' });
watch([install, setup.localModelInstallStatus], ([download, model]) => {
  const status = settingUp.value ? model : download;
  if (status) interfaceMode.localModelInstallStatus = status;
}, { flush: 'sync' });
watch(setup.runtimeInstallStatus, status => {
  if (status) interfaceMode.runtimeInstallStatus = status;
}, { flush: 'sync' });
const locked = computed(() => interfaceMode.localTranslationJobBusy || !ready.value || !statusReady.value || busy.value || actionBusy.value || llamaStore.isLoading);
const visibleModels = computed(() => (data.value?.models || []).filter(model =>
  filter.value === 'recommended' ? model.fit === 'recommended' : filter.value === 'novel_game' ? model.category === 'novel_game' : true));
const localModels = computed(() => llamaStore.models.filter(model => model.name.toLowerCase().includes(search.value.trim().toLowerCase())));
const fitText = { recommended: '適合這台電腦', possible: '可以嘗試', unknown: '尚無法判斷', not_recommended: '顯存較不足' };
const stateText = { idle: '等待下載', resolving: '準備下載', downloading: '下載中', verifying: '驗證中', completed: '下載完成', cancelled: '已取消', error: '下載失敗' };
const percent = computed(() => Math.min(100, Math.max(0, Math.round((install.value?.progress || 0) * 100))));
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
let handledJob = '';
let statusGeneration = 0;
const pendingJobKey = 'local-translation.pending-install';
function rememberJob(job: string) {
  try { if (job) sessionStorage.setItem(pendingJobKey, job); else sessionStorage.removeItem(pendingJobKey); } catch { /* Restricted WebView. */ }
}
function pendingJob() {
  try { return sessionStorage.getItem(pendingJobKey); } catch { return null; }
}

function bytes(value: number) { return `${(value / 1024 / 1024).toFixed(1)} MB`; }
function installedPath(model: CatalogModel, quant = model.recommended_quant) {
  if (!quant) return;
  const escapedQuant = quant.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const quantToken = new RegExp(`(?:^|[._-])${escapedQuant}(?=[.-]|$)`, 'i');
  const normalize = (value: string) => value.toLowerCase().replace(/[^a-z0-9]/g, '');
  const stems = [model.repo.split('/').pop() || '', model.name]
    .map(name => normalize(name.replace(/[-_. ]?gguf$/i, ''))).filter(Boolean);
  return llamaStore.models.find(file => {
    const token = quantToken.exec(file.name);
    if (!token) return false;
    const stem = normalize(file.name.slice(0, token.index));
    return stems.some(name => stem === name);
  })?.path;
}
async function load(refresh = false) {
  loading.value = true;
  error.value = '';
  try { data.value = await llamaApi.getModelRecommendations(refresh); }
  catch { error.value = '無法讀取推薦模型，請稍後重新偵測。'; }
  finally { loading.value = false; }
}
async function scan() {
  if (locked.value) return;
  error.value = '';
  await llamaStore.loadModels(directory.value.trim());
  await llamaStore.saveConfig();
}
async function select(path: string) {
  actionBusy.value = true;
  error.value = '';
  try { await llamaStore.selectModel(path); await llamaStore.saveConfig(); }
  catch { error.value = '無法選擇模型，請重新掃描後再試。'; }
  finally { actionBusy.value = false; }
}
async function applyStatus(status: ModelInstallStatus) {
  install.value = status;
  if (['cancelled', 'error'].includes(status.state)) rememberJob('');
  if (status.state === 'error') error.value = '模型下載失敗，請檢查網路與磁碟空間後重試。';
  if (status.state === 'completed' && status.path && handledJob !== (status.job_id || status.path)) {
    actionBusy.value = true;
    try {
      const folder = status.directory || status.path.replace(/[\\/][^\\/]+$/, '');
      if (!llamaStore.modelDirectory) llamaStore.modelDirectory = folder;
      const configuredDirectory = llamaStore.modelDirectory;
      try { await llamaStore.loadModels(folder); }
      finally { llamaStore.modelDirectory = configuredDirectory; }
      if (llamaStore.errorMessage) throw new Error(llamaStore.errorMessage);
      directory.value = llamaStore.modelDirectory;
      await llamaStore.selectModel(status.path);
      await llamaStore.saveConfig();
    } catch {
      error.value = '下載完成，但無法自動套用模型；請到「本機已有」手動選擇。';
    } finally {
      handledJob = status.job_id || status.path;
      rememberJob('');
      actionBusy.value = false;
    }
  }
}
function schedulePoll() {
  if (timer) clearTimeout(timer);
  if (!disposed && !interfaceMode.isSimple && busy.value) timer = setTimeout(poll, 1000);
}
async function poll() {
  const generation = ++statusGeneration;
  try {
    const status = await llamaApi.getSimpleModelInstallStatus();
    if (!disposed && generation === statusGeneration) await applyStatus(status);
  } catch { error.value = '暫時無法取得下載進度，正在重試。'; }
  finally { schedulePoll(); }
}
async function useModel(model: CatalogModel, minimum = false) {
  if (locked.value) return;
  const quant = minimum ? model.minimum_quant : model.recommended_quant;
  const path = installedPath(model, quant);
  if (path) { await select(path); return; }
  actionBusy.value = true;
  error.value = '';
  try {
    const result = await llamaApi.installSimpleModel(model.id, quant);
    if (!result.success) throw new Error('install rejected');
    rememberJob(result.job_id);
    install.value = { state: 'resolving', job_id: result.job_id, catalog_id: model.id, quant,
      filename: model.name, progress: 0, bytes_downloaded: 0, bytes_total: 0,
      deployment_config: {}, message: '', model_id: model.id, path: '', sha256: '', error: '' };
    await poll();
  } catch { error.value = '無法開始下載，請檢查網路後重試。'; }
  finally { actionBusy.value = false; }
}
async function cancel() {
  actionBusy.value = true;
  ++statusGeneration;
  if (timer) clearTimeout(timer);
  try {
    const status = await cancelModelInstallWithRetry(install.value?.job_id);
    await applyStatus(status);
    if (isModelInstallBusy(status)) error.value = '下載工作已變更，無法取消；請重新整理此頁。';
  }
  catch { error.value = '取消下載失敗，請再試一次。'; }
  finally { actionBusy.value = false; schedulePoll(); }
}
async function switchBackend() {
  switching.value = true;
  try {
    const config = await configApi.getConfig(true);
    await translationStore.saveConfigSection('translation', { ...config.translation, backend: 'llama' });
    backend.value = 'llama';
  } catch { error.value = '無法儲存翻譯服務設定，請再試一次。'; }
  finally { switching.value = false; }
}
async function restoreDownload() {
  const generation = ++statusGeneration;
  try {
    const status = await llamaApi.getSimpleModelInstallStatus();
    if (disposed || generation !== statusGeneration) return;
    install.value = status;
    // Do not override a later manual selection with a historic completed job.
    if (status.state === 'completed') {
      if (pendingJob() === status.job_id) await applyStatus(status);
      else handledJob = status.job_id || status.path;
    }
    if (busy.value) rememberJob(status.job_id);
    if (status.state === 'error') error.value = '上次模型下載失敗，可重新下載。';
    statusReady.value = true;
    schedulePoll();
  } catch { error.value = '無法讀取下載狀態，請按「重試」。'; }
}
watch(() => interfaceMode.isSimple, async simple => {
  if (!ready.value || disposed) return;
  ++statusGeneration;
  if (timer) clearTimeout(timer);
  statusReady.value = false;
  if (!simple) { await restoreDownload(); return; }
  try {
    if (!data.value) await load();
    if (await setup.restore(data.value)) { await llamaStore.loadConfig(); backend.value = 'llama'; }
  } catch { if (!setupCancelled.value && !disposed) error.value = '無法接續設定，請重試。'; }
  finally { statusReady.value = true; }
});
onMounted(async () => {
  const recommendations = load();
  try {
    await llamaStore.initialize();
    directory.value = llamaStore.modelDirectory;
    ready.value = true;
    const config = await configApi.getConfig();
    backend.value = config.translation?.backend || '';
  } catch { error.value = '無法讀取設定，請重新開啟此頁。'; }
  if (!interfaceMode.isSimple) await restoreDownload();
  else {
    try {
      await recommendations;
      if (disposed) return;
      if (await setup.restore(data.value)) { await llamaStore.loadConfig(); backend.value = 'llama'; }
      else if (setup.setupMessage.value) error.value = setup.setupMessage.value;
    } catch { if (!setupCancelled.value && !disposed) error.value = '無法接續設定，請重試。'; }
    finally { statusReady.value = true; }
  }
});
onUnmounted(() => { interfaceMode.localViewJobBusy = false; disposed = true; ++statusGeneration; if (timer) clearTimeout(timer); });
</script>

<template>
  <div v-if="interfaceMode.isSimple" class="commercial-page local-translation mx-auto max-w-xl space-y-5 p-5">
    <h1 class="text-2xl font-bold">本地翻譯</h1>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-if="!ready || (!statusReady && !settingUp && !setupCancelled)">正在讀取設定…</p>
    <section v-else-if="!simpleReady || changingModel || settingUp || setupCancelled" class="commercial-panel p-4 space-y-4">
      <h2>使用這台電腦翻譯</h2>
      <p>自動下載適合這台電腦的翻譯引擎與模型{{ selectedOption ? `，大約需要 ${selectedOption.size_gb} GB。` : '。' }}</p>
      <fieldset v-if="!settingUp && setupOptions.length" class="space-y-3">
        <legend>選擇翻譯模型</legend>
        <label v-for="option in setupOptions" :key="option.key" class="flex items-start gap-3">
          <input type="radio" name="simple-model" :value="option.key" :checked="selectedOption?.key === option.key"
            style="width: auto" @change="selectedOptionKey = option.key">
          <span>{{ option.name }} · {{ option.quant }} · 約 {{ option.size_gb }} GB
            <span v-if="option.recommended" class="badge">推薦</span>
            <small>{{ option.note }}</small>
          </span>
        </label>
      </fieldset>
      <template v-if="data?.simple_setup.supported === false">
        <p>{{ data.simple_setup.reason }}</p>
        <p>可在「一般設定」改用雲端翻譯，或切換到進階模式。</p>
      </template>
      <button v-else-if="!settingUp" class="commercial-primary-action" :disabled="!selectedOption || loading || !statusReady || setup.runtimeBackgroundBusy.value" @click="startSetup">開始設定</button>
      <button v-if="changingModel && !settingUp" @click="cancelModelChange">取消</button>
      <button v-if="!data && !loading" @click="load(true)">重新偵測</button>
      <div v-if="settingUp || setupCancelled" class="space-y-3" role="status" aria-live="polite">
        <p>{{ setupStep }}</p>
        <template v-if="settingUp">
          <progress :value="setupPercent" max="100" aria-label="設定進度" />
          <p>{{ setupPercent }}%</p>
          <button :disabled="setupCancelled || setup.phase.value === 'saving'" @click="cancelSetup">取消</button>
        </template>
      </div>
    </section>
    <template v-else>
      <section class="commercial-panel p-4 space-y-4">
        <h2>{{ modelName }}</h2>
        <span class="badge" role="status">{{ simpleStatus }}</span>
        <div><button class="commercial-primary-action" :disabled="actionBusy || llamaStore.isLoading || testing" @click="toggleSimpleServer">{{ llamaStore.isServerRunning ? '停止' : '啟動' }}</button></div>
      </section>
      <section class="commercial-panel p-4 space-y-3">
        <h2>試譯</h2>
        <label for="simple-test">輸入想翻譯的文字</label>
        <textarea id="simple-test" v-model="testText" rows="4" placeholder="翻譯成繁體中文" />
        <button :disabled="!llamaStore.isServerReady || testing || actionBusy || !testText.trim()" @click="testSimpleTranslation">{{ testing ? '翻譯中…' : '試譯' }}</button>
        <p v-if="!llamaStore.isServerReady">啟動後即可試譯。</p>
        <p v-if="testResult" class="whitespace-pre-wrap" role="status">{{ testResult }}</p>
      </section>
      <button :disabled="locked || testing" @click="changingModel = true">更換模型</button>
    </template>
  </div>
  <div v-else class="commercial-page local-translation mx-auto max-w-7xl space-y-5 p-5">
    <header><h1 class="text-2xl font-bold">本地翻譯</h1><p>選擇模型、啟動服務，再試譯一段文字。</p></header>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-if="llamaStore.errorMessage" class="notice error" role="alert">{{ llamaStore.errorMessage }}</p>
    <button v-if="ready && !statusReady" @click="restoreDownload">重試下載狀態</button>
    <aside class="commercial-panel p-4 space-y-2" aria-labelledby="usage-guide">
      <h2 id="usage-guide">使用步驟</h2>
      <ol class="space-y-2 text-sm">
        <li>① <span v-if="llamaStore.selectedModelPath">✓ </span>在下方「1. 選擇模型」按「下載並使用」，或到「本機已有」選資料夾掃描後選擇模型。<button type="button" class="smaller-version-link" @click="scrollToStep('choose-model')">選擇模型 ↓</button></li>
        <li>② <span v-if="llamaStore.isServerRunning">✓ </span>下載完成後往下捲到「2. 啟動」，按啟動服務。<button type="button" class="smaller-version-link" @click="scrollToStep('start-server')">啟動服務 ↓</button></li>
        <li>③ 在「3. 試譯」輸入一句確認能翻譯，之後首頁的「本地 LLM 翻譯」開關就能直接使用。<button type="button" class="smaller-version-link" @click="scrollToStep('test-translation')">試譯 ↓</button></li>
      </ol>
    </aside>
    <section aria-labelledby="choose-model" class="space-y-4">
      <h2 id="choose-model">1. 選擇模型</h2>
      <div class="segments" role="group" aria-label="模型來源">
        <button :aria-pressed="tab === 'recommended'" @click="tab = 'recommended'">推薦下載</button>
        <button :aria-pressed="tab === 'local'" @click="tab = 'local'">本機已有</button>
      </div>
      <template v-if="tab === 'recommended'">
        <div class="commercial-panel p-4 space-y-2">
          <p v-if="data?.selected_gpu">{{ data.selected_gpu.name }} · {{ data.vram_gb }} GB VRAM</p>
          <p v-else>尚未取得顯卡資訊，可切換「全部」查看模型。</p>
          <p>{{ data?.notice }}</p>
          <button :disabled="loading" @click="load(true)">{{ loading ? '偵測中…' : '重新偵測硬體' }}</button>
        </div>
        <div class="segments" role="group" aria-label="篩選模型">
          <button v-for="item in [{id:'recommended',label:'適合這台電腦'}, {id:'all',label:'全部'}, {id:'novel_game',label:'小說遊戲'}]" :key="item.id" :aria-pressed="filter === item.id" @click="filter = item.id">{{ item.label }}</button>
        </div>
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <article v-for="model in visibleModels" :key="model.id" class="commercial-panel model-card p-4 space-y-3">
            <div class="flex flex-wrap gap-2"><span class="badge">{{ fitText[model.fit] || '需手動確認' }}</span><span v-if="model.app_preferred" class="badge">★ 本程式首選</span></div>
            <h3>{{ model.name }}</h3><small>{{ model.repo }}</small>
            <p v-if="model.use_case">{{ model.use_case }}</p><p>{{ model.summary }}</p>
            <p v-if="model.app_preference_reason">{{ model.app_preference_reason }}</p>
            <div class="quant-info"><small>建議品質：{{ model.recommended_quant }} · {{ model.model_size_gb }} GB<br>建議 {{ model.comfortable_vram_gb }} GB VRAM</small></div>
            <div class="quant-info"><small>較小版本：{{ model.minimum_quant }} · {{ model.minimum_size_gb }} GB<br>最低 {{ model.min_vram_gb }} GB VRAM</small></div>
            <small>{{ model.vram_basis }}</small><p>{{ model.fit_reason }}</p>
            <small v-if="model.runtime_note">{{ model.runtime_note }}</small>
            <p v-if="/sakura/i.test(model.id + model.name)" class="notice">Sakura 採 CC BY-NC-SA 4.0 授權；使用前請確認模型頁的授權限制。</p>
            <small v-if="!installedPath(model) && installedPath(model, model.minimum_quant)">
              本機已有較小版本
              <button class="smaller-version-link" :disabled="locked" @click="useModel(model, true)">使用較小版本</button>
            </small>
            <div class="card-actions">
              <button class="commercial-primary-action" :disabled="locked" @click="useModel(model)">{{ installedPath(model) ? '使用此模型' : '下載並使用' }}</button>
              <button v-if="model.minimum_quant !== model.recommended_quant" class="text-sm" :disabled="locked" @click="useModel(model, true)">{{ installedPath(model, model.minimum_quant) ? '使用較小版本' : '下載較小版本' }}（{{ model.minimum_quant }}）</button>
              <a v-if="/sakura/i.test(model.id + model.name)" :href="model.url" target="_blank" rel="noopener noreferrer">查看模型授權</a>
            </div>
          </article>
        </div>
        <p v-if="!loading && !visibleModels.length">目前沒有符合條件的模型，請切換「全部」查看。</p>
      </template>
      <template v-else>
        <div class="commercial-panel p-4 space-y-3">
          <label for="model-folder">模型資料夾</label>
          <div class="scan-row"><input id="model-folder" v-model="directory" placeholder="例如 D:\Models" @keyup.enter="scan"><button v-if="available" :disabled="locked" @click="chooseModelFolder">選擇資料夾…</button><button :disabled="locked" @click="scan">{{ llamaStore.isLoading ? '掃描中…' : '掃描' }}</button></div>
          <label for="model-search">搜尋模型</label><input id="model-search" v-model="search" placeholder="輸入模型名稱">
        </div>
        <div class="grid gap-3 md:grid-cols-2">
          <article v-for="model in localModels" :key="model.path" class="commercial-panel local-model p-3" :class="{ selected: llamaStore.selectedModelPath === model.path }">
            <button class="model-select" :disabled="locked" :aria-pressed="llamaStore.selectedModelPath === model.path" @click="select(model.path)"><strong>{{ model.name }}</strong><small>{{ model.size_mb.toFixed(0) }} MB</small><small>{{ model.path }}</small><span v-if="llamaStore.selectedModelPath === model.path">已選擇</span></button>
            <button :aria-label="llamaStore.favoriteModelPaths.includes(model.path) ? '取消收藏 ' + model.name : '收藏 ' + model.name" :aria-pressed="llamaStore.favoriteModelPaths.includes(model.path)" @click="llamaStore.toggleFavoriteModel(model.path)">{{ llamaStore.favoriteModelPaths.includes(model.path) ? '★' : '☆' }}</button>
          </article>
        </div>
        <p v-if="!llamaStore.isLoading && !localModels.length">尚未找到模型，請確認資料夾後掃描。</p>
      </template>
      <div v-if="install && install.state !== 'idle'" class="commercial-panel p-4 space-y-2" role="status" aria-live="polite">
        <p>{{ stateText[install.state] }}：{{ install.filename }}</p>
        <progress :value="percent" max="100" :aria-label="'下載進度 ' + percent + '%'" />
        <p>{{ bytes(install.bytes_downloaded) }} / {{ install.bytes_total ? bytes(install.bytes_total) : '大小待確認' }} · {{ percent }}%</p>
        <button v-if="busy" :disabled="actionBusy" @click="cancel">取消</button>
      </div>
      <p v-if="llamaStore.selectedModelPath" class="notice">已選擇：{{ llamaStore.selectedModelPath.split(/[\\/]/).pop() }}</p>
    </section>
    <LlamaSettings v-if="ready" initialized hide-errors>
      <template #status-heading>
        <h2 id="start-server" class="step-title">2. 啟動</h2>
        <div v-if="backend !== 'llama' && backend !== 'localllm'" class="notice space-y-2">
          <p>翻譯服務尚未使用本機模型。</p>
          <button :disabled="switching" @click="switchBackend">{{ switching ? '儲存中…' : '將翻譯服務切換為本機模型' }}</button>
        </div>
        <p v-else class="notice">翻譯服務已設為本機模型。</p>
      </template>
      <template #test-heading><h2 id="test-translation" class="step-title">3. 試譯</h2></template>
    </LlamaSettings>
    <p v-else>正在讀取本機設定…</p>
  </div>
</template>

<style scoped>
.local-translation { color: var(--fw-text); min-width: 0; overflow-wrap: anywhere; }
h2 { font-size: 1.2rem; font-weight: 650; } h3 { font-weight: 650; }
p, small { color: var(--fw-text-secondary); } small { display: block; }
button, input, textarea { min-height: 44px; border: 1px solid var(--fw-border-strong); border-radius: var(--fw-radius-md); padding: .6rem .85rem; color: var(--fw-text); background: var(--fw-surface-raised); max-width: 100%; }
button:disabled { opacity: .5; cursor: not-allowed; } button { cursor: pointer; }
textarea { width: 100%; resize: vertical; }
input { width: 100%; min-width: 0; } button:focus-visible, input:focus-visible, textarea:focus-visible, a:focus-visible { outline: 2px solid var(--fw-primary); outline-offset: 2px; }
.segments { display: flex; flex-wrap: wrap; gap: .5rem; } [aria-pressed="true"], .selected { border-color: var(--fw-primary); background: var(--fw-primary-soft); }
.badge, .notice, .quant-info { padding: .5rem .75rem; border-radius: var(--fw-radius-md); background: var(--fw-surface-subtle); }
.badge { font-size: .75rem; } .error { color: #ed9a9a; } .notice { margin-bottom: 1rem; }
.model-card { display: flex; flex-direction: column; min-width: 0; } .card-actions { margin-top: auto; display: grid; gap: .5rem; padding-top: .75rem; }
.scan-row { display: flex; gap: .75rem; } .scan-row input { flex: 1; min-width: 0; } .scan-row button { flex-shrink: 0; white-space: nowrap; } .local-model { display: flex; gap: .5rem; align-items: start; min-width: 0; }
.model-select { flex: 1; min-width: 0; text-align: left; overflow-wrap: anywhere; } .model-select small { margin-top: .5rem; }
.smaller-version-link { border: 0; background: transparent; color: var(--fw-primary); text-decoration: underline; }
progress { width: 100%; accent-color: var(--fw-primary); } .step-title { margin: 1.5rem 0 1rem; }
@media(max-width: 480px) { .local-translation { padding: 1rem; } .scan-row { flex-direction: column; } }
</style>
