"""Unit tests for _timeline helper functions."""
import datetime
import types

from django.test import SimpleTestCase

from apps.planning.views._timeline import _build_lane_cells
from apps.planning.views._timeline import _build_timeline_layers
from apps.planning.views._timeline import _coverage
from apps.planning.views._timeline import _week_starts


def _phase(name="P"):
    return types.SimpleNamespace(name=name)


class TestWeekStarts(SimpleTestCase):
    def test_single_week(self):
        weeks = _week_starts(datetime.date(2026, 1, 5), datetime.date(2026, 1, 9))
        self.assertEqual(len(weeks), 1)
        self.assertEqual(weeks[0].weekday(), 0)  # Monday

    def test_multiple_weeks(self):
        weeks = _week_starts(datetime.date(2026, 1, 5), datetime.date(2026, 2, 2))
        self.assertGreater(len(weeks), 1)
        for w in weeks:
            self.assertEqual(w.weekday(), 0)

    def test_start_mid_week_gives_monday(self):
        # Wednesday 2026-01-07
        weeks = _week_starts(datetime.date(2026, 1, 7), datetime.date(2026, 1, 13))
        self.assertEqual(weeks[0], datetime.date(2026, 1, 5))  # preceding Monday


class TestCoverage(SimpleTestCase):
    def setUp(self):
        # 4 weeks: Jan 5, 12, 19, 26
        self.weeks = _week_starts(datetime.date(2026, 1, 5), datetime.date(2026, 1, 26))

    def test_item_within_first_week(self):
        start_col, span = _coverage(datetime.date(2026, 1, 5), datetime.date(2026, 1, 11), self.weeks)
        self.assertEqual(start_col, 0)
        self.assertEqual(span, 1)

    def test_item_spanning_two_weeks(self):
        start_col, span = _coverage(datetime.date(2026, 1, 5), datetime.date(2026, 1, 18), self.weeks)
        self.assertEqual(start_col, 0)
        self.assertEqual(span, 2)

    def test_item_spanning_all_weeks(self):
        start_col, span = _coverage(datetime.date(2026, 1, 5), datetime.date(2026, 2, 2), self.weeks)
        self.assertEqual(start_col, 0)
        self.assertEqual(span, 4)

    def test_item_before_range_returns_none(self):
        start_col, span = _coverage(datetime.date(2025, 12, 1), datetime.date(2025, 12, 31), self.weeks)
        self.assertIsNone(start_col)
        self.assertIsNone(span)

    def test_item_after_range_returns_none(self):
        # Last week (Jan 26) ends Feb 1; Feb 2+ is clearly outside
        start_col, span = _coverage(datetime.date(2026, 2, 2), datetime.date(2026, 2, 28), self.weeks)
        self.assertIsNone(start_col)
        self.assertIsNone(span)

    def test_item_at_last_week(self):
        start_col, span = _coverage(datetime.date(2026, 1, 26), datetime.date(2026, 2, 1), self.weeks)
        self.assertEqual(start_col, 3)
        self.assertEqual(span, 1)


class TestBuildLaneCells(SimpleTestCase):
    def test_empty_lane_all_empty_cells(self):
        cells = _build_lane_cells(4, [])
        types_ = {c["type"] for c in cells}
        self.assertEqual(types_, {"empty"})
        total_span = sum(c["colspan"] for c in cells)
        self.assertEqual(total_span, 4)

    def test_single_phase_cell_plus_empty_gaps(self):
        ph = _phase()
        cells = _build_lane_cells(4, [(1, 1, ph)])
        phase_cells = [c for c in cells if c["type"] == "phase"]
        empty_cells = [c for c in cells if c["type"] == "empty"]
        self.assertEqual(len(phase_cells), 1)
        self.assertEqual(phase_cells[0]["colspan"], 1)
        self.assertEqual(phase_cells[0]["col_start"], 1)
        # Empty cells cover cols 0 and 2-3
        empty_span = sum(c["colspan"] for c in empty_cells)
        self.assertEqual(empty_span, 3)

    def test_phase_spanning_full_width_no_empty_cells(self):
        ph = _phase()
        cells = _build_lane_cells(4, [(0, 4, ph)])
        self.assertEqual(len(cells), 1)
        self.assertEqual(cells[0]["type"], "phase")
        self.assertEqual(cells[0]["colspan"], 4)

    def test_two_adjacent_phases(self):
        ph1, ph2 = _phase("A"), _phase("B")
        cells = _build_lane_cells(4, [(0, 2, ph1), (2, 2, ph2)])
        phase_cells = [c for c in cells if c["type"] == "phase"]
        self.assertEqual(len(phase_cells), 2)
        self.assertFalse(any(c["type"] == "empty" for c in cells))

    def test_overlapping_phases_both_emitted(self):
        ph1, ph2 = _phase("A"), _phase("B")
        # Both start at col 0 — both should still be emitted
        cells = _build_lane_cells(4, [(0, 2, ph1), (0, 4, ph2)])
        phase_cells = [c for c in cells if c["type"] == "phase"]
        self.assertEqual(len(phase_cells), 2)

    def test_empty_cells_dont_overlap_phase_columns(self):
        ph = _phase()
        cells = _build_lane_cells(4, [(1, 2, ph)])
        empty_cols = set()
        for c in cells:
            if c["type"] == "empty":
                for col in range(c["col_start"], c["col_end"] + 1):
                    empty_cols.add(col)
        # Cols 1 and 2 are covered by phase — should not appear in empty cells
        self.assertNotIn(1, empty_cols)
        self.assertNotIn(2, empty_cols)


class TestBuildTimelineLayers(SimpleTestCase):
    def test_no_phases_returns_single_empty_layer(self):
        layers = _build_timeline_layers(4, [], set())
        self.assertEqual(len(layers), 1)
        types_ = {c["type"] for c in layers[0]}
        self.assertEqual(types_, {"empty"})

    def test_non_overlapping_phases_fit_in_one_layer(self):
        ph1, ph2 = _phase("A"), _phase("B")
        layers = _build_timeline_layers(4, [(0, 1, ph1), (2, 1, ph2)], set())
        self.assertEqual(len(layers), 1)
        phase_cells = [c for c in layers[0] if c["type"] == "phase"]
        self.assertEqual(len(phase_cells), 2)

    def test_overlapping_phases_go_to_separate_layers(self):
        ph1, ph2 = _phase("A"), _phase("B")
        # Both occupy cols 0-1 — must be in separate layers
        layers = _build_timeline_layers(4, [(0, 2, ph1), (0, 2, ph2)], set())
        self.assertEqual(len(layers), 2)

    def test_leave_cells_inserted_in_empty_gaps(self):
        leave_week_set = {1}  # col 1 is a leave week
        layers = _build_timeline_layers(4, [], leave_week_set)
        leave_cells = [c for c in layers[0] if c["type"] == "leave"]
        self.assertTrue(len(leave_cells) > 0)
        self.assertEqual(leave_cells[0]["col_start"], 1)

    def test_leave_cells_not_in_phase_columns(self):
        ph = _phase()
        leave_week_set = {0, 1, 2, 3}
        layers = _build_timeline_layers(4, [(1, 2, ph)], leave_week_set)
        for layer in layers:
            for cell in layer:
                if cell["type"] == "leave":
                    # Leave cells should not overlap with the phase (cols 1-2)
                    for col in range(cell["col_start"], cell["col_end"] + 1):
                        self.assertNotIn(col, [1, 2],
                            msg=f"Leave cell at col {col} overlaps with phase at cols 1-2")

    def test_cell_colspan_sum_equals_n_weeks(self):
        ph = _phase()
        layers = _build_timeline_layers(4, [(1, 1, ph)], {3})
        for layer in layers:
            total = sum(c["colspan"] for c in layer)
            self.assertEqual(total, 4)

    def test_three_mutually_overlapping_phases_give_three_layers(self):
        segments = [(0, 4, _phase(f"P{i}")) for i in range(3)]
        layers = _build_timeline_layers(4, segments, set())
        self.assertEqual(len(layers), 3)
