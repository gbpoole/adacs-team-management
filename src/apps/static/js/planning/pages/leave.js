(function () {
  var cfg = window.leavePageConfig || {};
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

  function restoreShowPastPreference() {
    if (!cfg.showPast) {
      if (safeLocalStorageGet("leave_show_past") === "1") {
        window.location.replace("?show_past=1");
      }
      return;
    }
    safeLocalStorageSet("leave_show_past", "1");
  }

  window.openEditLeave = function (row) {
    document.getElementById("edit-leave-id").value = row.dataset.pk;
    document.getElementById("edit-leave-developer").value = row.dataset.developer;
    document.getElementById("edit-leave-start").value = row.dataset.start;
    document.getElementById("edit-leave-end").value = row.dataset.end;
    document.getElementById("leave-edit-form").action = "/planning/leave/" + row.dataset.pk + "/update/";
    document.getElementById("leave-edit-modal").showModal();
  };

  window.confirmDeleteLeave = function () {
    var pk = document.getElementById("edit-leave-id").value;
    if (!pk || !confirm(label("deleteConfirm", "Delete this leave period?"))) {
      return;
    }
    document.getElementById("leave-edit-modal").close();
    var csrf = document.querySelector("[name=csrfmiddlewaretoken]").value;
    var body = new FormData();
    body.append("csrfmiddlewaretoken", csrf);
    postAndReload(
      "/planning/leave/" + pk + "/delete/",
      body,
      label("deleteFailedStatus", "Delete failed"),
      label("deleteFailed", "Delete failed."),
    );
  };

  var sortCol = null;
  var sortAsc = true;

  function cmpRows(a, b, col, asc) {
    var av;
    var bv;
    var cmp;
    if (col === "name") {
      av = a.dataset.sortName || "";
      bv = b.dataset.sortName || "";
      cmp = av.localeCompare(bv);
    } else if (col === "start") {
      av = a.dataset.start || "";
      bv = b.dataset.start || "";
      cmp = av < bv ? -1 : av > bv ? 1 : 0;
    } else if (col === "end") {
      av = a.dataset.end || "";
      bv = b.dataset.end || "";
      cmp = av < bv ? -1 : av > bv ? 1 : 0;
    } else {
      av = parseFloat(a.dataset.sortDuration || "0");
      bv = parseFloat(b.dataset.sortDuration || "0");
      cmp = av - bv;
    }
    return asc ? cmp : -cmp;
  }

  function applySort() {
    var tbody = document.querySelector("#leave-table tbody");
    if (!tbody) {
      return;
    }
    tbody.querySelectorAll("tr.leave-separator").forEach(function (row) {
      row.remove();
    });

    var rows = Array.from(tbody.querySelectorAll("tr[data-start]"));
    var todayStr = new Date().toISOString().slice(0, 10);
    rows.sort(function (a, b) {
      return cmpRows(a, b, sortCol, sortAsc);
    });

    var futureRows = rows.filter(function (row) {
      return row.dataset.end >= todayStr;
    });
    var pastRows = rows.filter(function (row) {
      return row.dataset.end < todayStr;
    });

    futureRows.forEach(function (row) {
      row.style.opacity = "";
    });
    pastRows.forEach(function (row) {
      row.style.opacity = "0.4";
    });

    futureRows.forEach(function (row) {
      tbody.appendChild(row);
    });
    if (futureRows.length > 0 && pastRows.length > 0) {
      var colCount = document.querySelectorAll("#leave-table thead th").length;
      var sep = document.createElement("tr");
      sep.className = "leave-separator";
      var td = document.createElement("td");
      td.colSpan = colCount;
      td.textContent = label("past", "Past");
      td.style.cssText = "padding:3px 8px;text-align:center;font-size:11px;letter-spacing:0.06em;text-transform:uppercase;color:#9ca3af;border-top:1px solid #e5e7eb;border-bottom:1px solid #e5e7eb;pointer-events:none;";
      sep.appendChild(td);
      tbody.appendChild(sep);
    }
    pastRows.forEach(function (row) {
      tbody.appendChild(row);
    });

    document.querySelectorAll("#leave-table th[data-col]").forEach(function (th) {
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
    safeLocalStorageSet("leave_sort", JSON.stringify({ col: sortCol, asc: sortAsc }));
  }

  window.sortLeaveTable = function (col) {
    if (sortCol === col) {
      sortAsc = !sortAsc;
    } else {
      sortCol = col;
      sortAsc = col === "name";
    }
    applySort();
  };

  var highlightBg = "#4E79A7";
  var highlightFg = "#ffffff";
  var dayNames = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];

  function renderMiniCal(year, month, startDate, endDate) {
    var monthLabel = new Date(year, month, 1).toLocaleString("default", {
      month: "long",
      year: "numeric",
    });
    var html = '<div style="min-width:168px">'
      + '<div style="text-align:center;font-weight:600;margin-bottom:4px">' + monthLabel + "</div>"
      + '<div style="display:grid;grid-template-columns:repeat(7,24px);gap:1px;text-align:center">';
    dayNames.forEach(function (d) {
      html += '<div style="font-size:10px;color:#9ca3af;padding-bottom:2px">' + d + "</div>";
    });
    var first = new Date(year, month, 1);
    var firstDow = (first.getDay() + 6) % 7;
    for (var i = 0; i < firstDow; i += 1) {
      html += "<div></div>";
    }
    var daysInMonth = new Date(year, month + 1, 0).getDate();
    for (var day = 1; day <= daysInMonth; day += 1) {
      var cur = new Date(year, month, day);
      var inRange = cur >= startDate && cur <= endDate;
      var style = inRange
        ? "background:" + highlightBg + ";color:" + highlightFg + ";border-radius:4px;"
        : "";
      html += '<div style="padding:2px 0;font-size:12px;' + style + '">' + day + "</div>";
    }
    html += "</div></div>";
    return html;
  }

  window.showLeaveCalendar = function (row, event) {
    var startDate = new Date(row.dataset.start + "T00:00:00");
    var endDate = new Date(row.dataset.end + "T00:00:00");
    var startYear = startDate.getFullYear();
    var startMonth = startDate.getMonth();
    var endYear = endDate.getFullYear();
    var endMonth = endDate.getMonth();
    var monthSpan = (endYear - startYear) * 12 + (endMonth - startMonth) + 1;

    var inner = "";
    if (monthSpan <= 2) {
      inner = '<div style="display:flex;gap:12px">';
      for (var monthOffset = 0; monthOffset < monthSpan; monthOffset += 1) {
        var y = startYear + Math.floor((startMonth + monthOffset) / 12);
        var m = (startMonth + monthOffset) % 12;
        inner += renderMiniCal(y, m, startDate, endDate);
      }
      inner += "</div>";
    } else {
      var connector = '<div style="display:flex;align-items:center;justify-content:center;'
        + 'padding:0 10px;color:#374151;font-size:20px;font-weight:700">&rarr;</div>';
      inner = '<div style="display:flex;gap:4px;align-items:center">'
        + renderMiniCal(startYear, startMonth, startDate, endDate)
        + connector
        + renderMiniCal(endYear, endMonth, startDate, endDate)
        + "</div>";
    }

    var popup = document.getElementById("leave-cal-popup");
    popup.innerHTML = inner;
    popup.style.visibility = "hidden";
    popup.style.display = "block";
    var pw = popup.offsetWidth;
    var ph = popup.offsetHeight;
    popup.style.visibility = "";

    var margin = 12;
    var x = event.clientX + margin;
    var yPos = event.clientY + margin;
    if (x + pw > window.innerWidth - margin) {
      x = event.clientX - pw - margin;
    }
    if (yPos + ph > window.innerHeight - margin) {
      yPos = event.clientY - ph - margin;
    }
    popup.style.left = x + "px";
    popup.style.top = yPos + "px";
  };

  window.hideLeaveCalendar = function () {
    var popup = document.getElementById("leave-cal-popup");
    if (popup) {
      popup.style.display = "none";
    }
  };

  document.addEventListener("DOMContentLoaded", function () {
    restoreShowPastPreference();

    sortCol = "start";
    sortAsc = true;
    try {
      var saved = JSON.parse(safeLocalStorageGet("leave_sort") || "null");
      if (saved && saved.col) {
        sortCol = saved.col;
        sortAsc = saved.asc;
      }
    } catch (_err) {
      // Ignore invalid JSON.
    }
    applySort();

    if (cfg.canEdit) {
      var editForm = document.getElementById("leave-edit-form");
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
