(function () {
  var cfg = window.tagsPageConfig || {};
  window.PlanningColourEntityEditor.init({
    labels: cfg.labels || {},
    entityPath: "tags",
    formId: "edit-tag-form",
    editModalId: "edit-tag-modal",
    editNameInputId: "edit-tag-name",
    addSwatchesId: "add-colour-swatches",
    editSwatchesId: "edit-colour-swatches",
    openFunctionName: "openEditTag",
    confirmDeleteFunctionName: "confirmDeleteTag",
    defaultDeleteConfirm: "Delete this tag?",
  });
})();
