// Synthetic browser-state checks only; does not create annotations or model data.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const html = fs.readFileSync(path.join(__dirname, 'semantic_label_template.html'), 'utf8');
const source = html.match(/<script>([\s\S]*)<\/script>/)[1]
  .replace('__FRAME_DATA__', JSON.stringify([
    {id: 'a', image: 'a.jpg'}, {id: 'b', image: 'b.jpg'}, {id: 'c', image: 'c.jpg'}
  ])).replace('__MANIFEST_SHA__', 'test-manifest');
const elements = {};
for (const id of ['frame', 'status', 'who', 'hand', 'no_hand', 'uncertain', 'load']) {
  elements[id] = {value: '', style: {}, disabled: false, addEventListener() {}};
}
Object.defineProperty(elements.frame, 'src', {
  set(value) { this._src = value; this.complete = false; this.naturalWidth = 0; },
  get() { return this._src; }
});
const finishLoad = () => {
  elements.frame.complete = true;
  elements.frame.naturalWidth = 640;
  elements.frame.onload();
};
const callbacks = {};
const alerts = [];
const context = vm.createContext({
  document: {
    getElementById: id => elements[id],
    addEventListener: (type, fn) => { callbacks[type] = fn; }
  },
  localStorage: {getItem: () => null, setItem() {}},
  alert: message => alerts.push(message)
});
vm.runInContext(source, context);
const value = expression => vm.runInContext(expression, context);
const key = (key, repeat = false, tagName = 'BODY') => callbacks.keydown({
  key, repeat, target: {tagName}, preventDefault() {}
});

(async () => {
  assert.equal(value('imageReady'), false);
  assert.equal(elements.hand.disabled, true);
  value("mark('hand')");
  assert.equal(value('Object.keys(labels).length'), 0, 'A loading image cannot be labelled');
  finishLoad();
  assert.equal(value('imageReady'), true);
  key('1', true);
  assert.equal(value('Object.keys(labels).length'), 0, 'Held-key repeat must be ignored');
  key('1', false, 'INPUT');
  assert.equal(value('Object.keys(labels).length'), 0, 'Typing a name must not label a frame');
  key('1');
  assert.equal(value('labels.a'), 'hand');
  assert.equal(value('index'), 1);
  assert.equal(value('imageReady'), false);
  key('2');
  assert.equal(value('labels.b'), undefined, 'Previous visible image cannot label the next ID');
  const oldLoad = elements.frame.onload;
  value('move(1)');
  elements.frame.onload();
  assert.equal(value('imageReady'), false, 'A queued event cannot enable an incomplete current image');
  oldLoad();
  assert.equal(value('imageReady'), false, 'An old load callback cannot enable a newer frame');
  elements.frame.onerror();
  key('3');
  assert.equal(value('labels.c'), undefined, 'Decode/load failure cannot receive a label');
  finishLoad();
  key('۳');
  assert.equal(value('labels.c'), 'uncertain', 'Persian numeric shortcuts work after load');
  assert.throws(() => value("validatedLabels([{id:'a',label:'hand'},{id:'a',label:'no_hand'}])"));
  assert.throws(() => value("validatedLabels([{id:'missing',label:'hand'}])"));
  assert.throws(() => value("validatedLabels([{id:'b',label:'made_up'}])"));
  const before = value('JSON.stringify(labels)');
  await elements.load.onchange({target: {files: [{text: async () => JSON.stringify({
    manifest_sha256: 'test-manifest', label_source: 'model', labels: [{id: 'b', label: 'hand'}]
  })}]}});
  assert.equal(value('JSON.stringify(labels)'), before, 'Non-human imports must not overwrite labels');
  assert.equal(alerts.length, 1);
  console.log('Synthetic UI checks passed: loading, stale callbacks, image errors, key repeat, label validation, and non-human import rejection.');
})().catch(error => {console.error(error); process.exitCode = 1;});
