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
            cells.append({
                "type": "empty",
                "colspan": end - col + 1,
                "phase": None,
                "col_start": col,
                "col_end": end,
            })
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


def _build_timeline_layers(n_weeks, phase_segments, leave_week_set):
    """
    Assign phase_segments to non-overlapping layers and build cell lists.

    Uses a first-fit algorithm: each phase is placed in the first layer where
    it does not overlap any existing phase.

    phase_segments: list of (start_col, span, phase)
    leave_week_set: set of week indices covered by leave

    Returns list of layers; each layer is a list of cell dicts:
      {'type': 'empty'|'leave'|'phase', 'colspan': int, 'phase': Phase|None,
       'col_start': int, 'col_end': int}
    """
    layers_data = []
    for seg in sorted(phase_segments, key=lambda x: x[0]):
        start_col, span, phase = seg
        placed = False
        for layer in layers_data:
            if not any(s < start_col + span and s + p > start_col for s, p, _ in layer):
                layer.append(seg)
                placed = True
                break
        if not placed:
            layers_data.append([seg])

    if not layers_data:
        layers_data = [[]]

    result = []
    for layer in layers_data:
        phase_at = {s: (s, span, ph) for s, span, ph in layer}
        cells = []
        col = 0
        while col < n_weeks:
            if col in phase_at:
                s, span, ph = phase_at[col]
                cells.append({
                    "type": "phase",
                    "colspan": span,
                    "phase": ph,
                    "col_start": s,
                    "col_end": s + span - 1,
                })
                col += span
            else:
                next_phase = min((s for s in phase_at if s > col), default=n_weeks)
                run = col
                while run < next_phase:
                    if run in leave_week_set:
                        end = run
                        while end + 1 < next_phase and end + 1 in leave_week_set:
                            end += 1
                        cells.append({
                            "type": "leave",
                            "colspan": end - run + 1,
                            "phase": None,
                            "col_start": run,
                            "col_end": end,
                        })
                        run = end + 1
                    else:
                        end = run
                        while end + 1 < next_phase and end + 1 not in leave_week_set:
                            end += 1
                        cells.append({
                            "type": "empty",
                            "colspan": end - run + 1,
                            "phase": None,
                            "col_start": run,
                            "col_end": end,
                        })
                        run = end + 1
                col = next_phase
        result.append(cells)
    return result
