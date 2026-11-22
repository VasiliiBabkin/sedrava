"use strict";
const fs = require("node:fs");
const vm = require("node:vm");
const assert = require("node:assert/strict");

const html = fs.readFileSync(process.argv[2], "utf8");
const match = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(match, "inline script is present");

const elements = new Map();
function element(tag) {
  return {
    tag,
    children: [],
    textContent: "",
    handlers: {},
    replaceChildren() { this.children = []; },
    appendChild(child) { this.children.push(child); },
    addEventListener(event, handler) { this.handlers[event] = handler; }
  };
}
for (const id of ["title", "app", "error"]) elements.set(id, element(id));
const document = {
  getElementById(id) { return elements.get(id); },
  createElement: element
};
const sandbox = vm.createContext({ document });
vm.runInContext(match[1], sandbox, { timeout: 1000 });
function readState() { return vm.runInContext("state.count", sandbox); }
function action(name) {
  vm.runInContext("runAction(" + JSON.stringify(name) + ")", sandbox);
}
assert.equal(readState(), 0, "initial state");
assert.equal(elements.get("app").children.length, 5, "counter widgets");
action("decrement");
assert.equal(readState(), 0, "invariant rollback");
assert.match(elements.get("error").textContent, /rule rejected/);
action("increment");
action("increment");
assert.equal(readState(), 2, "accepted actions");
assert.equal(elements.get("error").textContent, "");
assert.equal(elements.get("app").children[1].textContent, "2", "rerendered value");
const add = elements.get("app").children[2];
assert.equal(add.tag, "button");
add.handlers.click();
assert.equal(readState(), 3, "button triggers compiled action");
action("reset");
assert.equal(readState(), 0, "reset");
console.log("PASS independent Web IR JS state/rules/buttons");

