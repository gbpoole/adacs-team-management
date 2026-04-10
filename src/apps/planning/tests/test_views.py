"""Integration tests for planning views."""
import datetime

from django.core.files.uploadedfile import SimpleUploadedFile
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
from apps.planning.models import Stream
from apps.planning.models import Tag
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


_ROLE_FACTORIES = {
    "admin": AdminUserFactory,
    "pm": PMUserFactory,
    "developer": DeveloperUserFactory,
    "observer": ObserverUserFactory,
}


class PlanningTestCase(TestCase):
    def assertRoleAccess(self, url, method="get", allowed=(), denied=(), data=None):
        for role in allowed:
            self.client.force_login(_ROLE_FACTORIES[role]())
            resp = getattr(self.client, method)(url, data or {})
            self.assertNotEqual(resp.status_code, 403,
                msg=f"Role '{role}' should be allowed at {url}")
        for role in denied:
            self.client.force_login(_ROLE_FACTORIES[role]())
            resp = getattr(self.client, method)(url, data or {})
            self.assertEqual(resp.status_code, 403,
                msg=f"Role '{role}' should be denied at {url}")


class HomeViewTests(TestCase):
    def test_redirects_anonymous(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/", response["Location"])

    def test_authenticated_can_access(self):
        self.client.force_login(AdminUserFactory())
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

    def test_developer_context_populated(self):
        dev = DeveloperProfileFactory()
        self.client.force_login(dev.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["my_profile"], dev)

    def test_developer_effort_available_in_context(self):
        dev = DeveloperProfileFactory()
        sem = Semester.get_current()
        SemesterDeveloper.objects.create(developer=dev, semester=sem, effort_available=15)
        self.client.force_login(dev.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["my_effort_available"], 15)

    def test_developer_without_profile_shows_no_error(self):
        # A user with role=DEVELOPER but no DeveloperProfile should still get 200
        from apps.planning.tests.factories import DeveloperUserFactory
        user = DeveloperUserFactory()
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("my_profile", response.context)

    def test_observer_project_count_in_context(self):
        obs = ObserverProfileFactory()
        project = ProjectFactory()
        obs.project_access.add(project)
        self.client.force_login(obs.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["my_project_count"], 1)

    def test_admin_sees_summary_counts(self):
        DeveloperProfileFactory()
        ProjectFactory()
        self.client.force_login(AdminUserFactory())
        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["dev_count"], 1)
        self.assertEqual(response.context["project_count"], 1)


class DevelopersViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:developers")
        self.semester = SemesterFactory(year=2026, semester_type=SemesterType.A)

    def test_redirects_anonymous(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_role_access(self):
        self.assertRoleAccess(self.url, allowed=["admin", "pm", "developer"], denied=["observer"])

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


class ObserversViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:observers")

    def test_redirects_anonymous(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_role_access(self):
        self.assertRoleAccess(self.url, allowed=["admin", "pm"], denied=["developer", "observer"])

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


class ProjectsViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:projects")
        self.semester = SemesterFactory(year=2026, semester_type=SemesterType.A)

    def test_redirects_anonymous(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_role_access(self):
        self.assertRoleAccess(self.url, allowed=["admin", "pm", "developer"])

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

class PlanningViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:planning")

    def test_redirects_anonymous(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_role_access(self):
        self.assertRoleAccess(self.url, allowed=["admin", "pm", "observer"], denied=["developer"])

    def test_context_contains_developer_rows(self):
        sem = Semester.get_current()
        dev = DeveloperProfileFactory()
        project = ProjectFactory()
        Phase.objects.create(
            developer=dev, project=project, semester=sem,
            start_date=sem.start_date, end_date=sem.start_date + datetime.timedelta(days=6),
        )
        self.client.force_login(AdminUserFactory())
        response = self.client.get(self.url)
        self.assertIn("developer_rows", response.context)
        pks = [row["developer"].pk for row in response.context["developer_rows"]]
        self.assertIn(dev.pk, pks)
        row = next(r for r in response.context["developer_rows"] if r["developer"].pk == dev.pk)
        self.assertIn("lanes", row)
        self.assertIn("overallocated_cols", row)

    def test_tag_filter_excludes_untagged_developers(self):
        sem = Semester.get_current()
        tag, _ = Tag.objects.get_or_create(name="python")
        dev_with = DeveloperProfileFactory()
        dev_with.tags.set([tag])
        dev_without = DeveloperProfileFactory()
        for dev in (dev_with, dev_without):
            Phase.objects.create(
                developer=dev, project=ProjectFactory(), semester=sem,
                start_date=sem.start_date, end_date=sem.start_date + datetime.timedelta(days=6),
            )
        self.client.force_login(AdminUserFactory())
        response = self.client.get(self.url + "?tags=python")
        pks = [row["developer"].pk for row in response.context["developer_rows"]]
        self.assertIn(dev_with.pk, pks)
        self.assertNotIn(dev_without.pk, pks)


# ---------------------------------------------------------------------------
# Schedule page
# ---------------------------------------------------------------------------

class ScheduleViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:schedule")

    def test_redirects_anonymous(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_role_access(self):
        self.assertRoleAccess(self.url, allowed=["admin", "pm", "observer"], denied=["developer"])

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


class PhaseViewTestCase(PlanningTestCase):
    def setUp(self):
        self.admin = AdminUserFactory()
        self.dev = DeveloperProfileFactory()
        self.sem = SemesterFactory()
        self.project = ProjectFactory()
        self.phase = Phase.objects.create(
            developer=self.dev,
            project=self.project,
            semester=self.sem,
            start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 2, 2),
        )


class PhaseCreateViewTests(PlanningTestCase):
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
        self.assertEqual(Phase.objects.count(), 0)

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

    def test_invalid_date_returns_redirect_not_500(self):
        self.client.force_login(self.admin)
        data = dict(self.post_data, start_date="not-a-date")
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Phase.objects.count(), 0)


class PhaseDeleteViewTests(PhaseViewTestCase):
    def setUp(self):
        super().setUp()
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


class PhaseUpdateViewTests(PhaseViewTestCase):
    """Tests for the drag/resize HTMX endpoint (returns 204)."""

    def setUp(self):
        super().setUp()
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

    def test_invalid_date_returns_400_not_500(self):
        self.client.force_login(self.admin)
        data = dict(self.post_data, start_date="not-a-date")
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 400)

    def test_end_before_start_returns_400(self):
        self.client.force_login(self.admin)
        data = dict(self.post_data, start_date="2026-02-09", end_date="2026-01-12")
        original_start = self.phase.start_date
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 400)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.start_date, original_start)

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


class PhaseEditViewTests(PhaseViewTestCase):
    """Tests for the modal-form full-page edit endpoint."""

    def setUp(self):
        super().setUp()
        self.project2 = ProjectFactory()
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


class DeveloperCreateViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:developer_add")
        self.admin = AdminUserFactory()
        self.post_data = {
            "email": "newdev@example.com",
            "name": "New Developer",
            "organisation": "ADACS",
            "emoji": "",
        }

    def test_role_access(self):
        self.assertRoleAccess(
            self.url, method="post",
            allowed=["admin", "pm"], denied=["developer", "observer"],
            data=self.post_data,
        )

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


class DeveloperUpdateViewTests(PlanningTestCase):
    def setUp(self):
        self.admin = AdminUserFactory()
        self.profile = DeveloperProfileFactory()
        self.url = reverse("planning:developer_edit", args=[self.profile.pk])
        self.post_data = {
            "name": "Updated Name",
            "organisation": "Updated Org",
            "emoji": "",
        }

    def test_role_access(self):
        self.assertRoleAccess(
            self.url, method="post",
            allowed=["admin", "pm"], denied=["developer"],
            data=self.post_data,
        )

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


class DeveloperDeleteViewTests(PlanningTestCase):
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
        self.assertFalse(DeveloperProfile.objects.filter(pk=profile.pk).exists())

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


class ObserverCreateViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:observer_add")
        self.admin = AdminUserFactory()
        self.post_data = {
            "email": "newobs@example.com",
            "name": "New Observer",
            "organisation": "External",
            "emoji": "",
        }

    def test_role_access(self):
        self.assertRoleAccess(
            self.url, method="post",
            allowed=["admin", "pm"], denied=["developer", "observer"],
            data=self.post_data,
        )

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


class ObserverUpdateViewTests(PlanningTestCase):
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


class ObserverDeleteViewTests(PlanningTestCase):
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
        self.assertFalse(ObserverProfile.objects.filter(pk=profile.pk).exists())

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


class ProjectCreateViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:project_add")
        self.admin = AdminUserFactory()
        self.post_data = {
            "name": "New Project",
            "streams": "Engineering",
            "effort_resourced": "10",
        }

    def test_role_access(self):
        self.assertRoleAccess(
            self.url, method="post",
            allowed=["admin", "pm"], denied=["developer", "observer"],
            data=self.post_data,
        )

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


class ProjectUpdateViewTests(PlanningTestCase):
    def setUp(self):
        self.admin = AdminUserFactory()
        self.semester = SemesterFactory()
        self.project = ProjectFactory()
        ProjectSemesterNameFactory(project=self.project, semester=self.semester, name="Old Name")
        self.url = reverse("planning:project_edit", args=[self.project.pk])
        self.post_data = {
            "name": "New Name",
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


class ProjectDeleteViewTests(PlanningTestCase):
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
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())

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


class LeaveViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:leave")

    def test_redirects_anonymous(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_role_access(self):
        self.assertRoleAccess(self.url, allowed=["admin", "pm", "developer"], denied=["observer"])

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
        self.assertEqual(len(pks), 1)

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


class LeaveCreateViewTests(PlanningTestCase):
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

    def test_invalid_date_returns_redirect_not_500(self):
        self.client.force_login(self.admin)
        data = dict(self.post_data, start_date="not-a-date")
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Leave.objects.count(), 0)

    def test_end_before_start_returns_redirect(self):
        self.client.force_login(self.admin)
        data = dict(self.post_data, start_date="2026-06-07", end_date="2026-06-01")
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Leave.objects.count(), 0)


class LeaveDeleteViewTests(PlanningTestCase):
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

    def test_pm_can_delete_confirms_db(self):
        self.client.force_login(PMUserFactory())
        self.client.post(self.url, {})
        self.assertFalse(Leave.objects.filter(pk=self.leave.pk).exists())

    def test_observer_denied(self):
        self.client.force_login(ObserverUserFactory())
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 403)


class LeaveUpdateViewTests(PlanningTestCase):
    def setUp(self):
        self.dev = DeveloperProfileFactory()
        self.leave = LeaveFactory(
            developer=self.dev,
            start_date=datetime.date(2026, 3, 2),
            end_date=datetime.date(2026, 3, 6),
        )
        self.url = reverse("planning:leave_update", args=[self.leave.pk])
        self.valid_data = {"start_date": "2026-03-09", "end_date": "2026-03-13"}

    def test_developer_can_update_own_leave(self):
        self.client.force_login(self.dev.user)
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, 204)
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.start_date, datetime.date(2026, 3, 9))

    def test_developer_cannot_update_others_leave(self):
        other_dev = DeveloperProfileFactory()
        self.client.force_login(other_dev.user)
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, 403)
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.start_date, datetime.date(2026, 3, 2))

    def test_pm_can_update_any_leave(self):
        self.client.force_login(PMUserFactory())
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, 204)
        self.leave.refresh_from_db()
        self.assertEqual(self.leave.start_date, datetime.date(2026, 3, 9))

    def test_observer_denied(self):
        self.client.force_login(ObserverUserFactory())
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, 403)

    def test_invalid_date_returns_400(self):
        self.client.force_login(PMUserFactory())
        response = self.client.post(self.url, {"start_date": "not-a-date", "end_date": "2026-03-13"})
        self.assertEqual(response.status_code, 400)


# ---------------------------------------------------------------------------
# Developer upload view
# ---------------------------------------------------------------------------


def _tsv_bytes(rows):
    """Build a tab-separated bytes object from a list of dicts."""
    if not rows:
        return b""
    header = "\t".join(rows[0].keys())
    body = "\n".join("\t".join(str(v) for v in r.values()) for r in rows)
    return (header + "\n" + body).encode("utf-8")


class DeveloperUploadViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:developer_upload")
        self.admin = AdminUserFactory()

    def _post(self, rows):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("devs.tsv", _tsv_bytes(rows), content_type="text/plain")
        self.client.force_login(self.admin)
        return self.client.post(self.url, {"tsv_file": f})

    def test_role_access(self):
        self.assertRoleAccess(self.url, method="post", denied=["developer", "observer"])

    def test_missing_file_redirects(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 302)

    def test_upload_creates_developer(self):
        self._post([{"email": "upload@example.com", "name": "Upload Dev", "organisation": "", "emoji": "", "tags": "", "effort_available": ""}])
        self.assertTrue(DeveloperProfile.objects.filter(user__email="upload@example.com").exists())

    def test_upload_sets_effort(self):
        self._post([{"email": "effort@example.com", "name": "Effort Dev", "organisation": "", "emoji": "", "tags": "", "effort_available": "12"}])
        profile = DeveloperProfile.objects.get(user__email="effort@example.com")
        self.assertTrue(SemesterDeveloper.objects.filter(developer=profile, effort_available=12).exists())

    def test_upload_invalid_email_returns_redirect_with_error(self):
        response = self._post([{"email": "not-an-email", "name": "Bad", "organisation": "", "emoji": "", "tags": "", "effort_available": ""}])
        self.assertEqual(response.status_code, 302)
        self.assertFalse(DeveloperProfile.objects.filter(user__email="not-an-email").exists())


# ---------------------------------------------------------------------------
# Project upload view
# ---------------------------------------------------------------------------


class ProjectUploadViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:project_upload")
        self.admin = AdminUserFactory()

    def _post(self, rows):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("projects.tsv", _tsv_bytes(rows), content_type="text/plain")
        self.client.force_login(self.admin)
        return self.client.post(self.url, {"tsv_file": f})

    def test_role_access(self):
        self.assertRoleAccess(self.url, method="post", denied=["developer", "observer"])

    def test_missing_file_redirects(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 302)

    def test_upload_creates_project(self):
        self._post([{"name": "Uploaded Project", "streams": "Engineering", "tags": "", "effort_resourced": "8"}])
        self.assertTrue(ProjectSemesterName.objects.filter(name="Uploaded Project").exists())

    def test_upload_assigns_streams(self):
        self._post([{"name": "Stream Project", "streams": "Engineering", "tags": "", "effort_resourced": ""}])
        psn = ProjectSemesterName.objects.get(name="Stream Project")
        self.assertTrue(psn.project.streams.filter(name="Engineering").exists())

    def test_upload_creates_allocation(self):
        self._post([{"name": "Alloc Project", "streams": "", "tags": "", "effort_resourced": "5"}])
        psn = ProjectSemesterName.objects.get(name="Alloc Project")
        self.assertTrue(ProjectAllocation.objects.filter(project=psn.project, weeks_new=5).exists())

    def test_upload_invalid_name_returns_redirect_with_error(self):
        before = Project.objects.count()
        self._post([{"name": "", "streams": "", "tags": "", "effort_resourced": ""}])
        self.assertEqual(Project.objects.count(), before)


# ---------------------------------------------------------------------------
# Tags management views
# ---------------------------------------------------------------------------


class TagsViewTests(PlanningTestCase):
    def setUp(self):
        self.pm = PMUserFactory()
        self.url = reverse("planning:tags")

    def test_pm_can_get_list(self):
        self.client.force_login(self.pm)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_role_access(self):
        self.assertRoleAccess(self.url, method="get", denied=["developer", "observer"])

    def test_create_tag_with_name_and_colour(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("planning:tag_add"), {"name": "new-tag", "colour": "#4E79A7"})
        tag = Tag.objects.get(name="new-tag")
        self.assertEqual(tag.colour, "#4E79A7")

    def test_create_tag_auto_assigns_colour_when_not_provided(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("planning:tag_add"), {"name": "auto-colour-tag", "colour": ""})
        tag = Tag.objects.get(name="auto-colour-tag")
        self.assertTrue(tag.colour)

    def test_rename_tag_preserves_pk(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("planning:tag_add"), {"name": "original", "colour": "#4E79A7"})
        tag = Tag.objects.get(name="original")
        original_pk = tag.pk
        self.client.post(reverse("planning:tag_edit", args=[tag.pk]), {"name": "renamed", "colour": "#4E79A7"})
        tag.refresh_from_db()
        self.assertEqual(tag.name, "renamed")
        self.assertEqual(tag.pk, original_pk)

    def test_update_colour(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("planning:tag_add"), {"name": "colour-test", "colour": "#4E79A7"})
        tag = Tag.objects.get(name="colour-test")
        self.client.post(reverse("planning:tag_edit", args=[tag.pk]), {"name": "colour-test", "colour": "#E15759"})
        tag.refresh_from_db()
        self.assertEqual(tag.colour, "#E15759")

    def test_delete_tag(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("planning:tag_add"), {"name": "to-delete", "colour": "#4E79A7"})
        tag = Tag.objects.get(name="to-delete")
        self.client.post(reverse("planning:tag_delete", args=[tag.pk]))
        self.assertFalse(Tag.objects.filter(pk=tag.pk).exists())

    def test_developer_cannot_access(self):
        from apps.planning.tests.factories import DeveloperUserFactory
        self.client.force_login(DeveloperUserFactory())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_observer_cannot_access(self):
        from apps.planning.tests.factories import ObserverUserFactory
        self.client.force_login(ObserverUserFactory())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# Streams management views
# ---------------------------------------------------------------------------


class StreamsViewTests(PlanningTestCase):
    def setUp(self):
        self.pm = PMUserFactory()
        self.url = reverse("planning:streams")

    def test_pm_can_get_list(self):
        self.client.force_login(self.pm)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_role_access(self):
        self.assertRoleAccess(self.url, method="get", denied=["developer", "observer"])

    def test_create_stream_with_name_and_colour(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("planning:stream_add"), {"name": "new-stream", "colour": "#76B7B2"})
        stream = Stream.objects.get(name="new-stream")
        self.assertEqual(stream.colour, "#76B7B2")

    def test_create_stream_auto_assigns_colour_when_not_provided(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("planning:stream_add"), {"name": "auto-colour-stream", "colour": ""})
        stream = Stream.objects.get(name="auto-colour-stream")
        self.assertTrue(stream.colour)

    def test_rename_stream_preserves_pk(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("planning:stream_add"), {"name": "original-stream", "colour": "#76B7B2"})
        stream = Stream.objects.get(name="original-stream")
        original_pk = stream.pk
        self.client.post(reverse("planning:stream_edit", args=[stream.pk]), {"name": "renamed-stream", "colour": "#76B7B2"})
        stream.refresh_from_db()
        self.assertEqual(stream.name, "renamed-stream")
        self.assertEqual(stream.pk, original_pk)

    def test_update_colour(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("planning:stream_add"), {"name": "stream-colour-test", "colour": "#76B7B2"})
        stream = Stream.objects.get(name="stream-colour-test")
        self.client.post(reverse("planning:stream_edit", args=[stream.pk]), {"name": "stream-colour-test", "colour": "#59A14F"})
        stream.refresh_from_db()
        self.assertEqual(stream.colour, "#59A14F")

    def test_delete_stream(self):
        self.client.force_login(self.pm)
        self.client.post(reverse("planning:stream_add"), {"name": "stream-to-delete", "colour": "#76B7B2"})
        stream = Stream.objects.get(name="stream-to-delete")
        self.client.post(reverse("planning:stream_delete", args=[stream.pk]))
        self.assertFalse(Stream.objects.filter(pk=stream.pk).exists())

    def test_developer_cannot_access(self):
        from apps.planning.tests.factories import DeveloperUserFactory
        self.client.force_login(DeveloperUserFactory())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_observer_cannot_access(self):
        from apps.planning.tests.factories import ObserverUserFactory
        self.client.force_login(ObserverUserFactory())
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
