(function () {
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

  window.PlanningColourEntityEditor = {
    init: function (opts) {
      var form = document.getElementById(opts.formId);
      var editModal = document.getElementById(opts.editModalId);
      var labels = opts.labels || {};

      function label(key, fallback) {
        return labels[key] || fallback;
      }

      initColourSwatches(opts.addSwatchesId);
      initColourSwatches(opts.editSwatchesId);

      window[opts.openFunctionName] = function (row) {
        var pk = row.dataset.pk;
        document.getElementById(opts.editNameInputId).value = row.dataset.name;
        form.action = "/planning/" + opts.entityPath + "/" + pk + "/edit/";
        form.dataset.pk = pk;
        selectColourSwatch(opts.editSwatchesId, row.dataset.colour);
        editModal.showModal();
      };

      window[opts.confirmDeleteFunctionName] = function () {
        var pk = form.dataset.pk;
        if (!pk || !confirm(label("deleteConfirm", opts.defaultDeleteConfirm))) {
          return;
        }
        editModal.close();
        var csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
        var body = new FormData();
        body.append("csrfmiddlewaretoken", csrf);
        postAndReload(
          "/planning/" + opts.entityPath + "/" + pk + "/delete/",
          body,
          label("deleteFailedStatus", "Delete failed"),
          label("deleteFailed", "Delete failed."),
        );
      };

      form.addEventListener("submit", function (event) {
        event.preventDefault();
        postAndReload(
          this.action,
          new FormData(this),
          label("saveFailedStatus", "Save failed"),
          label("saveFailed", "Save failed."),
        );
      });
    },
  };
})();
