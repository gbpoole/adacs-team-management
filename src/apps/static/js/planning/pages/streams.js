(function () {
  var cfg = window.streamsPageConfig || {};

  window.submitAddStream = function () {
    var form = document.getElementById("add-stream-form");
    if (!form) { return; }
    var nameInput = form.querySelector('input[name="name"]');
    if (nameInput) {
      var name = nameInput.value.trim();
      if (!name) { alert("Name is required."); return; }
      if (name.indexOf("||") !== -1 || name.indexOf("\t") !== -1) {
        alert("Name may not contain '||' or tab characters.");
        return;
      }
    }
    form.submit();
  };

  window.PlanningColourEntityEditor.init({
    labels: cfg.labels || {},
    entityPath: "streams",
    formId: "edit-stream-form",
    editModalId: "edit-stream-modal",
    editNameInputId: "edit-stream-name",
    addSwatchesId: "add-colour-swatches",
    editSwatchesId: "edit-colour-swatches",
    openFunctionName: "openEditStream",
    confirmDeleteFunctionName: "confirmDeleteStream",
    defaultDeleteConfirm: "Delete this stream?",
    addModalId: "add-stream-modal",
  });
})();
