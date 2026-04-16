(function () {
  var cfg = window.projectPageConfig || {};
  var labels = cfg.labels || {};
  var continuationData = cfg.continuationData || {};
  var canEdit = Boolean(cfg.canEdit);
  var hasContinuationSemesters = Boolean(cfg.hasContinuationSemesters);

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

  function addCheckboxButton(containerId, fieldName, name) {
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

  window.projAddStream = function () {
    var input = document.getElementById("proj-new-stream");
    if (!input) {
      return;
    }
    addCheckboxButton("proj-stream-buttons", "streams", input.value.trim());
    input.value = "";
    input.focus();
  };

  window.projAddTag = function () {
    var input = document.getElementById("proj-new-tag");
    if (!input) {
      return;
    }
    addCheckboxButton("proj-tag-buttons", "tags", input.value.trim());
    input.value = "";
    input.focus();
  };

  window.toggleSciLeadAdd = function (type) {
    var people = document.getElementById("add-sci-lead-people");
    var external = document.getElementById("add-sci-lead-external");
    if (!people || !external) {
      return;
    }
    people.classList.toggle("hidden", type !== "people");
    external.classList.toggle("hidden", type !== "external");
    if (type === "people") {
      var extInput = document.querySelector("#add-sci-lead-external input");
      if (extInput) {
        extInput.value = "";
      }
    } else {
      var peopleSelect = document.querySelector("#add-sci-lead-people select");
      if (peopleSelect) {
        peopleSelect.value = "";
      }
    }
  };

  function updateContProjects(semSelectId, projSelectId) {
    var semSel = document.getElementById(semSelectId);
    var projSel = document.getElementById(projSelectId);
    if (!semSel || !projSel) {
      return;
    }
    var semPk = semSel.value;
    var placeholder = label("selectProject", "- select project -");
    projSel.innerHTML = '<option value="">' + placeholder + "</option>";
    if (semPk && continuationData[semPk]) {
      continuationData[semPk].forEach(function (project) {
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
    if (!input) {
      return;
    }
    addCheckboxButton("edit-proj-stream-buttons", "streams", input.value.trim());
    input.value = "";
    input.focus();
  };

  window.editProjAddTag = function () {
    var input = document.getElementById("edit-proj-new-tag");
    if (!input) {
      return;
    }
    addCheckboxButton("edit-proj-tag-buttons", "tags", input.value.trim());
    input.value = "";
    input.focus();
  };

  window.toggleSciLeadEdit = function (type) {
    var people = document.getElementById("edit-sci-lead-people");
    var external = document.getElementById("edit-sci-lead-external");
    if (!people || !external) {
      return;
    }
    people.classList.toggle("hidden", type !== "people");
    external.classList.toggle("hidden", type !== "external");
    if (type === "people") {
      var nameInput = document.getElementById("edit-science-lead-name");
      if (nameInput) {
        nameInput.value = "";
      }
    } else {
      var leadSelect = document.getElementById("edit-science-lead");
      if (leadSelect) {
        leadSelect.value = "";
      }
    }
  };

  window.updateEditContProjects = function () {
    updateContProjects("edit-cont-semester", "edit-cont-project");
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
    var sciLeadName = row.dataset.scienceLeadName || "";
    var contOfPk = row.dataset.continuationOfPk || "";

    document.getElementById("edit-project-id").value = pk;
    document.getElementById("edit-project-name-heading").textContent = row.dataset.name;
    document.getElementById("edit-project-name").value = row.dataset.name;
    document.getElementById("edit-project-effort").value = row.dataset.effort;

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
    if (sciLeadName && !sciLeadPk) {
      document.querySelector(
        'input[name="edit_sci_lead_type"][value="external"]',
      ).checked = true;
      window.toggleSciLeadEdit("external");
      document.getElementById("edit-science-lead-name").value = sciLeadName;
    } else {
      document.querySelector(
        'input[name="edit_sci_lead_type"][value="people"]',
      ).checked = true;
      window.toggleSciLeadEdit("people");
      document.getElementById("edit-science-lead").value = sciLeadPk;
    }

    var editContSem = document.getElementById("edit-cont-semester");
    var editContProj = document.getElementById("edit-cont-project");
    if (editContSem && editContProj) {
      editContSem.value = "";
      editContProj.innerHTML = '<option value="">' + label("selectProject", "- select project -") + "</option>";
      editContProj.disabled = true;
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
          window.updateEditContProjects();
          editContProj.value = contOfPk;
        }
      }
    }

    document.getElementById("project-edit-form").action = "/planning/projects/" + pk + "/edit/";
    document.getElementById("project-edit-modal").showModal();
  };

  window.confirmRemoveProject = function () {
    var pk = document.getElementById("edit-project-id").value;
    if (!pk || !confirm(label("removeConfirm", "Remove project?"))) {
      return;
    }
    document.getElementById("project-edit-modal").close();
    var csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
    var body = new FormData();
    body.append("csrfmiddlewaretoken", csrf);
    postAndReload(
      "/planning/projects/" + pk + "/delete/",
      body,
      label("removeFailedStatus", "Remove failed"),
      label("removeFailed", "Remove failed."),
    );
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
          : (type === "unallocated"
            ? project.weeks_unallocated
            : project.weeks_resourced);
        var checkedAttr = checked ? " checked" : "";
        var readonlyAttr = isCustom ? "" : " readonly";
        var opacityClass = isCustom ? "" : " opacity-50 cursor-not-allowed";
        return '<label class="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-base-200 migrate-proj-row"'
          + ' data-pk="' + project.pk + '"'
          + ' data-resourced="' + project.weeks_resourced + '"'
          + ' data-unallocated="' + project.weeks_unallocated + '">'
          + '<input type="checkbox" name="project_pks" value="' + project.pk + '" class="checkbox checkbox-sm migrate-proj-cb"' + checkedAttr + ">"
          + '<span class="flex-1 text-sm">' + escapeHtml(project.name) + "</span>"
          + '<select class="select select-bordered select-xs migrate-type-sel" onchange="applyProjEffortType(this)" onclick="event.stopPropagation()">'
          + '<option value="resourced"' + (type === "resourced" ? " selected" : "") + ">"
          + label("resourced", "Resourced") + " (" + project.weeks_resourced + ")</option>"
          + '<option value="unallocated"' + (type === "unallocated" ? " selected" : "") + ">"
          + label("unallocated", "Unallocated") + " (" + project.weeks_unallocated + ")</option>"
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
    var value = selectEl.value === "unallocated"
      ? row.dataset.unallocated
      : row.dataset.resourced;
    setEffortInput(input, value, isCustom);
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
    if (!hasContinuationSemesters) {
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

  document.addEventListener("DOMContentLoaded", function () {
    initFilterPersistence();
    initSort();
    initCheckboxButtons("proj-stream-buttons");
    initCheckboxButtons("proj-tag-buttons");

    var projStreamInput = document.getElementById("proj-new-stream");
    if (projStreamInput) {
      projStreamInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          window.projAddStream();
        }
      });
    }

    var projTagInput = document.getElementById("proj-new-tag");
    if (projTagInput) {
      projTagInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          window.projAddTag();
        }
      });
    }

    if (canEdit) {
      initCheckboxButtons("edit-proj-stream-buttons");
      initCheckboxButtons("edit-proj-tag-buttons");

      var editStreamInput = document.getElementById("edit-proj-new-stream");
      if (editStreamInput) {
        editStreamInput.addEventListener("keydown", function (event) {
          if (event.key === "Enter") {
            event.preventDefault();
            window.editProjAddStream();
          }
        });
      }

      var editTagInput = document.getElementById("edit-proj-new-tag");
      if (editTagInput) {
        editTagInput.addEventListener("keydown", function (event) {
          if (event.key === "Enter") {
            event.preventDefault();
            window.editProjAddTag();
          }
        });
      }

      var editForm = document.getElementById("project-edit-form");
      if (editForm) {
        editForm.addEventListener("submit", function (event) {
          event.preventDefault();
          postAndReload(
            this.action,
            new FormData(this),
            label("saveFailedStatus", "Save failed"),
            label("saveFailed", "Save failed."),
          );
        });
      }
    }
  });
})();
