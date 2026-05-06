(function () {
  function initSemesterSwitch() {
    var select = document.getElementById("semester-switch-select");
    var form = document.getElementById("semester-switch-form");
    if (!select || !form) {
      return;
    }
    select.addEventListener("change", function () {
      form.submit();
    });
  }

  function initSemesterModalButtons() {
    var openBtn = document.getElementById("open-add-semester-modal");
    if (openBtn) {
      openBtn.addEventListener("click", function () {
        var modal = document.getElementById("add-semester-modal");
        if (modal) {
          modal.showModal();
        }
      });
    }

    var closeBtn = document.getElementById("close-add-semester-modal");
    if (closeBtn) {
      closeBtn.addEventListener("click", function () {
        var modal = document.getElementById("add-semester-modal");
        if (modal) {
          modal.close();
        }
      });
    }
  }

  function init() {
    initSemesterSwitch();
    initSemesterModalButtons();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
