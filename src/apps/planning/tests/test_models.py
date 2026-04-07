"""Unit tests for planning models and business logic."""
import datetime
from unittest.mock import patch

from django.test import TestCase

from django.db import IntegrityError
from django.db.models import ProtectedError

from apps.planning.models import COLOUR_PALETTE
from apps.planning.models import DeveloperLane
from apps.planning.models import Leave
from apps.planning.models import ObserverProfile
from apps.planning.models import Phase
from apps.planning.models import Project
from apps.planning.models import ProjectSemesterName
from apps.planning.models import Semester
from apps.planning.models import SemesterDeveloper
from apps.planning.models import SemesterType
from django.core.exceptions import ValidationError

from apps.planning.models import _assign_colour_if_blank
from apps.planning.models import _create_next_lane
from apps.planning.models import _delete_empty_lane
from apps.planning.models import _find_or_create_non_overlapping_lane
from apps.planning.models import _next_colour
from apps.planning.tests.factories import DeveloperLaneFactory
from apps.planning.tests.factories import DeveloperProfileFactory
from apps.planning.tests.factories import LeaveFactory
from apps.planning.tests.factories import ObserverProfileFactory
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
    def test_get_current_creates_semester_A_in_june(self):
        fixed = datetime.date(2026, 6, 15)
        with patch("apps.planning.models.datetime") as mock_dt:
            mock_dt.date.today.return_value = fixed
            sem = Semester.get_current()
        self.assertEqual(sem.year, 2026)
        self.assertEqual(sem.semester_type, SemesterType.A)

    def test_get_current_creates_semester_B_in_july(self):
        fixed = datetime.date(2026, 7, 1)
        with patch("apps.planning.models.datetime") as mock_dt:
            mock_dt.date.today.return_value = fixed
            sem = Semester.get_current()
        self.assertEqual(sem.year, 2026)
        self.assertEqual(sem.semester_type, SemesterType.B)

    def test_get_current_idempotent(self):
        fixed = datetime.date(2026, 3, 1)
        with patch("apps.planning.models.datetime") as mock_dt:
            mock_dt.date.today.return_value = fixed
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
        self.assertEqual(name, f"Project #{self.project.pk}")

    def test_fallback_returns_most_recent_of_multiple_priors(self):
        sem_2025a = SemesterFactory(year=2025, semester_type=SemesterType.A)
        sem_2025b = SemesterFactory(year=2025, semester_type=SemesterType.B)
        sem_2026b = SemesterFactory(year=2026, semester_type=SemesterType.B)
        ProjectSemesterNameFactory(project=self.project, semester=sem_2025a, name="Old Name")
        ProjectSemesterNameFactory(project=self.project, semester=sem_2025b, name="Newer Name")
        # 2026B has no direct name; should fall back to 2025B, not 2025A
        self.assertEqual(self.project.name_for_semester(sem_2026b), "Newer Name")


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

    def test_other_developer_leave_not_subtracted(self):
        # Phase Mon 5 Jan – Fri 16 Jan = 2.0 weeks
        phase = self._phase(datetime.date(2026, 1, 5), datetime.date(2026, 1, 16))
        other_dev = DeveloperProfileFactory()
        LeaveFactory(
            developer=other_dev,
            start_date=datetime.date(2026, 1, 12),
            end_date=datetime.date(2026, 1, 16),
        )
        # Other developer's leave must not affect this phase
        self.assertAlmostEqual(phase.effort_weeks(), 2.0)

    def test_leave_on_weekend_only_does_not_reduce_effort(self):
        # Phase Mon 5 Jan – Fri 9 Jan = 5 work days = 1.0 week
        # Leave covers Sat 3 Jan – Sun 4 Jan only — no work days overlap
        phase = self._phase(datetime.date(2026, 1, 5), datetime.date(2026, 1, 9))
        LeaveFactory(
            developer=self.dev,
            start_date=datetime.date(2026, 1, 3),
            end_date=datetime.date(2026, 1, 4),
        )
        self.assertAlmostEqual(phase.effort_weeks(), 1.0)

    def test_multiple_non_contiguous_leave_periods(self):
        # Phase Mon 5 Jan – Fri 23 Jan = 15 work days = 3.0 weeks
        # Leave week 1 (5 days) and leave week 3 (5 days) → 5 days remain = 1.0 week
        phase = self._phase(datetime.date(2026, 1, 5), datetime.date(2026, 1, 23))
        LeaveFactory(developer=self.dev,
                     start_date=datetime.date(2026, 1, 5), end_date=datetime.date(2026, 1, 9))
        LeaveFactory(developer=self.dev,
                     start_date=datetime.date(2026, 1, 19), end_date=datetime.date(2026, 1, 23))
        self.assertAlmostEqual(phase.effort_weeks(), 1.0)

    def test_leave_partially_overlapping_phase_start(self):
        # Phase Wed 7 Jan – Fri 9 Jan = 3 work days
        # Leave Mon 5 Jan – Wed 7 Jan: only Wed 7 Jan falls inside the phase → 2 work days remain
        phase = self._phase(datetime.date(2026, 1, 7), datetime.date(2026, 1, 9))
        LeaveFactory(developer=self.dev,
                     start_date=datetime.date(2026, 1, 5), end_date=datetime.date(2026, 1, 7))
        self.assertAlmostEqual(phase.effort_weeks(), round(2 / 5, 2))

    def test_effort_multiplier_zero_returns_zero(self):
        phase = self._phase(datetime.date(2026, 1, 5), datetime.date(2026, 1, 9), multiplier=0.0)
        self.assertAlmostEqual(phase.effort_weeks(), 0.0)

    def test_single_day_phase(self):
        # Mon 5 Jan only = 1 work day = 0.2 weeks
        phase = self._phase(datetime.date(2026, 1, 5), datetime.date(2026, 1, 5))
        self.assertAlmostEqual(phase.effort_weeks(), 0.2)


# ---------------------------------------------------------------------------
# Project.colour auto-assignment
# ---------------------------------------------------------------------------


class TestProjectColour(TestCase):
    def test_colour_auto_assigned_on_save(self):
        project = ProjectFactory(colour="")
        self.assertIn(project.colour, [h for h, _ in COLOUR_PALETTE])

    def test_colour_cycles_for_multiple_projects(self):
        p1 = ProjectFactory(colour="")
        p2 = ProjectFactory(colour="")
        self.assertNotEqual(p1.colour, p2.colour)

    def test_explicit_colour_preserved(self):
        colour = COLOUR_PALETTE[0][0]
        project = ProjectFactory(colour=colour)
        self.assertEqual(project.colour, colour)


# ---------------------------------------------------------------------------
# ObserverProfile.project_access M2M
# ---------------------------------------------------------------------------


class TestObserverProjectAccess(TestCase):
    def setUp(self):
        self.obs = ObserverProfileFactory()
        self.project = ProjectFactory()

    def test_no_access_by_default(self):
        self.assertEqual(self.obs.project_access.count(), 0)

    def test_add_gives_access(self):
        self.obs.project_access.add(self.project)
        self.assertIn(self.project, self.obs.project_access.all())

    def test_remove_revokes_access(self):
        self.obs.project_access.add(self.project)
        self.obs.project_access.remove(self.project)
        self.assertNotIn(self.project, self.obs.project_access.all())

    def test_deleting_project_removes_it_from_access(self):
        self.obs.project_access.add(self.project)
        project_pk = self.project.pk
        self.project.delete()
        self.assertFalse(self.obs.project_access.filter(pk=project_pk).exists())

    def test_deleting_observer_does_not_delete_project(self):
        self.obs.project_access.add(self.project)
        project_pk = self.project.pk
        self.obs.delete()
        self.assertTrue(Project.objects.filter(pk=project_pk).exists())


# ---------------------------------------------------------------------------
# DeveloperLane model constraints
# ---------------------------------------------------------------------------


class TestDeveloperLaneModel(TestCase):
    def setUp(self):
        self.dev = DeveloperProfileFactory()
        self.sem = SemesterFactory()
        self.project = ProjectFactory()

    def test_str_contains_order_and_semester(self):
        lane = DeveloperLane.objects.create(developer=self.dev, semester=self.sem, order=0)
        s = str(lane)
        self.assertIn("0", s)
        self.assertIn(str(self.sem), s)

    def test_unique_together_prevents_duplicate_order(self):
        DeveloperLane.objects.create(developer=self.dev, semester=self.sem, order=0)
        with self.assertRaises(IntegrityError):
            DeveloperLane.objects.create(developer=self.dev, semester=self.sem, order=0)

    def test_ordering_by_order_then_pk(self):
        l2 = DeveloperLane.objects.create(developer=self.dev, semester=self.sem, order=2)
        l0 = DeveloperLane.objects.create(developer=self.dev, semester=self.sem, order=0)
        l1 = DeveloperLane.objects.create(developer=self.dev, semester=self.sem, order=1)
        lanes = list(DeveloperLane.objects.filter(developer=self.dev, semester=self.sem))
        self.assertEqual(lanes, [l0, l1, l2])

    def test_lane_protected_when_it_has_phases(self):
        lane = DeveloperLane.objects.create(developer=self.dev, semester=self.sem, order=0)
        Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 1, 5), end_date=datetime.date(2026, 2, 2),
            lane=lane,
        )
        with self.assertRaises(ProtectedError):
            lane.delete()


# ---------------------------------------------------------------------------
# Leave model
# ---------------------------------------------------------------------------


class TestLeaveModel(TestCase):
    def setUp(self):
        self.dev = DeveloperProfileFactory()

    def test_str_contains_developer_and_dates(self):
        leave = LeaveFactory(
            developer=self.dev,
            start_date=datetime.date(2026, 3, 1),
            end_date=datetime.date(2026, 3, 7),
        )
        s = str(leave)
        self.assertIn(self.dev.user.email, s)

    def test_cascade_delete_with_developer(self):
        leave = LeaveFactory(developer=self.dev)
        pk = leave.pk
        self.dev.delete()
        self.assertFalse(Leave.objects.filter(pk=pk).exists())

    def test_ordering_by_start_date(self):
        l2 = LeaveFactory(developer=self.dev, start_date=datetime.date(2026, 5, 1),
                          end_date=datetime.date(2026, 5, 7))
        l1 = LeaveFactory(developer=self.dev, start_date=datetime.date(2026, 3, 1),
                          end_date=datetime.date(2026, 3, 7))
        leaves = list(Leave.objects.filter(developer=self.dev))
        self.assertEqual(leaves[0].pk, l1.pk)
        self.assertEqual(leaves[1].pk, l2.pk)


# ---------------------------------------------------------------------------
# SemesterDeveloper model constraints
# ---------------------------------------------------------------------------


class TestSemesterDeveloperModel(TestCase):
    def setUp(self):
        self.dev = DeveloperProfileFactory()
        self.sem = SemesterFactory()

    def test_effort_available_defaults_to_zero(self):
        record = SemesterDeveloper.objects.create(developer=self.dev, semester=self.sem)
        self.assertEqual(record.effort_available, 0)

    def test_unique_together_prevents_duplicate(self):
        SemesterDeveloper.objects.create(developer=self.dev, semester=self.sem, effort_available=26)
        with self.assertRaises(IntegrityError):
            SemesterDeveloper.objects.create(developer=self.dev, semester=self.sem, effort_available=20)

    def test_cascade_delete_with_developer(self):
        record = SemesterDeveloper.objects.create(developer=self.dev, semester=self.sem)
        pk = record.pk
        self.dev.delete()
        self.assertFalse(SemesterDeveloper.objects.filter(pk=pk).exists())


# ---------------------------------------------------------------------------
# ProjectSemesterName model
# ---------------------------------------------------------------------------


class TestProjectSemesterNameModel(TestCase):
    def setUp(self):
        self.sem = SemesterFactory(year=2026, semester_type=SemesterType.A)
        self.project = ProjectFactory()

    def test_str_contains_name_and_semester(self):
        psn = ProjectSemesterNameFactory(
            project=self.project, semester=self.sem, name="My Project",
        )
        s = str(psn)
        self.assertIn("My Project", s)
        self.assertIn("2026A", s)

    def test_unique_together_prevents_duplicate(self):
        ProjectSemesterNameFactory(project=self.project, semester=self.sem, name="First")
        with self.assertRaises(IntegrityError):
            ProjectSemesterName.objects.create(
                project=self.project, semester=self.sem, name="Second",
            )

    def test_cascade_delete_with_project(self):
        psn = ProjectSemesterNameFactory(
            project=self.project, semester=self.sem, name="My Project",
        )
        pk = psn.pk
        self.project.delete()
        self.assertFalse(ProjectSemesterName.objects.filter(pk=pk).exists())


class TestAssignColourIfBlank(TestCase):
    """Tests for the shared _assign_colour_if_blank() helper."""

    def test_assigns_when_blank(self):
        profile = DeveloperProfileFactory(colour="")
        # Factory triggers save(), which calls _assign_colour_if_blank
        self.assertIn(profile.colour, [hex_val for hex_val, _ in COLOUR_PALETTE])

    def test_no_op_when_colour_set(self):
        profile = DeveloperProfileFactory(colour="#4E79A7")
        original = profile.colour
        _assign_colour_if_blank(profile, type(profile))
        self.assertEqual(profile.colour, original)

    def test_developer_profile_and_project_both_use_palette_colours(self):
        dev = DeveloperProfileFactory(colour="")
        proj = ProjectFactory(colour="")
        self.assertIn(dev.colour, [hex_val for hex_val, _ in COLOUR_PALETTE])
        self.assertIn(proj.colour, [hex_val for hex_val, _ in COLOUR_PALETTE])


class TestLeaveValidation(TestCase):
    """Tests for Leave.clean() model-level validation."""

    def setUp(self):
        self.dev = DeveloperProfileFactory()

    def test_clean_raises_if_end_before_start(self):
        leave = Leave(
            developer=self.dev,
            start_date=datetime.date(2026, 2, 10),
            end_date=datetime.date(2026, 2, 5),
        )
        with self.assertRaises(ValidationError):
            leave.full_clean()

    def test_clean_passes_when_end_equals_start(self):
        leave = Leave(
            developer=self.dev,
            start_date=datetime.date(2026, 2, 5),
            end_date=datetime.date(2026, 2, 5),
        )
        leave.full_clean()  # must not raise


class TestPhaseValidation(TestCase):
    """Tests for Phase.clean() and effort_multiplier validators."""

    def setUp(self):
        self.sem = SemesterFactory()
        self.dev = DeveloperProfileFactory()
        self.proj = ProjectFactory()

    def _phase(self, start, end, multiplier=1.0):
        return Phase(
            developer=self.dev,
            project=self.proj,
            semester=self.sem,
            start_date=start,
            end_date=end,
            effort_multiplier=multiplier,
        )

    def test_clean_raises_if_end_before_start(self):
        phase = self._phase(datetime.date(2026, 2, 10), datetime.date(2026, 2, 5))
        with self.assertRaises(ValidationError):
            phase.full_clean()

    def test_clean_passes_when_end_equals_start(self):
        phase = self._phase(datetime.date(2026, 2, 5), datetime.date(2026, 2, 5))
        phase.full_clean()  # must not raise

    def test_effort_multiplier_rejects_negative(self):
        phase = self._phase(datetime.date(2026, 1, 5), datetime.date(2026, 1, 9), multiplier=-0.1)
        with self.assertRaises(ValidationError):
            phase.full_clean()

    def test_effort_multiplier_rejects_above_one(self):
        phase = self._phase(datetime.date(2026, 1, 5), datetime.date(2026, 1, 9), multiplier=1.5)
        with self.assertRaises(ValidationError):
            phase.full_clean()
