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

  function initPeopleHoverCard() {
    var pop = document.getElementById("people-pop");
    if (!pop) {
      return;
    }
    var iconPm = '<svg style="display:inline;vertical-align:middle;color:#f59e0b" width="16" height="16" fill="currentColor" viewBox="0 0 24 24"><path d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"/></svg>';
    var iconDev = '<svg style="display:inline;vertical-align:middle;color:#0ea5e9" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>';
    var iconObs = '<svg style="display:inline;vertical-align:middle;color:#8b5cf6" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>';

    function positionPop(event) {
      var x = event.clientX + 16;
      var y = event.clientY + 16;
      if (x + 288 > window.innerWidth) {
        x = event.clientX - 296;
      }
      if (y + pop.offsetHeight > window.innerHeight) {
        y = event.clientY - pop.offsetHeight - 8;
      }
      pop.style.left = x + "px";
      pop.style.top = y + "px";
    }

    document.querySelectorAll('#people-table tbody tr[data-email]').forEach(function (row) {
      row.addEventListener("mouseenter", function (event) {
        var name = row.dataset.name || "";
        var email = row.dataset.email || "";
        var lines = [];
        lines.push('<div style="font-weight:600;margin-bottom:4px">' + (name || email) + "</div>");
        if (name && email !== name) {
          lines.push('<div style="color:#6b7280;font-size:0.8em;margin-bottom:6px">' + email + "</div>");
        }
        var roles = [];
        if (row.dataset.iconPm) {
          roles.push(iconPm + " <span>" + label("rolePm", "Project Manager") + "</span>");
        }
        if (row.dataset.iconDev) {
          roles.push(iconDev + " <span>" + label("roleDev", "Developer (selected semester)") + "</span>");
        }
        if (row.dataset.iconObs) {
          roles.push(iconObs + " <span>" + label("roleObs", "Observer (selected semester)") + "</span>");
        }
        roles.forEach(function (role) {
          lines.push('<div style="display:flex;align-items:center;gap:6px;margin-top:4px">' + role + "</div>");
        });
        pop.innerHTML = lines.join("");
        pop.classList.remove("hidden");
        positionPop(event);
      });
      row.addEventListener("mousemove", positionPop);
      row.addEventListener("mouseleave", function () {
        pop.classList.add("hidden");
      });
    });
  }

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

      var tagPks = row.dataset.tags ? row.dataset.tags.split(",").filter(Boolean) : [];
      document
        .querySelectorAll('#edit-person-tag-buttons input[type="checkbox"]')
        .forEach(function (cb) {
          cb.checked = tagPks.indexOf(cb.value) !== -1;
          cb.dispatchEvent(new Event("change"));
        });

      var projPks = row.dataset.projects ? row.dataset.projects.split(",").filter(Boolean) : [];
      var projSel = document.getElementById("edit-projects");
      if (projSel) {
        Array.from(projSel.options).forEach(function (opt) {
          opt.selected = projPks.indexOf(opt.value) !== -1;
        });
      }

      var streamPks = row.dataset.streams
        ? row.dataset.streams.split(",").filter(Boolean)
        : [];
      document
        .querySelectorAll('#edit-person-stream-buttons input[type="checkbox"]')
        .forEach(function (cb) {
          cb.checked = streamPks.indexOf(cb.value) !== -1;
          cb.dispatchEvent(new Event("change"));
        });

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

  document.addEventListener("DOMContentLoaded", function () {
    initFilterPersistence();
    initSorting();
    initPeopleHoverCard();
    initCheckboxButtons("edit-person-tag-buttons");
    initCheckboxButtons("edit-person-stream-buttons");
    initEditModal();
  });
})();
