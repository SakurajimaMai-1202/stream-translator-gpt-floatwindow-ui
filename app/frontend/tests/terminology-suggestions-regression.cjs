const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync('src/composables/settings/useTerminologySettings.ts', 'utf8');
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const timers = new Map();
let nextTimer = 0;
let fail = false;
let state = 'downloading';
const suggestions = ['水星', '流星'].map(canonical => ({ alias: '彗星', canonical }));
const api = {
  getAliasSuggestions: async () => ({ suggestions }),
  getReadingAddon: async () => {
    if (fail) throw Error('temporary failure');
    return { installed: false, state };
  },
};
const moduleExports = {};
vm.runInNewContext(compiled, {
  exports: moduleExports,
  require: name => name === 'vue' ? {
    ref: value => ({ value }), computed: getter => ({ get value() { return getter(); } }),
    onScopeDispose() {}, watch() {}, nextTick: async () => {}, toRaw: value => value,
  } : { terminologyApi: api },
  setTimeout: (callback, delay) => {
    assert.equal(delay, 1000);
    timers.set(++nextTimer, callback);
    return nextTimer;
  },
  clearTimeout: id => timers.delete(id),
});

(async () => {
  const config = { value: { transcription: {}, terminology: { glossary_list: [] } } };
  const review = moduleExports.useTerminologySettings(config, {}, async () => {});
  await review.startSuggestionReview();
  assert.equal(review.readingAddon.value.installed, false);
  assert.equal(timers.size, 1);
  fail = true;
  const tick = [...timers.values()][0];
  timers.clear();
  tick();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(timers.size, 1);
  review.ignoreAliasSuggestion(suggestions[0]);
  assert.equal(review.aliasSuggestions.value.length, 1);
  assert.equal(review.aliasSuggestions.value[0].canonical, '流星');
  await review.refreshAliasSuggestions();
  assert.equal(review.aliasSuggestions.value.length, 1);
  config.value.terminology.ignored_alias_suggestions = [];
  await review.refreshAliasSuggestions();
  review.acceptAliasSuggestion(suggestions[0]);
  assert.equal(review.aliasSuggestions.value.length, 1);
  await review.refreshAliasSuggestions();
  assert.equal(review.aliasSuggestions.value.length, 1);
  assert.equal(review.aliasSuggestions.value[0].canonical, '流星');
  fail = false;
  state = 'idle';
  await review.refreshReadingAddon();
  assert.equal(timers.size, 0);
  state = 'installing';
  await review.refreshReadingAddon();
  assert.equal(timers.size, 1);
  review.stopSuggestionReview();
  assert.equal(timers.size, 0);
  await review.refreshReadingAddon();
  assert.equal(timers.size, 0);
  console.log('Terminology suggestions regressions passed');
})().catch(error => { console.error(error); process.exitCode = 1; });

