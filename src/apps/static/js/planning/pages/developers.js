(function () {
  var cfg = window.developerPageConfig || {};
  var labels = cfg.labels || {};
  var canEdit = Boolean(cfg.canEdit);
  var migrateData = cfg.migrateData || {};

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
    var storageKey = "developers_filter";
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
        // Ignore bad localStorage data.
      }
    }

    function submitFilter() {
      var tags = Array.from(
        form.querySelectorAll('input[name="tags"]:checked'),
      ).map(function (cb) {
        return cb.value;
      });
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

  var sortCol = "name";
  var sortAsc = true;

  function applyDevSort() {
    var tbody = document.querySelector("#dev-table tbody");
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

    document.querySelectorAll("#dev-table th[data-col]").forEach(function (th) {
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
      "developers_sort",
      JSON.stringify({ col: sortCol, asc: sortAsc }),
    );
  }

  window.sortDevTable = function (col) {
    if (sortCol === col) {
      sortAsc = !sortAsc;
    } else {
      sortCol = col;
      sortAsc = col === "name";
    }
    applyDevSort();
  };

  function initSort() {
    try {
      var saved = JSON.parse(safeLocalStorageGet("developers_sort") || "null");
      if (saved && saved.col) {
        sortCol = saved.col;
        sortAsc = saved.asc;
      }
    } catch (_err) {
      // Ignore bad localStorage data.
    }
    applyDevSort();
  }

  function initTagButtons(containerId) {
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

  function addTagButton(containerId, name) {
    if (!name) {
      return;
    }
    var container = document.getElementById(containerId);
    if (!container) {
      return;
    }
    var safeName = name.replace(/"/g, "\\\"");
    var existing = container.querySelector(
      'input[name="tags"][value="' + safeName + '"]',
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
    cb.name = "tags";
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

  window.downloadDevelopersTSV = function () {
    fetch(cfg.urls.download)
      .then(function (resp) {
        return resp.text();
      })
      .then(function (text) {
        var blob = new Blob([text], { type: "text/tab-separated-values" });
        var url = URL.createObjectURL(blob);
        var link = document.createElement("a");
        link.href = url;
        link.download = "developers_" + cfg.semester + ".tsv";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      });
  };

  window.filterAddDevList = function () {
    var input = document.getElementById("add-dev-search");
    var q = input ? input.value.toLowerCase() : "";
    document.querySelectorAll("#add-dev-list .add-dev-item").forEach(function (el) {
      el.style.display = el.dataset.search.indexOf(q) !== -1 ? "" : "none";
    });
  };

  window.addDevSelectAll = function () {
    document.querySelectorAll("#add-dev-list .add-dev-item").forEach(function (el) {
      if (el.style.display !== "none") {
        el.querySelector('input[type="checkbox"]').checked = true;
      }
    });
  };

  window.addDevDeselectAll = function () {
    document
      .querySelectorAll('#add-dev-list input[type="checkbox"]')
      .forEach(function (cb) {
        cb.checked = false;
      });
  };

  window.submitAddDevelopers = function () {
    var form = document.getElementById("add-developer-form");
    var selected = Array.from(
      form.querySelectorAll('input[name="profile_pks"]:checked, input[name="user_pks"]:checked'),
    );

    document.getElementById("add-dev-effort-error").classList.add("hidden");
    form.querySelectorAll('input[type="number"]').forEach(function (input) {
      input.classList.remove("input-error");
    });

    if (selected.length === 0) {
      form.submit();
      return;
    }

    var missing = selected.filter(function (cb) {
      var input = form.querySelector('input[name="effort_' + cb.value + '"]');
      return input && input.value.trim() === "";
    });
    if (missing.length > 0) {
      missing.forEach(function (cb) {
        var input = form.querySelector('input[name="effort_' + cb.value + '"]');
        if (input) {
          input.classList.add("input-error");
        }
      });
      document.getElementById("add-dev-effort-error").classList.remove("hidden");
      return;
    }

    var changed = [];
    selected.forEach(function (cb) {
      var pk = cb.value;
      var input = form.querySelector('input[name="effort_' + pk + '"]');
      if (!input) {
        return;
      }
      var base = input.dataset.base;
      var val = parseFloat(input.value);
      if (base === "" || Math.abs(parseFloat(base) - val) > 0.001) {
        var rowLabel = cb.closest("label");
        var name = rowLabel.querySelector(".font-medium").textContent.trim();
        changed.push({ pk: pk, name: name, effort: val });
      }
    });

    if (changed.length > 0) {
      var list = document.getElementById("add-dev-base-list");
      list.innerHTML = "";
      changed.forEach(function (dev) {
        var lbl = document.createElement("label");
        lbl.className = "flex items-center gap-2 px-2 py-1 hover:bg-base-200 rounded cursor-pointer";
        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.checked = true;
        cb.className = "checkbox checkbox-sm shrink-0";
        cb.dataset.pk = dev.pk;

        var nameSpan = document.createElement("span");
        nameSpan.className = "flex-1 font-medium";
        nameSpan.textContent = dev.name;

        var effortSpan = document.createElement("span");
        effortSpan.className = "text-xs text-neutral-500 shrink-0";
        effortSpan.textContent = dev.effort.toFixed(1) + " " + label("weeks", "wks");

        lbl.appendChild(cb);
        lbl.appendChild(nameSpan);
        lbl.appendChild(effortSpan);
        list.appendChild(lbl);
      });
      document.getElementById("add-dev-base-modal").showModal();
      return;
    }
    form.submit();
  };

  window.submitAddDevWithBase = function (useChecked) {
    var form = document.getElementById("add-developer-form");
    form.querySelectorAll('input[name^="update_base_"]').forEach(function (input) {
      input.remove();
    });
    if (useChecked) {
      document
        .querySelectorAll('#add-dev-base-list input[type="checkbox"]:checked')
        .forEach(function (cb) {
          var hidden = document.createElement("input");
          hidden.type = "hidden";
          hidden.name = "update_base_" + cb.dataset.pk;
          hidden.value = "1";
          form.appendChild(hidden);
        });
    }
    document.getElementById("add-dev-base-modal").close();
    form.submit();
  };

  window.updateMigrateList = function () {
    var semPk = document.getElementById("migrate-sem-select").value;
    var controls = document.getElementById("migrate-controls");
    var list = document.getElementById("migrate-dev-list");
    document.getElementById("migrate-tag-filter").value = "";
    if (!semPk || !migrateData[semPk]) {
      controls.classList.add("hidden");
      list.innerHTML = "";
      return;
    }
    controls.classList.remove("hidden");
    renderMigrateList(migrateData[semPk]);
  };

  function renderMigrateList(devs) {
    var q = (document.getElementById("migrate-tag-filter").value || "").toLowerCase();
    var list = document.getElementById("migrate-dev-list");
    list.innerHTML = "";
    var filtered = q
      ? devs.filter(function (dev) {
        return dev.tags.some(function (tag) {
          return tag.toLowerCase().indexOf(q) !== -1;
        });
      })
      : devs;
    if (filtered.length === 0) {
      list.innerHTML = '<p class="text-neutral-500 text-sm text-center py-4">'
        + label("migrateEmpty", "No developers to migrate.")
        + "</p>";
      return;
    }
    filtered.forEach(function (dev) {
      var row = document.createElement("label");
      row.className = "flex items-center gap-2 px-2 py-1 hover:bg-base-200 rounded cursor-pointer";

      var cb = document.createElement("input");
      cb.type = "checkbox";
      cb.name = "profile_pks";
      cb.value = dev.pk;
      cb.className = "checkbox checkbox-sm shrink-0";
      cb.checked = true;

      var nameSpan = document.createElement("span");
      nameSpan.className = "flex-1 min-w-0 font-medium";
      nameSpan.textContent = dev.name;

      var emailSpan = document.createElement("span");
      emailSpan.className = "text-xs text-neutral-500 ml-1";
      emailSpan.textContent = dev.email !== dev.name ? dev.email : "";
      nameSpan.appendChild(emailSpan);

      row.appendChild(cb);
      row.appendChild(nameSpan);
      list.appendChild(row);
    });
  }

  window.filterMigrateList = function () {
    var semPk = document.getElementById("migrate-sem-select").value;
    if (!semPk || !migrateData[semPk]) {
      return;
    }
    renderMigrateList(migrateData[semPk]);
  };

  window.migrateSelectAll = function () {
    document
      .querySelectorAll('#migrate-dev-list input[type="checkbox"]')
      .forEach(function (cb) {
        cb.checked = true;
      });
  };

  window.migrateDeselectAll = function () {
    document
      .querySelectorAll('#migrate-dev-list input[type="checkbox"]')
      .forEach(function (cb) {
        cb.checked = false;
      });
  };

  window.editDevAddTag = function () {
    var input = document.getElementById("edit-dev-new-tag");
    if (!input) {
      return;
    }
    var name = input.value.trim();
    if (name.indexOf("||") !== -1 || name.indexOf("\t") !== -1) {
      alert("Tag name may not contain '||' or tab characters.");
      return;
    }
    addTagButton("edit-dev-tag-buttons", name);
    input.value = "";
    input.focus();
  };

  window.openEditDeveloper = function (row) {
    if (!canEdit || !row) {
      return;
    }
    var pk = row.dataset.pk;
    var tags = row.dataset.tags ? row.dataset.tags.split(",").filter(Boolean) : [];

    document.getElementById("edit-developer-id").value = pk;
    document.getElementById("edit-developer-name-heading").textContent = row.dataset.name || row.dataset.email;
    document.getElementById("edit-developer-email-subheading").textContent = row.dataset.email;

    var effortVal = parseFloat(row.dataset.effort);
    document.getElementById("edit-developer-effort").value = Number.isNaN(effortVal)
      ? ""
      : effortVal.toFixed(1);

    document
      .querySelectorAll('#edit-dev-tag-buttons input[type="checkbox"]')
      .forEach(function (cb) {
        cb.checked = tags.indexOf(cb.value) !== -1;
        cb.dispatchEvent(new Event("change"));
      });

    var form = document.getElementById("developer-edit-form");
    form.dataset.baseTags = row.dataset.baseTags || "";
    form.action = "/planning/developers/" + pk + "/edit/";
    document.getElementById("developer-edit-modal").showModal();
  };

  function submitDeveloperForm(updateBaseTags) {
    var form = document.getElementById("developer-edit-form");
    var existing = form.querySelector('input[name="update_base_tags"]');
    if (existing) {
      existing.remove();
    }
    if (updateBaseTags) {
      var hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "update_base_tags";
      hidden.value = "1";
      form.appendChild(hidden);
    }
    postAndReload(
      form.action,
      new FormData(form),
      label("saveFailedStatus", "Save failed"),
      label("saveFailed", "Save failed."),
    );
  }

  window.confirmDeleteDeveloper = function () {
    var pk = document.getElementById("edit-developer-id").value;
    if (!pk || !confirm(label("removeConfirm", "Remove developer?"))) {
      return;
    }
    document.getElementById("developer-edit-modal").close();
    var csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
    var body = new FormData();
    body.append("csrfmiddlewaretoken", csrf);
    postAndReload(
      "/planning/developers/" + pk + "/delete/",
      body,
      label("removeFailedStatus", "Remove failed"),
      label("removeFailed", "Remove failed."),
    );
  };

  function init() {
    initFilterPersistence();
    initSort();
    initTagButtons("edit-dev-tag-buttons");

    document.querySelectorAll("#dev-table th[data-sort-col]").forEach(function (th) {
      th.addEventListener("click", function () {
        window.sortDevTable(th.dataset.sortCol);
      });
    });

    document.querySelectorAll(".js-edit-developer-row").forEach(function (row) {
      row.addEventListener("click", function () {
        window.openEditDeveloper(row);
      });
    });

    document.querySelectorAll("#add-dev-list .js-effort-input").forEach(function (input) {
      input.addEventListener("click", function (event) {
        event.stopPropagation();
      });
    });

    var openAddModalBtn = document.getElementById("open-add-developer-modal");
    if (openAddModalBtn) {
      openAddModalBtn.addEventListener("click", function () {
        var modal = document.getElementById("add-developer-modal");
        if (modal) {
          modal.showModal();
        }
      });
    }

    var openMigrateModalBtn = document.getElementById("open-migrate-developer-modal");
    if (openMigrateModalBtn) {
      openMigrateModalBtn.addEventListener("click", function () {
        var modal = document.getElementById("migrate-developer-modal");
        if (modal) {
          modal.showModal();
        }
      });
    }

    var downloadBtn = document.getElementById("download-developers-tsv");
    if (downloadBtn) {
      downloadBtn.addEventListener("click", function () {
        window.downloadDevelopersTSV();
      });
    }

    var addDevSearch = document.getElementById("add-dev-search");
    if (addDevSearch) {
      addDevSearch.addEventListener("input", function () {
        window.filterAddDevList();
      });
    }

    var addAllBtn = document.getElementById("add-dev-select-all");
    if (addAllBtn) {
      addAllBtn.addEventListener("click", function () {
        window.addDevSelectAll();
      });
    }

    var addNoneBtn = document.getElementById("add-dev-select-none");
    if (addNoneBtn) {
      addNoneBtn.addEventListener("click", function () {
        window.addDevDeselectAll();
      });
    }

    var closeAddBtn = document.getElementById("close-add-developer-modal");
    if (closeAddBtn) {
      closeAddBtn.addEventListener("click", function () {
        var modal = document.getElementById("add-developer-modal");
        if (modal) {
          modal.close();
        }
      });
    }

    var submitAddBtn = document.getElementById("submit-add-developers");
    if (submitAddBtn) {
      submitAddBtn.addEventListener("click", function () {
        window.submitAddDevelopers();
      });
    }

    var baseSkipBtn = document.getElementById("submit-add-dev-base-skip");
    if (baseSkipBtn) {
      baseSkipBtn.addEventListener("click", function () {
        window.submitAddDevWithBase(false);
      });
    }

    var baseConfirmBtn = document.getElementById("submit-add-dev-base-confirm");
    if (baseConfirmBtn) {
      baseConfirmBtn.addEventListener("click", function () {
        window.submitAddDevWithBase(true);
      });
    }

    var migrateSem = document.getElementById("migrate-sem-select");
    if (migrateSem) {
      migrateSem.addEventListener("change", function () {
        window.updateMigrateList();
      });
    }

    var migrateFilter = document.getElementById("migrate-tag-filter");
    if (migrateFilter) {
      migrateFilter.addEventListener("input", function () {
        window.filterMigrateList();
      });
    }

    var migrateAllBtn = document.getElementById("migrate-select-all");
    if (migrateAllBtn) {
      migrateAllBtn.addEventListener("click", function () {
        window.migrateSelectAll();
      });
    }

    var migrateNoneBtn = document.getElementById("migrate-select-none");
    if (migrateNoneBtn) {
      migrateNoneBtn.addEventListener("click", function () {
        window.migrateDeselectAll();
      });
    }

    var closeMigrateBtn = document.getElementById("close-migrate-developer-modal");
    if (closeMigrateBtn) {
      closeMigrateBtn.addEventListener("click", function () {
        var modal = document.getElementById("migrate-developer-modal");
        if (modal) {
          modal.close();
        }
      });
    }

    var editNewTag = document.getElementById("edit-dev-new-tag");
    if (editNewTag) {
      editNewTag.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          event.preventDefault();
          window.editDevAddTag();
        }
      });
    }

    if (canEdit) {
      var editAddTagBtn = document.getElementById("edit-dev-add-tag");
      if (editAddTagBtn) {
        editAddTagBtn.addEventListener("click", function () {
          window.editDevAddTag();
        });
      }

      var confirmDeleteBtn = document.getElementById("confirm-delete-developer");
      if (confirmDeleteBtn) {
        confirmDeleteBtn.addEventListener("click", function () {
          window.confirmDeleteDeveloper();
        });
      }

      var closeEditBtn = document.getElementById("close-developer-edit-modal");
      if (closeEditBtn) {
        closeEditBtn.addEventListener("click", function () {
          var modal = document.getElementById("developer-edit-modal");
          if (modal) {
            modal.close();
          }
        });
      }

      var baseYes = document.getElementById("base-tags-yes");
      var baseNo = document.getElementById("base-tags-no");
      if (baseYes) {
        baseYes.addEventListener("click", function () {
          document.getElementById("base-tags-confirm-modal").close();
          submitDeveloperForm(true);
        });
      }
      if (baseNo) {
        baseNo.addEventListener("click", function () {
          document.getElementById("base-tags-confirm-modal").close();
          submitDeveloperForm(false);
        });
      }

      var editForm = document.getElementById("developer-edit-form");
      if (editForm) {
        editForm.addEventListener("submit", function (event) {
          event.preventDefault();
          var semTags = Array.from(
            this.querySelectorAll('#edit-dev-tag-buttons input[type="checkbox"]:checked'),
          )
            .map(function (cb) {
              return cb.value;
            })
            .sort();
          var baseTags = (this.dataset.baseTags || "").split(",").filter(Boolean).sort();
          var tagsChanged = semTags.join(",") !== baseTags.join(",");
          if (tagsChanged) {
            document.getElementById("base-tags-confirm-modal").showModal();
          } else {
            submitDeveloperForm(false);
          }
        });
      }

      var addDevModal = document.getElementById("add-developer-modal");
      if (addDevModal) {
        addDevModal.addEventListener("close", function () {
          var form = document.getElementById("add-developer-form");
          if (form) {
            form.reset();
            form.querySelectorAll("input.input-error").forEach(function (el) {
              el.classList.remove("input-error");
            });
          }
          var errDiv = document.getElementById("add-dev-effort-error");
          if (errDiv) { errDiv.classList.add("hidden"); }
          document.querySelectorAll("#add-dev-list .add-dev-item").forEach(function (el) {
            el.style.display = "";
          });
        });
      }

      var migrateModal = document.getElementById("migrate-developer-modal");
      if (migrateModal) {
        migrateModal.addEventListener("close", function () {
          document.getElementById("migrate-sem-select").value = "";
          document.getElementById("migrate-controls").classList.add("hidden");
          document.getElementById("migrate-dev-list").innerHTML = "";
        });
      }
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
