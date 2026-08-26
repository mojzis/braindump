(function () {
  "use strict";

  // Getting text *out* of the app. `bd app` runs this UI in a pywebview window,
  // which has no right-click menu and — on the Qt backend — no JS clipboard
  // access until `web/desktop.py` grants it. This is the in-page half of that
  // fix, and it's what makes copy work even when the native half couldn't:
  //
  //   * `[data-copy-from]` / `[data-copy-url]` buttons copy a whole entry or
  //     journal day without selecting anything first;
  //   * a ⌘/ctrl+C fallback finishes the copy when the webview's own copy
  //     handler never fires. In a real browser it stays dormant — the native
  //     `copy` event lands first and the fallback stands down.

  var FEEDBACK_MS = 1200;
  // Long enough for a native copy to land first, short enough that the
  // fallback still beats the user to their next paste.
  var NATIVE_COPY_GRACE_MS = 120;

  function selectionText() {
    var el = document.activeElement;
    // Selection inside a form field is invisible to window.getSelection().
    if (el && typeof el.selectionStart === "number" && typeof el.value === "string") {
      return el.value.slice(el.selectionStart, el.selectionEnd);
    }
    return String(window.getSelection());
  }

  function execCopy(text) {
    // Pre-async-clipboard fallback. It copies by selecting a throwaway
    // textarea, so put the user's own selection and focus back afterwards.
    var selection = window.getSelection();
    var ranges = [];
    for (var i = 0; i < selection.rangeCount; i++) ranges.push(selection.getRangeAt(i));
    var focused = document.activeElement;

    var scratch = document.createElement("textarea");
    scratch.value = text;
    scratch.setAttribute("readonly", "");
    scratch.style.position = "fixed";
    scratch.style.opacity = "0";
    document.body.appendChild(scratch);
    scratch.select();
    var copied;
    try {
      copied = document.execCommand("copy");
    } catch (err) {
      copied = false;
    }
    document.body.removeChild(scratch);

    selection.removeAllRanges();
    ranges.forEach(function (range) { selection.addRange(range); });
    if (focused && typeof focused.focus === "function") focused.focus();
    return copied;
  }

  function copy(text) {
    if (!text) return Promise.reject(new Error("nothing to copy"));
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(function (err) {
        if (!execCopy(text)) throw err;
      });
    }
    return execCopy(text) ? Promise.resolve() : Promise.reject(new Error("copy blocked"));
  }

  // --- copy buttons ---------------------------------------------------------

  function sourceText(btn) {
    if (btn.dataset.copyUrl) {
      return fetch(btn.dataset.copyUrl).then(function (res) {
        if (!res.ok) throw new Error("copy source returned " + res.status);
        return res.text();
      });
    }
    var el = btn.dataset.copyFrom && document.querySelector(btn.dataset.copyFrom);
    if (!el) return Promise.reject(new Error("no copy source"));
    // A <script type="application/json"> holds markdown the page renders as
    // HTML elsewhere; everything else is either a field or plain text.
    if (el.tagName === "SCRIPT") return Promise.resolve(JSON.parse(el.textContent));
    if (typeof el.value === "string") return Promise.resolve(el.value);
    return Promise.resolve(el.innerText);
  }

  function flash(btn, message) {
    var original = btn.dataset.copyLabel || btn.textContent;
    btn.dataset.copyLabel = original;
    btn.textContent = message;
    clearTimeout(btn.copyTimer);
    btn.copyTimer = setTimeout(function () { btn.textContent = original; }, FEEDBACK_MS);
  }

  // Delegated, so buttons in lazily loaded journal days work without rebinding.
  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-copy-from], [data-copy-url]");
    if (!btn) return;
    e.preventDefault();
    sourceText(btn)
      .then(copy)
      .then(function () { flash(btn, "copied ✓"); })
      .catch(function () { flash(btn, "copy failed"); });
  });

  // --- ⌘/ctrl+C fallback ----------------------------------------------------

  var nativeCopied = false;
  document.addEventListener("copy", function () { nativeCopied = true; }, true);

  document.addEventListener("keydown", function (e) {
    if (e.altKey || !(e.ctrlKey || e.metaKey)) return;
    if (e.key !== "c" && e.key !== "C") return;
    var text = selectionText();
    if (!text) return;
    nativeCopied = false;
    setTimeout(function () {
      if (!nativeCopied) copy(text).catch(function () {});
    }, NATIVE_COPY_GRACE_MS);
  });
})();
