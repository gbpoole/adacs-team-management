"""Unit tests for planning models and business logic."""
import datetime

from django.test import TestCase

from apps.planning.models import COLOUR_PALETTE
from apps.planning.models import Semester
from apps.planning.models import SemesterType
from apps.planning.models import _next_colour
from apps.planning.tests.factories import DeveloperProfileFactory
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
