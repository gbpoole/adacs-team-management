(function () {
  var cfg = window.peoplePageConfig || {};
  var labels = cfg.labels || {};

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
    var storageKey = "people_filter";
    var params = new URLSearchParams(window.location.search);
    var urlTags = params.getAll("tags");
    if (urlTags.length > 0) {
      safeLocalStorageSet(storageKey, JSON.stringify({ tags: urlTags }));
    } else {
      try {
        var saved = JSON.parse(safeLocalStorageGet(storageKey) || "null");
        if (saved && saved.tags && saved.tags.length > 0) {
          var p = new URLSearchParams();
          saved.tags.forEach(function (tag) {
            p.append("tags", tag);
          });
          window.location.replace(window.location.pathname + "?" + p.toString());
          return;
        }
      } catch (_err) {
        // Ignore invalid storage data.
      }
    }

    function submitFilter() {
      var tags = Array.from(form.querySelectorAll('input[name="tags"]:checked')).map(
        function (cb) {
          return cb.value;
        },
      );
      safeLocalStorageSet(storageKey, JSON.stringify({ tags: tags }));
      form.submit();
    }

    form.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
      cb.addEventListener("change", submitFilter);
    });
    form.querySelectorAll("button[data-group]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var selectAll = btn.dataset.action === "all";
        form.querySelectorAll('input[name="tags"]').forEach(function (cb) {
          cb.checked = selectAll;
        });
        submitFilter();
      });
    });
  }

  function initSorting() {
    var sortKey = "people_sort";
    var sortCol = "name";
    var sortAsc = true;

    function applySort() {
      var tbody = document.querySelector("#people-table tbody");
      if (!tbody) {
        return;
      }
      var rows = Array.from(tbody.querySelectorAll("tr[data-sort-name]"));
      rows.sort(function (a, b) {
        var dataKey = "sort" + sortCol.charAt(0).toUpperCase() + sortCol.slice(1);
        var av = a.dataset[dataKey] || "";
        var bv = b.dataset[dataKey] || "";
        var cmp = av.localeCompare(bv);
        return sortAsc ? cmp : -cmp;
      });
      rows.forEach(function (row) {
        tbody.appendChild(row);
      });
      document.querySelectorAll("#people-table th[data-col]").forEach(function (th) {
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
      safeLocalStorageSet(sortKey, JSON.stringify({ col: sortCol, asc: sortAsc }));
    }

    window.sortPeopleTable = function (col) {
      if (sortCol === col) {
        sortAsc = !sortAsc;
      } else {
        sortCol = col;
        sortAsc = true;
      }
      applySort();
    };

    try {
      var saved = JSON.parse(safeLocalStorageGet(sortKey) || "null");
      if (saved && saved.col) {
        sortCol = saved.col;
        sortAsc = saved.asc;
      }
    } catch (_err) {
      // Ignore bad localStorage data.
    }
    applySort();
  }

  function addCheckboxButton(containerId, inputName, name) {
    if (!name) { return; }
    var container = document.getElementById(containerId);
    if (!container) { return; }
    var safeName = name.replace(/"/g, "\\\"");
    var existing = container.querySelector('input[name="' + inputName + '"][value="' + safeName + '"]');
    if (existing) {
      existing.checked = true;
      existing.dispatchEvent(new Event("change"));
      return;
    }
    var labelEl = document.createElement("label");
    labelEl.className = "btn btn-sm btn-primary cursor-pointer";
    var cb = document.createElement("input");
    cb.type = "checkbox";
    cb.name = inputName;
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

  window.personAddTag = function () {
    var input = document.getElementById("edit-person-new-tag");
    if (!input) { return; }
    var name = input.value.trim();
    if (!name) { return; }
    if (name.indexOf("||") !== -1 || name.indexOf("\t") !== -1) {
      alert("Tag name may not contain '||' or tab characters.");
      return;
    }
    addCheckboxButton("edit-person-tag-buttons", "tags", name);
    input.value = "";
    input.focus();
  };

  window.personAddStream = function () {
    var input = document.getElementById("edit-person-new-stream");
    if (!input) { return; }
    var name = input.value.trim();
    if (!name) { return; }
    if (name.indexOf("||") !== -1 || name.indexOf("\t") !== -1) {
      alert("Stream name may not contain '||' or tab characters.");
      return;
    }
    addCheckboxButton("edit-person-stream-buttons", "stream_access", name);
    input.value = "";
    input.focus();
  };

  function initCheckboxButtons(containerId) {
    var container = document.getElementById(containerId);
    if (!container) {
      return;
    }
    container.querySelectorAll('input[type="checkbox"]').forEach(function (cb) {
      var labelEl = cb.closest("label");

      function sync() {
        labelEl.classList.toggle("btn-primary", cb.checked);
        labelEl.classList.toggle("btn-outline", !cb.checked);
      }

      sync();
      cb.addEventListener("change", sync);
    });
  }

  function initEditModal() {
    if (!cfg.canEdit) {
      return;
    }

    window.openEditPerson = function (row) {
      var name = row.dataset.name || row.dataset.email || "";
      var email = row.dataset.email || "";

      document.getElementById("edit-person-heading").textContent = name || email;
      document.getElementById("edit-person-subheading").textContent =
        name && email !== name ? email : "";

      var effortEl = document.getElementById("edit-effort");
      if (effortEl) {
        effortEl.value = row.dataset.effort || "";
      }

      var tagNames = row.dataset.tags ? row.dataset.tags.split(",").filter(Boolean) : [];
      document
        .querySelectorAll('#edit-person-tag-buttons input[type="checkbox"]')
        .forEach(function (cb) {
          cb.checked = tagNames.indexOf(cb.value) !== -1;
          cb.dispatchEvent(new Event("change"));
        });

      var projPks = row.dataset.projects ? row.dataset.projects.split(",").filter(Boolean) : [];
      var projSel = document.getElementById("edit-projects");
      if (projSel) {
        Array.from(projSel.options).forEach(function (opt) {
          opt.selected = projPks.indexOf(opt.value) !== -1;
        });
      }

      var streamNames = row.dataset.streams
        ? row.dataset.streams.split(",").filter(Boolean)
        : [];
      document
        .querySelectorAll('#edit-person-stream-buttons input[type="checkbox"]')
        .forEach(function (cb) {
          cb.checked = streamNames.indexOf(cb.value) !== -1;
          cb.dispatchEvent(new Event("change"));
        });

      var allProjectsCb = document.getElementById("edit-all-projects");
      if (allProjectsCb) {
        allProjectsCb.checked = row.dataset.allProjects === "true";
        function syncProjects() {
          if (projSel) { projSel.disabled = allProjectsCb.checked; }
        }
        allProjectsCb.onchange = syncProjects;
        syncProjects();
      }

      var allStreamsCb = document.getElementById("edit-all-streams");
      if (allStreamsCb) {
        allStreamsCb.checked = row.dataset.allStreams === "true";
        function syncStreams() {
          var container = document.getElementById("edit-person-stream-buttons");
          if (container) {
            container.querySelectorAll("input").forEach(function (cb) {
              cb.disabled = allStreamsCb.checked;
            });
            container.style.opacity = allStreamsCb.checked ? "0.4" : "";
            container.style.pointerEvents = allStreamsCb.checked ? "none" : "";
          }
        }
        allStreamsCb.onchange = syncStreams;
        syncStreams();
      }

      document.getElementById("person-edit-form").action =
        "/planning/people/" + row.dataset.pk + "/edit/";
      document.getElementById("person-edit-modal").showModal();
    };

    var editForm = document.getElementById("person-edit-form");
    if (editForm) {
      editForm.addEventListener("submit", function (event) {
        event.preventDefault();
        fetch(this.action, { method: "POST", body: new FormData(this) })
          .then(function (resp) {
            if (resp.ok) {
              window.location.reload();
            } else {
              alert(label("saveFailedStatus", "Save failed") + " (status " + resp.status + "). Please try again.");
            }
          })
          .catch(function () {
            alert(label("saveFailed", "Save failed. Please check your connection and try again."));
          });
      });
    }
  }

  function init() {
    initFilterPersistence();
    initSorting();
    initCheckboxButtons("edit-person-tag-buttons");
    initCheckboxButtons("edit-person-stream-buttons");
    initEditModal();

    var newTagInput = document.getElementById("edit-person-new-tag");
    if (newTagInput) {
      newTagInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          window.personAddTag();
        }
      });
    }

    var newStreamInput = document.getElementById("edit-person-new-stream");
    if (newStreamInput) {
      newStreamInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          window.personAddStream();
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
