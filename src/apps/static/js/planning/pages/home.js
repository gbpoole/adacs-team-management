var HIGHLIGHT_BG = '#4E79A7';
var HIGHLIGHT_FG = '#ffffff';
var DAY_NAMES = ['Mo','Tu','We','Th','Fr','Sa','Su'];

function renderMiniCal(year, month, startDate, endDate) {
  var monthLabel = new Date(year, month, 1)
    .toLocaleString('default', { month: 'long', year: 'numeric' });
  var html = '<div style="min-width:168px">'
    + '<div style="text-align:center;font-weight:600;margin-bottom:4px">' + monthLabel + '</div>'
    + '<div style="display:grid;grid-template-columns:repeat(7,24px);gap:1px;text-align:center">';
  DAY_NAMES.forEach(function(d) {
    html += '<div style="font-size:10px;color:#9ca3af;padding-bottom:2px">' + d + '</div>';
  });
  var first = new Date(year, month, 1);
  var firstDow = (first.getDay() + 6) % 7;
  for (var i = 0; i < firstDow; i++) { html += '<div></div>'; }
  var daysInMonth = new Date(year, month + 1, 0).getDate();
  for (var d = 1; d <= daysInMonth; d++) {
    var cur = new Date(year, month, d);
    var inRange = cur >= startDate && cur <= endDate;
    var style = inRange
      ? 'background:' + HIGHLIGHT_BG + ';color:' + HIGHLIGHT_FG + ';border-radius:4px;'
      : '';
    html += '<div style="padding:2px 0;font-size:12px;' + style + '">' + d + '</div>';
  }
  html += '</div></div>';
  return html;
}

function showLeaveCalendar(row, event) {
  var startDate = new Date(row.dataset.start + 'T00:00:00');
  var endDate   = new Date(row.dataset.end   + 'T00:00:00');
  var startYear = startDate.getFullYear(), startMonth = startDate.getMonth();
  var endYear   = endDate.getFullYear(),   endMonth   = endDate.getMonth();
  var monthSpan = (endYear - startYear) * 12 + (endMonth - startMonth) + 1;
  var inner = '';
  if (monthSpan <= 2) {
    inner = '<div style="display:flex;gap:12px">';
    for (var m = 0; m < monthSpan; m++) {
      var y  = startYear + Math.floor((startMonth + m) / 12);
      var mo = (startMonth + m) % 12;
      inner += renderMiniCal(y, mo, startDate, endDate);
    }
    inner += '</div>';
  } else {
    var connector = '<div style="display:flex;align-items:center;justify-content:center;'
      + 'padding:0 10px;color:#374151;font-size:20px;font-weight:700">&rarr;</div>';
    inner = '<div style="display:flex;gap:4px;align-items:center">'
      + renderMiniCal(startYear, startMonth, startDate, endDate)
      + connector
      + renderMiniCal(endYear, endMonth, startDate, endDate)
      + '</div>';
  }
  var popup = document.getElementById('leave-cal-popup');
  popup.innerHTML = inner;
  popup.style.visibility = 'hidden';
  popup.style.display = 'block';
  var pw = popup.offsetWidth, ph = popup.offsetHeight;
  popup.style.visibility = '';
  var margin = 12;
  var x = event.clientX + margin;
  var y = event.clientY + margin;
  if (x + pw > window.innerWidth  - margin) { x = event.clientX - pw - margin; }
  if (y + ph > window.innerHeight - margin) { y = event.clientY - ph - margin; }
  popup.style.left = x + 'px';
  popup.style.top  = y + 'px';
}

function hideLeaveCalendar() {
  document.getElementById('leave-cal-popup').style.display = 'none';
}
