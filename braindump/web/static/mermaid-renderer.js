(function () {
  "use strict";

  let mermaidPromise;
  let initialized = false;
  let diagramNumber = 0;

  function loadMermaid() {
    if (window.mermaid) return Promise.resolve(window.mermaid);
    if (mermaidPromise) return mermaidPromise;

    mermaidPromise = new Promise(function (resolve, reject) {
      const script = document.createElement("script");
      script.src = "/static/vendor/mermaid-11.12.1.min.js";
      script.onload = function () { resolve(window.mermaid); };
      script.onerror = function () {
        reject(new Error("The Mermaid renderer could not be loaded."));
      };
      document.head.appendChild(script);
    });
    return mermaidPromise;
  }

  function showError(block, message) {
    const pre = block.parentElement;
    pre.classList.add("mermaid-error");
    if (pre.nextElementSibling &&
        pre.nextElementSibling.classList.contains("mermaid-error-message")) return;

    const notice = document.createElement("p");
    notice.className = "mermaid-error-message";
    notice.setAttribute("role", "alert");
    notice.textContent = message;
    pre.insertAdjacentElement("afterend", notice);
  }

  async function renderBlock(renderer, block) {
    block.dataset.mermaidProcessed = "true";
    const source = block.textContent;
    const valid = await renderer.parse(source, { suppressErrors: true });
    if (!valid) {
      showError(block, "Unable to render Mermaid diagram: check the diagram syntax.");
      return;
    }

    diagramNumber += 1;
    const result = await renderer.render("braindump-mermaid-" + diagramNumber, source);
    const container = document.createElement("div");
    container.className = "mermaid-diagram";
    container.setAttribute("role", "img");
    container.setAttribute("aria-label", "Mermaid diagram");
    container.innerHTML = result.svg;
    block.parentElement.replaceWith(container);
    if (result.bindFunctions) result.bindFunctions(container);
  }

  async function renderMermaid(root) {
    const blocks = Array.from(
      root.querySelectorAll("pre > code.language-mermaid:not([data-mermaid-processed])")
    );
    if (!blocks.length) return;

    let renderer;
    try {
      renderer = await loadMermaid();
      if (!initialized) {
        renderer.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          suppressErrorRendering: true,
          theme: "neutral",
        });
        initialized = true;
      }
    } catch (error) {
      blocks.forEach(function (block) { showError(block, error.message); });
      return;
    }

    for (const block of blocks) {
      try {
        await renderBlock(renderer, block);
      } catch (_error) {
        showError(block, "Unable to render Mermaid diagram: check the diagram syntax.");
      }
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderMermaid(document);
  });
  document.addEventListener("htmx:afterSwap", function (event) {
    renderMermaid(event.detail.target);
  });
})();
