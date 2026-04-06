"""Unit tests for planning models and business logic."""
import datetime

from django.test import TestCase

from apps.planning.models import COLOUR_PALETTE
from apps.planning.models import DeveloperLane
from apps.planning.models import Phase
from apps.planning.models import Semester
from apps.planning.models import SemesterType
from apps.planning.models import _create_next_lane
from apps.planning.models import _delete_empty_lane
from apps.planning.models import _find_or_create_non_overlapping_lane
from apps.planning.models import _next_colour
from apps.planning.tests.factories import DeveloperLaneFactory
from apps.planning.tests.factories import DeveloperProfileFactory
from apps.planning.tests.factories import LeaveFactory
from apps.planning.tests.factories import ProjectAllocationFactory
from apps.planning.tests.factories import ProjectFactory
from apps.planning.tests.factories import ProjectSemesterNameFactory
from apps.planning.tests.factories import SemesterDeveloperFactory
from apps.planning.tests.factories import SemesterFactory


class TestNextColour(TestCase):
    def test_returns_first_unused(self):
        used = set()
        colour = _next_colour(used)
        self.assertEqual(colour, COLOUR_PALETTE[0][0])

    def test_skips_used(self):
        used = {COLOUR_PALETTE[0][0]}
        colour = _next_colour(used)
        self.assertEqual(colour, COLOUR_PALETTE[1][0])

    def test_all_used_wraps_to_first(self):
        used = {hex_val for hex_val, _ in COLOUR_PALETTE}
        colour = _next_colour(used)
        self.assertEqual(colour, COLOUR_PALETTE[0][0])


class TestDeveloperProfileColour(TestCase):
    def test_colour_auto_assigned_on_save(self):
        dev = DeveloperProfileFactory(colour="")
        self.assertIn(dev.colour, [h for h, _ in COLOUR_PALETTE])

    def test_colour_cycles_for_multiple_devs(self):
        d1 = DeveloperProfileFactory(colour="")
        d2 = DeveloperProfileFactory(colour="")
        self.assertNotEqual(d1.colour, d2.colour)


class TestSemesterDates(TestCase):
    def test_a_semester_start_end(self):
        sem = SemesterFactory(year=2026, semester_type=SemesterType.A)
        self.assertEqual(sem.start_date, datetime.date(2026, 1, 1))
        self.assertEqual(sem.end_date, datetime.date(2026, 6, 30))

    def test_b_semester_start_end(self):
        sem = SemesterFactory(year=2026, semester_type=SemesterType.B)
        self.assertEqual(sem.start_date, datetime.date(2026, 7, 1))
        self.assertEqual(sem.end_date, datetime.date(2026, 12, 31))

    def test_code(self):
        sem = SemesterFactory(year=2026, semester_type=SemesterType.A)
        self.assertEqual(sem.code, "2026A")

    def test_str(self):
        sem = SemesterFactory(year=2026, semester_type=SemesterType.B)
        self.assertEqual(str(sem), "2026B")


class TestSemesterGetCurrent(TestCase):
    def test_get_current_creates_if_missing(self):
        today = datetime.date.today()
        expected_type = SemesterType.A if today.month <= 6 else SemesterType.B
        sem = Semester.get_current()
        self.assertEqual(sem.year, today.year)
        self.assertEqual(sem.semester_type, expected_type)

    def test_get_current_idempotent(self):
        s1 = Semester.get_current()
        s2 = Semester.get_current()
        self.assertEqual(s1.pk, s2.pk)


class TestProjectNameForSemester(TestCase):
    def setUp(self):
        self.sem_a = SemesterFactory(year=2026, semester_type=SemesterType.A)
        self.sem_b = SemesterFactory(year=2026, semester_type=SemesterType.B)
        self.project = ProjectFactory()

    def test_returns_name_for_exact_semester(self):
        ProjectSemesterNameFactory(
            project=self.project, semester=self.sem_a, name="Alpha",
        )
        self.assertEqual(self.project.name_for_semester(self.sem_a), "Alpha")

    def test_returns_fallback_for_later_semester(self):
        ProjectSemesterNameFactory(
            project=self.project, semester=self.sem_a, name="Alpha",
        )
        self.assertEqual(self.project.name_for_semester(self.sem_b), "Alpha")

    def test_returns_placeholder_when_no_name(self):
        name = self.project.name_for_semester(self.sem_a)
        self.assertIn(str(self.project.pk), name)


class TestProjectAllocationTotalWeeks(TestCase):
    def test_total_weeks_sums_new_and_carryover(self):
        alloc = ProjectAllocationFactory(weeks_new=8, weeks_carryover=2)
        self.assertEqual(alloc.total_weeks, 10)


class TestSemesterDeveloper(TestCase):
    def test_str(self):
        record = SemesterDeveloperFactory(effort_available=26)
        self.assertIn("26", str(record))


# ---------------------------------------------------------------------------
# Phase.save() — auto lane assignment
# ---------------------------------------------------------------------------

class TestPhaseLaneAutoAssignment(TestCase):
    def setUp(self):
        self.dev = DeveloperProfileFactory()
        self.sem = SemesterFactory()
        self.project = ProjectFactory()

    def _make_phase(self, start, end, **kwargs):
        return Phase.objects.create(
            developer=self.dev,
            project=self.project,
            semester=self.sem,
            start_date=start,
            end_date=end,
            **kwargs,
        )

    def test_lane_assigned_on_create(self):
        phase = self._make_phase(datetime.date(2026, 1, 5), datetime.date(2026, 2, 2))
        self.assertIsNotNone(phase.lane_id)

    def test_lane_auto_assigned_via_factory(self):
        """PhaseFactory (which omits lane) should produce a phase with a lane assigned."""
        from apps.planning.tests.factories import PhaseFactory
        phase = PhaseFactory()
        self.assertIsNotNone(phase.lane_id)

    def test_lane_not_reassigned_when_explicit(self):
        lane = DeveloperLaneFactory(developer=self.dev, semester=self.sem, order=0)
        phase = Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 1, 5), end_date=datetime.date(2026, 2, 2),
            lane=lane,
        )
        self.assertEqual(phase.lane_id, lane.pk)

    def test_non_overlapping_phases_share_lane(self):
        phase1 = self._make_phase(datetime.date(2026, 1, 5), datetime.date(2026, 2, 2))
        phase2 = self._make_phase(datetime.date(2026, 3, 2), datetime.date(2026, 4, 6))
        self.assertEqual(phase1.lane_id, phase2.lane_id)

    def test_overlapping_phases_get_separate_lanes(self):
        phase1 = self._make_phase(datetime.date(2026, 1, 5), datetime.date(2026, 2, 2))
        phase2 = self._make_phase(datetime.date(2026, 1, 12), datetime.date(2026, 2, 9))
        self.assertNotEqual(phase1.lane_id, phase2.lane_id)

    def test_three_way_overlap_creates_three_lanes(self):
        phase1 = self._make_phase(datetime.date(2026, 1, 5), datetime.date(2026, 3, 2))
        phase2 = self._make_phase(datetime.date(2026, 1, 12), datetime.date(2026, 3, 9))
        phase3 = self._make_phase(datetime.date(2026, 1, 19), datetime.date(2026, 3, 16))
        lanes = {phase1.lane_id, phase2.lane_id, phase3.lane_id}
        self.assertEqual(len(lanes), 3)


# ---------------------------------------------------------------------------
# _find_or_create_non_overlapping_lane()
# ---------------------------------------------------------------------------

class TestFindOrCreateNonOverlappingLane(TestCase):
    def setUp(self):
        self.dev = DeveloperProfileFactory()
        self.sem = SemesterFactory()
        self.project = ProjectFactory()
        self.preferred = DeveloperLaneFactory(developer=self.dev, semester=self.sem, order=0)

    def _phase_in_lane(self, lane, start, end):
        """Create a phase directly in a specific lane, bypassing auto-assignment."""
        phase = Phase(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=start, end_date=end, lane=lane,
        )
        Phase.save(phase)  # calls super since lane is already set
        return phase

    def test_returns_preferred_when_lane_is_empty(self):
        result = _find_or_create_non_overlapping_lane(
            self.dev, self.sem,
            datetime.date(2026, 1, 5), datetime.date(2026, 2, 2),
            self.preferred,
        )
        self.assertEqual(result, self.preferred)

    def test_returns_preferred_when_existing_phase_does_not_overlap(self):
        # Phase ends before our target start
        Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 1, 5), end_date=datetime.date(2026, 1, 30),
            lane=self.preferred,
        )
        result = _find_or_create_non_overlapping_lane(
            self.dev, self.sem,
            datetime.date(2026, 3, 2), datetime.date(2026, 4, 6),
            self.preferred,
        )
        self.assertEqual(result, self.preferred)

    def test_bumps_to_second_lane_on_overlap(self):
        second = DeveloperLaneFactory(developer=self.dev, semester=self.sem, order=1)
        Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 1, 5), end_date=datetime.date(2026, 2, 2),
            lane=self.preferred,
        )
        result = _find_or_create_non_overlapping_lane(
            self.dev, self.sem,
            datetime.date(2026, 1, 12), datetime.date(2026, 2, 9),
            self.preferred,
        )
        self.assertEqual(result, second)

    def test_creates_new_lane_when_all_overlap(self):
        Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 1, 5), end_date=datetime.date(2026, 2, 2),
            lane=self.preferred,
        )
        before_count = DeveloperLane.objects.filter(developer=self.dev, semester=self.sem).count()
        result = _find_or_create_non_overlapping_lane(
            self.dev, self.sem,
            datetime.date(2026, 1, 12), datetime.date(2026, 2, 9),
            self.preferred,
        )
        after_count = DeveloperLane.objects.filter(developer=self.dev, semester=self.sem).count()
        self.assertEqual(after_count, before_count + 1)
        self.assertEqual(result.order, self.preferred.order + 1)

    def test_first_lane_created_at_order_zero(self):
        # No lanes exist for this developer/semester
        dev2 = DeveloperProfileFactory()
        lane = DeveloperLane.objects.create(developer=dev2, semester=self.sem, order=0)
        result = _find_or_create_non_overlapping_lane(
            dev2, self.sem,
            datetime.date(2026, 1, 5), datetime.date(2026, 2, 2),
            lane,
        )
        self.assertEqual(result.order, 0)

    def test_exclude_phase_pk_allows_self_update(self):
        """A phase can slide its own dates within the same lane without being bumped."""
        phase = Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 1, 5), end_date=datetime.date(2026, 2, 2),
            lane=self.preferred,
        )
        result = _find_or_create_non_overlapping_lane(
            self.dev, self.sem,
            datetime.date(2026, 1, 12), datetime.date(2026, 2, 9),
            self.preferred,
            exclude_phase_pk=phase.pk,
        )
        self.assertEqual(result, self.preferred)

    def test_adjacent_dates_are_not_overlap(self):
        """Phase ending Jan 31 and new phase starting Feb 1 must not be counted as overlap."""
        Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 1, 5), end_date=datetime.date(2026, 1, 30),
            lane=self.preferred,
        )
        result = _find_or_create_non_overlapping_lane(
            self.dev, self.sem,
            datetime.date(2026, 2, 2), datetime.date(2026, 3, 2),
            self.preferred,
        )
        self.assertEqual(result, self.preferred)


# ---------------------------------------------------------------------------
# _create_next_lane()
# ---------------------------------------------------------------------------

class TestCreateNextLane(TestCase):
    def setUp(self):
        self.dev = DeveloperProfileFactory()
        self.sem = SemesterFactory()

    def test_creates_order_zero_when_no_lanes(self):
        lane = _create_next_lane(self.dev, self.sem)
        self.assertEqual(lane.order, 0)
        self.assertEqual(lane.developer, self.dev)
        self.assertEqual(lane.semester, self.sem)

    def test_creates_order_one_when_one_lane_at_zero(self):
        DeveloperLane.objects.create(developer=self.dev, semester=self.sem, order=0)
        lane = _create_next_lane(self.dev, self.sem)
        self.assertEqual(lane.order, 1)

    def test_creates_max_plus_one(self):
        for order in (0, 2, 7):
            DeveloperLane.objects.create(developer=self.dev, semester=self.sem, order=order)
        lane = _create_next_lane(self.dev, self.sem)
        self.assertEqual(lane.order, 8)


# ---------------------------------------------------------------------------
# _delete_empty_lane()
# ---------------------------------------------------------------------------

class TestDeleteEmptyLane(TestCase):
    def setUp(self):
        self.dev = DeveloperProfileFactory()
        self.sem = SemesterFactory()
        self.project = ProjectFactory()

    def test_deletes_empty_lane(self):
        lane = DeveloperLane.objects.create(developer=self.dev, semester=self.sem, order=0)
        pk = lane.pk
        _delete_empty_lane(lane)
        self.assertFalse(DeveloperLane.objects.filter(pk=pk).exists())

    def test_keeps_lane_with_phases(self):
        lane = DeveloperLane.objects.create(developer=self.dev, semester=self.sem, order=0)
        Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 1, 5), end_date=datetime.date(2026, 2, 2),
            lane=lane,
        )
        _delete_empty_lane(lane)
        self.assertTrue(DeveloperLane.objects.filter(pk=lane.pk).exists())

    def test_none_is_noop(self):
        # Must not raise
        _delete_empty_lane(None)


# ---------------------------------------------------------------------------
# Phase.effort_weeks()
# ---------------------------------------------------------------------------

class TestPhaseEffortWeeks(TestCase):
    def setUp(self):
        self.dev = DeveloperProfileFactory()
        self.sem = SemesterFactory()
        self.project = ProjectFactory()

    def _phase(self, start, end, multiplier=1.0):
        return Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=start, end_date=end, effort_multiplier=multiplier,
        )

    def test_basic_five_day_week(self):
        # Mon 5 Jan – Fri 9 Jan = 5 working days = 1.0 week
        phase = self._phase(datetime.date(2026, 1, 5), datetime.date(2026, 1, 9))
        self.assertAlmostEqual(phase.effort_weeks(), 1.0)

    def test_excludes_weekends(self):
        # Mon 5 Jan – Sun 11 Jan = 5 working days = 1.0 week
        phase = self._phase(datetime.date(2026, 1, 5), datetime.date(2026, 1, 11))
        self.assertAlmostEqual(phase.effort_weeks(), 1.0)

    def test_leave_subtracts_working_days(self):
        # Mon 5 Jan – Fri 16 Jan = 10 working days = 2.0 weeks
        # Leave Mon 12 Jan – Fri 16 Jan = 5 working days
        # Net = 1.0 week
        phase = self._phase(datetime.date(2026, 1, 5), datetime.date(2026, 1, 16))
        LeaveFactory(
            developer=self.dev,
            start_date=datetime.date(2026, 1, 12),
            end_date=datetime.date(2026, 1, 16),
        )
        self.assertAlmostEqual(phase.effort_weeks(), 1.0)

    def test_effort_multiplier_scales_result(self):
        # 5 working days × 0.5 = 0.5 weeks
        phase = self._phase(
            datetime.date(2026, 1, 5), datetime.date(2026, 1, 9), multiplier=0.5,
        )
        self.assertAlmostEqual(phase.effort_weeks(), 0.5)

    def test_full_leave_returns_zero(self):
        # Phase = 1 week; leave covers entire phase
        phase = self._phase(datetime.date(2026, 1, 5), datetime.date(2026, 1, 9))
        LeaveFactory(
            developer=self.dev,
            start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 1, 9),
        )
        self.assertAlmostEqual(phase.effort_weeks(), 0.0)
