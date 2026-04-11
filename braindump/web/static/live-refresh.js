(function () {
  let lastLocalMutation = 0;
  document.addEventListener("htmx:beforeRequest", function (e) {
    const verb = (e.detail && e.detail.requestConfig && e.detail.requestConfig.verb || "get").toLowerCase();
    if (verb !== "get") lastLocalMutation = Date.now();
  });

  let debounceTimer = null;
  function scheduleReload() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(function () {
      const a = document.activeElement;
      if (a && (a.tagName === "INPUT" || a.tagName === "TEXTAREA" || a.isContentEditable)) {
        return;
      }
      if (Date.now() - lastLocalMutation < 1500) return;
      window.location.reload();
    }, 250);
  }

  const es = new EventSource("/events");
  es.addEventListener("change", scheduleReload);
})();
