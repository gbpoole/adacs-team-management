(function () {
  var cfg = window.streamsPageConfig || {};

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

  var openAddModalBtn = document.getElementById("open-add-stream-modal");
  if (openAddModalBtn) {
    openAddModalBtn.addEventListener("click", function () {
      var modal = document.getElementById("add-stream-modal");
      if (modal) {
        modal.showModal();
      }
    });
  }

  document.querySelectorAll(".js-edit-stream-row").forEach(function (row) {
    row.addEventListener("click", function () {
      window.openEditStream(row);
    });
  });

  var closeAddModalBtn = document.getElementById("close-add-stream-modal");
  if (closeAddModalBtn) {
    closeAddModalBtn.addEventListener("click", function () {
      var modal = document.getElementById("add-stream-modal");
      if (modal) {
        modal.close();
      }
    });
  }

  var closeEditModalBtn = document.getElementById("close-edit-stream-modal");
  if (closeEditModalBtn) {
    closeEditModalBtn.addEventListener("click", function () {
      var modal = document.getElementById("edit-stream-modal");
      if (modal) {
        modal.close();
      }
    });
  }

  var confirmDeleteBtn = document.getElementById("confirm-delete-stream");
  if (confirmDeleteBtn) {
    confirmDeleteBtn.addEventListener("click", function () {
      window.confirmDeleteStream();
    });
  }

  var addForm = document.getElementById("add-stream-form");
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
