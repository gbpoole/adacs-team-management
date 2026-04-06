"""Integration tests for planning views."""
import datetime

from django.test import TestCase
from django.urls import reverse

from apps.planning.models import DeveloperLane
from apps.planning.models import Phase
from apps.planning.models import Semester
from apps.planning.tests.factories import AdminUserFactory
from apps.planning.tests.factories import DeveloperLaneFactory
from apps.planning.tests.factories import DeveloperProfileFactory
from apps.planning.tests.factories import DeveloperUserFactory
from apps.planning.tests.factories import ObserverProfileFactory
from apps.planning.tests.factories import ObserverUserFactory
from apps.planning.tests.factories import PMUserFactory
from apps.planning.tests.factories import ProjectFactory
from apps.planning.tests.factories import ProjectSemesterNameFactory
from apps.planning.tests.factories import SemesterFactory
from apps.planning.tests.factories import SemesterType


class DevelopersViewTests(TestCase):
    def setUp(self):
        self.url = reverse("planning:developers")
        self.semester = SemesterFactory(year=2026, semester_type=SemesterType.A)

    def test_redirects_anonymous(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_admin_can_access(self):
        user = AdminUserFactory()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_pm_can_access(self):
        user = PMUserFactory()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_developer_can_access(self):
        user = DeveloperUserFactory()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_observer_denied(self):
        user = ObserverUserFactory()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_shows_developer_in_table(self):
        dev_profile = DeveloperProfileFactory()
        self.client.force_login(dev_profile.user)
        response = self.client.get(self.url)
        # Template shows name when set, falling back to email
        expected = dev_profile.user.name or dev_profile.user.email
        self.assertContains(response, expected)

    def test_pm_sees_add_button(self):
        user = PMUserFactory()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertContains(response, "Add Developer")

    def test_developer_does_not_see_add_button(self):
        dev_profile = DeveloperProfileFactory()
        self.client.force_login(dev_profile.user)
        response = self.client.get(self.url)
        self.assertNotContains(response, "Add Developer")


class ObserversViewTests(TestCase):
    def setUp(self):
        self.url = reverse("planning:observers")

    def test_redirects_anonymous(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_admin_can_access(self):
        user = AdminUserFactory()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_pm_can_access(self):
        user = PMUserFactory()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_developer_denied(self):
        user = DeveloperUserFactory()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_observer_denied(self):
        user = ObserverUserFactory()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_shows_observer_in_table(self):
        obs = ObserverProfileFactory()
        admin = AdminUserFactory()
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertContains(response, obs.user.email)

    def test_project_display_names_resolved(self):
        semester = Semester.get_current()
        project = ProjectFactory()
        ProjectSemesterNameFactory(project=project, semester=semester, name="My Real Project")
        obs = ObserverProfileFactory()
        obs.project_access.add(project)
        admin = AdminUserFactory()
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertContains(response, "My Real Project")
        self.assertNotContains(response, f"Project #{project.pk}")

    def test_observer_with_no_projects_shows_none(self):
        ObserverProfileFactory()
        admin = AdminUserFactory()
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertContains(response, "None")


class ProjectsViewTests(TestCase):
    def setUp(self):
        self.url = reverse("planning:projects")
        self.semester = SemesterFactory(year=2026, semester_type=SemesterType.A)

    def test_redirects_anonymous(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_admin_can_access(self):
        user = AdminUserFactory()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_developer_can_access(self):
        user = DeveloperUserFactory()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_observer_sees_only_authorized_projects(self):
        project_visible = ProjectFactory()
        ProjectSemesterNameFactory(
            project=project_visible, semester=self.semester, name="Visible Project",
        )
        project_hidden = ProjectFactory()
        ProjectSemesterNameFactory(
            project=project_hidden, semester=self.semester, name="Hidden Project",
        )

        obs = ObserverProfileFactory()
        obs.project_access.add(project_visible)
        self.client.force_login(obs.user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Project")
        self.assertNotContains(response, "Hidden Project")

    def test_shows_project_display_name(self):
        project = ProjectFactory()
        ProjectSemesterNameFactory(
            project=project, semester=self.semester, name="My Project Name",
        )
        user = DeveloperUserFactory()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertContains(response, "My Project Name")


# ---------------------------------------------------------------------------
# Planning page
# ---------------------------------------------------------------------------

class PlanningViewTests(TestCase):
    def setUp(self):
        self.url = reverse("planning:planning")

    def test_redirects_anonymous(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_admin_can_access(self):
        self.client.force_login(AdminUserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_pm_can_access(self):
        self.client.force_login(PMUserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_observer_denied(self):
        self.client.force_login(ObserverUserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 403)


# ---------------------------------------------------------------------------
# Schedule page
# ---------------------------------------------------------------------------

class ScheduleViewTests(TestCase):
    def setUp(self):
        self.url = reverse("planning:schedule")

    def test_redirects_anonymous(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_admin_can_access(self):
        self.client.force_login(AdminUserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_pm_can_access(self):
        self.client.force_login(PMUserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_observer_denied(self):
        self.client.force_login(ObserverUserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def _make_phase_in_current_semester(self, multiplier):
        sem = Semester.get_current()
        dev = DeveloperProfileFactory()
        project = ProjectFactory()
        # Use start of semester so it's within the rendered range
        start = sem.start_date
        end = start + datetime.timedelta(days=6)
        return Phase.objects.create(
            developer=dev, project=project, semester=sem,
            start_date=start, end_date=end, effort_multiplier=multiplier,
        )

    def _find_phase_in_context(self, response):
        for row in response.context["project_rows"]:
            for layer in row["layers"]:
                for cell in layer["cells"]:
                    if cell["type"] == "phase":
                        return cell["phase"]
        return None

    def test_effort_unfilled_pct_full_time(self):
        self._make_phase_in_current_semester(1.0)
        self.client.force_login(AdminUserFactory())
        response = self.client.get(self.url)
        phase = self._find_phase_in_context(response)
        self.assertIsNotNone(phase)
        self.assertAlmostEqual(phase.effort_unfilled_pct, 0.0)

    def test_effort_unfilled_pct_half_time(self):
        self._make_phase_in_current_semester(0.5)
        self.client.force_login(AdminUserFactory())
        response = self.client.get(self.url)
        phase = self._find_phase_in_context(response)
        self.assertIsNotNone(phase)
        self.assertAlmostEqual(phase.effort_unfilled_pct, 50.0)


# ---------------------------------------------------------------------------
# Phase CRUD views
# ---------------------------------------------------------------------------

class PhaseCreateViewTests(TestCase):
    def setUp(self):
        self.url = reverse("planning:phase_add")
        self.admin = AdminUserFactory()
        self.semester = Semester.get_current()
        self.dev = DeveloperProfileFactory()
        self.project = ProjectFactory()
        self.post_data = {
            "developer": self.dev.pk,
            "project": self.project.pk,
            "start_date": "2026-01-05",
            "end_date": "2026-02-02",
            "effort_multiplier": "1.0",
        }

    def test_admin_can_create(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        self.assertEqual(Phase.objects.count(), 1)

    def test_pm_can_create(self):
        self.client.force_login(PMUserFactory())
        self.client.post(self.url, self.post_data)
        self.assertEqual(Phase.objects.count(), 1)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Phase.objects.count(), 0)

    def test_observer_denied(self):
        self.client.force_login(ObserverUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_creates_phase_with_correct_fields(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        phase = Phase.objects.get()
        self.assertEqual(phase.developer, self.dev)
        self.assertEqual(phase.project, self.project)
        self.assertEqual(phase.start_date, datetime.date(2026, 1, 5))
        self.assertEqual(phase.end_date, datetime.date(2026, 2, 2))
        self.assertAlmostEqual(phase.effort_multiplier, 1.0)

    def test_phase_gets_lane_assigned(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        phase = Phase.objects.get()
        self.assertIsNotNone(phase.lane_id)

    def test_overlapping_phase_gets_new_lane(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        overlapping_data = dict(self.post_data, start_date="2026-01-12", end_date="2026-02-09")
        self.client.post(self.url, overlapping_data)
        phases = list(Phase.objects.all())
        self.assertEqual(len(phases), 2)
        self.assertNotEqual(phases[0].lane_id, phases[1].lane_id)

    def test_lane_pk_new_requests_new_lane(self):
        self.client.force_login(self.admin)
        # First phase — creates a lane
        self.client.post(self.url, self.post_data)
        first_lane = Phase.objects.first().lane
        # Second non-overlapping phase with lane_pk=new — must land in a NEW lane
        non_overlapping = dict(self.post_data, start_date="2026-03-02", end_date="2026-04-06",
                               lane_pk="new")
        self.client.post(self.url, non_overlapping)
        second_phase = Phase.objects.order_by("-pk").first()
        self.assertNotEqual(second_phase.lane, first_lane)

    def test_redirects_to_next_url(self):
        self.client.force_login(self.admin)
        data = dict(self.post_data, next="/planning/planning/")
        response = self.client.post(self.url, data)
        self.assertRedirects(response, "/planning/planning/", fetch_redirect_response=False)


class PhaseDeleteViewTests(TestCase):
    def setUp(self):
        self.admin = AdminUserFactory()
        self.dev = DeveloperProfileFactory()
        self.sem = SemesterFactory()
        self.project = ProjectFactory()
        self.phase = Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 1, 5), end_date=datetime.date(2026, 2, 2),
        )
        self.url = reverse("planning:phase_delete", args=[self.phase.pk])

    def test_admin_can_delete(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 302)

    def test_pm_can_delete(self):
        self.client.force_login(PMUserFactory())
        self.client.post(self.url, {})
        self.assertFalse(Phase.objects.filter(pk=self.phase.pk).exists())

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Phase.objects.filter(pk=self.phase.pk).exists())

    def test_deletes_phase(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {})
        self.assertFalse(Phase.objects.filter(pk=self.phase.pk).exists())

    def test_empty_lane_deleted_after_delete(self):
        lane_pk = self.phase.lane_id
        self.client.force_login(self.admin)
        self.client.post(self.url, {})
        self.assertFalse(DeveloperLane.objects.filter(pk=lane_pk).exists())

    def test_non_empty_lane_kept_after_delete(self):
        # Add a second phase to the same lane so it won't be empty after deletion
        Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 3, 2), end_date=datetime.date(2026, 4, 6),
            lane=self.phase.lane,
        )
        lane_pk = self.phase.lane_id
        self.client.force_login(self.admin)
        self.client.post(self.url, {})
        self.assertTrue(DeveloperLane.objects.filter(pk=lane_pk).exists())


class PhaseUpdateViewTests(TestCase):
    """Tests for the drag/resize HTMX endpoint (returns 204)."""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.dev = DeveloperProfileFactory()
        self.sem = SemesterFactory()
        self.project = ProjectFactory()
        self.phase = Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 1, 5), end_date=datetime.date(2026, 2, 2),
        )
        self.url = reverse("planning:phase_update", args=[self.phase.pk])
        self.post_data = {
            "start_date": "2026-01-12",
            "end_date": "2026-02-09",
        }

    def test_admin_can_update(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 204)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_returns_204_not_redirect(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 204)

    def test_updates_dates(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.start_date, datetime.date(2026, 1, 12))
        self.assertEqual(self.phase.end_date, datetime.date(2026, 2, 9))

    def test_lane_pk_new_changes_developer(self):
        new_dev = DeveloperProfileFactory()
        self.client.force_login(self.admin)
        self.client.post(self.url, {
            **self.post_data,
            "lane_pk": "new",
            "developer_pk": new_dev.pk,
        })
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.developer, new_dev)

    def test_overlap_bumps_to_new_lane(self):
        # Create a second phase in the same lane, non-overlapping
        phase2 = Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 3, 2), end_date=datetime.date(2026, 4, 6),
        )
        original_lane = phase2.lane
        # Move phase2 to overlap with self.phase
        url2 = reverse("planning:phase_update", args=[phase2.pk])
        self.client.force_login(self.admin)
        self.client.post(url2, {
            "start_date": "2026-01-12",
            "end_date": "2026-02-09",
            "lane_pk": str(original_lane.pk),
        })
        phase2.refresh_from_db()
        self.assertNotEqual(phase2.lane, original_lane)

    def test_old_empty_lane_deleted_on_developer_change(self):
        # phase is alone in its lane; change developer → old lane should be deleted
        new_dev = DeveloperProfileFactory()
        old_lane_pk = self.phase.lane_id
        self.client.force_login(self.admin)
        self.client.post(self.url, {
            **self.post_data,
            "lane_pk": "new",
            "developer_pk": new_dev.pk,
        })
        self.assertFalse(DeveloperLane.objects.filter(pk=old_lane_pk).exists())

    def test_old_non_empty_lane_kept_on_developer_change(self):
        # Add another phase to the same lane
        Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 3, 2), end_date=datetime.date(2026, 4, 6),
            lane=self.phase.lane,
        )
        new_dev = DeveloperProfileFactory()
        old_lane_pk = self.phase.lane_id
        self.client.force_login(self.admin)
        self.client.post(self.url, {
            **self.post_data,
            "lane_pk": "new",
            "developer_pk": new_dev.pk,
        })
        self.assertTrue(DeveloperLane.objects.filter(pk=old_lane_pk).exists())


class PhaseEditViewTests(TestCase):
    """Tests for the modal-form full-page edit endpoint."""

    def setUp(self):
        self.admin = AdminUserFactory()
        self.dev = DeveloperProfileFactory()
        self.sem = SemesterFactory()
        self.project = ProjectFactory()
        self.project2 = ProjectFactory()
        self.phase = Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 1, 5), end_date=datetime.date(2026, 2, 2),
            effort_multiplier=1.0,
        )
        self.url = reverse("planning:phase_edit", args=[self.phase.pk])
        self.post_data = {
            "developer": self.dev.pk,
            "project": self.project2.pk,
            "start_date": "2026-01-12",
            "end_date": "2026-02-09",
            "effort_multiplier": "0.5",
        }

    def test_admin_can_edit(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_updates_project_dates_multiplier(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.project, self.project2)
        self.assertEqual(self.phase.start_date, datetime.date(2026, 1, 12))
        self.assertEqual(self.phase.end_date, datetime.date(2026, 2, 9))
        self.assertAlmostEqual(self.phase.effort_multiplier, 0.5)

    def test_same_developer_keeps_lane(self):
        original_lane = self.phase.lane
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.lane, original_lane)

    def test_developer_change_assigns_new_lane(self):
        new_dev = DeveloperProfileFactory()
        self.client.force_login(self.admin)
        self.client.post(self.url, dict(self.post_data, developer=new_dev.pk))
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.developer, new_dev)
        self.assertEqual(self.phase.lane.developer, new_dev)

    def test_developer_change_deletes_empty_old_lane(self):
        old_lane_pk = self.phase.lane_id
        new_dev = DeveloperProfileFactory()
        self.client.force_login(self.admin)
        self.client.post(self.url, dict(self.post_data, developer=new_dev.pk))
        self.assertFalse(DeveloperLane.objects.filter(pk=old_lane_pk).exists())

    def test_developer_change_keeps_non_empty_old_lane(self):
        # Put another phase in the same lane
        Phase.objects.create(
            developer=self.dev, project=self.project, semester=self.sem,
            start_date=datetime.date(2026, 3, 2), end_date=datetime.date(2026, 4, 6),
            lane=self.phase.lane,
        )
        old_lane_pk = self.phase.lane_id
        new_dev = DeveloperProfileFactory()
        self.client.force_login(self.admin)
        self.client.post(self.url, dict(self.post_data, developer=new_dev.pk))
        self.assertTrue(DeveloperLane.objects.filter(pk=old_lane_pk).exists())
