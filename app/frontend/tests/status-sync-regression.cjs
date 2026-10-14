// Run with: node tests/status-sync-regression.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

(async () => {
  let mounted, unmounted, interval, clears = 0, fetches = 0, state;
  let created = 0;
  let source;
  const newSource = () => ({ listeners: {}, closed: false, readyState: 0,
    addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); },
    removeEventListener(name, fn) { this.listeners[name] = (this.listeners[name] || []).filter(item => item !== fn); },
    emit(name, data) { for (const fn of this.listeners[name] || []) fn(data === undefined ? {} : { data: JSON.stringify(data) }); },
    count(name) { return (this.listeners[name] || []).length; },
    close() { this.closed = true; }
  });
  const load = (file, extra) => {
    const exports = {};
    const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/composables', file), 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 }
    }).outputText;
    vm.runInNewContext(code, { exports, console, ...extra });
    return exports;
  };
  const shared = load('sharedSyncSource.ts', { require(name) {
    if (name === '../services/api') return { syncApi: { createEventSource: () => { created++; source = newSource(); return source; } } };
    throw new Error(name);
  } });
  const exports = load('useStatusSync.ts', {
    setInterval(fn, delay) { assert.equal(delay, 1000); interval = fn; return 1; },
    clearInterval() { clears++; interval = undefined; },
    require(name) {
      if (name === 'vue') return { onMounted(fn) { mounted = fn; }, onUnmounted(fn) { unmounted = fn; } };
      if (name === './sharedSyncSource') return shared;
      throw new Error(name);
    }
  });
  const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
  exports.useStatusSync('model_download.status', async () => { fetches++; return { status: 'snapshot' }; }, payload => { state = payload.status; });
  mounted(); await flush();
  assert.equal(fetches, 1); assert.equal(state, 'snapshot');
  source.emit('model_download.status', { status: 'downloading' });
  assert.equal(state, 'downloading');
  source.emit('error'); source.emit('error');
  assert.equal(typeof interval, 'function');
  interval(); await flush(); assert.equal(fetches, 2);
  source.emit('open'); await flush();
  assert.equal(fetches, 3); assert.equal(interval, undefined); assert.equal(clears, 1);
  source.emit('error'); unmounted();
  assert.equal(source.closed, true); assert.equal(interval, undefined);
  assert.equal(source.count('model_download.status'), 0);
  // Several consumers share one connection; it closes after the last one stops.
  const a = exports.createStatusSync('a', async () => ({}), () => {});
  const b = exports.createStatusSync('b', async () => ({}), () => {});
  const before = created;
  a.start(); b.start();
  assert.equal(created, before + 1);
  const sharedSource = source;
  a.stop(); assert.equal(sharedSource.closed, false); assert.equal(sharedSource.count('a'), 0);
  b.stop(); assert.equal(sharedSource.closed, true);
  // An older GET must not overwrite a pushed state.
  let resolve;
  const sync = exports.createStatusSync('status', () => new Promise(r => { resolve = r; }), payload => { state = payload.status; });
  sync.start();
  source.emit('status', { status: 'completed' });
  resolve({ status: 'downloading' }); await flush();
  assert.equal(state, 'completed'); sync.stop();
  console.log('Status sync regression: mount, push, reconnect, polling fallback, cleanup, shared connection and stale GET passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
