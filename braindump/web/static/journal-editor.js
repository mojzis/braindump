(function () {
  "use strict";

  // "earlier days" toggle lives in the always-visible sticky toolbar so it's
  // reachable no matter how tall the editor grows. Wire it before the EasyMDE
  // guard below, so it works even if the editor library fails to load.
  var earlierBtn = document.getElementById("earlier-days-btn");
  var pastSection = document.getElementById("past-days-section");
  if (earlierBtn && pastSection) {
    earlierBtn.addEventListener("click", function () {
      var show = pastSection.hasAttribute("hidden");
      if (show) {
        pastSection.removeAttribute("hidden");
        pastSection.scrollIntoView({ behavior: "smooth", block: "start" });
      } else {
        pastSection.setAttribute("hidden", "");
      }
      earlierBtn.setAttribute("aria-expanded", show ? "true" : "false");
      earlierBtn.textContent = (show ? "▾" : "▸") + " earlier days";
    });
  }

  var ta = document.getElementById("journal-editor");
  if (!ta || typeof EasyMDE === "undefined") return;

  var day = document.currentScript.getAttribute("data-day");
  var todayForm = document.getElementById("today-editor-form");
  var parseForm = document.getElementById("parse-form");
  var dot = document.getElementById("autosave-dot");

  var mde = new EasyMDE({
    element: ta,
    toolbar: false,
    status: false,
    spellChecker: false,
    autofocus: true,
  });

  // Tint `[→type#id]` annotation marks in-editor via a tiny CM5 overlay mode.
  var CM = mde.codemirror.constructor;
  CM.defineMode("bd-refs", function (config) {
    return CM.overlayMode(CM.getMode(config, "gfm"), {
      token: function (stream) {
        if (stream.match(/\[→(todo|til|thought|prompt)#\d+\]/)) return "bd-ref";
        while (stream.next() != null) {
          if (stream.match(/\[→/, false)) break;
        }
        return null;
      },
    });
  });
  mde.codemirror.setOption("mode", "bd-refs");

  // EasyMDE swallows native `input` events on the textarea, so sync the
  // hidden textarea by hand and re-fire `input` to preserve the autosave
  // contract (`hx-trigger="input ... from:textarea"` on the surrounding form).
  mde.codemirror.on("change", function () {
    ta.value = mde.value();
    htmx.trigger(ta, "input");
  });

  function lock() {
    document.body.dataset.parseRunning = "1";
    mde.codemirror.setOption("readOnly", "nocursor");
  }

  function unlock() {
    delete document.body.dataset.parseRunning;
    fetch("/api/journal/" + day + "/body")
      .then(function (res) { return res.ok ? res.text() : null; })
      .then(function (text) {
        if (text !== null) {
          mde.value(text);
          ta.value = text;
        }
      })
      .finally(function () {
        mde.codemirror.setOption("readOnly", false);
      });
  }

  if (parseForm) parseForm.addEventListener("htmx:beforeRequest", lock);
  document.body.addEventListener("parse-done", unlock);

  document.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && parseForm && mde.codemirror.hasFocus()) {
      e.preventDefault();
      parseForm.requestSubmit();
    }
  });

  if (todayForm && dot) {
    var dotText = dot.querySelector(".autosave-text");
    var setDot = function (status, text) {
      dot.dataset.status = status;
      if (dotText) dotText.textContent = text;
    };
    setDot("idle", "");
    todayForm.addEventListener("htmx:beforeRequest", function () { setDot("saving", "saving…"); });
    todayForm.addEventListener("htmx:afterRequest", function () {
      setDot("saved", "saved");
      setTimeout(function () { setDot("idle", ""); }, 1600);
    });
  }
})();
