// Run with: node tests/translation-sse-regression.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

class MockEventSource {
  listeners = {};
  readyState = 1;
  addEventListener(type, callback) { this.listeners[type] = callback; }
  close() { this.readyState = 2; }
  emit(type, data) {
    const event = { data: JSON.stringify(data) };
    this.listeners[type]?.(event);
    if (type === 'error') this.onerror?.(event);
  }
  transportError() {
    const event = {};
    this.listeners.error?.(event);
    this.onerror?.(event);
  }
}

function createStore() {
  const sources = [];
  const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/stores/translation.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  vm.runInNewContext(code, {
    exports,
    require(name) {
      if (name === 'pinia') return { defineStore: (_name, setup) => setup };
      if (name === 'vue') return { ref: value => ({ value }), computed: get => ({ get value() { return get(); } }) };
      if (name === '../services/api') return { translationApi: { createEventSource() {
        const source = new MockEventSource(); sources.push(source); return source;
      } } };
      throw new Error(`Unexpected import: ${name}`);
    },
    BroadcastChannel: class { postMessage() {} },
    console: { log() {}, error() {} },
    performance,
    requestAnimationFrame: callback => callback(),
  });
  const store = exports.useTranslationStore();
  store.isRunning.value = true;
  store.asrReady.value = true;
  store.connectEventSource('first');
  return { store, sources };
}

{
  const { store, sources: [source] } = createStore();
  source.emit('error', { message: '目標程序已退出，請重新選擇。' });
  source.transportError();
  assert.equal(store.errorMessage.value, '目標程序已退出，請重新選擇。');
  assert.equal(store.isRunning.value, false);
  assert.equal(store.asrReady.value, false);
  assert.equal(source.readyState, 2);
}

for (const status of ['completed', 'stopped', 'error']) {
  const { store, sources: [source] } = createStore();
  source.emit('subtitle', { original: '最後一句', translated: '最後一句翻譯' });
  source.emit('status', { status, message: '任務已結束', asr_ready: true });
  source.transportError();
  assert.equal(store.isRunning.value, false);
  assert.equal(store.asrReady.value, false);
  assert.equal(store.subtitles.value.length, 1);
  assert.equal(store.subtitles.value[0].translated, '最後一句翻譯');
  assert.equal(store.errorMessage.value, status === 'error' ? '任務已結束' : '');
  assert.equal(source.readyState, 2);
}

{
  const { store, sources: [source] } = createStore();
  source.transportError();
  assert.equal(store.errorMessage.value, 'SSE 連接中斷');
  assert.equal(store.isRunning.value, false);
}

{
  const { store, sources } = createStore();
  store.connectEventSource('second');
  sources[0].transportError();
  assert.equal(store.isRunning.value, true);
  assert.equal(store.errorMessage.value, '');
  assert.equal(sources[1].readyState, 1);
}

console.log('SSE lifecycle regression: 6 scenarios passed');
