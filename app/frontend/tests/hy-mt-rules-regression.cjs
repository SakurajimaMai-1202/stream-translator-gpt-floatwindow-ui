// Run with: node tests/hy-mt-rules-regression.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(path.join(__dirname, '../src/utils/hyMtRules.ts'), 'utf8');
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
});
const rules = {};
vm.runInThisContext(`(function(exports) {\n${outputText}\n})`)(rules);
const { hyMtContextForcedOff, isHyMtForcedModelPath, hyMtMemoryOptionsAfterSwitch } = rules;

const small = 'Hy-MT3-1.8B';
const large = 'Hy-MT3-7B';
const hyMt2 = 'Hy-MT2-7B';
const index = 'Index-Translate';
const smallPath = 'C:\\models\\HY_MT3_1_8b-Q4.gguf';
const largePath = '/models/Hy-MT3-7B.gguf';
const local = { backend: 'llama', gpt_model: small };
const custom = { backend: 'custom:chosen', custom_models: [
  { name: 'other', model_name: large },
  { name: 'chosen', model_name: small },
] };

for (const provider of ['lm_studio', 'llama_cpp']) {
  const url = `hy_mt2_${provider}_url`;
  const model = `hy_mt2_${provider}_model`;
  const external = { ...local, hy_mt2_provider: provider, [url]: ' http://localhost ', [model]: ` ${small} ` };
  assert.equal(hyMtContextForcedOff('hy_mt2', external, [large], largePath), true, provider);
  assert.equal(hyMtContextForcedOff('hy_mt2', { ...external, [model]: large }, [small], smallPath), false, provider);
  assert.equal(hyMtContextForcedOff('hy_mt2', { ...external, [url]: ' ' }, [large], smallPath), false, `${provider}: empty URL falls back`);
  assert.equal(hyMtContextForcedOff('hy_mt2', { ...external, [model]: '' }, [small], largePath), true, `${provider}: empty model falls back`);
}

assert.equal(hyMtContextForcedOff('hy_mt2', local, [small, large], largePath), true, 'first served model wins');
assert.equal(hyMtContextForcedOff('hy_mt2', local, [large, small], smallPath), false, 'second served model is ignored');
assert.equal(hyMtContextForcedOff('hy_mt2', custom, [large], ''), false, 'served model wins over custom model');
for (const backend of ['llama', 'localllm']) {
  assert.equal(hyMtContextForcedOff('hy_mt2', { backend }, [], smallPath), true, backend);
  assert.equal(hyMtContextForcedOff('hy_mt2', { backend }, [], undefined, smallPath), true, 'selected path fallback');
  assert.equal(hyMtContextForcedOff('hy_mt2', { ...local, backend }, [], largePath, smallPath), false, 'configured path wins');
  assert.equal(hyMtContextForcedOff('hy_mt2', { backend }, [], `/models/${small}/${large}.gguf`), false, 'only the filename counts');
}
assert.equal(hyMtContextForcedOff('hy_mt2', { ...custom, gpt_model: large }, [], largePath), true, 'named custom model');
assert.equal(hyMtContextForcedOff('hy_mt2', { ...custom, backend: 'custom:other', gpt_model: small }, [], ''), false, 'custom model wins over GPT model');
assert.equal(hyMtContextForcedOff('hy_mt2', { ...custom, backend: 'custom:missing', gpt_model: small }, [], ''), true, 'missing custom model falls back');
assert.equal(hyMtContextForcedOff('hy_mt2', local, [], ''), true, 'GPT model fallback');
for (const model of [large, hyMt2, index]) {
  assert.equal(hyMtContextForcedOff('hy_mt2', { gpt_model: model }, [], ''), false, model);
}
assert.equal(hyMtContextForcedOff('index_translate', local, [small], smallPath), false, 'family gate');

assert.equal(isHyMtForcedModelPath('/models/Hy-MT.gguf'), true);
assert.equal(isHyMtForcedModelPath('C:\\models\\HY_MT2-7B.gguf'), true);
assert.equal(isHyMtForcedModelPath(smallPath), false);
assert.equal(isHyMtForcedModelPath(largePath), false);
assert.equal(isHyMtForcedModelPath('/models/Hy-MT2/Index-Translate.gguf'), false);

const automatic = { flash_attn: 'auto', no_mmap: false };
const forced = { flash_attn: 'off', no_mmap: true };
const userOn = { flash_attn: 'on', no_mmap: false };
assert.deepEqual(hyMtMemoryOptionsAfterSwitch(isHyMtForcedModelPath(hyMt2), false, userOn), forced);
assert.deepEqual(hyMtMemoryOptionsAfterSwitch(isHyMtForcedModelPath(smallPath), true, forced), automatic);
assert.deepEqual(hyMtMemoryOptionsAfterSwitch(false, true, { ...forced, flash_attn: 'on' }), userOn);
assert.deepEqual(hyMtMemoryOptionsAfterSwitch(false, true, { ...forced, no_mmap: false }), automatic);
assert.deepEqual(hyMtMemoryOptionsAfterSwitch(false, true, {}), { flash_attn: undefined, no_mmap: undefined });
assert.deepEqual(hyMtMemoryOptionsAfterSwitch(false, false, forced), forced);
assert.deepEqual(hyMtMemoryOptionsAfterSwitch(false, undefined, forced), forced);
assert.deepEqual(hyMtMemoryOptionsAfterSwitch(true, undefined, automatic), forced);

console.log('Hy-MT rules regression passed.');
