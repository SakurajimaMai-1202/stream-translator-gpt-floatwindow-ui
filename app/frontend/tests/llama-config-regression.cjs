// Run with: node tests/llama-config-regression.cjs
// Execute the actual store with real Vue/Pinia and an in-memory config API.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const vue = require('vue');
const pinia = require('pinia');

const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/stores/llama.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function createStore(initial) {
  let persisted = structuredClone(initial);
  const writes = [];
  const presets = [];
  const exports = {};
  const context = {
    exports,
    require(name) {
      if (name === 'pinia') return pinia;
      if (name === 'vue') return vue;
      if (name === '../services/api') return { configApi: {
        getConfig: async () => ({ llama: structuredClone(persisted) }),
        updateSection: async (section, value) => {
          assert.equal(section, 'llama');
          persisted = JSON.parse(JSON.stringify(value));
          writes.push(persisted);
        },
      } };
      if (name === '../services/llamaApi') return { llamaApi: {
        getPresets: async () => ({}),
        getServerStatus: async () => ({ is_running: false, is_ready: false }),
        saveCustomPreset: async (name, value) => presets.push({ name, value: JSON.parse(JSON.stringify(value)) }),
      } };
      throw new Error(`Unexpected import: ${name}`);
    },
    sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    console: { log() {}, warn() {}, error() {} },
    // Message clearing and auto-save timers are outside this persistence test.
    setTimeout() { return 0; }, clearTimeout() {},
  };
  const evaluate = vm.runInThisContext(`(function(exports, require, sessionStorage, console, setTimeout, clearTimeout) {\n${code}\n})`);
  evaluate(exports, context.require, context.sessionStorage, context.console, context.setTimeout, context.clearTimeout);
  pinia.setActivePinia(pinia.createPinia());
  return { store: exports.useLlamaStore(), writes, presets };
}

(async () => {
  const zeros = { temp: 0, top_k: 0, top_p: 0, repeat_penalty: 0, n_predict: 0, n_threads: 0, n_ctx: 0, n_gpu_layers: 0 };
  const { store, writes, presets } = createStore({ ...zeros, model_path: 'Index-Translate.gguf' });
  await store.loadConfig();
  for (const key of Object.keys(zeros)) assert.equal(store.serverConfig[key], 0, `${key} loads as zero`);
  await store.saveConfig();
  for (const key of Object.keys(zeros)) assert.equal(writes.at(-1)[key], 0, `${key} saves as zero`);
  await store.loadConfig();
  assert.equal(store.serverConfig.temp, 0, 'greedy temperature survives save/reload');
  assert.equal(store.serverConfig.top_k, 0, 'disabled top-k survives save/reload');
  await store.saveCustomPreset('Index greedy');
  assert.equal(presets[0].value.temp, 0);
  assert.equal(presets[0].value.top_k, 0);

  const fallback = createStore({ temp: null, top_k: null });
  await fallback.store.loadConfig();
  assert.equal(fallback.store.serverConfig.temp, 0.8);
  assert.equal(fallback.store.serverConfig.top_k, 40);
  assert.equal(fallback.store.serverConfig.n_predict, 512);

  const restored = createStore({ default_preset: 'custom:Index greedy', custom_presets: {
    'Index greedy': { model_path: 'Index-Translate.gguf', temp: 0, top_k: 0 },
  } });
  await restored.store.initialize();
  await vue.nextTick();
  assert.equal(restored.store.serverConfig.temp, 0, 'default preset applies zero temperature');
  assert.equal(restored.store.serverConfig.top_k, 0, 'default preset applies zero top-k');
  await restored.store.saveConfig();
  await restored.store.loadConfig();
  assert.equal(restored.store.serverConfig.temp, 0, 'preset zero survives persisted reload');
  assert.equal(restored.store.serverConfig.top_k, 0);
  console.log('Llama config regression passed: zero values, defaults, save/reload, custom preset startup.');
})().catch(error => { console.error(error); process.exitCode = 1; });
