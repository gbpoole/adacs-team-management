(function () {
  var cfg = window.planningPageConfig || {};
  var labels = cfg.labels || {};
  var urls = cfg.urls || {};

  function label(key, fallback) {
    return labels[key] || fallback;
  }

  function safeLocalStorageSet(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (_err) {
      // Ignore storage failures.
    }
  }

  function safeLocalStorageGet(key) {
    try {
      return localStorage.getItem(key);
    } catch (_err) {
      return null;
    }
  }

  function initFilterPersistence() {
    var form = document.getElementById("filter-form");
    if (!form) {
      return;
    }
    var storageKey = "planning_filter";
    var params = new URLSearchParams(window.location.search);
    var urlTags = params.getAll("tags");
    var urlStreams = params.getAll("streams");
    if (urlTags.length > 0 || urlStreams.length > 0) {
      safeLocalStorageSet(
        storageKey,
        JSON.stringify({ tags: urlTags, streams: urlStreams }),
      );
    } else {
      try {
        var saved = JSON.parse(safeLocalStorageGet(storageKey) || "null");
        if (
          saved
          && ((saved.tags && saved.tags.length > 0)
            || (saved.streams && saved.streams.length > 0))
        ) {
          var p = new URLSearchParams();
          (saved.tags || []).forEach(function (tag) {
            p.append("tags", tag);
          });
          (saved.streams || []).forEach(function (stream) {
            p.append("streams", stream);
          });
          window.location.replace(window.location.pathname + "?" + p.toString());
          return;
        }
      } catch (_err) {
        // Ignore invalid storage data.
      }
    }

    function submitFilter() {
      var tags = Array.from(
        form.querySelectorAll('input[name="tags"]:checked'),
      ).map(function (cb) {
        return cb.value;
      });
      var streams = Array.from(
        form.querySelectorAll('input[name="streams"]:checked'),
      ).map(function (cb) {
        return cb.value;
      });
      safeLocalStorageSet(
        storageKey,
        JSON.stringify({ tags: tags, streams: streams }),
      );
      form.submit();
    }

    form.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
      cb.addEventListener("change", submitFilter);
    });
    form.querySelectorAll("button[data-group]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var group = btn.dataset.group;
        var selectAll = btn.dataset.action === "all";
        form.querySelectorAll('input[name="' + group + '"]').forEach(function (cb) {
          cb.checked = selectAll;
        });
        submitFilter();
      });
    });
  }

  var weeks = cfg.weeks || [];
  var weekWidth = 64;
  var developerNames = cfg.developerNames || {};

  function reloadPreservingScroll() {
    // Scroll position is saved on pagehide and restored on load by the shared
    // scroll_persistence.js (the scroll container has data-scroll-preserve).
    window.location.reload();
  }

  function handleFetchResponse(resp) {
    if (resp.ok) {
      reloadPreservingScroll();
    } else {
      alert(label("operationFailed", "Operation failed") + " (status " + resp.status + "). Please try again.");
    }
  }

  function handleFetchError() {
    alert(label("networkError", "Network error. Please check your connection and try again."));
  }

  function isoToDate(iso) {
    var parts = iso.split("-").map(Number);
    return new Date(parts[0], parts[1] - 1, parts[2]);
  }

  function addDays(iso, days) {
    var d = isoToDate(iso);
    d.setDate(d.getDate() + days);
    return d.toISOString().split("T")[0];
  }

  function deletePhase(phaseId, closeModal) {
    if (!phaseId || !confirm(label("deletePhaseConfirm", "Delete this phase?"))) {
      return;
    }
    if (closeModal) {
      document.getElementById("phase-edit-modal").close();
    }
    var csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
    var body = new FormData();
    body.append("csrfmiddlewaretoken", csrf);
    fetch("/planning/phase/" + phaseId + "/delete/", { method: "POST", body: body })
      .then(handleFetchResponse)
      .catch(handleFetchError);
  }

  window.confirmDeletePhase = function () {
    deletePhase(document.getElementById("edit-phase-id").value, true);
  };

  window.confirmDeleteLeave = function () {
    var leaveId = document.getElementById("edit-leave-id").value;
    if (!leaveId || !confirm(label("deleteLeaveConfirm", "Delete this leave period?"))) {
      return;
    }
    document.getElementById("leave-edit-modal").close();
    var csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
    var body = new FormData();
    body.append("csrfmiddlewaretoken", csrf);
    fetch("/planning/leave/" + leaveId + "/delete/", { method: "POST", body: body })
      .then(handleFetchResponse)
      .catch(handleFetchError);
  };

  function siblingLeaveBars(leaveBar) {
    return Array.from(
      document.querySelectorAll('.leave-bar[data-leave-id="' + leaveBar.dataset.leaveId + '"]'),
    );
  }

  function initDeleteButtons() {
    document.addEventListener("click", function (event) {
      var btn = event.target.closest(".phase-delete-btn");
      if (!btn) {
        return;
      }
      event.stopPropagation();
      deletePhase(btn.dataset.phaseId, false);
    });
  }

  function initEditForms() {
    var leaveEditForm = document.getElementById("leave-edit-form");
    if (leaveEditForm) {
      leaveEditForm.addEventListener("submit", function (event) {
        event.preventDefault();
        fetch(this.action, { method: "POST", body: new FormData(this) })
          .then(handleFetchResponse)
          .catch(handleFetchError);
      });
    }

    var phaseEditForm = document.getElementById("phase-edit-form");
    if (phaseEditForm) {
      phaseEditForm.addEventListener("submit", function (event) {
        event.preventDefault();
        fetch(this.action, { method: "POST", body: new FormData(this) })
          .then(handleFetchResponse)
          .catch(handleFetchError);
      });
    }
  }

  function openPhaseEditModal(phaseBar) {
    var phaseForm = document.getElementById("phase-edit-form");
    phaseForm.action = "/planning/phase/" + phaseBar.dataset.phaseId + "/edit/";
    document.getElementById("edit-phase-id").value = phaseBar.dataset.phaseId;
    document.getElementById("edit-phase-developer").value = phaseBar.dataset.developerId;
    document.getElementById("edit-phase-project").value = phaseBar.dataset.projectId;
    document.getElementById("edit-phase-start-date").value = phaseBar.dataset.startDate;
    document.getElementById("edit-phase-end-date").value = phaseBar.dataset.endDate;
    document.getElementById("edit-phase-effort").value = phaseBar.dataset.effortMultiplier;
    document.getElementById("phase-edit-modal").showModal();
  }

  function openLeaveEditModal(leaveBar) {
    var leaveForm = document.getElementById("leave-edit-form");
    leaveForm.action = "/planning/leave/" + leaveBar.dataset.leaveId + "/update/";
    document.getElementById("edit-leave-id").value = leaveBar.dataset.leaveId;
    document.getElementById("leave-edit-start-date").value = leaveBar.dataset.startDate;
    document.getElementById("leave-edit-end-date").value = leaveBar.dataset.endDate;
    document.getElementById("leave-edit-modal").showModal();
  }

  var createMode = "phase";

  function setCreateMode(mode) {
    createMode = mode;
    var projectField = document.getElementById("create-project-field");
    var effortField = document.getElementById("create-effort-field");
    var submitBtn = document.getElementById("phase-create-submit");
    var togglePhase = document.getElementById("create-toggle-phase");
    var toggleLeave = document.getElementById("create-toggle-leave");
    var projectSelect = projectField.querySelector("select");
    var isLeave = mode === "leave";

    projectField.style.display = isLeave ? "none" : "";
    projectSelect.required = !isLeave;
    effortField.style.display = isLeave ? "none" : "";
    submitBtn.textContent = isLeave
      ? label("addLeave", "Add Leave")
      : label("addPhase", "Add Phase");

    togglePhase.classList.toggle("btn-primary", !isLeave);
    togglePhase.classList.toggle("btn-ghost", isLeave);
    toggleLeave.classList.toggle("btn-primary", isLeave);
    toggleLeave.classList.toggle("btn-ghost", !isLeave);
  }

  function initCreateModal() {
    var togglePhase = document.getElementById("create-toggle-phase");
    var toggleLeave = document.getElementById("create-toggle-leave");
    var createForm = document.getElementById("phase-create-form");
    if (!togglePhase || !toggleLeave || !createForm) {
      return;
    }

    togglePhase.addEventListener("click", function () {
      setCreateMode("phase");
    });
    toggleLeave.addEventListener("click", function () {
      setCreateMode("leave");
    });

    createForm.addEventListener("submit", function (event) {
      event.preventDefault();
      var body = new FormData(this);
      document.getElementById("phase-create-modal").close();
      var action = createMode === "leave" ? urls.leaveCreate : urls.phaseCreate;
      fetch(action, { method: "POST", body: body })
        .then(handleFetchResponse)
        .catch(handleFetchError);
    });
  }

  function initLeaveResize() {
    var resizing = null;
    var weekRects = [];

    function getColFromX(mouseX) {
      for (var i = weekRects.length - 1; i >= 0; i -= 1) {
        if (mouseX >= weekRects[i].left) {
          return i;
        }
      }
      return 0;
    }

    document.addEventListener("mousedown", function (event) {
      var handle = event.target.closest(".leave-resize-handle");
      if (!handle) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();

      var leaveBar = handle.closest(".leave-bar");
      var side = handle.classList.contains("leave-resize-right") ? "right" : "left";
      var table = leaveBar.closest("table");
      weekRects = Array.from(table.querySelectorAll("thead th"))
        .slice(1)
        .map(function (th) {
          return th.getBoundingClientRect();
        });

      resizing = {
        leaveBar: leaveBar,
        side: side,
        colStart: parseInt(leaveBar.dataset.colStart, 10),
        colEnd: parseInt(leaveBar.dataset.colEnd, 10),
      };
    });

    document.addEventListener("mousemove", function (event) {
      if (!resizing) {
        return;
      }
      var col = getColFromX(event.clientX);
      var leaveBar = resizing.leaveBar;
      var side = resizing.side;
      var colStart = resizing.colStart;
      var colEnd = resizing.colEnd;

      if (side === "right") {
        var newColEnd = Math.max(colStart, Math.min(col, weeks.length - 1));
        siblingLeaveBars(leaveBar).forEach(function (bar) {
          bar.style.width = (newColEnd - colStart + 1) * weekWidth + "px";
          bar.dataset.colEnd = newColEnd;
        });
      } else {
        var newColStart = Math.min(colEnd, Math.max(col, 0));
        siblingLeaveBars(leaveBar).forEach(function (bar) {
          bar.style.left = newColStart * weekWidth + "px";
          bar.style.width = (colEnd - newColStart + 1) * weekWidth + "px";
          bar.dataset.colStart = newColStart;
        });
      }
    });

    document.addEventListener("mouseup", function () {
      if (!resizing) {
        return;
      }
      var leaveBar = resizing.leaveBar;
      resizing = null;

      var newColStart = parseInt(leaveBar.dataset.colStart, 10);
      var newColEnd = parseInt(leaveBar.dataset.colEnd, 10);
      if (newColStart >= weeks.length || newColEnd < 0) {
        return;
      }

      var startDate = weeks[Math.max(0, newColStart)];
      var endDate = addDays(weeks[Math.min(weeks.length - 1, newColEnd)], 6);
      var csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
      var body = new FormData();
      body.append("csrfmiddlewaretoken", csrf);
      body.append("start_date", startDate);
      body.append("end_date", endDate);

      fetch("/planning/leave/" + leaveBar.dataset.leaveId + "/update/", { method: "POST", body: body })
        .then(handleFetchResponse)
        .catch(handleFetchError);
    });
  }

  function initLeaveMove() {
    var moving = null;
    var hasMoved = false;

    document.addEventListener("mousedown", function (event) {
      var leaveBar = event.target.closest(".leave-bar");
      if (!leaveBar || event.target.closest(".leave-resize-handle")) {
        return;
      }
      event.preventDefault();

      var table = leaveBar.closest("table");
      var wRects = Array.from(table.querySelectorAll("thead th"))
        .slice(1)
        .map(function (th) {
          return th.getBoundingClientRect();
        });
      var colStart = parseInt(leaveBar.dataset.colStart, 10);
      var colEnd = parseInt(leaveBar.dataset.colEnd, 10);

      hasMoved = false;
      moving = {
        leaveBar: leaveBar,
        span: colEnd - colStart + 1,
        origColStart: colStart,
        wRects: wRects,
        dragOffsetX: event.clientX - wRects[colStart].left,
      };
      document.body.style.cursor = "grabbing";
    });

    document.addEventListener("mousemove", function (event) {
      if (!moving) {
        return;
      }
      hasMoved = true;
      var anchorX = event.clientX - moving.dragOffsetX;
      var newCol = 0;
      for (var i = moving.wRects.length - 1; i >= 0; i -= 1) {
        if (anchorX >= moving.wRects[i].left) {
          newCol = i;
          break;
        }
      }
      newCol = Math.max(0, Math.min(newCol, moving.wRects.length - moving.span));
      siblingLeaveBars(moving.leaveBar).forEach(function (bar) {
        bar.style.left = newCol * weekWidth + "px";
        bar.dataset.colStart = newCol;
        bar.dataset.colEnd = newCol + moving.span - 1;
      });
    });

    document.addEventListener("mouseup", function () {
      if (!moving) {
        return;
      }
      var leaveBar = moving.leaveBar;
      var origColStart = moving.origColStart;
      var didMove = hasMoved;
      moving = null;
      hasMoved = false;
      document.body.style.cursor = "";

      if (!didMove) {
        openLeaveEditModal(leaveBar);
        return;
      }
      var newColStart = parseInt(leaveBar.dataset.colStart, 10);
      if (newColStart === origColStart) {
        return;
      }
      var newColEnd = parseInt(leaveBar.dataset.colEnd, 10);
      var startDate = weeks[Math.max(0, newColStart)];
      var endDate = addDays(weeks[Math.min(weeks.length - 1, newColEnd)], 6);
      var csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
      var body = new FormData();
      body.append("csrfmiddlewaretoken", csrf);
      body.append("start_date", startDate);
      body.append("end_date", endDate);

      fetch("/planning/leave/" + leaveBar.dataset.leaveId + "/update/", { method: "POST", body: body })
        .then(handleFetchResponse)
        .catch(handleFetchError);
    });
  }

  function initPhaseCreateDrag() {
    var dragging = false;
    var startCell = null;
    var startCol = null;
    var currentCol = null;
    var ghost = null;
    var weekRects = [];

    function getColFromX(mouseX) {
      for (var i = weekRects.length - 1; i >= 0; i -= 1) {
        if (mouseX >= weekRects[i].left) {
          return i;
        }
      }
      return 0;
    }

    function removeGhost() {
      if (ghost) {
        ghost.remove();
        ghost = null;
      }
    }

    document.addEventListener("mousedown", function (event) {
      var cell = event.target.closest(".timeline-cell");
      if (!cell) {
        return;
      }
      event.preventDefault();
      var table = cell.closest("table");
      weekRects = Array.from(table.querySelectorAll("thead th"))
        .slice(1)
        .map(function (th) {
          return th.getBoundingClientRect();
        });

      startCell = cell;
      startCol = getColFromX(event.clientX);
      currentCol = startCol;
      dragging = true;

      ghost = document.createElement("div");
      ghost.style.cssText = "position:absolute;top:1px;height:30px;"
        + "left:" + (startCol * weekWidth) + "px;width:" + weekWidth + "px;"
        + "z-index:12;pointer-events:none;border-radius:0.25rem;"
        + "background-color:color-mix(in oklch,var(--color-primary) 45%,transparent);"
        + "border:2px dashed color-mix(in oklch,var(--color-primary) 70%,transparent);"
        + "display:flex;align-items:center;padding:0 8px;"
        + "font-size:0.75rem;color:white;white-space:nowrap;overflow:hidden;";
      ghost.textContent = "+ New phase";
      cell.parentElement.appendChild(ghost);
    });

    document.addEventListener("mousemove", function (event) {
      if (!dragging || !ghost) {
        return;
      }
      currentCol = Math.max(0, Math.min(getColFromX(event.clientX), weeks.length - 1));
      var lo = Math.min(startCol, currentCol);
      var hi = Math.max(startCol, currentCol);
      ghost.style.left = lo * weekWidth + "px";
      ghost.style.width = (hi - lo + 1) * weekWidth + "px";
    });

    document.addEventListener("mouseup", function () {
      if (!dragging) {
        return;
      }
      dragging = false;

      var lo = Math.min(startCol, currentCol);
      var hi = Math.max(startCol, currentCol);
      removeGhost();

      var devId = startCell.dataset.developer;
      var lanePk = startCell.dataset.lanePk;
      var startDate = weeks[lo] || weeks[0];
      var endDate = hi < weeks.length
        ? addDays(weeks[hi], 6)
        : addDays(weeks[weeks.length - 1], 6);

      document.getElementById("phase-developer").value = devId;
      document.getElementById("phase-developer-display").textContent = developerNames[devId] || devId;
      document.getElementById("phase-lane-pk").value = lanePk || "";
      document.getElementById("phase-start-date").value = startDate;
      document.getElementById("phase-end-date").value = endDate;
      setCreateMode("phase");
      document.getElementById("phase-create-modal").showModal();

      startCell = null;
      startCol = null;
      currentCol = null;
    });
  }

  function initPhaseResize() {
    var resizing = null;
    var weekRects = [];

    function getColFromX(mouseX) {
      for (var i = weekRects.length - 1; i >= 0; i -= 1) {
        if (mouseX >= weekRects[i].left) {
          return i;
        }
      }
      return 0;
    }

    document.addEventListener("mousedown", function (event) {
      var handle = event.target.closest(".phase-resize-handle");
      if (!handle) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();

      var phaseBar = handle.closest(".phase-bar");
      var side = handle.classList.contains("phase-resize-right") ? "right" : "left";
      var table = phaseBar.closest("table");
      weekRects = Array.from(table.querySelectorAll("thead th"))
        .slice(1)
        .map(function (th) {
          return th.getBoundingClientRect();
        });

      resizing = {
        phaseBar: phaseBar,
        side: side,
        colStart: parseInt(phaseBar.dataset.colStart, 10),
        colEnd: parseInt(phaseBar.dataset.colEnd, 10),
      };
    });

    document.addEventListener("mousemove", function (event) {
      if (!resizing) {
        return;
      }
      var col = getColFromX(event.clientX);
      var phaseBar = resizing.phaseBar;
      var side = resizing.side;
      var colStart = resizing.colStart;
      var colEnd = resizing.colEnd;

      if (side === "right") {
        var newColEnd = Math.max(colStart, Math.min(col, weeks.length - 1));
        phaseBar.style.width = (newColEnd - colStart + 1) * weekWidth + "px";
        phaseBar.dataset.colEnd = newColEnd;
      } else {
        var newColStart = Math.min(colEnd, Math.max(col, 0));
        phaseBar.style.left = newColStart * weekWidth + "px";
        phaseBar.style.width = (colEnd - newColStart + 1) * weekWidth + "px";
        phaseBar.dataset.colStart = newColStart;
      }
    });

    document.addEventListener("mouseup", function () {
      if (!resizing) {
        return;
      }
      var phaseBar = resizing.phaseBar;
      resizing = null;

      var phaseId = phaseBar.dataset.phaseId;
      var newColStart = parseInt(phaseBar.dataset.colStart, 10);
      var newColEnd = parseInt(phaseBar.dataset.colEnd, 10);

      if (newColStart >= weeks.length || newColEnd < 0) {
        return;
      }
      var startDate = weeks[Math.max(0, newColStart)];
      var endDate = addDays(weeks[Math.min(weeks.length - 1, newColEnd)], 6);

      var csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
      var body = new FormData();
      body.append("csrfmiddlewaretoken", csrf);
      body.append("start_date", startDate);
      body.append("end_date", endDate);

      fetch("/planning/phase/" + phaseId + "/update/", { method: "POST", body: body })
        .then(handleFetchResponse)
        .catch(handleFetchError);
    });
  }

  function initPhaseMove() {
    var moving = null;
    var hasMoved = false;

    document.addEventListener("mousedown", function (event) {
      var phaseBar = event.target.closest(".phase-bar");
      if (
        !phaseBar
        || event.target.closest(".phase-resize-handle")
        || event.target.closest("button")
        || event.target.closest("form")
      ) {
        return;
      }
      event.preventDefault();

      var table = phaseBar.closest("table");
      var wRects = Array.from(table.querySelectorAll("thead th"))
        .slice(1)
        .map(function (th) {
          return th.getBoundingClientRect();
        });

      var colStart = parseInt(phaseBar.dataset.colStart, 10);
      var colEnd = parseInt(phaseBar.dataset.colEnd, 10);
      var origCanvas = phaseBar.closest(".lane-canvas");
      var origRow = phaseBar.closest("tr[data-lane-pk]");
      var origLanePk = origRow ? origRow.dataset.lanePk : null;

      var laneRows = Array.from(table.querySelectorAll("tr[data-lane-pk]")).map(function (tr) {
        return {
          pk: tr.dataset.lanePk,
          developerPk: tr.dataset.developerPk || null,
          canvas: tr.querySelector(".lane-canvas"),
          rect: tr.getBoundingClientRect(),
        };
      });

      hasMoved = false;
      moving = {
        phaseBar: phaseBar,
        span: colEnd - colStart + 1,
        origColStart: colStart,
        origLanePk: origLanePk,
        origCanvas: origCanvas,
        currentLanePk: origLanePk,
        currentDeveloperPk: null,
        wRects: wRects,
        laneRows: laneRows,
        dragOffsetX: event.clientX - wRects[colStart].left,
      };
      document.body.style.cursor = "grabbing";
    });

    document.addEventListener("mousemove", function (event) {
      if (!moving) {
        return;
      }
      hasMoved = true;

      var anchorX = event.clientX - moving.dragOffsetX;
      var newCol = 0;
      for (var i = moving.wRects.length - 1; i >= 0; i -= 1) {
        if (anchorX >= moving.wRects[i].left) {
          newCol = i;
          break;
        }
      }
      newCol = Math.max(0, Math.min(newCol, moving.wRects.length - moving.span));
      moving.phaseBar.style.left = newCol * weekWidth + "px";
      moving.phaseBar.dataset.colStart = newCol;
      moving.phaseBar.dataset.colEnd = newCol + moving.span - 1;

      var targetRow = null;
      moving.laneRows.forEach(function (lr) {
        if (!targetRow && event.clientY >= lr.rect.top && event.clientY < lr.rect.bottom) {
          targetRow = lr;
        }
      });

      if (targetRow) {
        if (targetRow.pk !== moving.currentLanePk && targetRow.canvas) {
          targetRow.canvas.appendChild(moving.phaseBar);
          moving.currentLanePk = targetRow.pk;
          moving.currentDeveloperPk = targetRow.developerPk;
        }
      } else if (moving.currentLanePk !== moving.origLanePk && moving.origCanvas) {
        moving.origCanvas.appendChild(moving.phaseBar);
        moving.currentLanePk = moving.origLanePk;
        moving.currentDeveloperPk = null;
      }
    });

    document.addEventListener("mouseup", function () {
      if (!moving) {
        return;
      }
      var state = moving;
      var didMove = hasMoved;
      moving = null;
      hasMoved = false;
      document.body.style.cursor = "";

      if (!didMove) {
        openPhaseEditModal(state.phaseBar);
        return;
      }

      var newColStart = parseInt(state.phaseBar.dataset.colStart, 10);
      var laneChanged = state.currentLanePk !== state.origLanePk;
      if (newColStart === state.origColStart && !laneChanged) {
        return;
      }

      var newColEnd = parseInt(state.phaseBar.dataset.colEnd, 10);
      var phaseId = state.phaseBar.dataset.phaseId;
      var startDate = weeks[Math.max(0, newColStart)];
      var endDate = addDays(weeks[Math.min(weeks.length - 1, newColEnd)], 6);
      var csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
      var body = new FormData();
      body.append("csrfmiddlewaretoken", csrf);
      body.append("start_date", startDate);
      body.append("end_date", endDate);
      if (laneChanged) {
        body.append("lane_pk", state.currentLanePk);
        if (state.currentLanePk === "new" && state.currentDeveloperPk) {
          body.append("developer_pk", state.currentDeveloperPk);
        }
      }

      fetch("/planning/phase/" + phaseId + "/update/", { method: "POST", body: body })
        .then(handleFetchResponse)
        .catch(handleFetchError);
    });
  }

  function initMyRowsFocus() {
    var btn = document.getElementById("focus-my-rows-btn");
    if (!btn) return;
    var container = document.getElementById("planning-scroll-container");
    var storageKey = "planning_focus_my_rows";
    var active = safeLocalStorageGet(storageKey) === "1";
    if (active && container) container.classList.add("focus-my-rows");
    updateFocusBtn(btn, active);
    btn.addEventListener("click", function () {
      active = !active;
      if (container) container.classList.toggle("focus-my-rows", active);
      safeLocalStorageSet(storageKey, active ? "1" : "0");
      updateFocusBtn(btn, active);
    });
  }

  function updateFocusBtn(btn, active) {
    btn.textContent = active ? "Show all rows" : "Focus my rows";
    btn.classList.toggle("btn-active", active);
  }

  function init() {
    initFilterPersistence();
    initMyRowsFocus();

    var closeCreateBtn = document.getElementById("close-phase-create-modal");
    if (closeCreateBtn) {
      closeCreateBtn.addEventListener("click", function () {
        var modal = document.getElementById("phase-create-modal");
        if (modal) {
          modal.close();
        }
      });
    }

    var confirmDeletePhaseBtn = document.getElementById("confirm-delete-phase");
    if (confirmDeletePhaseBtn) {
      confirmDeletePhaseBtn.addEventListener("click", function () {
        window.confirmDeletePhase();
      });
    }

    var closePhaseEditBtn = document.getElementById("close-phase-edit-modal");
    if (closePhaseEditBtn) {
      closePhaseEditBtn.addEventListener("click", function () {
        var modal = document.getElementById("phase-edit-modal");
        if (modal) {
          modal.close();
        }
      });
    }

    var confirmDeleteLeaveBtn = document.getElementById("confirm-delete-leave");
    if (confirmDeleteLeaveBtn) {
      confirmDeleteLeaveBtn.addEventListener("click", function () {
        window.confirmDeleteLeave();
      });
    }

    var closeLeaveEditBtn = document.getElementById("close-leave-edit-modal");
    if (closeLeaveEditBtn) {
      closeLeaveEditBtn.addEventListener("click", function () {
        var modal = document.getElementById("leave-edit-modal");
        if (modal) {
          modal.close();
        }
      });
    }

    initDeleteButtons();
    initEditForms();
    initCreateModal();
    initLeaveResize();
    initLeaveMove();
    initPhaseCreateDrag();
    initPhaseResize();
    initPhaseMove();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
