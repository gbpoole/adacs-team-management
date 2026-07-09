(function () {
  var cfg = window.projectPageConfig || {};
  var labels = cfg.labels || {};
  var continuationData = cfg.continuationData || {};
  var timeEntriesData = cfg.timeEntriesData || {};
  var canEdit = Boolean(cfg.canEdit);
  var hasMigrateSemesters = Boolean(cfg.hasMigrateSemesters);

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
    var storageKey = "projects_filter";
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
          var savedParams = new URLSearchParams();
          (saved.tags || []).forEach(function (tag) {
            savedParams.append("tags", tag);
          });
          (saved.streams || []).forEach(function (stream) {
            savedParams.append("streams", stream);
          });
          window.location.replace(
            window.location.pathname + "?" + savedParams.toString(),
          );
          return;
        }
      } catch (_err) {
        // Ignore bad localStorage data.
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

  var sortCol = "name";
  var sortAsc = true;

  function applyProjSort() {
    var tbody = document.querySelector("#proj-table tbody");
    if (!tbody) {
      return;
    }
    var rows = Array.from(tbody.querySelectorAll("tr[data-sort-name]"));
    rows.sort(function (a, b) {
      var key = "sort" + sortCol.charAt(0).toUpperCase() + sortCol.slice(1);
      var av = a.dataset[key] || "";
      var bv = b.dataset[key] || "";
      if (sortCol === "name") {
        return sortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
      }
      var cmp;
      var an = parseFloat(av);
      var bn = parseFloat(bv);
      if (av === "" && bv === "") {
        cmp = 0;
      } else if (av === "") {
        cmp = 1;
      } else if (bv === "") {
        cmp = -1;
      } else {
        cmp = an - bn;
      }
      return sortAsc ? cmp : -cmp;
    });
    rows.forEach(function (row) {
      tbody.appendChild(row);
    });
    document.querySelectorAll("#proj-table th[data-col]").forEach(function (th) {
      var icon = th.querySelector(".sort-icon");
      if (!icon) {
        return;
      }
      if (th.dataset.col === sortCol) {
        icon.textContent = sortAsc ? "▲" : "▼";
        icon.classList.remove("text-neutral-400");
      } else {
        icon.textContent = "⇅";
        icon.classList.add("text-neutral-400");
      }
    });
    safeLocalStorageSet(
      "projects_sort",
      JSON.stringify({ col: sortCol, asc: sortAsc }),
    );
  }

  window.sortProjTable = function (col) {
    if (sortCol === col) {
      sortAsc = !sortAsc;
    } else {
      sortCol = col;
      sortAsc = col === "name";
    }
    applyProjSort();
  };

  function initSort() {
    try {
      var saved = JSON.parse(safeLocalStorageGet("projects_sort") || "null");
      if (saved && saved.col) {
        sortCol = saved.col;
        sortAsc = saved.asc;
      }
    } catch (_err) {
      // Ignore invalid JSON.
    }
    applyProjSort();
  }

  function initCheckboxButtons(containerId) {
    document
      .querySelectorAll("#" + containerId + ' input[type="checkbox"]')
      .forEach(function (cb) {
        var labelEl = cb.closest("label");

        function sync() {
          labelEl.classList.toggle("btn-primary", cb.checked);
          labelEl.classList.toggle("btn-outline", !cb.checked);
        }

        sync();
        cb.addEventListener("change", sync);
      });
  }

  function addCheckboxButton(containerId, fieldName, name, isDynamic) {
    if (!name) {
      return;
    }
    var container = document.getElementById(containerId);
    if (!container) {
      return;
    }
    var safeName = name.replace(/"/g, "\\\"");
    var existing = container.querySelector(
      'input[name="' + fieldName + '"][value="' + safeName + '"]',
    );
    if (existing) {
      existing.checked = true;
      existing.dispatchEvent(new Event("change"));
      return;
    }

    var labelEl = document.createElement("label");
    labelEl.className = "btn btn-sm btn-primary cursor-pointer";
    if (isDynamic) { labelEl.dataset.dynamic = "true"; }
    var cb = document.createElement("input");
    cb.type = "checkbox";
    cb.name = fieldName;
    cb.value = name;
    cb.checked = true;
    cb.className = "hidden";
    cb.addEventListener("change", function () {
      labelEl.classList.toggle("btn-primary", cb.checked);
      labelEl.classList.toggle("btn-outline", !cb.checked);
    });
    labelEl.appendChild(cb);
    labelEl.appendChild(document.createTextNode(name));
    container.appendChild(labelEl);
  }

  function validateNameInput(name, kind) {
    if (name.indexOf("||") !== -1 || name.indexOf("\t") !== -1) {
      alert(kind + " name may not contain '||' or tab characters.");
      return false;
    }
    return true;
  }

  window.projAddStream = function () {
    var input = document.getElementById("proj-new-stream");
    if (!input) { return; }
    var name = input.value.trim();
    if (!validateNameInput(name, "Stream")) { return; }
    addCheckboxButton("proj-stream-buttons", "streams", name, true);
    input.value = "";
    input.focus();
  };

  window.projAddTag = function () {
    var input = document.getElementById("proj-new-tag");
    if (!input) { return; }
    var name = input.value.trim();
    if (!validateNameInput(name, "Tag")) { return; }
    addCheckboxButton("proj-tag-buttons", "tags", name, true);
    input.value = "";
    input.focus();
  };

  // PK of the continuation_of project currently set on the project being edited.
  // Used to keep the currently-linked project in the dropdown even if already_linked.
  var currentEditContOfPk = null;
  // PK of the project currently open in the edit modal (self-filtered from the
  // continuation dropdown and used by the time-entries modal).
  var currentEditProjectPk = null;

  function updateContProjects(semSelectId, projSelectId) {
    var semSel = document.getElementById(semSelectId);
    var projSel = document.getElementById(projSelectId);
    if (!semSel || !projSel) {
      return;
    }
    var semPk = semSel.value;
    var isEditModal = semSelectId === "edit-cont-semester";
    var placeholder = label("selectProject", "- select project -");
    projSel.innerHTML = '<option value="">' + placeholder + "</option>";
    if (semPk && continuationData[semPk]) {
      continuationData[semPk].forEach(function (project) {
        // A project cannot continue itself.
        if (isEditModal && String(project.pk) === String(currentEditProjectPk)) {
          return;
        }
        // Filter out projects already linked to another continuation,
        // unless this is the edit modal and it's the currently-set target.
        if (project.already_linked) {
          if (!isEditModal || String(project.pk) !== String(currentEditContOfPk)) {
            return;
          }
        }
        var option = document.createElement("option");
        option.value = project.pk;
        option.textContent = project.name;
        projSel.appendChild(option);
      });
      projSel.disabled = false;
    } else {
      projSel.disabled = true;
    }
  }

  window.updateAddContProjects = function () {
    updateContProjects("add-cont-semester", "add-cont-project");
  };

  window.editProjAddStream = function () {
    var input = document.getElementById("edit-proj-new-stream");
    if (!input) { return; }
    var name = input.value.trim();
    if (!validateNameInput(name, "Stream")) { return; }
    addCheckboxButton("edit-proj-stream-buttons", "streams", name);
    input.value = "";
    input.focus();
  };

  window.editProjAddTag = function () {
    var input = document.getElementById("edit-proj-new-tag");
    if (!input) { return; }
    var name = input.value.trim();
    if (!validateNameInput(name, "Tag")) { return; }
    addCheckboxButton("edit-proj-tag-buttons", "tags", name);
    input.value = "";
    input.focus();
  };

  window.updateEditContProjects = function () {
    updateContProjects("edit-cont-semester", "edit-cont-project");
    var hidden = document.getElementById("edit-cont-value");
    var projSel = document.getElementById("edit-cont-project");
    if (hidden && projSel) hidden.value = projSel.value;
  };

  window.syncEditContHidden = function () {
    var hidden = document.getElementById("edit-cont-value");
    var projSel = document.getElementById("edit-cont-project");
    if (hidden && projSel) hidden.value = projSel.value;
  };

  window.openEditProject = function (row) {
    if (!canEdit || !row) {
      return;
    }
    var pk = row.dataset.pk;
    var streams = row.dataset.streams ? row.dataset.streams.split(",") : [];
    var tags = row.dataset.tags ? row.dataset.tags.split(",") : [];
    var devLeadPk = row.dataset.devLeadPk || "";
    var sciLeadPk = row.dataset.scienceLeadPk || "";
    var contOfPk = row.dataset.continuationOfPk || "";
    currentEditProjectPk = pk;

    document.getElementById("edit-project-id").value = pk;
    document.getElementById("edit-project-name-heading").textContent = row.dataset.name;
    document.getElementById("edit-project-name").value = row.dataset.name;
    document.getElementById("edit-project-effort").value = row.dataset.effortNew;

    var carryoverNote = document.getElementById("edit-carryover-note");
    if (carryoverNote) {
      var carry = parseFloat(row.dataset.carryover || "0") || 0;
      carryoverNote.textContent = carry === 0
        ? ""
        : label("carriedOver", "Carried over:") + " " + carry + " " + label("weeks", "wks");
    }
    var timeEntriesBtn = document.getElementById("open-time-entries");
    if (timeEntriesBtn) {
      var entryCount = row.dataset.timeEntryCount || "0";
      timeEntriesBtn.textContent = label("nonDevTime", "Non-dev time") + " (" + entryCount + ")";
    }

    document
      .querySelectorAll('#edit-proj-stream-buttons input[type="checkbox"]')
      .forEach(function (cb) {
        cb.checked = streams.indexOf(cb.value) !== -1;
        cb.dispatchEvent(new Event("change"));
      });
    document
      .querySelectorAll('#edit-proj-tag-buttons input[type="checkbox"]')
      .forEach(function (cb) {
        cb.checked = tags.indexOf(cb.value) !== -1;
        cb.dispatchEvent(new Event("change"));
      });

    document.getElementById("edit-dev-lead").value = devLeadPk;
    document.getElementById("edit-science-lead").value = sciLeadPk;

    var editContSem = document.getElementById("edit-cont-semester");
    var editContProj = document.getElementById("edit-cont-project");
    var editContHidden = document.getElementById("edit-cont-value");
    if (editContSem && editContProj) {
      // Record which project is already the continuation target so the
      // already_linked filter allows it to stay visible in the dropdown.
      currentEditContOfPk = contOfPk || null;
      editContSem.value = "";
      editContProj.innerHTML = '<option value="">' + label("selectProject", "— None —") + "</option>";
      editContProj.disabled = true;
      if (editContHidden) editContHidden.value = "";
      if (contOfPk) {
        var foundSemPk = null;
        Object.keys(continuationData).forEach(function (semPk) {
          continuationData[semPk].forEach(function (project) {
            if (String(project.pk) === String(contOfPk)) {
              foundSemPk = semPk;
            }
          });
        });
        if (foundSemPk) {
          editContSem.value = foundSemPk;
          window.updateEditContProjects();  // populates list, syncs hidden to ""
          editContProj.value = contOfPk;
          if (editContHidden) editContHidden.value = contOfPk;  // sync after pre-select
        }
      }
    }

    var editUrl = "/planning/projects/" + pk + "/edit/";
    var editForm = document.getElementById("project-edit-form");
    if (editForm) {
      editForm.action = editUrl;
    }
    var deleteForm = document.getElementById("project-delete-form");
    if (deleteForm) {
      deleteForm.action = "/planning/projects/" + pk + "/delete/";
    }
    document.getElementById("project-edit-modal").showModal();
  };

  window.confirmRemoveProject = function () {
    var pk = document.getElementById("edit-project-id").value;
    if (!pk || !confirm(label("removeConfirm", "Remove project?"))) {
      return;
    }
    var deleteForm = document.getElementById("project-delete-form");
    if (!deleteForm) {
      return;
    }
    document.getElementById("project-edit-modal").close();
    deleteForm.submit();
  };

  function renderTimeEntriesList(pk) {
    var container = document.getElementById("time-entries-list");
    if (!container) {
      return;
    }
    var entries = timeEntriesData[String(pk)] || [];
    if (entries.length === 0) {
      container.innerHTML = '<div class="p-3 text-sm text-neutral-400">'
        + label("noTimeEntries", "No entries yet.")
        + "</div>";
      return;
    }
    container.innerHTML = entries
      .map(function (entry) {
        return '<div class="flex items-center gap-2 px-3 py-2">'
          + '<span class="text-sm font-medium w-16 text-right shrink-0">' + entry.weeks + " " + label("weeks", "wks") + "</span>"
          + '<span class="flex-1 text-sm text-neutral-600">' + escapeHtml(entry.comment) + "</span>"
          + '<button type="button" class="btn btn-ghost btn-xs text-error js-delete-time-entry" data-entry-pk="' + entry.pk + '">'
          + escapeHtml(label("deleteLabel", "Delete"))
          + "</button>"
          + "</div>";
      })
      .join("");
    container.querySelectorAll(".js-delete-time-entry").forEach(function (btn) {
      btn.addEventListener("click", function () {
        window.deleteTimeEntry(btn.dataset.entryPk);
      });
    });
  }

  window.openTimeEntriesModal = function () {
    var pk = currentEditProjectPk;
    var modal = document.getElementById("time-entries-modal");
    if (!pk || !modal) {
      return;
    }
    var heading = document.getElementById("time-entries-heading");
    var nameInput = document.getElementById("edit-project-name");
    if (heading && nameInput) {
      heading.textContent = label("nonDevTime", "Non-dev time") + " — " + nameInput.value;
    }
    var addForm = document.getElementById("time-entry-add-form");
    if (addForm) {
      addForm.action = (cfg.urls.timeEntryAdd || "").replace("/0/", "/" + pk + "/");
      addForm.reset();
    }
    renderTimeEntriesList(pk);
    modal.showModal();
  };

  window.deleteTimeEntry = function (entryPk) {
    if (!entryPk || !confirm(label("timeEntryDeleteConfirm", "Delete this time entry?"))) {
      return;
    }
    var deleteForm = document.getElementById("time-entry-delete-form");
    if (!deleteForm) {
      return;
    }
    deleteForm.action = (cfg.urls.timeEntryDelete || "").replace("/0/", "/" + entryPk + "/");
    deleteForm.submit();
  };

  var migrateProjects = [];
  var selectedMigrateStreams = new Set();
  var migrateState = {};

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function escapeAttr(value) {
    return String(value).replace(/"/g, "&quot;");
  }

  function setEffortInput(input, value, isCustom) {
    if (isCustom) {
      input.readOnly = false;
      input.classList.remove("opacity-50", "cursor-not-allowed");
      return;
    }
    input.value = value;
    input.readOnly = true;
    input.classList.add("opacity-50", "cursor-not-allowed");
  }

  function saveMigrateState() {
    document.querySelectorAll(".migrate-proj-row").forEach(function (row) {
      var pk = row.dataset.pk;
      var cb = row.querySelector(".migrate-proj-cb");
      var sel = row.querySelector(".migrate-type-sel");
      var input = row.querySelector(".migrate-effort-input");
      migrateState[pk] = {
        checked: cb.checked,
        type: sel.value,
        customValue: input.value,
      };
    });
  }

  function renderMigrateProjList(items) {
    var container = document.getElementById("migrate-proj-list");
    if (!container) {
      return;
    }
    if (!items || items.length === 0) {
      container.innerHTML = '<div class="p-4 text-sm text-neutral-400">'
        + label("noProjectsToMigrate", "No projects to migrate.")
        + "</div>";
      return;
    }
    container.innerHTML = items
      .map(function (project) {
        var state = migrateState[project.pk] || {};
        var type = state.type || "resourced";
        var checked = state.checked !== undefined ? state.checked : true;
        var isCustom = type === "custom";
        var value = isCustom
          ? (state.customValue !== undefined
            ? state.customValue
            : project.weeks_resourced)
          : project.weeks_resourced;
        var checkedAttr = checked ? " checked" : "";
        var readonlyAttr = isCustom ? "" : " readonly";
        var opacityClass = isCustom ? "" : " opacity-50 cursor-not-allowed";
        var carry = project.weeks_unallocated || 0;
        var carryHint = (carry >= 0 ? "+" : "") + carry + " " + label("weeks", "wks")
          + " " + label("carryover", "carryover");
        return '<label class="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-base-200 migrate-proj-row"'
          + ' data-pk="' + project.pk + '"'
          + ' data-resourced="' + project.weeks_resourced + '">'
          + '<input type="checkbox" name="project_pks" value="' + project.pk + '" class="checkbox checkbox-sm migrate-proj-cb"' + checkedAttr + ">"
          + '<span class="flex-1 text-sm">' + escapeHtml(project.name)
          + ' <span class="text-xs ' + (carry < 0 ? "text-error" : "text-neutral-400") + '">' + carryHint + "</span></span>"
          + '<select class="select select-bordered select-xs migrate-type-sel" onchange="applyProjEffortType(this)" onclick="event.stopPropagation()">'
          + '<option value="resourced"' + (type === "resourced" ? " selected" : "") + ">"
          + label("resourced", "Resourced") + " (" + project.weeks_resourced + ")</option>"
          + '<option value="custom"' + (type === "custom" ? " selected" : "") + ">"
          + label("custom", "Custom") + "</option>"
          + "</select>"
          + '<input type="number" name="effort_' + project.pk + '" value="' + value + '" min="0" step="0.5"'
          + readonlyAttr
          + ' class="input input-bordered input-xs w-20 migrate-effort-input'
          + opacityClass
          + '" onclick="event.stopPropagation()">'
          + '<span class="text-xs text-neutral-400 shrink-0">'
          + label("weeks", "wks")
          + "</span>"
          + "</label>";
      })
      .join("");
  }

  function renderMigrateStreamFilters() {
    var container = document.getElementById("migrate-stream-filters");
    if (!container) {
      return;
    }
    var streamSet = {};
    migrateProjects.forEach(function (project) {
      (project.streams || []).forEach(function (stream) {
        streamSet[stream] = true;
      });
    });
    var streams = Object.keys(streamSet).sort();
    if (streams.length === 0) {
      container.innerHTML = "";
      return;
    }
    container.innerHTML = '<span class="text-xs text-neutral-500 shrink-0 mr-1">'
      + label("streams", "Streams:")
      + "</span>"
      + streams
        .map(function (stream) {
          var active = selectedMigrateStreams.has(stream);
          return '<button type="button" onclick="toggleMigrateStream(this)" data-stream="'
            + escapeAttr(stream)
            + '" class="btn btn-xs '
            + (active ? "btn-primary" : "btn-outline")
            + ' migrate-stream-btn">'
            + escapeHtml(stream)
            + "</button>";
        })
        .join("");
  }

  function getFilteredMigrateProjects() {
    var searchInput = document.getElementById("migrate-proj-search");
    var text = (searchInput ? searchInput.value : "").toLowerCase();
    return migrateProjects.filter(function (project) {
      if (text && project.name.toLowerCase().indexOf(text) === -1) {
        return false;
      }
      if (
        selectedMigrateStreams.size > 0
        && !(project.streams || []).some(function (stream) {
          return selectedMigrateStreams.has(stream);
        })
      ) {
        return false;
      }
      return true;
    });
  }

  window.toggleMigrateStream = function (btn) {
    if (!btn) {
      return;
    }
    saveMigrateState();
    var stream = btn.dataset.stream;
    if (selectedMigrateStreams.has(stream)) {
      selectedMigrateStreams.delete(stream);
    } else {
      selectedMigrateStreams.add(stream);
    }
    renderMigrateStreamFilters();
    renderMigrateProjList(getFilteredMigrateProjects());
  };

  window.filterMigrateProjList = function () {
    saveMigrateState();
    renderMigrateProjList(getFilteredMigrateProjects());
  };

  window.applyProjEffortType = function (selectEl) {
    if (!selectEl) {
      return;
    }
    var row = selectEl.closest(".migrate-proj-row");
    if (!row) {
      return;
    }
    var input = row.querySelector(".migrate-effort-input");
    var isCustom = selectEl.value === "custom";
    setEffortInput(input, row.dataset.resourced, isCustom);
  };

  window.setAllMigrateType = function () {
    var selectEl = document.getElementById("migrate-set-all");
    if (!selectEl) {
      return;
    }
    var type = selectEl.value;
    if (!type) {
      return;
    }
    document.querySelectorAll(".migrate-proj-row").forEach(function (row) {
      var sel = row.querySelector(".migrate-type-sel");
      sel.value = type;
      window.applyProjEffortType(sel);
    });
    selectEl.value = "";
  };

  window.updateMigrateProjList = function () {
    var semSel = document.getElementById("migrate-proj-semester");
    var semPk = semSel ? semSel.value : "";
    migrateProjects = continuationData[semPk] || [];
    migrateState = {};
    selectedMigrateStreams = new Set();
    var searchInput = document.getElementById("migrate-proj-search");
    if (searchInput) {
      searchInput.value = "";
    }
    renderMigrateStreamFilters();
    renderMigrateProjList(migrateProjects);
  };

  window.selectAllMigrateProjects = function (checked) {
    document.querySelectorAll(".migrate-proj-cb").forEach(function (cb) {
      cb.checked = checked;
    });
  };

  window.openMigrateProjects = function () {
    if (!hasMigrateSemesters) {
      return;
    }
    window.updateMigrateProjList();
    var modal = document.getElementById("migrate-project-modal");
    if (modal) {
      modal.showModal();
    }
  };

  window.downloadProjectsTSV = function () {
    fetch(cfg.urls.download)
      .then(function (response) {
        return response.blob();
      })
      .then(function (blob) {
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = "projects_" + cfg.semester + ".tsv";
        document.body.appendChild(link);
        link.click();
        setTimeout(function () {
          URL.revokeObjectURL(url);
          link.remove();
        }, 100);
      });
  };

  function resetAddProjectModal() {
    var form = document.getElementById("add-project-form");
    if (form) { form.reset(); }
    // Remove dynamically added stream/tag buttons
    document.querySelectorAll("#proj-stream-buttons [data-dynamic]").forEach(function (el) { el.remove(); });
    document.querySelectorAll("#proj-tag-buttons [data-dynamic]").forEach(function (el) { el.remove(); });
    // Uncheck all remaining checkbox buttons and sync visual state
    ["proj-stream-buttons", "proj-tag-buttons"].forEach(function (id) {
      document.querySelectorAll("#" + id + ' input[type="checkbox"]').forEach(function (cb) {
        cb.checked = false;
        var lbl = cb.closest("label");
        if (lbl) { lbl.classList.remove("btn-primary"); lbl.classList.add("btn-outline"); }
      });
    });
    // Reset science lead select
    var sciLeadSel = document.querySelector('#add-project-form select[name="science_lead"]');
    if (sciLeadSel) { sciLeadSel.value = ""; }
    // Reset continuation selects
    var contSem = document.getElementById("add-cont-semester");
    if (contSem) { contSem.value = ""; }
    var contProj = document.getElementById("add-cont-project");
    if (contProj) {
      contProj.innerHTML = '<option value="">' + label("selectProject", "— select project —") + "</option>";
      contProj.disabled = true;
    }
  }

  function bindAddProjectInputs() {
    initCheckboxButtons("proj-stream-buttons");
    initCheckboxButtons("proj-tag-buttons");

    var projStreamInput = document.getElementById("proj-new-stream");
    if (projStreamInput && !projStreamInput.dataset.boundEnter) {
      projStreamInput.dataset.boundEnter = "true";
      projStreamInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          window.projAddStream();
        }
      });
    }

    var projTagInput = document.getElementById("proj-new-tag");
    if (projTagInput && !projTagInput.dataset.boundEnter) {
      projTagInput.dataset.boundEnter = "true";
      projTagInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          window.projAddTag();
        }
      });
    }

    var addStreamBtn = document.getElementById("proj-add-stream-btn");
    if (addStreamBtn && !addStreamBtn.dataset.boundClick) {
      addStreamBtn.dataset.boundClick = "true";
      addStreamBtn.addEventListener("click", function () {
        window.projAddStream();
      });
    }

    var addTagBtn = document.getElementById("proj-add-tag-btn");
    if (addTagBtn && !addTagBtn.dataset.boundClick) {
      addTagBtn.dataset.boundClick = "true";
      addTagBtn.addEventListener("click", function () {
        window.projAddTag();
      });
    }

    var addContSemester = document.getElementById("add-cont-semester");
    if (addContSemester && !addContSemester.dataset.boundChange) {
      addContSemester.dataset.boundChange = "true";
      addContSemester.addEventListener("change", function () {
        window.updateAddContProjects();
      });
    }

    var closeAddModalBtn = document.getElementById("close-add-project-modal");
    if (closeAddModalBtn && !closeAddModalBtn.dataset.boundClick) {
      closeAddModalBtn.dataset.boundClick = "true";
      closeAddModalBtn.addEventListener("click", function () {
        var modal = document.getElementById("add-project-modal");
        if (modal) {
          modal.close();
        }
      });
    }
  }

  function bindEditProjectInputs() {
    initCheckboxButtons("edit-proj-stream-buttons");
    initCheckboxButtons("edit-proj-tag-buttons");

    var editStreamInput = document.getElementById("edit-proj-new-stream");
    if (editStreamInput && !editStreamInput.dataset.boundEnter) {
      editStreamInput.dataset.boundEnter = "true";
      editStreamInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          window.editProjAddStream();
        }
      });
    }

    var editTagInput = document.getElementById("edit-proj-new-tag");
    if (editTagInput && !editTagInput.dataset.boundEnter) {
      editTagInput.dataset.boundEnter = "true";
      editTagInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          window.editProjAddTag();
        }
      });
    }

    var editStreamBtn = document.getElementById("edit-proj-add-stream-btn");
    if (editStreamBtn && !editStreamBtn.dataset.boundClick) {
      editStreamBtn.dataset.boundClick = "true";
      editStreamBtn.addEventListener("click", function () {
        window.editProjAddStream();
      });
    }

    var editTagBtn = document.getElementById("edit-proj-add-tag-btn");
    if (editTagBtn && !editTagBtn.dataset.boundClick) {
      editTagBtn.dataset.boundClick = "true";
      editTagBtn.addEventListener("click", function () {
        window.editProjAddTag();
      });
    }

    var editContSemester = document.getElementById("edit-cont-semester");
    if (editContSemester && !editContSemester.dataset.boundChange) {
      editContSemester.dataset.boundChange = "true";
      editContSemester.addEventListener("change", function () {
        window.updateEditContProjects();
      });
    }

    var editContProject = document.getElementById("edit-cont-project");
    if (editContProject && !editContProject.dataset.boundChange) {
      editContProject.dataset.boundChange = "true";
      editContProject.addEventListener("change", function () {
        window.syncEditContHidden();
      });
    }

    var removeProjectBtn = document.getElementById("confirm-remove-project");
    if (removeProjectBtn && !removeProjectBtn.dataset.boundClick) {
      removeProjectBtn.dataset.boundClick = "true";
      removeProjectBtn.addEventListener("click", function () {
        window.confirmRemoveProject();
      });
    }

    var closeEditModalBtn = document.getElementById("close-project-edit-modal");
    if (closeEditModalBtn && !closeEditModalBtn.dataset.boundClick) {
      closeEditModalBtn.dataset.boundClick = "true";
      closeEditModalBtn.addEventListener("click", function () {
        var modal = document.getElementById("project-edit-modal");
        if (modal) {
          modal.close();
        }
      });
    }

    var openTimeEntriesBtn = document.getElementById("open-time-entries");
    if (openTimeEntriesBtn && !openTimeEntriesBtn.dataset.boundClick) {
      openTimeEntriesBtn.dataset.boundClick = "true";
      openTimeEntriesBtn.addEventListener("click", function () {
        window.openTimeEntriesModal();
      });
    }

    var closeTimeEntriesBtn = document.getElementById("close-time-entries-modal");
    if (closeTimeEntriesBtn && !closeTimeEntriesBtn.dataset.boundClick) {
      closeTimeEntriesBtn.dataset.boundClick = "true";
      closeTimeEntriesBtn.addEventListener("click", function () {
        var modal = document.getElementById("time-entries-modal");
        if (modal) {
          modal.close();
        }
      });
    }
  }

  function init() {
    initFilterPersistence();
    initSort();
    bindAddProjectInputs();

    var addProjectDialog = document.getElementById("add-project-modal");
    if (addProjectDialog) {
      addProjectDialog.addEventListener("close", resetAddProjectModal);
    }

    var openAddModalBtn = document.getElementById("open-add-project-modal");
    if (openAddModalBtn) {
      openAddModalBtn.addEventListener("click", function () {
        var modal = document.getElementById("add-project-modal");
        if (modal) {
          modal.showModal();
        }
      });
    }

    var openMigrateBtn = document.getElementById("open-migrate-projects");
    if (openMigrateBtn) {
      openMigrateBtn.addEventListener("click", function () {
        window.openMigrateProjects();
      });
    }

    var downloadBtn = document.getElementById("download-projects-tsv");
    if (downloadBtn) {
      downloadBtn.addEventListener("click", function () {
        window.downloadProjectsTSV();
      });
    }

    document.querySelectorAll("#proj-table th[data-sort-col]").forEach(function (th) {
      th.addEventListener("click", function () {
        window.sortProjTable(th.dataset.sortCol);
      });
    });

    document.querySelectorAll(".js-edit-project-row").forEach(function (row) {
      row.addEventListener("click", function () {
        window.openEditProject(row);
      });
    });

    var migrateSem = document.getElementById("migrate-proj-semester");
    if (migrateSem) {
      migrateSem.addEventListener("change", function () {
        window.updateMigrateProjList();
      });
    }

    var migrateSearch = document.getElementById("migrate-proj-search");
    if (migrateSearch) {
      migrateSearch.addEventListener("input", function () {
        window.filterMigrateProjList();
      });
    }

    var migrateSetAll = document.getElementById("migrate-set-all");
    if (migrateSetAll) {
      migrateSetAll.addEventListener("change", function () {
        window.setAllMigrateType();
      });
    }

    var migrateAllBtn = document.getElementById("migrate-select-all");
    if (migrateAllBtn) {
      migrateAllBtn.addEventListener("click", function () {
        window.selectAllMigrateProjects(true);
      });
    }

    var migrateNoneBtn = document.getElementById("migrate-select-none");
    if (migrateNoneBtn) {
      migrateNoneBtn.addEventListener("click", function () {
        window.selectAllMigrateProjects(false);
      });
    }

    var closeMigrateBtn = document.getElementById("close-migrate-project-modal");
    if (closeMigrateBtn) {
      closeMigrateBtn.addEventListener("click", function () {
        var modal = document.getElementById("migrate-project-modal");
        if (modal) {
          modal.close();
        }
      });
    }

    if (canEdit) {
      bindEditProjectInputs();

    }

    document.body.addEventListener("htmx:afterSwap", function (event) {
      var target = event && event.detail ? event.detail.target : null;
      if (!target) {
        return;
      }
      if (target.id === "add-project-form") {
        bindAddProjectInputs();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
