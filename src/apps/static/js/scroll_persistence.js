// Preserve the scroll position of the main content across full-page reloads
// caused by write actions (add / edit / delete / migrate / etc.). Any element
// tagged with data-scroll-preserve has its scroll position saved on pagehide
// and restored on the next load of the same path.
(function () {
  function containers() {
    return document.querySelectorAll("[data-scroll-preserve]");
  }

  function storageKey() {
    return "scrollpos:" + window.location.pathname;
  }

  function save() {
    var els = containers();
    if (!els.length) {
      return;
    }
    var data = {};
    els.forEach(function (el, i) {
      data[i] = { top: el.scrollTop, left: el.scrollLeft };
    });
    try {
      sessionStorage.setItem(storageKey(), JSON.stringify(data));
    } catch (_err) {
      // Ignore storage failures.
    }
  }

  function restore() {
    var raw;
    try {
      raw = sessionStorage.getItem(storageKey());
    } catch (_err) {
      return;
    }
    if (!raw) {
      return;
    }
    try {
      sessionStorage.removeItem(storageKey());
    } catch (_err) {
      // Ignore storage failures.
    }
    var data;
    try {
      data = JSON.parse(raw);
    } catch (_err) {
      return;
    }
    // Defer to the next frame so the page has laid out and any native scroll
    // reset has already happened.
    requestAnimationFrame(function () {
      containers().forEach(function (el, i) {
        if (data[i]) {
          el.scrollTop = data[i].top;
          el.scrollLeft = data[i].left || 0;
        }
      });
    });
  }

  window.addEventListener("pagehide", save);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", restore);
  } else {
    restore();
  }
})();
