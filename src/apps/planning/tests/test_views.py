"""Integration tests for planning views."""
import datetime

from django.test import TestCase
from django.urls import reverse

from django.contrib.auth import get_user_model

from apps.planning.models import DeveloperLane
from apps.planning.models import DeveloperProfile
from apps.planning.models import Leave
from apps.planning.models import ObserverProfile
from apps.planning.models import Phase
from apps.planning.models import Project
from apps.planning.models import ProjectAllocation
from apps.planning.models import ProjectSemesterName
from apps.planning.models import Semester
from apps.planning.models import SemesterDeveloper
from apps.planning.tests.factories import AdminUserFactory
from apps.planning.tests.factories import DeveloperLaneFactory
from apps.planning.tests.factories import DeveloperProfileFactory
from apps.planning.tests.factories import DeveloperUserFactory
from apps.planning.tests.factories import LeaveFactory
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


# ---------------------------------------------------------------------------
# Developer CRUD views
# ---------------------------------------------------------------------------


class DeveloperCreateViewTests(TestCase):
    def setUp(self):
        self.url = reverse("planning:developer_add")
        self.admin = AdminUserFactory()
        self.post_data = {
            "email": "newdev@example.com",
            "name": "New Developer",
            "organisation": "ADACS",
            "emoji": "",
        }

    def test_admin_can_create(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_pm_can_create(self):
        self.client.force_login(PMUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_observer_denied(self):
        self.client.force_login(ObserverUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_creates_user_and_profile(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        self.assertTrue(DeveloperProfile.objects.filter(user__email="newdev@example.com").exists())

    def test_empty_email_redirects_without_creating(self):
        before = DeveloperProfile.objects.count()
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {**self.post_data, "email": ""})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(DeveloperProfile.objects.count(), before)

    def test_sets_effort_available(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {**self.post_data, "effort_available": "20"})
        profile = DeveloperProfile.objects.get(user__email="newdev@example.com")
        self.assertTrue(SemesterDeveloper.objects.filter(developer=profile, effort_available=20).exists())


class DeveloperUpdateViewTests(TestCase):
    def setUp(self):
        self.admin = AdminUserFactory()
        self.profile = DeveloperProfileFactory()
        self.url = reverse("planning:developer_edit", args=[self.profile.pk])
        self.post_data = {
            "name": "Updated Name",
            "organisation": "Updated Org",
            "emoji": "",
        }

    def test_admin_can_update(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_pm_can_update(self):
        self.client.force_login(PMUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_updates_user_fields(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        self.profile.user.refresh_from_db()
        self.assertEqual(self.profile.user.name, "Updated Name")
        self.assertEqual(self.profile.user.organisation, "Updated Org")

    def test_updates_effort_available(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, {**self.post_data, "effort_available": "18"})
        self.assertTrue(
            SemesterDeveloper.objects.filter(developer=self.profile, effort_available=18).exists()
        )


class DeveloperDeleteViewTests(TestCase):
    def setUp(self):
        self.admin = AdminUserFactory()
        self.profile = DeveloperProfileFactory()
        self.url = reverse("planning:developer_delete", args=[self.profile.pk])

    def test_admin_can_delete(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 204)

    def test_pm_can_delete(self):
        profile = DeveloperProfileFactory()
        self.client.force_login(PMUserFactory())
        response = self.client.post(reverse("planning:developer_delete", args=[profile.pk]), {})
        self.assertEqual(response.status_code, 204)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 403)

    def test_deletes_profile_and_user(self):
        user_pk = self.profile.user_id
        profile_pk = self.profile.pk
        self.client.force_login(self.admin)
        self.client.post(self.url, {})
        self.assertFalse(DeveloperProfile.objects.filter(pk=profile_pk).exists())
        self.assertFalse(get_user_model().objects.filter(pk=user_pk).exists())


# ---------------------------------------------------------------------------
# Observer CRUD views
# ---------------------------------------------------------------------------


class ObserverCreateViewTests(TestCase):
    def setUp(self):
        self.url = reverse("planning:observer_add")
        self.admin = AdminUserFactory()
        self.post_data = {
            "email": "newobs@example.com",
            "name": "New Observer",
            "organisation": "External",
            "emoji": "",
        }

    def test_admin_can_create(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_pm_can_create(self):
        self.client.force_login(PMUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_observer_denied(self):
        self.client.force_login(ObserverUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_creates_user_and_profile(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        self.assertTrue(ObserverProfile.objects.filter(user__email="newobs@example.com").exists())

    def test_sets_project_access(self):
        project = ProjectFactory()
        self.client.force_login(self.admin)
        self.client.post(self.url, {**self.post_data, "project_access": [project.pk]})
        profile = ObserverProfile.objects.get(user__email="newobs@example.com")
        self.assertIn(project, profile.project_access.all())


class ObserverUpdateViewTests(TestCase):
    def setUp(self):
        self.admin = AdminUserFactory()
        self.profile = ObserverProfileFactory()
        self.url = reverse("planning:observer_edit", args=[self.profile.pk])
        self.post_data = {
            "name": "Updated Observer",
            "organisation": "Updated Org",
            "emoji": "",
        }

    def test_admin_can_update(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_updates_user_fields(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        self.profile.user.refresh_from_db()
        self.assertEqual(self.profile.user.name, "Updated Observer")
        self.assertEqual(self.profile.user.organisation, "Updated Org")

    def test_updates_project_access(self):
        project = ProjectFactory()
        self.client.force_login(self.admin)
        self.client.post(self.url, {**self.post_data, "project_access": [project.pk]})
        self.assertIn(project, self.profile.project_access.all())

    def test_clears_project_access(self):
        project = ProjectFactory()
        self.profile.project_access.add(project)
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)  # no project_access in POST
        self.assertEqual(self.profile.project_access.count(), 0)


class ObserverDeleteViewTests(TestCase):
    def setUp(self):
        self.admin = AdminUserFactory()
        self.profile = ObserverProfileFactory()
        self.url = reverse("planning:observer_delete", args=[self.profile.pk])

    def test_admin_can_delete(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 204)

    def test_pm_can_delete(self):
        profile = ObserverProfileFactory()
        self.client.force_login(PMUserFactory())
        response = self.client.post(reverse("planning:observer_delete", args=[profile.pk]), {})
        self.assertEqual(response.status_code, 204)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 403)

    def test_deletes_profile_and_user(self):
        user_pk = self.profile.user_id
        profile_pk = self.profile.pk
        self.client.force_login(self.admin)
        self.client.post(self.url, {})
        self.assertFalse(ObserverProfile.objects.filter(pk=profile_pk).exists())
        self.assertFalse(get_user_model().objects.filter(pk=user_pk).exists())


# ---------------------------------------------------------------------------
# Project CRUD views
# ---------------------------------------------------------------------------


class ProjectCreateViewTests(TestCase):
    def setUp(self):
        self.url = reverse("planning:project_add")
        self.admin = AdminUserFactory()
        self.post_data = {
            "name": "New Project",
            "stream": "Engineering",
            "effort_resourced": "10",
        }

    def test_admin_can_create(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_pm_can_create(self):
        self.client.force_login(PMUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_observer_denied(self):
        self.client.force_login(ObserverUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_creates_project_with_semester_name(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        self.assertTrue(ProjectSemesterName.objects.filter(name="New Project").exists())

    def test_creates_allocation(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        self.assertTrue(ProjectAllocation.objects.filter(weeks_new=10).exists())

    def test_empty_name_redirects_without_creating(self):
        before = Project.objects.count()
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {**self.post_data, "name": ""})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Project.objects.count(), before)


class ProjectUpdateViewTests(TestCase):
    def setUp(self):
        self.admin = AdminUserFactory()
        self.semester = SemesterFactory()
        self.project = ProjectFactory()
        ProjectSemesterNameFactory(project=self.project, semester=self.semester, name="Old Name")
        self.url = reverse("planning:project_edit", args=[self.project.pk])
        self.post_data = {
            "name": "New Name",
            "stream": "",
            "effort_resourced": "15",
        }

    def test_admin_can_update(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_updates_semester_name(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        self.assertTrue(
            ProjectSemesterName.objects.filter(project=self.project, name="New Name").exists()
        )

    def test_updates_allocation(self):
        self.client.force_login(self.admin)
        self.client.post(self.url, self.post_data)
        self.assertTrue(
            ProjectAllocation.objects.filter(project=self.project, weeks_new=15).exists()
        )


class ProjectDeleteViewTests(TestCase):
    def setUp(self):
        self.admin = AdminUserFactory()
        self.project = ProjectFactory()
        self.url = reverse("planning:project_delete", args=[self.project.pk])

    def test_admin_can_delete(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 204)

    def test_pm_can_delete(self):
        project = ProjectFactory()
        self.client.force_login(PMUserFactory())
        response = self.client.post(reverse("planning:project_delete", args=[project.pk]), {})
        self.assertEqual(response.status_code, 204)

    def test_developer_denied(self):
        self.client.force_login(DeveloperUserFactory())
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 403)

    def test_deletes_project(self):
        pk = self.project.pk
        self.client.force_login(self.admin)
        self.client.post(self.url, {})
        self.assertFalse(Project.objects.filter(pk=pk).exists())


# ---------------------------------------------------------------------------
# Leave views
# ---------------------------------------------------------------------------


class LeaveViewTests(TestCase):
    def setUp(self):
        self.url = reverse("planning:leave")

    def test_redirects_anonymous(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_admin_can_access(self):
        self.client.force_login(AdminUserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_pm_can_access(self):
        self.client.force_login(PMUserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_developer_can_access(self):
        dev = DeveloperProfileFactory()
        self.client.force_login(dev.user)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_observer_denied(self):
        self.client.force_login(ObserverUserFactory())
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_developer_sees_only_own_leave(self):
        dev1 = DeveloperProfileFactory()
        dev2 = DeveloperProfileFactory()
        # Use a far-future end_date so leave is not filtered out by the "show past" default
        leave1 = LeaveFactory(developer=dev1, end_date=datetime.date(2099, 3, 7))
        leave2 = LeaveFactory(developer=dev2, end_date=datetime.date(2099, 3, 14))
        self.client.force_login(dev1.user)
        response = self.client.get(self.url)
        pks = [lv.pk for lv in response.context["leave_periods"]]
        self.assertIn(leave1.pk, pks)
        self.assertNotIn(leave2.pk, pks)

    def test_admin_sees_all_leave(self):
        dev1 = DeveloperProfileFactory()
        dev2 = DeveloperProfileFactory()
        leave1 = LeaveFactory(developer=dev1, end_date=datetime.date(2099, 3, 7))
        leave2 = LeaveFactory(developer=dev2, end_date=datetime.date(2099, 3, 14))
        self.client.force_login(AdminUserFactory())
        response = self.client.get(self.url)
        pks = [lv.pk for lv in response.context["leave_periods"]]
        self.assertIn(leave1.pk, pks)
        self.assertIn(leave2.pk, pks)


class LeaveCreateViewTests(TestCase):
    def setUp(self):
        self.url = reverse("planning:leave_add")
        self.admin = AdminUserFactory()
        self.dev = DeveloperProfileFactory()
        self.post_data = {
            "developer": self.dev.pk,
            "start_date": "2026-06-01",
            "end_date": "2026-06-07",
        }

    def test_admin_can_create(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Leave.objects.count(), 1)

    def test_pm_can_create(self):
        self.client.force_login(PMUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Leave.objects.count(), 1)

    def test_observer_denied(self):
        self.client.force_login(ObserverUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_developer_creates_leave_for_own_profile(self):
        # The view ignores the submitted developer_id and uses the logged-in
        # developer's own profile.
        own_dev = DeveloperProfileFactory()
        self.client.force_login(own_dev.user)
        self.client.post(self.url, self.post_data)
        self.assertTrue(Leave.objects.filter(developer=own_dev).exists())

    def test_developer_without_profile_gets_403(self):
        # A user with role=DEVELOPER but no DeveloperProfile cannot create leave.
        user = DeveloperUserFactory()
        self.client.force_login(user)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)


class LeaveDeleteViewTests(TestCase):
    def setUp(self):
        self.admin = AdminUserFactory()
        self.dev = DeveloperProfileFactory()
        self.leave = LeaveFactory(developer=self.dev)
        self.url = reverse("planning:leave_delete", args=[self.leave.pk])

    def test_admin_can_delete(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Leave.objects.filter(pk=self.leave.pk).exists())

    def test_pm_can_delete(self):
        self.client.force_login(PMUserFactory())
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 302)

    def test_developer_can_delete_own_leave(self):
        self.client.force_login(self.dev.user)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Leave.objects.filter(pk=self.leave.pk).exists())

    def test_developer_cannot_delete_others_leave(self):
        other_dev = DeveloperProfileFactory()
        self.client.force_login(other_dev.user)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Leave.objects.filter(pk=self.leave.pk).exists())

    def test_observer_denied(self):
        self.client.force_login(ObserverUserFactory())
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 403)
