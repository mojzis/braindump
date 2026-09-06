const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(
  path.join(__dirname, "..", "braindump", "web", "static", "shortcuts.js"),
  "utf8",
);

function event(type, target, options = {}) {
  return {
    type,
    target,
    key: options.key,
    ctrlKey: options.ctrlKey || false,
    metaKey: options.metaKey || false,
    altKey: options.altKey || false,
    defaultPrevented: false,
    preventDefault() { this.defaultPrevented = true; },
  };
}

function harness() {
  const listeners = new Map();
  const elements = {};
  const document = {
    activeElement: null,
    body: { tagName: "BODY", isContentEditable: false },
    addEventListener(type, handler) { listeners.set(type, handler); },
    getElementById(id) { return elements[id]; },
    querySelector() { return null; },
    dispatchEvent(e) { listeners.get(e.type)(e); },
  };

  function element(tagName, properties = {}) {
    const handlers = new Map();
    return {
      tagName,
      isContentEditable: false,
      addEventListener(type, handler) { handlers.set(type, handler); },
      dispatchEvent(e) { handlers.get(e.type)(e); },
      focus() { document.activeElement = this; },
      ...properties,
    };
  }

  elements.shortcuts = element("DIALOG", {
    open: false,
    close() { this.open = false; },
    showModal() { this.open = true; },
  });
  elements["entry-jump-form"] = element("FORM");
  elements["entry-jump-id"] = element("INPUT", { value: "" });

  const window = { location: "" };
  vm.runInNewContext(script, {
    clearTimeout() {},
    document,
    encodeURIComponent,
    setTimeout() { return 1; },
    window,
  });

  return {
    document,
    input: elements["entry-jump-id"],
    window,
    press(key, target = document.body, options = {}) {
      const e = event("keydown", target, { key, ...options });
      document.dispatchEvent(e);
      return e;
    },
    submit() {
      const e = event("submit", elements["entry-jump-form"]);
      elements["entry-jump-form"].dispatchEvent(e);
      return e;
    },
    control(tagName, properties = {}) {
      return element(tagName, properties);
    },
  };
}

test("g i focuses the entry ID control", () => {
  const page = harness();

  page.press("g");
  const secondKey = page.press("i");

  assert.equal(page.document.activeElement, page.input);
  assert.equal(secondKey.defaultPrevented, true);
});

test("typing controls and modifier keys do not trigger g i", async (t) => {
  for (const tagName of ["INPUT", "TEXTAREA", "SELECT"]) {
    await t.test(tagName, () => {
      const page = harness();
      const control = page.control(tagName);

      page.press("g", control);
      page.press("i", control);

      assert.equal(page.document.activeElement, null);
    });
  }

  await t.test("contenteditable", () => {
    const page = harness();
    const control = page.control("DIV", { isContentEditable: true });

    page.press("g", control);
    page.press("i", control);

    assert.equal(page.document.activeElement, null);
  });

  for (const modifier of ["ctrlKey", "metaKey", "altKey"]) {
    await t.test(modifier, () => {
      const page = harness();

      page.press("g", page.document.body, { [modifier]: true });
      page.press("i");

      assert.equal(page.document.activeElement, null);
    });
  }
});

test("a modifier cancels an already pending g sequence", () => {
  const page = harness();

  page.press("g");
  page.press("i", page.document.body, { ctrlKey: true });
  page.press("i");

  assert.equal(page.document.activeElement, null);
});

test("submitting an entry ID navigates to its detail page", () => {
  const page = harness();
  page.input.value = "211";

  const submit = page.submit();

  assert.equal(submit.defaultPrevented, true);
  assert.equal(page.window.location, "/entries/211");
});

test("g l navigates to the TIL list", () => {
  const page = harness();

  page.press("g");
  const secondKey = page.press("l");

  assert.equal(secondKey.defaultPrevented, true);
  assert.equal(page.window.location, "/tils");
});
