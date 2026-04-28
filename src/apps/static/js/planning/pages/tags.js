(function () {
  var cfg = window.tagsPageConfig || {};

  window.submitAddTag = function () {
    var form = document.getElementById("add-tag-form");
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
    entityPath: "tags",
    formId: "edit-tag-form",
    editModalId: "edit-tag-modal",
    editNameInputId: "edit-tag-name",
    addSwatchesId: "add-colour-swatches",
    editSwatchesId: "edit-colour-swatches",
    openFunctionName: "openEditTag",
    confirmDeleteFunctionName: "confirmDeleteTag",
    defaultDeleteConfirm: "Delete this tag?",
    addModalId: "add-tag-modal",
  });
})();
