(function () {
  var cfg = window.streamsPageConfig || {};
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
  });
})();
