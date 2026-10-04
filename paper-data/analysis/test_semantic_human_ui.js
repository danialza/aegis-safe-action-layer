// Synthetic DOM/annotation-state checks. Never writes research labels or invokes models.
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const template = fs.readFileSync(path.join(__dirname, 'semantic_human_template.html'), 'utf8');
// Copy-only clarification must retain the existing stored category values.
assert.match(template, /خود دست چقدر دیده می‌شود؟/);
assert.match(template, /id="visibility" aria-describedby="visibilityHelp"/);
assert.match(template, /<option value="full">کامل دیده می‌شود<\/option>/);
assert.match(template, /<option value="partial">فقط بخشی دیده می‌شود<\/option>/);
assert.match(template, /<option value="uncertain">از این عکس مشخص نیست<\/option>/);
assert.match(template, /لازم نیست ساعد دیده شود/);
assert.match(template, /اگر چند دست هست، دیده‌شدنِ کاملِ یکی کافی است/);
const frames = ['a', 'b', 'c'].map(id => ({id, image: id + '.jpg'}));
const manifest = 'synthetic-manifest-not-research-data';
const source = template.match(/<script>([\s\S]*)<\/script>/)[1]
  .replace('__FRAME_DATA__', JSON.stringify(frames)).replace('__MANIFEST_SHA__', manifest);
const storageKey = 'aegis-human-426-' + manifest + '-main';
const stamp = '2026-09-24T20:00:00.000Z';
const clone = value => JSON.parse(JSON.stringify(value));

function row(id = 'a', label = 'hand') {
  return {id, label, cover: label === 'hand' ? 'glove' : null,
    visibility: label === 'hand' ? 'partial' : null, note: '', reviewed_at: stamp};
}
function payload(rows = [row()]) {
  return {schema_version: 'aegis-human-review-v1', label_source: 'human',
    review_manifest_sha256: manifest, annotator: 'Synthetic reviewer',
    prior_model_exposure: 'unsure', labels: rows, saved_at: stamp};
}
function harness(options = {}) {
  const elements = {}, documentCallbacks = {}, timers = [], downloads = [], blobs = [],
    revocations = [], opened = [], confirmationMessages = [];
  const storage = new Map(Object.entries(options.storage || {}));
  for (const match of template.matchAll(/\bid="([^"]+)"/g)) {
    const classes = new Set();
    elements[match[1]] = {value: '', textContent: '', disabled: false, hidden: false,
      style: {}, handlers: {}, classList: {toggle(name, enabled) {
        if (enabled) classes.add(name); else classes.delete(name);
      }, contains(name) { return classes.has(name); }},
      addEventListener(type, fn) { this.handlers[type] = fn; }, click() {}};
  }
  Object.defineProperty(elements.frame, 'src', {
    get() { return this._src; },
    set(value) { this._src = value; this.complete = false; this.naturalWidth = 0; }
  });
  class MockURL extends URL {
    static createObjectURL(blob) { blobs.push(blob); return 'blob:synthetic-' + blobs.length; }
    static revokeObjectURL(url) { revocations.push(url); }
  }
  class MockBlob { constructor(parts, config) { this.parts = parts; this.type = config.type; } }
  const document = {
    getElementById: id => { assert.ok(elements[id], 'Mock missing element: ' + id); return elements[id]; },
    addEventListener: (name, fn) => { documentCallbacks[name] = fn; },
    createElement: tag => {
      assert.equal(tag, 'a');
      return {click() { downloads.push({href: this.href, download: this.download}); }};
    }
  };
  const location = {search: options.search || '', href: 'http://127.0.0.1/synthetic.html' + (options.search || '')};
  const context = vm.createContext({document, location, URL: MockURL, URLSearchParams,
    Blob: MockBlob, crypto: {randomUUID: () => 'synthetic-independent-reviewer'},
    window: {open(...args) { opened.push(args); }},
    localStorage: {
      getItem(key) { return storage.get(key) || null; },
      setItem(key, value) { if (options.storageFails) throw Error('Synthetic storage failure'); storage.set(key, value); }
    },
    confirm(message) { confirmationMessages.push(message); return options.confirmResult !== false; },
    setTimeout(fn, delay) { timers.push({fn, delay}); return timers.length; }, console});
  vm.runInContext(source, context, {filename: 'semantic_human_template.inline.js'});
  const value = expression => vm.runInContext(expression, context);
  const json = expression => JSON.parse(value('JSON.stringify(' + expression + ')'));
  const key = (pressed, additions = {}) => {
    const event = {key: pressed, repeat: false, ctrlKey: false, altKey: false, metaKey: false,
      target: {tagName: 'BODY', isContentEditable: false}, prevented: false,
      preventDefault() { this.prevented = true; }, ...additions};
    documentCallbacks.keydown(event); return event;
  };
  const finishLoad = () => {
    elements.frame.complete = true; elements.frame.naturalWidth = 640; elements.frame.onload();
  };
  const identity = () => { elements.who.value = 'Synthetic reviewer'; elements.exposure.value = 'no'; };
  const snapshot = () => ({labels: json('labels'), index: value('index'), name: elements.who.value,
    exposure: elements.exposure.value, boundName: value('boundName'), boundExposure: value('boundExposure')});
  const upload = async data => elements.load.onchange({target: {files: [{text: async () =>
    typeof data === 'string' ? data : JSON.stringify(data)}]}});
  return {elements, value, json, key, finishLoad, identity, snapshot, upload, storage,
    timers, downloads, blobs, revocations, opened, confirmationMessages};
}

function testLoadAndIdentity() {
  const h = harness(), e = h.elements;
  assert.equal(h.value('imageReady'), false);
  for (const id of ['hand', 'no_hand', 'uncertain', 'submit']) assert.equal(e[id].disabled, true);
  h.identity(); h.value("choose('no_hand')");
  assert.equal(h.value('Object.keys(labels).length'), 0, 'Cannot label loading image');
  h.finishLoad(); e.who.value = ''; e.exposure.value = '';
  h.value("choose('no_hand')");
  assert.equal(h.value('Object.keys(labels).length'), 0, 'Identity is required');
  e.who.value = 'Synthetic reviewer'; h.value("choose('no_hand')");
  assert.equal(h.value('Object.keys(labels).length'), 0, 'Prior exposure declaration is required');
  assert.equal(h.value('exportPayload()'), null);
  h.identity(); h.key('1');
  assert.equal(h.value('Object.keys(labels).length'), 0, 'Hand choice alone is an uncommitted draft');
  assert.equal(e.conditionBox.hidden, false);
  h.value('commit()');
  assert.equal(h.value('Object.keys(labels).length'), 0, 'Cover and visibility must be explicit');
  e.cover.value = 'glove'; h.value('commit()');
  assert.equal(h.value('Object.keys(labels).length'), 0, 'Missing visibility cannot be guessed');
  e.visibility.value = 'partial'; e.note.value = 'Synthetic note'; h.value('commit()');
  assert.equal(h.value('labels.a.label'), 'hand');
  assert.equal(h.value('labels.a.cover'), 'glove');
  assert.equal(h.value('labels.a.visibility'), 'partial');
  assert.equal(h.value('labels.a.note'), 'Synthetic note');
  assert.equal(h.value('index'), 1);
  assert.equal(e.who.disabled, true); assert.equal(e.exposure.disabled, true);
  assert.equal(h.value('imageReady'), false, 'Next image must load before another label');
  h.finishLoad(); e.who.value = 'Different reviewer'; h.value("choose('no_hand')");
  assert.equal(h.value('labels.b'), undefined, 'Programmatic identity changes cannot mix reviewers');
  e.who.value = 'Synthetic reviewer'; e.exposure.value = 'yes'; h.value("choose('no_hand')");
  assert.equal(h.value('labels.b'), undefined, 'Exposure cannot be changed after annotation');
}

function testStaleImageAndKeys() {
  const h = harness(), e = h.elements;
  h.identity(); h.finishLoad();
  for (const tagName of ['INPUT', 'SELECT', 'TEXTAREA', 'BUTTON']) h.key('2', {target: {tagName}});
  for (const modifier of ['repeat', 'ctrlKey', 'metaKey', 'altKey']) h.key('2', {[modifier]: true});
  h.key('2', {target: {tagName: 'DIV', isContentEditable: true}});
  assert.equal(h.value('Object.keys(labels).length'), 0, 'Typing/repeat/modifiers cannot label');
  assert.equal(h.key('۲').prevented, true);
  assert.equal(h.value('labels.a.label'), 'no_hand');
  assert.equal(h.value('labels.a.cover'), null);
  const oldLoad = e.frame.onload, oldError = e.frame.onerror;
  h.value('move(1)');
  e.frame.onload();
  assert.equal(h.value('imageReady'), false, 'An incomplete current image is not ready');
  oldLoad();
  assert.equal(h.value('imageReady'), false, 'Old onload cannot enable new image');
  h.finishLoad(); oldError();
  assert.equal(h.value('imageReady'), true, 'Old error cannot disable successfully loaded current image');
  e.frame.onerror(); h.key('3');
  assert.equal(h.value('labels.c'), undefined, 'Image errors cannot receive labels');
  assert.equal(e.submit.disabled, true);
  h.finishLoad(); h.key('۳');
  assert.equal(h.value('labels.c.label'), 'uncertain');
  assert.equal(h.value('index'), 1, 'Next pending wraps to skipped image');
  assert.equal(h.value('imageReady'), false);
}

function testValidationAndAtomicImport() {
  const h = harness();
  h.value('importPayload(' + JSON.stringify(payload()) + ')');
  const before = h.snapshot();
  const invalid = [];
  for (const [field, value] of [['schema_version', 'other'], ['label_source', 'model'],
    ['review_manifest_sha256', 'other'], ['annotator', ' '], ['prior_model_exposure', 'unknown'],
    ['saved_at', 'yesterday'], ['labels', {}]]) {
    const d = payload(); d[field] = value; invalid.push(d);
  }
  invalid.push(payload([row(), row()]));
  for (const patch of [{id: 'unknown'}, {label: 'model_safe'}, {cover: 'synthetic'},
    {visibility: 'hidden'}, {cover: null}, {reviewed_at: 'bad-date'}, {note: 4}, {note: 'x'.repeat(2001)}]) {
    invalid.push(payload([{...row(), ...patch}]));
  }
  invalid.push(payload([{...row('b', 'no_hand'), cover: 'glove'}]));
  invalid.push(payload([{...row('b', 'uncertain'), visibility: 'partial'}]));
  for (const d of invalid) {
    assert.throws(() => h.value('importPayload(' + JSON.stringify(d) + ')'));
    assert.deepEqual(h.snapshot(), before, 'Invalid import must preserve all prior state');
  }
  for (const cover of ['bare', 'glove', 'mixed', 'uncertain']) {
    for (const visibility of ['full', 'partial', 'uncertain']) {
      assert.doesNotThrow(() => h.value('validatedPayload(' + JSON.stringify(payload([{...row(), cover, visibility}])) + ')'));
    }
  }
  assert.doesNotThrow(() => h.value('validatedPayload(' + JSON.stringify(payload([row('a', 'no_hand'), row('b', 'uncertain')])) + ')'));
}

async function testFileImport() {
  const h = harness({confirmResult: false});
  h.value('importPayload(' + JSON.stringify(payload()) + ')');
  const before = h.snapshot();
  await h.upload({...payload(), label_source: 'model'});
  assert.deepEqual(h.snapshot(), before);
  assert.equal(h.confirmationMessages.length, 0, 'Reject model output before asking to overwrite');
  await h.upload('{broken JSON'); assert.deepEqual(h.snapshot(), before);
  await h.upload(payload([row('b', 'no_hand')]));
  assert.equal(h.confirmationMessages.length, 1);
  assert.deepEqual(h.snapshot(), before, 'Cancelled import preserves progress');
  const fresh = harness();
  await fresh.upload(payload([row('b', 'no_hand')]));
  assert.equal(fresh.value('labels.b.label'), 'no_hand');
  assert.equal(fresh.value('index'), 0);
  assert.equal(fresh.elements.exposure.value, 'unsure');
  assert.equal(fresh.elements.who.disabled, true);
}

function testCompletionExportAndResume() {
  const h = harness(); h.identity();
  for (let i = 0; i < frames.length; i++) { h.finishLoad(); h.value("choose('no_hand')"); }
  assert.equal(h.value('Object.keys(labels).length'), 3);
  assert.equal(h.elements.progress.value, 3);
  assert.match(h.elements.message.textContent, /همهٔ تصاویر/);
  assert.match(h.elements.message.textContent, /JSON/);
  const exported = h.json('exportPayload()');
  assert.equal(exported.label_source, 'human');
  assert.equal(exported.review_manifest_sha256, manifest);
  assert.equal(exported.prior_model_exposure, 'no');
  assert.deepEqual(exported.labels.map(x => x.id), ['a', 'b', 'c']);
  h.value('save()');
  assert.equal(h.downloads.length, 1);
  assert.match(h.downloads[0].download, /^human_review_426_.*\.json$/);
  const file = JSON.parse(h.blobs[0].parts.join(''));
  assert.equal(file.labels.length, 3);
  assert.equal(h.revocations.length, 0, 'Blob URL must survive browser download dispatch');
  assert.equal(h.timers[0].delay, 1000); h.timers[0].fn();
  assert.deepEqual(h.revocations, ['blob:synthetic-1']);
  const resumed = harness({storage: Object.fromEntries(h.storage)});
  assert.deepEqual(resumed.json('labels'), h.json('labels'));
  assert.equal(resumed.elements.who.value, 'Synthetic reviewer');
  assert.equal(resumed.elements.exposure.value, 'no');
  assert.equal(resumed.elements.who.disabled, true);
  assert.equal(resumed.value('imageReady'), false, 'Resume still requires current image to load');
  h.value('newReviewer()');
  assert.equal(h.opened.length, 1);
  assert.match(h.opened[0][0], /reviewer=synthetic-independent-reviewer/);
  assert.equal(h.opened[0][2], 'noopener');
  const independent = harness({search: '?reviewer=synthetic-independent-reviewer', storage: Object.fromEntries(h.storage)});
  assert.equal(independent.value('Object.keys(labels).length'), 0, 'Independent reviewers have separate storage');
}

function testStorageFailureAndCorruption() {
  const failed = harness({storageFails: true}); failed.identity(); failed.finishLoad();
  failed.value("choose('uncertain')");
  assert.equal(failed.value('labels.a.label'), 'uncertain', 'Storage failure does not invent or drop in-memory labels');
  assert.match(failed.elements.backupStatus.textContent, /انجام نشد/);
  const corrupt = harness({storage: {[storageKey]: JSON.stringify({index: 0,
    labels: {a: row('b')}, annotator: 'Synthetic reviewer', exposure: 'no'})}});
  assert.equal(corrupt.value('Object.keys(labels).length'), 0);
  assert.match(corrupt.elements.message.textContent, /بازیابی مرورگر ناموفق/);
  const noIdentity = harness({storage: {[storageKey]: JSON.stringify({index: 0,
    labels: {a: row()}, annotator: '', exposure: 'no'})}});
  assert.equal(noIdentity.value('Object.keys(labels).length'), 0, 'Unattributed stored labels cannot silently resume');
}

(async () => {
  testLoadAndIdentity();
  testStaleImageAndKeys();
  testValidationAndAtomicImport();
  await testFileImport();
  testCompletionExportAndResume();
  testStorageFailureAndCorruption();
  console.log('Synthetic human-review UI checks passed: identity/exposure, hand conditions, load races, stale events, image errors, keyboard guards, strict atomic human imports, completion, export, localStorage, and independent reviewer isolation.');
})().catch(error => {console.error(error); process.exitCode = 1;});
