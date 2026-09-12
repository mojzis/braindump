const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(
  path.join(__dirname, "..", "braindump", "web", "static", "mermaid-renderer.js"),
  "utf8",
);

function classList(element) {
  return {
    add(name) {
      const names = new Set((element.className || "").split(/\s+/).filter(Boolean));
      names.add(name);
      element.className = Array.from(names).join(" ");
    },
    contains(name) {
      return (element.className || "").split(/\s+/).includes(name);
    },
  };
}

function element(tagName) {
  const node = {
    tagName: tagName.toUpperCase(),
    className: "",
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = value; },
  };
  node.classList = classList(node);
  return node;
}

function mermaidBlock(source) {
  const pre = element("pre");
  const block = element("code");
  block.dataset = {};
  block.textContent = source;
  block.parentElement = pre;
  pre.nextElementSibling = null;
  pre.insertAdjacentElement = (_position, notice) => {
    pre.nextElementSibling = notice;
  };
  pre.replaceWith = (replacement) => {
    pre.replacement = replacement;
  };
  return { block, pre };
}

function root(blocks) {
  return {
    queries: [],
    querySelectorAll(selector) {
      this.queries.push(selector);
      return blocks.map(({ block }) => block);
    },
  };
}

function harness(initialBlocks = []) {
  const listeners = new Map();
  const document = root(initialBlocks);
  document.head = { appendChild() {} };
  document.createElement = element;
  document.addEventListener = (type, handler) => listeners.set(type, handler);

  const initialized = [];
  const rendered = [];
  const renderer = {
    initialize(options) { initialized.push(options); },
    async parse(source) { return !source.includes("Broken -->"); },
    async render(id, source) {
      rendered.push({ id, source });
      return { svg: `<svg id="${id}"></svg>` };
    },
  };
  vm.runInNewContext(script, { Array, document, Error, Promise, window: { mermaid: renderer } });

  return {
    document,
    initialized,
    listeners,
    rendered,
    async dispatch(type, target = document, detailTarget = target) {
      listeners.get(type)({ target, detail: { target: detailTarget } });
      await new Promise((resolve) => setImmediate(resolve));
    },
  };
}

test("renders multiple valid diagrams and preserves an invalid source fallback", async () => {
  const first = mermaidBlock("flowchart LR\nA --> B");
  const second = mermaidBlock("sequenceDiagram\nA->>B: hello");
  const invalid = mermaidBlock("flowchart LR\nBroken -->");
  const page = harness([first, second, invalid]);

  await page.dispatch("DOMContentLoaded");

  assert.equal(page.rendered.length, 2);
  assert.notEqual(page.rendered[0].id, page.rendered[1].id);
  assert.equal(first.pre.replacement.className, "mermaid-diagram");
  assert.equal(second.pre.replacement.className, "mermaid-diagram");
  assert.equal(invalid.pre.replacement, undefined);
  assert.equal(invalid.pre.classList.contains("mermaid-error"), true);
  assert.equal(invalid.pre.nextElementSibling.attributes.role, "alert");
  assert.match(invalid.pre.nextElementSibling.textContent, /check the diagram syntax/);
  assert.equal(invalid.block.textContent, "flowchart LR\nBroken -->");
  assert.equal(page.initialized[0].securityLevel, "strict");
});

test("htmx outerHTML swap scans the inserted event target", async () => {
  const inserted = mermaidBlock("flowchart LR\nLater --> Page");
  const insertedRoot = root([inserted]);
  const detachedTarget = root([]);
  const page = harness();

  await page.dispatch("htmx:afterSwap", insertedRoot, detachedTarget);

  assert.equal(insertedRoot.queries.length, 1);
  assert.equal(detachedTarget.queries.length, 0);
  assert.equal(inserted.pre.replacement.className, "mermaid-diagram");
});
