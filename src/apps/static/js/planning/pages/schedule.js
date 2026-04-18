(function () {
  function safeLocalStorageSet(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (_err) {
      // Ignore storage failures.
    }
  }

  function safeLocalStorageGet(key) {
    try {
      return localStorage.getItem(key);
    } catch (_err) {
      return null;
    }
  }

  function initFilterPersistence() {
    var form = document.getElementById("filter-form");
    if (!form) {
      return;
    }

    var storageKey = "schedule_filter";
    var params = new URLSearchParams(window.location.search);
    var urlTags = params.getAll("tags");
    var urlStreams = params.getAll("streams");

    if (urlTags.length > 0 || urlStreams.length > 0) {
      safeLocalStorageSet(
        storageKey,
        JSON.stringify({ tags: urlTags, streams: urlStreams }),
      );
    } else {
      try {
        var saved = JSON.parse(safeLocalStorageGet(storageKey) || "null");
        if (
          saved
          && ((saved.tags && saved.tags.length > 0)
            || (saved.streams && saved.streams.length > 0))
        ) {
          var savedParams = new URLSearchParams();
          (saved.tags || []).forEach(function (tag) {
            savedParams.append("tags", tag);
          });
          (saved.streams || []).forEach(function (stream) {
            savedParams.append("streams", stream);
          });
          window.location.replace(
            window.location.pathname + "?" + savedParams.toString(),
          );
          return;
        }
      } catch (_err) {
        // Ignore invalid storage data.
      }
    }

    function submitFilter() {
      var tags = Array.from(form.querySelectorAll('input[name="tags"]:checked')).map(
        function (cb) {
          return cb.value;
        },
      );
      var streams = Array.from(
        form.querySelectorAll('input[name="streams"]:checked'),
      ).map(function (cb) {
        return cb.value;
      });
      safeLocalStorageSet(
        storageKey,
        JSON.stringify({ tags: tags, streams: streams }),
      );
      form.submit();
    }

    form.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
      cb.addEventListener("change", submitFilter);
    });
    form.querySelectorAll("button[data-group]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var group = btn.dataset.group;
        var selectAll = btn.dataset.action === "all";
        form.querySelectorAll('input[name="' + group + '"]').forEach(function (cb) {
          cb.checked = selectAll;
        });
        submitFilter();
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initFilterPersistence);
  } else {
    initFilterPersistence();
  }
})();
