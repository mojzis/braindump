(function () {
  const DIALOG = document.getElementById("shortcuts");
  const ENTRY_JUMP_FORM = document.getElementById("entry-jump-form");
  const ENTRY_JUMP_INPUT = document.getElementById("entry-jump-id");
  let gPending = false;
  let gTimer = null;

  function cancelGSequence() {
    gPending = false;
    clearTimeout(gTimer);
  }

  function isTyping(e) {
    const t = e.target;
    return t && (
      t.tagName === "INPUT"
      || t.tagName === "TEXTAREA"
      || t.tagName === "SELECT"
      || t.isContentEditable
    );
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      if (DIALOG.open) DIALOG.close();
      return;
    }
    if (isTyping(e)) {
      cancelGSequence();
      return;
    }
    // Don't hijack native shortcuts like Ctrl/⌘+C (copy), Ctrl+R, etc.
    if (e.ctrlKey || e.metaKey || e.altKey) {
      cancelGSequence();
      return;
    }
    if (e.key === "?") { e.preventDefault(); DIALOG.showModal(); return; }
    if (e.key === "c") { e.preventDefault(); window.location = "/capture"; return; }
    if (e.key === "/") {
      const s = document.querySelector('input[name="q"]');
      if (s) { e.preventDefault(); s.focus(); return; }
    }
    if (e.key === "g") {
      gPending = true;
      clearTimeout(gTimer);
      gTimer = setTimeout(function () { gPending = false; }, 800);
      return;
    }
    if (gPending) {
      cancelGSequence();
      if (e.key === "i") {
        e.preventDefault();
        ENTRY_JUMP_INPUT.focus();
        return;
      }
      const map = { d: "/", j: "/journal", t: "/todos", l: "/tils", c: "/capture", e: "/entries", p: "/projects", a: "/tags" };
      if (map[e.key]) { e.preventDefault(); window.location = map[e.key]; }
    }
  });

  ENTRY_JUMP_FORM.addEventListener("submit", function (e) {
    e.preventDefault();
    const entryId = ENTRY_JUMP_INPUT.value.trim();
    if (entryId) window.location = "/entries/" + encodeURIComponent(entryId);
  });
})();
