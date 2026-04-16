(function () {
  var cfg = window.tagsPageConfig || {};
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

  function initColourSwatches(containerId) {
    document
      .querySelectorAll("#" + containerId + ' input[type="radio"]')
      .forEach(function (radio) {
        var swatch = radio.nextElementSibling;

        function sync() {
          swatch.style.outline = radio.checked ? "2px solid currentColor" : "none";
          swatch.style.outlineOffset = radio.checked ? "2px" : "0";
        }

        sync();
        radio.addEventListener("change", function () {
          document
            .querySelectorAll("#" + containerId + " .colour-swatch")
            .forEach(function (el) {
              el.style.outline = "none";
            });
          swatch.style.outline = "2px solid currentColor";
          swatch.style.outlineOffset = "2px";
        });
      });
  }

  function selectColourSwatch(containerId, hex) {
    document
      .querySelectorAll("#" + containerId + ' input[type="radio"]')
      .forEach(function (radio) {
        radio.checked = radio.value === hex;
        var swatch = radio.nextElementSibling;
        swatch.style.outline = radio.checked ? "2px solid currentColor" : "none";
        swatch.style.outlineOffset = radio.checked ? "2px" : "0";
      });
  }

  window.openEditTag = function (row) {
    var pk = row.dataset.pk;
    document.getElementById("edit-tag-name").value = row.dataset.name;
    document.getElementById("edit-tag-form").action = "/planning/tags/" + pk + "/edit/";
    document.getElementById("edit-tag-form").dataset.pk = pk;
    selectColourSwatch("edit-colour-swatches", row.dataset.colour);
    document.getElementById("edit-tag-modal").showModal();
  };

  window.confirmDeleteTag = function () {
    var pk = document.getElementById("edit-tag-form").dataset.pk;
    if (!pk || !confirm(label("deleteConfirm", "Delete this tag?"))) {
      return;
    }
    document.getElementById("edit-tag-modal").close();
    var csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
    var body = new FormData();
    body.append("csrfmiddlewaretoken", csrf);
    postAndReload(
      "/planning/tags/" + pk + "/delete/",
      body,
      label("deleteFailedStatus", "Delete failed"),
      label("deleteFailed", "Delete failed."),
    );
  };

  document.addEventListener("DOMContentLoaded", function () {
    initColourSwatches("add-colour-swatches");
    initColourSwatches("edit-colour-swatches");

    var editForm = document.getElementById("edit-tag-form");
    if (editForm) {
      editForm.addEventListener("submit", function (event) {
        event.preventDefault();
        postAndReload(
          this.action,
          new FormData(this),
          label("saveFailedStatus", "Save failed"),
          label("saveFailed", "Save failed."),
        );
      });
    }
  });
})();
