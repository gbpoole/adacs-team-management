"""Tests for the live effort computation helper (apps.planning.effort)."""

import datetime

from django.test import TestCase

from apps.planning.effort import compute_project_effort
from apps.planning.models import Project
from apps.planning.models import SemesterType
from apps.planning.tests.factories import PhaseFactory
from apps.planning.tests.factories import ProjectAllocationFactory
from apps.planning.tests.factories import ProjectFactory
from apps.planning.tests.factories import ProjectTimeEntryFactory
from apps.planning.tests.factories import SemesterDeveloperFactory
from apps.planning.tests.factories import SemesterFactory


def _make_phase(project, semester, start, end, multiplier=1.0):
    sem_dev = SemesterDeveloperFactory(semester=semester)
    return PhaseFactory(
        developer=sem_dev.developer,
        project=project,
        semester=semester,
        start_date=start,
        end_date=end,
        effort_multiplier=multiplier,
    )


class ComputeProjectEffortTests(TestCase):
    def setUp(self):
        self.sem_a = SemesterFactory(year=2026, semester_type=SemesterType.A)
        self.sem_b = SemesterFactory(year=2026, semester_type=SemesterType.B)

    def _project(self, semester, weeks_new=0, continuation_of=None):
        project = ProjectFactory(semester=semester, continuation_of=continuation_of)
        ProjectAllocationFactory(
            project=project,
            semester=semester,
            weeks_new=weeks_new,
        )
        return project

    def test_project_without_allocation_row_is_zero(self):
        project = ProjectFactory(semester=self.sem_a)
        effort = compute_project_effort([project.pk])[project.pk]
        self.assertEqual(effort.weeks_new, 0)
        self.assertEqual(effort.resourced, 0)
        self.assertEqual(effort.carryover, 0)

    def test_positive_carryover_from_parent(self):
        parent = self._project(self.sem_a, weeks_new=10)
        # 2026-02-02 is a Monday; 4 weeks (Mon-Fri x4) = 20 working days
        _make_phase(
            parent,
            self.sem_a,
            datetime.date(2026, 2, 2),
            datetime.date(2026, 2, 27),
        )
        child = self._project(self.sem_b, weeks_new=5, continuation_of=parent)
        result = compute_project_effort([child.pk])
        self.assertEqual(result[parent.pk].allocated, 4.0)
        self.assertEqual(result[child.pk].carryover, 6.0)
        self.assertEqual(result[child.pk].resourced, 11.0)

    def test_negative_carryover_when_parent_over_allocated(self):
        parent = self._project(self.sem_a, weeks_new=2)
        _make_phase(
            parent,
            self.sem_a,
            datetime.date(2026, 2, 2),
            datetime.date(2026, 2, 27),
        )  # 4 weeks allocated vs 2 resourced
        child = self._project(self.sem_b, weeks_new=5, continuation_of=parent)
        result = compute_project_effort([child.pk])
        self.assertEqual(result[child.pk].carryover, -2.0)
        self.assertEqual(result[child.pk].resourced, 3.0)

    def test_carryover_chains_recursively(self):
        sem_c = SemesterFactory(year=2027, semester_type=SemesterType.A)
        a = self._project(self.sem_a, weeks_new=10)  # unallocated 10
        b = self._project(self.sem_b, weeks_new=1, continuation_of=a)
        c = self._project(sem_c, weeks_new=2, continuation_of=b)
        result = compute_project_effort([c.pk])
        # b resourced = 1 + 10 = 11, all unallocated; c carryover = 11
        self.assertEqual(result[b.pk].resourced, 11.0)
        self.assertEqual(result[c.pk].carryover, 11.0)
        self.assertEqual(result[c.pk].resourced, 13.0)

    def test_cycle_terminates(self):
        a = self._project(self.sem_a, weeks_new=4)
        b = self._project(self.sem_a, weeks_new=6, continuation_of=a)
        # Force a cycle directly in the DB (the views reject this).
        Project.objects.filter(pk=a.pk).update(continuation_of=b.pk)
        result = compute_project_effort([a.pk, b.pk])
        self.assertIn(a.pk, result)
        self.assertIn(b.pk, result)
        # Values are finite; the revisited parent contributes zero carryover.
        self.assertEqual(result[b.pk].carryover, 4.0)

    def test_time_entries_count_toward_allocated(self):
        project = self._project(self.sem_a, weeks_new=10)
        ProjectTimeEntryFactory(project=project, weeks=3, comment="Overheads")
        effort = compute_project_effort([project.pk])[project.pk]
        self.assertEqual(effort.allocated, 3.0)
        self.assertEqual(effort.unallocated, 7.0)

    def test_parent_time_entries_reduce_child_carryover(self):
        parent = self._project(self.sem_a, weeks_new=10)
        ProjectTimeEntryFactory(project=parent, weeks=4)
        child = self._project(self.sem_b, weeks_new=0, continuation_of=parent)
        result = compute_project_effort([child.pk])
        self.assertEqual(result[child.pk].carryover, 6.0)
        self.assertEqual(result[child.pk].resourced, 6.0)

    def test_carryover_is_live_after_parent_edit(self):
        parent = self._project(self.sem_a, weeks_new=10)
        child = self._project(self.sem_b, weeks_new=0, continuation_of=parent)
        before = compute_project_effort([child.pk])[child.pk]
        self.assertEqual(before.carryover, 10.0)
        ProjectTimeEntryFactory(project=parent, weeks=2.5)
        after = compute_project_effort([child.pk])[child.pk]
        self.assertEqual(after.carryover, 7.5)

    def test_empty_input_returns_empty_dict(self):
        self.assertEqual(compute_project_effort([]), {})
