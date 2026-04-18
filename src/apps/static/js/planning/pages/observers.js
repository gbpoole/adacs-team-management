(function () {
  var cfg = window.observersPageConfig || {};
  var labels = cfg.labels || {};

  function label(key, fallback) {
    return labels[key] || fallback;
  }

  function postAndReload(url, body, errorPrefix, errorMessage) {
    fetch(url, { method: "POST", body: body })
      .then(function (resp) {
        if (resp.ok) {
          window.location.reload();
        } else {
          alert(errorPrefix + " (status " + resp.status + "). Please try again.");
        }
      })
      .catch(function () {
        alert(errorMessage);
      });
  }

  window.openEditObserver = function (row) {
    var pk = row.dataset.pk;
    var projectPks = row.dataset.projects ? row.dataset.projects.split(",") : [];
    var streamPks = row.dataset.streams ? row.dataset.streams.split(",") : [];
    document.getElementById("edit-observer-id").value = pk;
    document.getElementById("edit-observer-name-heading").textContent = row.dataset.name || row.dataset.email;
    document.getElementById("edit-observer-email-subheading").textContent = row.dataset.email;

    var projSel = document.getElementById("edit-observer-projects");
    if (projSel) {
      Array.from(projSel.options).forEach(function (opt) {
        opt.selected = projectPks.indexOf(opt.value) !== -1;
      });
    }
    var streamSel = document.getElementById("edit-observer-streams");
    if (streamSel) {
      Array.from(streamSel.options).forEach(function (opt) {
        opt.selected = streamPks.indexOf(opt.value) !== -1;
      });
    }
    document.getElementById("observer-edit-form").action =
      "/planning/observers/" + pk + "/edit/";
    document.getElementById("observer-edit-modal").showModal();
  };

  window.confirmDeleteObserver = function () {
    var pk = document.getElementById("edit-observer-id").value;
    if (!pk || !confirm(label("removeConfirm", "Remove observer access?"))) {
      return;
    }
    document.getElementById("observer-edit-modal").close();
    var csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
    var body = new FormData();
    body.append("csrfmiddlewaretoken", csrf);
    postAndReload(
      "/planning/observers/" + pk + "/delete/",
      body,
      label("removeFailedStatus", "Remove failed"),
      label("removeFailed", "Remove failed. Please check your connection and try again."),
    );
  };

  function init() {
    var editForm = document.getElementById("observer-edit-form");
    if (editForm) {
      editForm.addEventListener("submit", function (event) {
        event.preventDefault();
        postAndReload(
          this.action,
          new FormData(this),
          label("saveFailedStatus", "Save failed"),
          label("saveFailed", "Save failed. Please check your connection and try again."),
        );
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
