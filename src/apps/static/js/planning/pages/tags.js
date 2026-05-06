(function () {
  var cfg = window.tagsPageConfig || {};

  function isValidName(name) {
    if (!name) {
      alert("Name is required.");
      return false;
    }
    if (name.indexOf("||") !== -1 || name.indexOf("\t") !== -1) {
      alert("Name may not contain '||' or tab characters.");
      return false;
    }
    return true;
  }

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

  var openAddModalBtn = document.getElementById("open-add-tag-modal");
  if (openAddModalBtn) {
    openAddModalBtn.addEventListener("click", function () {
      var modal = document.getElementById("add-tag-modal");
      if (modal) {
        modal.showModal();
      }
    });
  }

  document.querySelectorAll(".js-edit-tag-row").forEach(function (row) {
    row.addEventListener("click", function () {
      window.openEditTag(row);
    });
  });

  var closeAddModalBtn = document.getElementById("close-add-tag-modal");
  if (closeAddModalBtn) {
    closeAddModalBtn.addEventListener("click", function () {
      var modal = document.getElementById("add-tag-modal");
      if (modal) {
        modal.close();
      }
    });
  }

  var closeEditModalBtn = document.getElementById("close-edit-tag-modal");
  if (closeEditModalBtn) {
    closeEditModalBtn.addEventListener("click", function () {
      var modal = document.getElementById("edit-tag-modal");
      if (modal) {
        modal.close();
      }
    });
  }

  var confirmDeleteBtn = document.getElementById("confirm-delete-tag");
  if (confirmDeleteBtn) {
    confirmDeleteBtn.addEventListener("click", function () {
      window.confirmDeleteTag();
    });
  }

  var addForm = document.getElementById("add-tag-form");
  if (addForm) {
    addForm.addEventListener("submit", function (event) {
      var nameInput = addForm.querySelector('input[name="name"]');
      var name = nameInput ? nameInput.value.trim() : "";
      if (!isValidName(name)) {
        event.preventDefault();
      }
    });
  }
})();
