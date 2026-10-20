// Run with: node tests/subtitle-stream-regression.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function harness(overrides = {}) {
  const timers = new Map(), intervals = new Map(), sources = [], channels = [];
  let id = 0, task = null, scrolls = 0;
  class Source {
    listeners = {};
    constructor(url) { this.url = url; sources.push(this); }
    addEventListener(name, callback) { this.listeners[name] = callback; }
    close() { this.closed = true; }
    emit(name, data) { this.listeners[name]({ data: typeof data === 'string' ? data : JSON.stringify(data) }); }
  }
  const globals = {
    console: { log() {}, error() {} }, Date, Math,
    location: { protocol: 'https:', host: 'example.test:42' },
    fetch: async () => ({ json: async () => ({ success: !!task, task_id: task }) }),
    EventSource: Source,
    BroadcastChannel: class { constructor(name) { this.name = name; channels.push(this); } close() { this.closed = true; } },
    setTimeout: (fn, delay) => { timers.set(++id, { fn, delay }); return id; },
    clearTimeout: key => timers.delete(key),
    setInterval: (fn, delay) => { intervals.set(++id, { fn, delay }); return id; },
    clearInterval: key => intervals.delete(key),
  };
  function load(name) {
    const exports = {};
    const code = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/composables', name + '.ts'), 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
    }).outputText;
    vm.runInNewContext(code, { ...globals, exports, require(name) {
      if (name === 'vue') return { ref: value => ({ value }) };
      if (name === './subtitleStreamLogic') return load('subtitleStreamLogic');
      throw new Error(`Unexpected import: ${name}`);
    } });
    return exports;
  }
  const stream = load('useSubtitleStream').useSubtitleStream({
    transport: 'sse', maxItems: () => 2, queueLatency: true,
    scrollDuringTyping: true, shouldScroll: () => true, scrollToBottom: () => scrolls++, ...overrides,
  });
  return { stream, sources, channels, timers, intervals, logic: load('subtitleStreamLogic'),
    setTask: value => { task = value; }, scrolls: () => scrolls,
    async retry(delay) {
      const [key, timer] = [...timers][0];
      assert.equal(timer.delay, delay); timers.delete(key); await timer.fn();
    },
  };
}

(async () => {
  const h = harness();
  await h.stream.connect();
  assert.equal(h.stream.status.value, 'waiting');
  await h.retry(5000);
  h.setTask('task-1');
  await h.retry(5000);
  const source = h.sources[0];
  assert.equal(source.url, 'https://example.test:42/api/translation/stream/task-1');
  source.emit('subtitle', '{broken');
  source.emit('subtitle', {});
  assert.equal(h.stream.subtitles.value.length, 0);
  source.emit('subtitle', { timestamp: 'a', original: 'hello', partial: true });
  const item = h.stream.subtitles.value[0];
  const timer = [...h.intervals.values()][0];
  assert.equal(timer.delay, 18);
  for (let i = 0; i < 4; i++) timer.fn();
  assert.equal(item.displayOriginal, 'hell');
  assert.equal(h.scrolls(), 2);
  source.emit('subtitle', { timestamp: 'a', original: 'help', translated: 'done', final: true });
  assert.equal(h.stream.subtitles.value[0], item);
  assert.equal(item.displayOriginal, 'hel');
  assert.equal(h.scrolls(), 2);
  source.emit('subtitle', { original: 'b' });
  source.emit('subtitle', { original: 'c' });
  assert.equal(h.stream.subtitles.value.length, 2);
  assert.ok(!h.stream.typingItemIds.value.includes(item.id));
  source.emit('status', { status: 'stopped' });
  assert.equal(h.timers.size, 0);
  source.emit('status', { status: 'completed' });
  assert.equal(source.closed, true);
  await h.retry(3000);
  h.sources[1].onerror();
  assert.equal(h.stream.status.value, 'error');
  await h.retry(3000);
  h.sources[2].emit('status', { status: 'error' });
  h.stream.dispose();
  assert.equal(h.timers.size, 0);
  assert.equal(h.intervals.size, 0);

  const mobile = harness({ queueLatency: false, trimBeforeTyping: true, scrollDuringTyping: false });
  mobile.setTask('mobile'); await mobile.stream.connect();
  mobile.sources[0].emit('subtitle', { original: 'hello', translation_queue_latency_ms: 12 });
  assert.equal('translation_queue_latency_ms' in mobile.stream.subtitles.value[0], false);
  for (let i = 0; i < 4; i++) [...mobile.intervals.values()][0].fn();
  assert.equal(mobile.scrolls(), 1);
  mobile.stream.dispose();

  const floating = harness({ transport: 'broadcast', trimAll: true, scrollOnReplacement: true });
  await floating.stream.connect();
  assert.equal(floating.sources.length, 0);
  const channel = floating.channels[0];
  assert.equal(channel.name, 'subtitle-updates');
  channel.onmessage({ data: null });
  channel.onmessage({ data: { backend_timestamp: 'a', original: 'one' } });
  channel.onmessage({ data: { backend_timestamp: 'a', translated: 'two' } });
  assert.equal(floating.stream.subtitles.value.length, 1);
  assert.equal(floating.stream.subtitles.value[0].original, '');
  assert.ok(floating.stream.subtitles.value[0].timestamp instanceof Date);
  assert.equal(floating.scrolls(), 2);
  floating.stream.dispose();
  assert.equal(channel.closed, true);

  for (const broadcast of [false, true]) {
    const statusLines = [];
    const identity = broadcast ? { backend_timestamp: 'status' } : { timestamp: 'status' };
    for (const status of ['failed', 'timeout']) {
      h.logic.updateLine(statusLines, { ...identity, original: 'x', translation_status: status }, broadcast, true);
      assert.equal(statusLines.length, 1);
      assert.equal(statusLines[0].translation_status, status);
    }
    h.logic.updateLine(statusLines, { ...identity, original: 'x' }, broadcast, true);
    assert.equal(statusLines[0].translation_status, null);
  }

  const lines = [];
  for (let i = 0; i < 5; i++) h.logic.updateLine(lines, { original: 'x' }, false, true);
  h.logic.trimLines(lines, 2, false, () => {});
  assert.equal(lines.length, 4); // SSE removes only one even after lowering the limit.
  h.logic.trimLines(lines, 2, true, () => {});
  assert.equal(lines.length, 2);
  console.log('Subtitle stream regression: parsing, replacement, trimming, typing, transports and reconnect timers passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
