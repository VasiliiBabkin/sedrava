// Node.js smoke test of a generated Rust Web application.
// Uses a minimal DOM stub: no claim of real-browser compatibility yet.
'use strict';
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const file = process.argv[2];
if (!file) throw Error('Usage: node scripts/verify_native_web_node.js OUTPUT.html');
const html = fs.readFileSync(file, 'utf8');
const match = html.match(/<script>([\s\S]*?)<\/script>/);
if (!match) throw Error('Missing generated application script');
function build(dataset) {
  return {
    dataset, value: '', textContent: '', hidden: false, events: Object.create(null),
    addEventListener(event, cb) { this.events[event] = cb; }
  };
}
function nodes(attribute) {
  return [...html.matchAll(new RegExp(attribute + '="([^"]+)"', 'g'))]
    .map(m => build({[attribute.replace('data-', '').replace(/-([a-z])/g, (_, c) => c.toUpperCase())]: m[1]}));
}
const groups = {
  '[data-action]': nodes('data-action'),
  '[data-state]': nodes('data-state'),
  '[data-input]': nodes('data-input'),
  '[data-show]': nodes('data-show'),
  '[data-display]': [...html.matchAll(/data-display(?![-a-z])/g)].map(() => build({}))
};
const error = build({});
const document = {
  activeElement: null,
  getElementById(id) { return id === 'sedrava-error' ? error : null; },
  querySelectorAll(selector) { return groups[selector] || []; }
};
vm.runInNewContext(match[1], {document, console}, {timeout: 5000});
function output(name) {
  const el = groups['[data-state]'].find(e => e.dataset.state === name);
  if (!el) throw Error('Missing state output for ' + name);
  return el.textContent;
}
function action(name) {
  const el = groups['[data-action]'].find(e => e.dataset.action === name);
  if (!el) throw Error('Missing action: ' + name);
  assert.equal(typeof el.events.click, 'function');
  el.events.click();
}
assert.equal(output('count'), '0');
assert.equal(output('double'), '0');
assert.equal(groups['[data-show]'][0].hidden, true);
action('add');
assert.equal(output('count'), '1');
assert.equal(output('double'), '2');
assert.equal(groups['[data-show]'][0].hidden, false);
const count = groups['[data-input]'].find(e => e.dataset.input === 'count');
count.value = '-999';
count.events.change();
assert.equal(output('count'), '1');
assert.equal(error.hidden, false);
count.value = '4';
count.events.change();
assert.equal(output('count'), '4');
assert.equal(output('double'), '8');
action('reset');
assert.equal(output('count'), '0');
assert.equal(groups['[data-show]'][0].hidden, true);
const label = groups['[data-input]'].find(e => e.dataset.input === 'label');
label.value = '</script><img src=x onerror=alert(1)>';
label.events.change();
assert.equal(error.hidden, true);
assert.equal(label.value, '</script><img src=x onerror=alert(1)>');
console.log('PASS: native Web DOM smoke test, state, rules, input, show, safe text');
