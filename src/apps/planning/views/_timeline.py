import datetime


def _week_starts(start: datetime.date, end: datetime.date) -> list:
    """Return list of Monday dates covering the range [start, end]."""
    first = start - datetime.timedelta(days=start.weekday())
    weeks = []
    w = first
    while w <= end:
        weeks.append(w)
        w += datetime.timedelta(weeks=1)
    return weeks


def _build_lane_cells(n_weeks, phase_segments):
    """
    Build a cell list for a single lane.
    phase_segments: list of (start_col, span, phase).

    All phases are emitted as individual cells regardless of overlap — absolute
    positioning in the template renders them correctly even when they overlap.
    Empty cells are emitted for column runs not covered by any phase (used for
    drag-to-create).
    """
    # Mark columns covered by at least one phase
    covered = bytearray(n_weeks)
    for start_col, span, _ in phase_segments:
        for c in range(max(0, start_col), min(n_weeks, start_col + span)):
            covered[c] = 1

    # Emit every phase cell (sorted for deterministic order)
    cells = [
        {
            "type": "phase",
            "colspan": span,
            "phase": ph,
            "col_start": start_col,
            "col_end": start_col + span - 1,
        }
        for start_col, span, ph in sorted(phase_segments, key=lambda x: x[0])
    ]

    # Emit empty cells for uncovered column runs
    col = 0
    while col < n_weeks:
        if not covered[col]:
            end = col
            while end + 1 < n_weeks and not covered[end + 1]:
                end += 1
            cells.append(
                {
                    "type": "empty",
                    "colspan": end - col + 1,
                    "phase": None,
                    "col_start": col,
                    "col_end": end,
                }
            )
            col = end + 1
        else:
            col += 1

    return cells


def _coverage(item_start: datetime.date, item_end: datetime.date, weeks: list):
    """Return (start_col, span) for an item over the given week list, or (None, None)."""
    start_col = end_col = None
    for i, ws in enumerate(weeks):
        we = ws + datetime.timedelta(days=6)
        if item_start <= we and item_end >= ws:
            if start_col is None:
                start_col = i
            end_col = i
    if start_col is None:
        return None, None
    return start_col, end_col - start_col + 1
