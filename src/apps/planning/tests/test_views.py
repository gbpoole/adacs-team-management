"""Integration tests for planning views."""

import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse

from apps.planning.models import DeveloperLane
from apps.planning.models import DeveloperProfile
from apps.planning.models import Leave
from apps.planning.models import Phase
from apps.planning.models import Project
from apps.planning.models import ProjectAllocation
from apps.planning.models import Semester
from apps.planning.models import SemesterDeveloper
from apps.planning.models import Stream
from apps.planning.models import Tag
from apps.planning.models import UserProjectAccess
from apps.planning.tests.factories import DeveloperProfileFactory
from apps.planning.tests.factories import LeaveFactory
from apps.planning.tests.factories import PMUserFactory
from apps.planning.tests.factories import ProjectAllocationFactory
from apps.planning.tests.factories import ProjectFactory
from apps.planning.tests.factories import SemesterFactory
from apps.planning.tests.factories import SemesterType
from apps.planning.tests.factories import StreamFactory
from apps.planning.tests.factories import TagFactory
from apps.planning.tests.factories import UserFactory
from apps.planning.tests.factories import UserProjectAccessFactory
from apps.planning.tests.factories import make_restricted_access_user
from apps.planning.tests.factories import make_semester_developer

_ROLE_FACTORIES = {
    "pm": lambda: PMUserFactory(),
    "developer": lambda: make_semester_developer().user,
    "restricted": lambda: make_restricted_access_user().user,
    # Backward-compatible alias for older role labels in this test module.
    "observer": lambda: make_restricted_access_user().user,
}


class PlanningTestCase(TestCase):
    def assertRoleAccess(self, url, method="get", allowed=(), denied=(), data=None):
        for role in allowed:
            self.client.force_login(_ROLE_FACTORIES[role]())
            resp = getattr(self.client, method)(url, data or {})
            self.assertLess(
                resp.status_code,
                400,
                msg=(
                    f"Role '{role}' should be allowed at {url}; "
                    f"got status {resp.status_code}"
                ),
            )
        for role in denied:
            self.client.force_login(_ROLE_FACTORIES[role]())
            resp = getattr(self.client, method)(url, data or {})
            self.assertEqual(
                resp.status_code,
                403,
                msg=f"Role '{role}' should be denied at {url}",
            )


class HomeViewTests(TestCase):
    def test_redirects_anonymous(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/", response["Location"])

    def test_authenticated_can_access(self):
        self.client.force_login(PMUserFactory())
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

    def test_developer_context_populated(self):
        dev = make_semester_developer()
        self.client.force_login(dev.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["my_profile"], dev)

    def test_developer_effort_available_in_context(self):
        dev = DeveloperProfileFactory()
        sem = Semester.get_current()
        SemesterDeveloper.objects.create(
            developer=dev,
            semester=sem,
            effort_available=15,
        )
        self.client.force_login(dev.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["my_effort_available"], 15)

    def test_user_without_profile_shows_no_error(self):
        # A plain user with no DeveloperProfile should still get 200
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("my_profile", response.context)

    def test_observer_project_count_in_context(self):
        obs = UserProjectAccessFactory()
        project = ProjectFactory()
        obs.project_access.add(project)
        self.client.force_login(obs.user)
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["my_project_count"], 1)

    def test_pm_sees_summary_counts(self):
        DeveloperProfileFactory()
        ProjectFactory()
        self.client.force_login(PMUserFactory())
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
        self.assertRoleAccess(
            self.url,
            allowed=["pm"],
            denied=["developer", "observer"],
        )

    def test_shows_developer_in_table(self):
        dev_profile = make_semester_developer()
        self.client.force_login(PMUserFactory())
        response = self.client.get(self.url)
        # Template shows name when set, falling back to email
        expected = dev_profile.user.name or dev_profile.user.email
        self.assertContains(response, expected)

    def test_pm_sees_add_button(self):
        user = PMUserFactory()
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertContains(response, "Add Developer")


class ObserversViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:observers")

    def test_redirects_anonymous(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_role_access(self):
        self.assertRoleAccess(
            self.url,
            allowed=["pm"],
            denied=["developer", "observer"],
        )

    def test_shows_observer_in_table(self):
        obs = UserProjectAccessFactory()
        admin = PMUserFactory()
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertContains(response, obs.user.email)

    def test_project_display_names_resolved(self):
        semester = Semester.get_current()
        project = ProjectFactory(semester=semester, name="My Real Project")
        obs = UserProjectAccessFactory()
        obs.project_access.add(project)
        admin = PMUserFactory()
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertContains(response, "My Real Project")
        self.assertNotContains(response, f"Project #{project.pk}")

    def test_observer_with_no_projects_shows_dash(self):
        UserProjectAccessFactory()
        admin = PMUserFactory()
        self.client.force_login(admin)
        response = self.client.get(self.url)
        self.assertContains(response, "—")


class ProjectsViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:projects")
        self.semester = SemesterFactory(year=2026, semester_type=SemesterType.A)

    def test_redirects_anonymous(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_role_access(self):
        self.assertRoleAccess(self.url, allowed=["pm", "developer", "observer"])

    def test_observer_sees_only_authorized_projects(self):
        project_visible = ProjectFactory(semester=self.semester, name="Visible Project")
        ProjectFactory(semester=self.semester, name="Hidden Project")

        obs = UserProjectAccessFactory()
        obs.project_access.add(project_visible)
        self.client.force_login(obs.user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Project")
        self.assertNotContains(response, "Hidden Project")

    def test_observer_with_empty_restrictions_sees_no_projects(self):
        ProjectFactory(semester=self.semester, name="Alpha Project")
        ProjectFactory(semester=self.semester, name="Beta Project")
        obs = UserProjectAccessFactory()
        # project_access and stream_access both empty → no access
        self.client.force_login(obs.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Alpha Project")
        self.assertNotContains(response, "Beta Project")

    def test_observer_with_all_project_access_flag_sees_all_projects(self):
        ProjectFactory(semester=self.semester, name="Alpha Project")
        ProjectFactory(semester=self.semester, name="Beta Project")
        obs = UserProjectAccessFactory()
        obs.all_project_access = True
        obs.save()
        self.client.force_login(obs.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Project")
        self.assertContains(response, "Beta Project")

    def test_observer_with_stream_access_sees_stream_projects(self):
        stream = StreamFactory()
        project_in = ProjectFactory(semester=self.semester, name="Stream Project")
        project_in.streams.add(stream)
        ProjectFactory(semester=self.semester, name="Other Project")
        obs = UserProjectAccessFactory()
        obs.stream_access.add(stream)
        self.client.force_login(obs.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stream Project")
        self.assertNotContains(response, "Other Project")

    def test_observer_with_combined_access_sees_union(self):
        stream = StreamFactory()
        project_direct = ProjectFactory(semester=self.semester, name="Direct Project")
        project_via_stream = ProjectFactory(semester=self.semester, name="Stream Project")
        project_via_stream.streams.add(stream)
        ProjectFactory(semester=self.semester, name="Hidden Project")
        obs = UserProjectAccessFactory()
        obs.project_access.add(project_direct)
        obs.stream_access.add(stream)
        self.client.force_login(obs.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Direct Project")
        self.assertContains(response, "Stream Project")
        self.assertNotContains(response, "Hidden Project")

    def test_developer_with_project_access_restriction_sees_only_allowed_projects(self):
        dev = make_semester_developer(semester=self.semester)
        project_visible = ProjectFactory(semester=self.semester, name="Visible Project")
        ProjectFactory(semester=self.semester, name="Hidden Project")
        access = UserProjectAccessFactory(user=dev.user)
        access.project_access.add(project_visible)

        self.client.force_login(dev.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Project")
        self.assertNotContains(response, "Hidden Project")

    def test_developer_with_empty_access_record_sees_no_projects(self):
        dev = make_semester_developer(semester=self.semester)
        ProjectFactory(semester=self.semester, name="Alpha Project")
        ProjectFactory(semester=self.semester, name="Beta Project")
        UserProjectAccessFactory(user=dev.user)
        # empty access record + no phases on these projects = no access

        self.client.force_login(dev.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Alpha Project")
        self.assertNotContains(response, "Beta Project")

    def test_user_with_phase_sees_project_despite_empty_access_record(self):
        dev = make_semester_developer(semester=self.semester)
        project_with_phase = ProjectFactory(semester=self.semester, name="Phase Project")
        ProjectFactory(semester=self.semester, name="Hidden Project")
        access = UserProjectAccessFactory(user=dev.user)
        Phase.objects.create(
            developer=dev,
            project=project_with_phase,
            semester=self.semester,
            start_date=self.semester.start_date,
            end_date=self.semester.start_date + datetime.timedelta(days=6),
        )

        self.client.force_login(dev.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Phase Project")
        self.assertNotContains(response, "Hidden Project")
        del access  # suppress unused-variable warning

    def test_user_as_dev_lead_sees_project_despite_empty_access_record(self):
        dev = make_semester_developer(semester=self.semester)
        ProjectFactory(semester=self.semester, name="Lead Project", dev_lead=dev.user)
        ProjectFactory(semester=self.semester, name="Hidden Project")
        UserProjectAccessFactory(user=dev.user)

        self.client.force_login(dev.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lead Project")
        self.assertNotContains(response, "Hidden Project")

    def test_shows_project_display_name(self):
        ProjectFactory(semester=self.semester, name="My Project Name")
        user = make_semester_developer().user
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
        self.assertRoleAccess(
            self.url,
            allowed=["pm", "developer"],
            denied=["observer"],
        )

    def test_context_contains_developer_rows(self):
        sem = Semester.get_current()
        dev = DeveloperProfileFactory()
        project = ProjectFactory()
        Phase.objects.create(
            developer=dev,
            project=project,
            semester=sem,
            start_date=sem.start_date,
            end_date=sem.start_date + datetime.timedelta(days=6),
        )
        self.client.force_login(PMUserFactory())
        response = self.client.get(self.url)
        self.assertIn("developer_rows", response.context)
        pks = [row["developer"].pk for row in response.context["developer_rows"]]
        self.assertIn(dev.pk, pks)
        row = next(
            r for r in response.context["developer_rows"] if r["developer"].pk == dev.pk
        )
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
                developer=dev,
                project=ProjectFactory(),
                semester=sem,
                start_date=sem.start_date,
                end_date=sem.start_date + datetime.timedelta(days=6),
            )
        self.client.force_login(PMUserFactory())
        response = self.client.get(self.url + "?tags=python")
        pks = [row["developer"].pk for row in response.context["developer_rows"]]
        self.assertIn(dev_with.pk, pks)
        self.assertNotIn(dev_without.pk, pks)

    def test_developer_can_access_planning(self):
        dev = make_semester_developer()
        self.client.force_login(dev.user)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_observer_cannot_access_planning(self):
        obs = make_restricted_access_user()
        self.client.force_login(obs.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_developer_sees_can_edit_false(self):
        dev = make_semester_developer()
        self.client.force_login(dev.user)
        response = self.client.get(self.url)
        self.assertFalse(response.context["can_edit"])

    def test_developer_sees_all_developer_rows_on_planning(self):
        """Developer has unrestricted access — all developer rows appear in context."""
        sem = Semester.get_current()
        dev_profile = make_semester_developer(semester=sem)
        self.client.force_login(dev_profile.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        developer_pks = [
            row["developer"].pk for row in response.context["developer_rows"]
        ]
        self.assertIn(dev_profile.pk, developer_pks)

    def test_developer_with_project_restrictions_sees_only_allowed_projects_in_context(
        self,
    ):
        sem = Semester.get_current()
        dev_profile = make_semester_developer(semester=sem)
        visible = ProjectFactory(semester=sem, name="Visible Project")
        ProjectFactory(semester=sem, name="Hidden Project")
        access = UserProjectAccessFactory(user=dev_profile.user)
        access.project_access.add(visible)

        self.client.force_login(dev_profile.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        project_names = {p.display_name for p in response.context["projects"]}
        self.assertIn("Visible Project", project_names)
        self.assertNotIn("Hidden Project", project_names)

    def test_developer_with_phases_sees_all_phase_projects_via_team_membership(
        self,
    ):
        # Team membership (having a phase) grants access regardless of explicit
        # project_access restrictions.
        sem = Semester.get_current()
        dev_profile = make_semester_developer(semester=sem)
        visible = ProjectFactory(semester=sem, name="Visible Project")
        hidden = ProjectFactory(semester=sem, name="Hidden Project")
        Phase.objects.create(
            developer=dev_profile,
            project=visible,
            semester=sem,
            start_date=sem.start_date,
            end_date=sem.start_date + datetime.timedelta(days=6),
        )
        Phase.objects.create(
            developer=dev_profile,
            project=hidden,
            semester=sem,
            start_date=sem.start_date,
            end_date=sem.start_date + datetime.timedelta(days=6),
        )
        access = UserProjectAccessFactory(user=dev_profile.user)
        access.project_access.add(visible)

        self.client.force_login(dev_profile.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        # Both projects are visible because team membership via phases grants access.
        self.assertContains(response, "Visible Project")
        self.assertContains(response, "Hidden Project")

    def test_overlapping_phases_render_in_separate_lanes(self):
        sem = Semester.get_current()
        dev = DeveloperProfileFactory()
        p1 = ProjectFactory(semester=sem)
        p2 = ProjectFactory(semester=sem)
        Phase.objects.create(
            developer=dev,
            project=p1,
            semester=sem,
            start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 2, 2),
        )
        Phase.objects.create(
            developer=dev,
            project=p2,
            semester=sem,
            start_date=datetime.date(2026, 1, 12),
            end_date=datetime.date(2026, 2, 9),
        )
        self.client.force_login(PMUserFactory())
        response = self.client.get(self.url)
        row = next(
            r for r in response.context["developer_rows"] if r["developer"].pk == dev.pk
        )
        self.assertEqual(len(row["lanes"]), 2)

    def test_non_overlapping_phases_share_single_lane(self):
        sem = Semester.get_current()
        dev = DeveloperProfileFactory()
        p1 = ProjectFactory(semester=sem)
        p2 = ProjectFactory(semester=sem)
        Phase.objects.create(
            developer=dev,
            project=p1,
            semester=sem,
            start_date=datetime.date(2026, 1, 5),
            end_date=datetime.date(2026, 2, 2),
        )
        Phase.objects.create(
            developer=dev,
            project=p2,
            semester=sem,
            start_date=datetime.date(2026, 2, 9),
            end_date=datetime.date(2026, 3, 2),
        )
        self.client.force_login(PMUserFactory())
        response = self.client.get(self.url)
        row = next(
            r for r in response.context["developer_rows"] if r["developer"].pk == dev.pk
        )
        self.assertEqual(len(row["lanes"]), 1)


# ---------------------------------------------------------------------------
# Schedule page
# ---------------------------------------------------------------------------


class ScheduleViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:schedule")

    def test_redirects_anonymous(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_role_access(self):
        self.assertRoleAccess(
            self.url,
            allowed=["pm", "developer", "observer"],
        )

    def _make_phase_in_current_semester(self, multiplier):
        sem = Semester.get_current()
        dev = DeveloperProfileFactory()
        project = ProjectFactory(semester=sem)
        # Use start of semester so it's within the rendered range
        start = sem.start_date
        end = start + datetime.timedelta(days=6)
        return Phase.objects.create(
            developer=dev,
            project=project,
            semester=sem,
            start_date=start,
            end_date=end,
            effort_multiplier=multiplier,
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
        self.client.force_login(PMUserFactory())
        response = self.client.get(self.url)
        phase = self._find_phase_in_context(response)
        self.assertIsNotNone(phase)
        self.assertAlmostEqual(phase.effort_unfilled_pct, 0.0)

    def test_effort_unfilled_pct_half_time(self):
        self._make_phase_in_current_semester(0.5)
        self.client.force_login(PMUserFactory())
        response = self.client.get(self.url)
        phase = self._find_phase_in_context(response)
        self.assertIsNotNone(phase)
        self.assertAlmostEqual(phase.effort_unfilled_pct, 50.0)


# ---------------------------------------------------------------------------
# Phase CRUD views
# ---------------------------------------------------------------------------


class PhaseViewTestCase(PlanningTestCase):
    def setUp(self):
        self.pm = PMUserFactory()
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
        self.pm = PMUserFactory()
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

    def test_pm_can_create(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, self.post_data)
        self.assertEqual(Phase.objects.count(), 1)

    def test_developer_denied(self):
        self.client.force_login(make_semester_developer().user)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Phase.objects.count(), 0)

    def test_observer_denied(self):
        self.client.force_login(make_restricted_access_user().user)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(Phase.objects.count(), 0)

    def test_creates_phase_with_correct_fields(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, self.post_data)
        phase = Phase.objects.get()
        self.assertEqual(phase.developer, self.dev)
        self.assertEqual(phase.project, self.project)
        self.assertEqual(phase.start_date, datetime.date(2026, 1, 5))
        self.assertEqual(phase.end_date, datetime.date(2026, 2, 2))
        self.assertAlmostEqual(phase.effort_multiplier, 1.0)

    def test_phase_gets_lane_assigned(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, self.post_data)
        phase = Phase.objects.get()
        self.assertIsNotNone(phase.lane_id)

    def test_overlapping_phase_gets_new_lane(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, self.post_data)
        overlapping_data = dict(
            self.post_data,
            start_date="2026-01-12",
            end_date="2026-02-09",
        )
        self.client.post(self.url, overlapping_data)
        phases = list(Phase.objects.all())
        self.assertEqual(len(phases), 2)
        self.assertNotEqual(phases[0].lane_id, phases[1].lane_id)

    def test_lane_pk_new_requests_new_lane(self):
        self.client.force_login(self.pm)
        # First phase — creates a lane
        self.client.post(self.url, self.post_data)
        first_lane = Phase.objects.first().lane
        # Second non-overlapping phase with lane_pk=new — must land in a NEW lane
        non_overlapping = dict(
            self.post_data,
            start_date="2026-03-02",
            end_date="2026-04-06",
            lane_pk="new",
        )
        self.client.post(self.url, non_overlapping)
        second_phase = Phase.objects.order_by("-pk").first()
        self.assertNotEqual(second_phase.lane, first_lane)

    def test_redirects_to_next_url(self):
        self.client.force_login(self.pm)
        data = dict(self.post_data, next="/planning/planning/")
        response = self.client.post(self.url, data)
        self.assertRedirects(
            response,
            "/planning/planning/",
            fetch_redirect_response=False,
        )

    def test_invalid_date_rejected_without_creating_phase(self):
        self.client.force_login(self.pm)
        data = dict(self.post_data, start_date="not-a-date")
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Phase.objects.count(), 0)

    def test_end_before_start_does_not_create_phase(self):
        self.client.force_login(self.pm)
        data = dict(self.post_data, start_date="2026-02-09", end_date="2026-01-12")
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Phase.objects.count(), 0)


class PhaseDeleteViewTests(PhaseViewTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("planning:phase_delete", args=[self.phase.pk])

    def test_pm_can_delete(self):
        self.client.force_login(PMUserFactory())
        self.client.post(self.url, {})
        self.assertFalse(Phase.objects.filter(pk=self.phase.pk).exists())

    def test_developer_denied(self):
        self.client.force_login(UserFactory())
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Phase.objects.filter(pk=self.phase.pk).exists())

    def test_empty_lane_deleted_after_delete(self):
        lane_pk = self.phase.lane_id
        self.client.force_login(self.pm)
        self.client.post(self.url, {})
        self.assertFalse(DeveloperLane.objects.filter(pk=lane_pk).exists())

    def test_non_empty_lane_kept_after_delete(self):
        # Add a second phase to the same lane so it won't be empty after deletion
        Phase.objects.create(
            developer=self.dev,
            project=self.project,
            semester=self.sem,
            start_date=datetime.date(2026, 3, 2),
            end_date=datetime.date(2026, 4, 6),
            lane=self.phase.lane,
        )
        lane_pk = self.phase.lane_id
        self.client.force_login(self.pm)
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

    def test_pm_can_update(self):
        self.client.force_login(self.pm)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 204)

    def test_developer_denied(self):
        self.client.force_login(UserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_invalid_date_returns_400(self):
        self.client.force_login(self.pm)
        data = dict(self.post_data, start_date="not-a-date")
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 400)

    def test_end_before_start_returns_400(self):
        self.client.force_login(self.pm)
        data = dict(self.post_data, start_date="2026-02-09", end_date="2026-01-12")
        original_start = self.phase.start_date
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 400)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.start_date, original_start)

    def test_updates_dates(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, self.post_data)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.start_date, datetime.date(2026, 1, 12))
        self.assertEqual(self.phase.end_date, datetime.date(2026, 2, 9))

    def test_lane_pk_new_changes_developer(self):
        new_dev = DeveloperProfileFactory()
        self.client.force_login(self.pm)
        self.client.post(
            self.url,
            {
                **self.post_data,
                "lane_pk": "new",
                "developer_pk": new_dev.pk,
            },
        )
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.developer, new_dev)

    def test_overlap_bumps_to_new_lane(self):
        # Create a second phase in the same lane, non-overlapping
        phase2 = Phase.objects.create(
            developer=self.dev,
            project=self.project,
            semester=self.sem,
            start_date=datetime.date(2026, 3, 2),
            end_date=datetime.date(2026, 4, 6),
        )
        original_lane = phase2.lane
        # Move phase2 to overlap with self.phase
        url2 = reverse("planning:phase_update", args=[phase2.pk])
        self.client.force_login(self.pm)
        self.client.post(
            url2,
            {
                "start_date": "2026-01-12",
                "end_date": "2026-02-09",
                "lane_pk": str(original_lane.pk),
            },
        )
        phase2.refresh_from_db()
        self.assertNotEqual(phase2.lane, original_lane)

    def test_old_empty_lane_deleted_on_developer_change(self):
        # phase is alone in its lane; change developer → old lane should be deleted
        new_dev = DeveloperProfileFactory()
        old_lane_pk = self.phase.lane_id
        self.client.force_login(self.pm)
        self.client.post(
            self.url,
            {
                **self.post_data,
                "lane_pk": "new",
                "developer_pk": new_dev.pk,
            },
        )
        self.assertFalse(DeveloperLane.objects.filter(pk=old_lane_pk).exists())

    def test_old_non_empty_lane_kept_on_developer_change(self):
        # Add another phase to the same lane
        Phase.objects.create(
            developer=self.dev,
            project=self.project,
            semester=self.sem,
            start_date=datetime.date(2026, 3, 2),
            end_date=datetime.date(2026, 4, 6),
            lane=self.phase.lane,
        )
        new_dev = DeveloperProfileFactory()
        old_lane_pk = self.phase.lane_id
        self.client.force_login(self.pm)
        self.client.post(
            self.url,
            {
                **self.post_data,
                "lane_pk": "new",
                "developer_pk": new_dev.pk,
            },
        )
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

    def test_pm_can_edit(self):
        self.client.force_login(self.pm)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_developer_denied(self):
        self.client.force_login(UserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_updates_project_dates_multiplier(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, self.post_data)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.project, self.project2)
        self.assertEqual(self.phase.start_date, datetime.date(2026, 1, 12))
        self.assertEqual(self.phase.end_date, datetime.date(2026, 2, 9))
        self.assertAlmostEqual(self.phase.effort_multiplier, 0.5)

    def test_same_developer_keeps_lane(self):
        original_lane = self.phase.lane
        self.client.force_login(self.pm)
        self.client.post(self.url, self.post_data)
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.lane, original_lane)

    def test_developer_change_assigns_new_lane(self):
        new_dev = DeveloperProfileFactory()
        self.client.force_login(self.pm)
        self.client.post(self.url, dict(self.post_data, developer=new_dev.pk))
        self.phase.refresh_from_db()
        self.assertEqual(self.phase.developer, new_dev)
        self.assertEqual(self.phase.lane.developer, new_dev)

    def test_developer_change_deletes_empty_old_lane(self):
        old_lane_pk = self.phase.lane_id
        new_dev = DeveloperProfileFactory()
        self.client.force_login(self.pm)
        self.client.post(self.url, dict(self.post_data, developer=new_dev.pk))
        self.assertFalse(DeveloperLane.objects.filter(pk=old_lane_pk).exists())

    def test_developer_change_keeps_non_empty_old_lane(self):
        # Put another phase in the same lane
        Phase.objects.create(
            developer=self.dev,
            project=self.project,
            semester=self.sem,
            start_date=datetime.date(2026, 3, 2),
            end_date=datetime.date(2026, 4, 6),
            lane=self.phase.lane,
        )
        old_lane_pk = self.phase.lane_id
        new_dev = DeveloperProfileFactory()
        self.client.force_login(self.pm)
        self.client.post(self.url, dict(self.post_data, developer=new_dev.pk))
        self.assertTrue(DeveloperLane.objects.filter(pk=old_lane_pk).exists())


# ---------------------------------------------------------------------------
# Developer CRUD views
# ---------------------------------------------------------------------------


class DeveloperCreateViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:developer_add")
        self.pm = PMUserFactory()
        self.profile = DeveloperProfileFactory()

    def test_role_access(self):
        self.assertRoleAccess(
            self.url,
            method="post",
            allowed=["pm"],
            denied=["developer", "observer"],
            data={"user_pks": [self.profile.user.pk]},
        )

    def test_adds_profile_to_semester(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, {"user_pks": [self.profile.user.pk]})
        self.assertTrue(
            SemesterDeveloper.objects.filter(developer=self.profile).exists(),
        )

    def test_empty_pks_redirects_without_creating(self):
        before = SemesterDeveloper.objects.count()
        self.client.force_login(self.pm)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SemesterDeveloper.objects.count(), before)

    def test_sets_effort_available(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, {"user_pks": [self.profile.user.pk]})
        self.assertTrue(
            SemesterDeveloper.objects.filter(
                developer=self.profile,
                effort_available=self.profile.base_effort_weeks,
            ).exists(),
        )

    def test_creates_profile_if_not_exists(self):
        """Creating from a user with no DeveloperProfile creates one."""
        user = UserFactory()
        self.assertFalse(DeveloperProfile.objects.filter(user=user).exists())
        self.client.force_login(self.pm)
        self.client.post(self.url, {"user_pks": [user.pk], f"effort_{user.pk}": "15"})
        self.assertTrue(DeveloperProfile.objects.filter(user=user).exists())

    def test_updates_base_effort_when_profile_created(self):
        """effort_<pk> sets base_effort_weeks on newly created profile."""
        user = UserFactory()
        self.client.force_login(self.pm)
        self.client.post(self.url, {"user_pks": [user.pk], f"effort_{user.pk}": "18"})
        profile = DeveloperProfile.objects.get(user=user)
        self.assertEqual(float(profile.base_effort_weeks), 18.0)

    def test_update_base_flag_updates_existing_profile(self):
        """update_base_<pk> flag causes base_effort_weeks to be updated on existing profile."""
        self.client.force_login(self.pm)
        original_base = float(self.profile.base_effort_weeks)
        new_effort = original_base + 5
        self.client.post(
            self.url,
            {
                "user_pks": [self.profile.user.pk],
                f"effort_{self.profile.user.pk}": str(new_effort),
                f"update_base_{self.profile.user.pk}": "1",
            },
        )
        self.profile.refresh_from_db()
        self.assertEqual(float(self.profile.base_effort_weeks), new_effort)

    def test_no_update_base_flag_leaves_existing_profile_unchanged(self):
        """Without update_base_<pk>, existing profile base_effort_weeks is not changed."""
        self.client.force_login(self.pm)
        original_base = float(self.profile.base_effort_weeks)
        new_effort = original_base + 5
        self.client.post(
            self.url,
            {
                "user_pks": [self.profile.user.pk],
                f"effort_{self.profile.user.pk}": str(new_effort),
            },
        )
        self.profile.refresh_from_db()
        self.assertEqual(float(self.profile.base_effort_weeks), original_base)

    def test_seeds_semester_tags_from_base_tags(self):
        """When a developer is added to a semester, their SemesterDeveloper gets the base tags."""
        tag = Tag.objects.create(name="TestTag")
        self.profile.tags.add(tag)
        self.client.force_login(self.pm)
        self.client.post(
            self.url,
            {
                "user_pks": [self.profile.user.pk],
                f"effort_{self.profile.user.pk}": "20",
            },
        )
        sd = SemesterDeveloper.objects.get(developer=self.profile)
        self.assertIn(tag, sd.tags.all())


class DeveloperUpdateViewTests(PlanningTestCase):
    def setUp(self):
        self.pm = PMUserFactory()
        self.profile = DeveloperProfileFactory()
        self.url = reverse("planning:developer_edit", args=[self.profile.pk])
        self.post_data = {
            "name": "Updated Name",
            "organisation": "Updated Org",
        }

    def test_role_access(self):
        self.assertRoleAccess(
            self.url,
            method="post",
            allowed=["pm"],
            denied=["developer"],
            data=self.post_data,
        )

    def test_updates_effort_available(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, {**self.post_data, "effort_available": "18"})
        self.assertTrue(
            SemesterDeveloper.objects.filter(
                developer=self.profile,
                effort_available=18,
            ).exists(),
        )


class DeveloperDeleteViewTests(PlanningTestCase):
    def setUp(self):
        self.pm = PMUserFactory()
        self.profile = DeveloperProfileFactory()
        self.url = reverse("planning:developer_delete", args=[self.profile.pk])

    def test_removes_from_semester_only(self):
        profile = DeveloperProfileFactory()
        semester = Semester.get_current()
        sd = SemesterDeveloper.objects.create(
            developer=profile,
            semester=semester,
            effort_available=20,
        )
        self.client.force_login(PMUserFactory())
        response = self.client.post(
            reverse("planning:developer_delete", args=[profile.pk]),
            {},
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(SemesterDeveloper.objects.filter(pk=sd.pk).exists())
        self.assertTrue(DeveloperProfile.objects.filter(pk=profile.pk).exists())

    def test_developer_denied(self):
        self.client.force_login(UserFactory())
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 403)

    def test_removes_semester_developer_record(self):
        semester = Semester.get_current()
        sd = SemesterDeveloper.objects.create(
            developer=self.profile,
            semester=semester,
            effort_available=20,
        )
        sd_pk = sd.pk
        self.client.force_login(self.pm)
        self.client.post(self.url, {})
        self.assertFalse(SemesterDeveloper.objects.filter(pk=sd_pk).exists())

    def test_profile_and_user_remain_after_removal(self):
        """Removing a developer from a semester does not delete their profile or user account."""
        profile = DeveloperProfileFactory()
        semester = Semester.get_current()
        SemesterDeveloper.objects.create(
            developer=profile,
            semester=semester,
            effort_available=20,
        )
        self.client.force_login(self.pm)
        self.client.post(reverse("planning:developer_delete", args=[profile.pk]), {})
        self.assertTrue(DeveloperProfile.objects.filter(pk=profile.pk).exists())
        User = get_user_model()
        self.assertTrue(User.objects.filter(pk=profile.user.pk).exists())


# ---------------------------------------------------------------------------
# Observer CRUD views
# ---------------------------------------------------------------------------


class ObserverCreateViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:observer_add")
        self.pm = PMUserFactory()
        self.target_user = UserFactory()
        self.post_data = {"user": self.target_user.pk}

    def test_role_access(self):
        self.assertRoleAccess(
            self.url,
            method="post",
            allowed=["pm"],
            denied=["developer", "observer"],
            data=self.post_data,
        )

    def test_creates_user_project_access(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, self.post_data)
        self.assertTrue(
            UserProjectAccess.objects.filter(user=self.target_user).exists(),
        )

    def test_sets_project_access(self):
        project = ProjectFactory()
        self.client.force_login(self.pm)
        self.client.post(self.url, {**self.post_data, "project_access": [project.pk]})
        obs = UserProjectAccess.objects.get(user=self.target_user)
        self.assertIn(project, obs.project_access.all())


class ObserverUpdateViewTests(PlanningTestCase):
    def setUp(self):
        self.pm = PMUserFactory()
        self.obs = UserProjectAccessFactory()
        self.url = reverse("planning:observer_edit", args=[self.obs.pk])
        self.post_data = {
            "name": "Updated Observer",
            "organisation": "Updated Org",
        }

    def test_pm_can_update(self):
        self.client.force_login(self.pm)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_developer_denied(self):
        self.client.force_login(UserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_updates_project_access(self):
        project = ProjectFactory()
        self.client.force_login(self.pm)
        self.client.post(self.url, {**self.post_data, "project_access": [project.pk]})
        self.obs.refresh_from_db()
        self.assertIn(project, self.obs.project_access.all())

    def test_clears_project_access(self):
        project = ProjectFactory()
        self.obs.project_access.add(project)
        self.client.force_login(self.pm)
        self.client.post(self.url, self.post_data)  # no project_access in POST
        self.assertEqual(self.obs.project_access.count(), 0)


class ObserverDeleteViewTests(PlanningTestCase):
    def setUp(self):
        self.pm = PMUserFactory()
        self.obs = UserProjectAccessFactory()
        self.url = reverse("planning:observer_delete", args=[self.obs.pk])

    def test_pm_can_revoke_access(self):
        obs = UserProjectAccessFactory()
        project = ProjectFactory()
        obs.project_access.add(project)
        self.client.force_login(PMUserFactory())
        response = self.client.post(
            reverse("planning:observer_delete", args=[obs.pk]),
            {},
        )
        self.assertEqual(response.status_code, 204)
        obs.refresh_from_db()
        self.assertEqual(obs.project_access.count(), 0)

    def test_developer_denied(self):
        self.client.force_login(UserFactory())
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 403)

    def test_revokes_access_keeps_observer_and_user(self):
        user_pk = self.obs.user_id
        obs_pk = self.obs.pk
        project = ProjectFactory()
        self.obs.project_access.add(project)
        self.client.force_login(self.pm)
        self.client.post(self.url, {})
        self.assertTrue(UserProjectAccess.objects.filter(pk=obs_pk).exists())
        self.assertTrue(get_user_model().objects.filter(pk=user_pk).exists())
        self.obs.refresh_from_db()
        self.assertEqual(self.obs.project_access.count(), 0)

    def test_access_record_persists_after_revoke(self):
        """The UserProjectAccess record itself is not deleted when access is revoked."""
        project = ProjectFactory()
        stream = Stream.objects.create(name="TestStream", colour="#aabbcc")
        self.obs.project_access.add(project)
        self.obs.stream_access.add(stream)
        obs_pk = self.obs.pk
        self.client.force_login(self.pm)
        self.client.post(self.url, {})
        self.assertTrue(UserProjectAccess.objects.filter(pk=obs_pk).exists())
        self.obs.refresh_from_db()
        self.assertEqual(self.obs.project_access.count(), 0)
        self.assertEqual(self.obs.stream_access.count(), 0)


# ---------------------------------------------------------------------------
# Project CRUD views
# ---------------------------------------------------------------------------


class ProjectCreateViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:project_add")
        self.pm = PMUserFactory()
        self.post_data = {
            "name": "New Project",
            "streams": "Engineering",
            "effort_resourced": "10",
        }

    def test_role_access(self):
        self.assertRoleAccess(
            self.url,
            method="post",
            allowed=["pm"],
            denied=["developer", "observer"],
            data=self.post_data,
        )

    def test_creates_project_with_name(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, self.post_data)
        self.assertTrue(Project.objects.filter(name="New Project").exists())

    def test_creates_allocation(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, self.post_data)
        self.assertTrue(ProjectAllocation.objects.filter(weeks_new=10).exists())

    def test_empty_name_redirects_without_creating(self):
        before = Project.objects.count()
        self.client.force_login(self.pm)
        response = self.client.post(self.url, {**self.post_data, "name": ""})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Project.objects.count(), before)

    def test_creates_project_with_dev_lead(self):
        user = UserFactory()
        self.client.force_login(self.pm)
        self.client.post(self.url, {**self.post_data, "dev_lead": str(user.pk)})
        project = Project.objects.latest("pk")
        self.assertEqual(project.dev_lead, user)

    def test_creates_project_with_internal_science_lead(self):
        user = UserFactory()
        self.client.force_login(self.pm)
        self.client.post(self.url, {**self.post_data, "science_lead": str(user.pk)})
        project = Project.objects.latest("pk")
        self.assertEqual(project.science_lead, user)
        self.assertEqual(project.science_lead_name, "")

    def test_creates_project_with_external_science_lead(self):
        self.client.force_login(self.pm)
        self.client.post(
            self.url,
            {**self.post_data, "science_lead_name": "Prof. External"},
        )
        project = Project.objects.latest("pk")
        self.assertIsNone(project.science_lead)
        self.assertEqual(project.science_lead_name, "Prof. External")

    def test_creates_project_with_continuation_of(self):
        source = ProjectFactory()
        self.client.force_login(self.pm)
        self.client.post(
            self.url,
            {**self.post_data, "continuation_of": str(source.pk)},
        )
        project = Project.objects.latest("pk")
        self.assertEqual(project.continuation_of, source)

    def test_invalid_effort_does_not_create_project(self):
        before = Project.objects.count()
        self.client.force_login(self.pm)
        response = self.client.post(
            self.url,
            {
                **self.post_data,
                "name": "Bad Effort",
                "effort_resourced": "not-a-number",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Project.objects.count(), before)

    def test_negative_effort_does_not_create_project(self):
        before = Project.objects.count()
        self.client.force_login(self.pm)
        response = self.client.post(
            self.url,
            {**self.post_data, "name": "Negative Effort", "effort_resourced": "-1"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Project.objects.count(), before)

    def test_invalid_name_with_separator_does_not_create_project(self):
        before = Project.objects.count()
        self.client.force_login(self.pm)
        response = self.client.post(
            self.url,
            {**self.post_data, "name": "Bad||Name"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Project.objects.count(), before)


class ProjectUpdateViewTests(PlanningTestCase):
    def setUp(self):
        self.pm = PMUserFactory()
        self.semester = SemesterFactory()
        self.project = ProjectFactory(semester=self.semester, name="Old Name")
        ProjectAllocationFactory(
            project=self.project,
            semester=self.semester,
            weeks_new=3,
            weeks_carryover=0,
        )
        self.url = reverse("planning:project_edit", args=[self.project.pk])
        self.post_data = {
            "name": "New Name",
            "effort_resourced": "15",
        }

    def test_pm_can_update(self):
        self.client.force_login(self.pm)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)

    def test_developer_denied(self):
        self.client.force_login(UserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_updates_name(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, self.post_data)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "New Name")

    def test_updates_allocation(self):
        self.client.force_login(self.pm)
        self.client.post(self.url, self.post_data)
        self.assertTrue(
            ProjectAllocation.objects.filter(
                project=self.project,
                weeks_new=15,
            ).exists(),
        )

    def test_updates_dev_lead(self):
        user = UserFactory()
        self.client.force_login(self.pm)
        self.client.post(self.url, {**self.post_data, "dev_lead": str(user.pk)})
        self.project.refresh_from_db()
        self.assertEqual(self.project.dev_lead, user)

    def test_updates_science_lead_name(self):
        self.client.force_login(self.pm)
        self.client.post(
            self.url,
            {**self.post_data, "science_lead_name": "External Lead"},
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.science_lead_name, "External Lead")

    def test_clears_science_lead_name_when_internal_lead_set(self):
        self.project.science_lead_name = "Old External"
        self.project.save()
        user = UserFactory()
        self.client.force_login(self.pm)
        self.client.post(self.url, {**self.post_data, "science_lead": str(user.pk)})
        self.project.refresh_from_db()
        self.assertEqual(self.project.science_lead, user)
        self.assertEqual(self.project.science_lead_name, "")

    def test_updates_continuation_of(self):
        source = ProjectFactory()
        self.client.force_login(self.pm)
        self.client.post(
            self.url,
            {**self.post_data, "continuation_of": str(source.pk)},
        )
        self.project.refresh_from_db()
        self.assertEqual(self.project.continuation_of, source)

    def test_invalid_effort_keeps_existing_project_state(self):
        self.client.force_login(self.pm)
        response = self.client.post(
            self.url,
            {**self.post_data, "name": "Should Not Save", "effort_resourced": "bad"},
        )
        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Old Name")
        alloc = ProjectAllocation.objects.get(
            project=self.project,
            semester=self.semester,
        )
        self.assertEqual(float(alloc.weeks_new), 3.0)

    def test_negative_effort_keeps_existing_project_state(self):
        self.client.force_login(self.pm)
        response = self.client.post(
            self.url,
            {**self.post_data, "name": "Should Not Save", "effort_resourced": "-2"},
        )
        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Old Name")
        alloc = ProjectAllocation.objects.get(
            project=self.project,
            semester=self.semester,
        )
        self.assertEqual(float(alloc.weeks_new), 3.0)

    def test_invalid_name_with_tab_keeps_existing_project_state(self):
        self.client.force_login(self.pm)
        response = self.client.post(
            self.url,
            {**self.post_data, "name": "Bad\tName"},
        )
        self.assertEqual(response.status_code, 302)
        self.project.refresh_from_db()
        self.assertEqual(self.project.name, "Old Name")


class ProjectDeleteViewTests(PlanningTestCase):
    def setUp(self):
        self.pm = PMUserFactory()
        self.project = ProjectFactory()
        self.url = reverse("planning:project_delete", args=[self.project.pk])

    def test_pm_can_delete(self):
        project = ProjectFactory()
        self.client.force_login(PMUserFactory())
        response = self.client.post(
            reverse("planning:project_delete", args=[project.pk]),
            {},
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())

    def test_developer_denied(self):
        self.client.force_login(UserFactory())
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 403)

    def test_deletes_project(self):
        pk = self.project.pk
        self.client.force_login(self.pm)
        self.client.post(self.url, {})
        self.assertFalse(Project.objects.filter(pk=pk).exists())

    def test_delete_always_removes_whole_project(self):
        project = ProjectFactory()
        self.client.force_login(self.pm)
        response = self.client.post(
            reverse("planning:project_delete", args=[project.pk]),
            {},
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Project.objects.filter(pk=project.pk).exists())


# ---------------------------------------------------------------------------
# Project migrate view
# ---------------------------------------------------------------------------


class ProjectMigrateViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:project_migrate")
        self.pm = PMUserFactory()
        self.target_sem = SemesterFactory(year=2026, semester_type=SemesterType.A)
        self.source_sem = SemesterFactory(year=2025, semester_type=SemesterType.B)
        self.source_project = ProjectFactory(semester=self.source_sem, name="Old Project")
        ProjectAllocationFactory(
            project=self.source_project,
            semester=self.source_sem,
            weeks_new=8,
            weeks_carryover=2,
        )

    def _migrate(self, effort=None, extra=None):
        self.client.force_login(self.pm)
        session = self.client.session
        session["selected_semester"] = "2026A"
        session.save()
        data = {
            "source_semester": str(self.source_sem.pk),
            "project_pks": [str(self.source_project.pk)],
            f"effort_{self.source_project.pk}": str(
                effort if effort is not None else 8,
            ),
        }
        if extra:
            data.update(extra)
        return self.client.post(self.url, data)

    def test_role_access(self):
        self.assertRoleAccess(
            self.url,
            method="post",
            allowed=["pm"],
            denied=["developer", "observer"],
            data={"source_semester": str(self.source_sem.pk), "project_pks": []},
        )

    def test_creates_new_project(self):
        before = Project.objects.count()
        self._migrate()
        self.assertEqual(Project.objects.count(), before + 1)

    def test_new_project_has_continuation_of(self):
        self._migrate()
        new = Project.objects.latest("pk")
        self.assertEqual(new.continuation_of, self.source_project)

    def test_new_project_has_name_and_semester(self):
        self._migrate()
        new = Project.objects.latest("pk")
        self.assertEqual(new.name, "Old Project")
        self.assertEqual(new.semester, self.target_sem)

    def test_new_project_has_allocation(self):
        self._migrate(effort=5)
        new = Project.objects.latest("pk")
        self.assertTrue(
            ProjectAllocation.objects.filter(
                project=new,
                semester=self.target_sem,
                weeks_new=5,
            ).exists(),
        )

    def test_copies_dev_lead(self):
        dev = UserFactory()
        self.source_project.dev_lead = dev
        self.source_project.save()
        self._migrate()
        new = Project.objects.latest("pk")
        self.assertEqual(new.dev_lead, dev)

    def test_copies_science_lead(self):
        sci = UserFactory()
        self.source_project.science_lead = sci
        self.source_project.save()
        self._migrate()
        new = Project.objects.latest("pk")
        self.assertEqual(new.science_lead, sci)

    def test_copies_external_science_lead_name(self):
        self.source_project.science_lead_name = "Prof. External"
        self.source_project.save()
        self._migrate()
        new = Project.objects.latest("pk")
        self.assertEqual(new.science_lead_name, "Prof. External")

    def test_invalid_source_semester_redirects(self):
        self.client.force_login(self.pm)
        response = self.client.post(
            self.url,
            {"source_semester": "99999", "project_pks": []},
        )
        self.assertEqual(response.status_code, 302)

    def test_invalid_effort_does_not_migrate_any_project(self):
        before = Project.objects.count()
        self._migrate(effort="not-a-number")
        self.assertEqual(Project.objects.count(), before)

    def test_negative_effort_does_not_migrate_any_project(self):
        before = Project.objects.count()
        self._migrate(effort="-1")
        self.assertEqual(Project.objects.count(), before)


# ---------------------------------------------------------------------------
# Leave views
# ---------------------------------------------------------------------------


class LeaveViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:leave")

    def test_redirects_anonymous(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_role_access(self):
        self.assertRoleAccess(
            self.url,
            allowed=["pm", "developer"],
            denied=["observer"],
        )

    def test_developer_sees_only_own_leave(self):
        dev1 = make_semester_developer()
        dev2 = make_semester_developer()
        # Use a far-future end_date so leave is not filtered out by the "show past" default
        leave1 = LeaveFactory(developer=dev1, end_date=datetime.date(2099, 3, 7))
        leave2 = LeaveFactory(developer=dev2, end_date=datetime.date(2099, 3, 14))
        self.client.force_login(dev1.user)
        response = self.client.get(self.url)
        pks = [lv.pk for lv in response.context["leave_periods"]]
        self.assertIn(leave1.pk, pks)
        self.assertNotIn(leave2.pk, pks)
        self.assertEqual(len(pks), 1)

    def test_pm_sees_all_leave(self):
        dev1 = DeveloperProfileFactory()
        dev2 = DeveloperProfileFactory()
        leave1 = LeaveFactory(developer=dev1, end_date=datetime.date(2099, 3, 7))
        leave2 = LeaveFactory(developer=dev2, end_date=datetime.date(2099, 3, 14))
        self.client.force_login(PMUserFactory())
        response = self.client.get(self.url)
        pks = [lv.pk for lv in response.context["leave_periods"]]
        self.assertIn(leave1.pk, pks)
        self.assertIn(leave2.pk, pks)


class LeaveCreateViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:leave_add")
        self.pm = PMUserFactory()
        self.dev = DeveloperProfileFactory()
        self.post_data = {
            "developer": self.dev.pk,
            "start_date": "2026-06-01",
            "end_date": "2026-06-07",
        }

    def test_pm_can_create(self):
        self.client.force_login(PMUserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Leave.objects.count(), 1)

    def test_observer_denied(self):
        self.client.force_login(UserFactory())
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_developer_creates_leave_for_own_profile(self):
        # The view ignores the submitted developer_id and uses the logged-in
        # developer's own profile.
        own_dev = make_semester_developer()
        self.client.force_login(own_dev.user)
        self.client.post(self.url, self.post_data)
        self.assertTrue(Leave.objects.filter(developer=own_dev).exists())

    def test_developer_without_profile_gets_403(self):
        # A user with role=DEVELOPER but no DeveloperProfile cannot create leave.
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.post(self.url, self.post_data)
        self.assertEqual(response.status_code, 403)

    def test_invalid_date_rejected_without_creating_leave(self):
        self.client.force_login(self.pm)
        data = dict(self.post_data, start_date="not-a-date")
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Leave.objects.count(), 0)

    def test_end_before_start_returns_redirect(self):
        self.client.force_login(self.pm)
        data = dict(self.post_data, start_date="2026-06-07", end_date="2026-06-01")
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Leave.objects.count(), 0)


class LeaveDeleteViewTests(PlanningTestCase):
    def setUp(self):
        self.pm = PMUserFactory()
        self.dev = make_semester_developer()
        self.leave = LeaveFactory(developer=self.dev)
        self.url = reverse("planning:leave_delete", args=[self.leave.pk])

    def test_pm_can_delete(self):
        self.client.force_login(self.pm)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Leave.objects.filter(pk=self.leave.pk).exists())

    def test_developer_can_delete_own_leave(self):
        self.client.force_login(self.dev.user)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Leave.objects.filter(pk=self.leave.pk).exists())

    def test_developer_cannot_delete_others_leave(self):
        other_dev = make_semester_developer()
        self.client.force_login(other_dev.user)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Leave.objects.filter(pk=self.leave.pk).exists())

    def test_observer_denied(self):
        self.client.force_login(UserFactory())
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 403)


class LeaveUpdateViewTests(PlanningTestCase):
    def setUp(self):
        self.dev = make_semester_developer()
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
        other_dev = make_semester_developer()
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
        self.client.force_login(UserFactory())
        response = self.client.post(self.url, self.valid_data)
        self.assertEqual(response.status_code, 403)

    def test_invalid_date_returns_400(self):
        self.client.force_login(PMUserFactory())
        response = self.client.post(
            self.url,
            {"start_date": "not-a-date", "end_date": "2026-03-13"},
        )
        self.assertEqual(response.status_code, 400)


# ---------------------------------------------------------------------------
# Developer download view
# ---------------------------------------------------------------------------


class DeveloperDownloadViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:developer_download")
        self.pm = PMUserFactory()

    def test_role_access(self):
        self.assertRoleAccess(self.url, method="get", denied=["developer", "observer"])

    def test_returns_tsv_response(self):
        profile = DeveloperProfileFactory()
        semester = Semester.get_current()
        SemesterDeveloper.objects.get_or_create(
            developer=profile,
            semester=semester,
            defaults={"effort_available": 20},
        )
        self.client.force_login(self.pm)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/octet-stream", response["Content-Type"])
        content = response.content.decode()
        self.assertIn("email", content)
        self.assertIn(profile.user.email, content)


# ---------------------------------------------------------------------------
# Project download view
# ---------------------------------------------------------------------------


class ProjectDownloadViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:project_download")
        self.pm = PMUserFactory()
        self.semester = SemesterFactory(year=2026, semester_type=SemesterType.A)

    def test_role_access(self):
        self.assertRoleAccess(self.url, method="get", denied=["developer", "observer"])

    def test_returns_tsv_file(self):
        ProjectFactory(semester=self.semester, name="My Project")
        self.client.force_login(self.pm)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/octet-stream")
        self.assertIn("projects_", response["Content-Disposition"])

    def test_tsv_contains_project_name(self):
        ProjectFactory(semester=self.semester, name="Download Me")
        self.client.force_login(self.pm)
        response = self.client.get(self.url)
        self.assertIn(b"Download Me", response.content)

    def test_tsv_contains_dev_lead_name(self):
        dev = UserFactory(name="Dev Lead Person")
        ProjectFactory(semester=self.semester, name="Led Project", dev_lead=dev)
        self.client.force_login(self.pm)
        response = self.client.get(self.url)
        self.assertIn(b"Dev Lead Person", response.content)

    def test_tsv_contains_external_science_lead(self):
        ProjectFactory(semester=self.semester, name="Sci Project", science_lead_name="Prof. Smith")
        self.client.force_login(self.pm)
        response = self.client.get(self.url)
        self.assertIn(b"Prof. Smith", response.content)


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
        self.client.post(
            reverse("planning:tag_add"),
            {"name": "new-tag", "colour": "#4E79A7"},
        )
        tag = Tag.objects.get(name="new-tag")
        self.assertEqual(tag.colour, "#4E79A7")

    def test_create_tag_auto_assigns_colour_when_not_provided(self):
        self.client.force_login(self.pm)
        self.client.post(
            reverse("planning:tag_add"),
            {"name": "auto-colour-tag", "colour": ""},
        )
        tag = Tag.objects.get(name="auto-colour-tag")
        self.assertTrue(tag.colour)

    def test_rename_tag_preserves_pk(self):
        self.client.force_login(self.pm)
        self.client.post(
            reverse("planning:tag_add"),
            {"name": "original", "colour": "#4E79A7"},
        )
        tag = Tag.objects.get(name="original")
        original_pk = tag.pk
        self.client.post(
            reverse("planning:tag_edit", args=[tag.pk]),
            {"name": "renamed", "colour": "#4E79A7"},
        )
        tag.refresh_from_db()
        self.assertEqual(tag.name, "renamed")
        self.assertEqual(tag.pk, original_pk)

    def test_update_colour(self):
        self.client.force_login(self.pm)
        self.client.post(
            reverse("planning:tag_add"),
            {"name": "colour-test", "colour": "#4E79A7"},
        )
        tag = Tag.objects.get(name="colour-test")
        self.client.post(
            reverse("planning:tag_edit", args=[tag.pk]),
            {"name": "colour-test", "colour": "#E15759"},
        )
        tag.refresh_from_db()
        self.assertEqual(tag.colour, "#E15759")

    def test_delete_tag(self):
        self.client.force_login(self.pm)
        self.client.post(
            reverse("planning:tag_add"),
            {"name": "to-delete", "colour": "#4E79A7"},
        )
        tag = Tag.objects.get(name="to-delete")
        self.client.post(reverse("planning:tag_delete", args=[tag.pk]))
        self.assertFalse(Tag.objects.filter(pk=tag.pk).exists())


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
        self.client.post(
            reverse("planning:stream_add"),
            {"name": "new-stream", "colour": "#76B7B2"},
        )
        stream = Stream.objects.get(name="new-stream")
        self.assertEqual(stream.colour, "#76B7B2")

    def test_create_stream_auto_assigns_colour_when_not_provided(self):
        self.client.force_login(self.pm)
        self.client.post(
            reverse("planning:stream_add"),
            {"name": "auto-colour-stream", "colour": ""},
        )
        stream = Stream.objects.get(name="auto-colour-stream")
        self.assertTrue(stream.colour)

    def test_rename_stream_preserves_pk(self):
        self.client.force_login(self.pm)
        self.client.post(
            reverse("planning:stream_add"),
            {"name": "original-stream", "colour": "#76B7B2"},
        )
        stream = Stream.objects.get(name="original-stream")
        original_pk = stream.pk
        self.client.post(
            reverse("planning:stream_edit", args=[stream.pk]),
            {"name": "renamed-stream", "colour": "#76B7B2"},
        )
        stream.refresh_from_db()
        self.assertEqual(stream.name, "renamed-stream")
        self.assertEqual(stream.pk, original_pk)

    def test_update_colour(self):
        self.client.force_login(self.pm)
        self.client.post(
            reverse("planning:stream_add"),
            {"name": "stream-colour-test", "colour": "#76B7B2"},
        )
        stream = Stream.objects.get(name="stream-colour-test")
        self.client.post(
            reverse("planning:stream_edit", args=[stream.pk]),
            {"name": "stream-colour-test", "colour": "#59A14F"},
        )
        stream.refresh_from_db()
        self.assertEqual(stream.colour, "#59A14F")

    def test_delete_stream(self):
        self.client.force_login(self.pm)
        self.client.post(
            reverse("planning:stream_add"),
            {"name": "stream-to-delete", "colour": "#76B7B2"},
        )
        stream = Stream.objects.get(name="stream-to-delete")
        self.client.post(reverse("planning:stream_delete", args=[stream.pk]))
        self.assertFalse(Stream.objects.filter(pk=stream.pk).exists())


# ---------------------------------------------------------------------------
# get_selected_semester helper
# ---------------------------------------------------------------------------


class GetSelectedSemesterTests(TestCase):
    def _request(self, session=None):
        factory = RequestFactory()
        req = factory.get("/")
        req.session = session or {}
        return req

    def test_returns_current_when_no_session(self):
        from apps.planning.views._semester import get_selected_semester

        result = get_selected_semester(self._request())
        self.assertEqual(result, Semester.get_current())

    def test_returns_session_semester_when_set(self):
        from apps.planning.views._semester import get_selected_semester

        sem_db = SemesterFactory(year=2026, semester_type=SemesterType.A)
        result = get_selected_semester(self._request({"selected_semester": "2026A"}))
        self.assertEqual(result, sem_db)

    def test_falls_back_on_nonexistent_code(self):
        from apps.planning.views._semester import get_selected_semester

        result = get_selected_semester(self._request({"selected_semester": "9999Z"}))
        self.assertEqual(result, Semester.get_current())

    def test_falls_back_on_malformed_code(self):
        from apps.planning.views._semester import get_selected_semester

        result = get_selected_semester(
            self._request({"selected_semester": "not-a-code"}),
        )
        self.assertEqual(result, Semester.get_current())

    def test_falls_back_on_empty_string(self):
        from apps.planning.views._semester import get_selected_semester

        result = get_selected_semester(self._request({"selected_semester": ""}))
        self.assertEqual(result, Semester.get_current())


# ---------------------------------------------------------------------------
# semester_context context processor
# ---------------------------------------------------------------------------


class SemesterContextProcessorTests(TestCase):
    def _request(self, user=None, session=None):
        factory = RequestFactory()
        req = factory.get("/")
        req.user = user or AnonymousUser()
        req.session = session or {}
        return req

    def test_returns_empty_dict_for_anonymous(self):
        from apps.planning.context_processors import semester_context

        result = semester_context(self._request())
        self.assertEqual(result, {})

    def test_injects_selected_semester(self):
        from apps.planning.context_processors import semester_context

        result = semester_context(self._request(user=PMUserFactory()))
        self.assertIn("selected_semester", result)
        self.assertIsInstance(result["selected_semester"], Semester)

    def test_injects_all_semesters(self):
        from apps.planning.context_processors import semester_context

        sem_a = SemesterFactory(year=2026, semester_type=SemesterType.A)
        sem_b = SemesterFactory(year=2026, semester_type=SemesterType.B)
        result = semester_context(self._request(user=PMUserFactory()))
        self.assertIn("all_semesters", result)
        self.assertIn(sem_a, result["all_semesters"])
        self.assertIn(sem_b, result["all_semesters"])

    def test_respects_session_semester(self):
        from apps.planning.context_processors import semester_context

        sem = SemesterFactory(year=2026, semester_type=SemesterType.A)
        result = semester_context(
            self._request(user=PMUserFactory(), session={"selected_semester": "2026A"}),
        )
        self.assertEqual(result["selected_semester"], sem)

    def test_semesters_ordered_by_year_type(self):
        from apps.planning.context_processors import semester_context

        sem_2026b = SemesterFactory(year=2026, semester_type=SemesterType.B)
        sem_2026a = SemesterFactory(year=2026, semester_type=SemesterType.A)
        sem_2025b = SemesterFactory(year=2025, semester_type=SemesterType.B)
        result = semester_context(self._request(user=PMUserFactory()))
        sems = result["all_semesters"]
        self.assertEqual(sems[0], sem_2025b)
        self.assertEqual(sems[1], sem_2026a)
        self.assertEqual(sems[2], sem_2026b)


# ---------------------------------------------------------------------------
# SemesterSwitchView
# ---------------------------------------------------------------------------


class SemesterSwitchViewTests(TestCase):
    def test_requires_login(self):
        response = self.client.post(
            reverse("planning:semester_switch"),
            {"semester": "2026A"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/", response["Location"])

    def test_valid_code_sets_session(self):
        SemesterFactory(year=2026, semester_type=SemesterType.A)
        self.client.force_login(PMUserFactory())
        self.client.post(reverse("planning:semester_switch"), {"semester": "2026A"})
        self.assertEqual(self.client.session.get("selected_semester"), "2026A")

    def test_invalid_code_ignored(self):
        self.client.force_login(PMUserFactory())
        self.client.post(reverse("planning:semester_switch"), {"semester": "9999Z"})
        self.assertNotIn("selected_semester", self.client.session)

    def test_malformed_code_ignored(self):
        self.client.force_login(PMUserFactory())
        self.client.post(reverse("planning:semester_switch"), {"semester": "invalid"})
        self.assertNotIn("selected_semester", self.client.session)

    def test_redirects_to_next_parameter(self):
        SemesterFactory(year=2026, semester_type=SemesterType.A)
        self.client.force_login(PMUserFactory())
        response = self.client.post(
            reverse("planning:semester_switch"),
            {"semester": "2026A", "next": "/planning/schedule/"},
        )
        self.assertRedirects(
            response,
            "/planning/schedule/",
            fetch_redirect_response=False,
        )

    def test_redirects_to_default_when_no_next(self):
        SemesterFactory(year=2026, semester_type=SemesterType.A)
        self.client.force_login(PMUserFactory())
        response = self.client.post(
            reverse("planning:semester_switch"),
            {"semester": "2026A"},
        )
        self.assertRedirects(
            response,
            "/planning/planning/",
            fetch_redirect_response=False,
        )


# ---------------------------------------------------------------------------
# SemesterCreateView
# ---------------------------------------------------------------------------


class SemesterCreateViewTests(PlanningTestCase):
    def test_role_access(self):
        self.assertRoleAccess(
            reverse("planning:semester_add"),
            method="post",
            allowed=["pm"],
            denied=["developer", "observer"],
            data={"year": "2027", "semester_type": "A"},
        )

    def test_creates_semester(self):
        self.client.force_login(PMUserFactory())
        self.client.post(
            reverse("planning:semester_add"),
            {"year": "2027", "semester_type": "A"},
        )
        self.assertTrue(
            Semester.objects.filter(year=2027, semester_type=SemesterType.A).exists(),
        )

    def test_type_case_insensitive(self):
        self.client.force_login(PMUserFactory())
        self.client.post(
            reverse("planning:semester_add"),
            {"year": "2027", "semester_type": "a"},
        )
        self.assertTrue(
            Semester.objects.filter(year=2027, semester_type=SemesterType.A).exists(),
        )

    def test_ignores_invalid_year(self):
        self.client.force_login(PMUserFactory())
        before = Semester.objects.count()
        self.client.post(
            reverse("planning:semester_add"),
            {"year": "not-a-year", "semester_type": "A"},
        )
        self.assertEqual(Semester.objects.count(), before)

    def test_ignores_invalid_type(self):
        self.client.force_login(PMUserFactory())
        before = Semester.objects.count()
        self.client.post(
            reverse("planning:semester_add"),
            {"year": "2027", "semester_type": "C"},
        )
        self.assertEqual(Semester.objects.count(), before)

    def test_idempotent(self):
        self.client.force_login(PMUserFactory())
        self.client.post(
            reverse("planning:semester_add"),
            {"year": "2027", "semester_type": "B"},
        )
        self.client.post(
            reverse("planning:semester_add"),
            {"year": "2027", "semester_type": "B"},
        )
        self.assertEqual(
            Semester.objects.filter(year=2027, semester_type=SemesterType.B).count(),
            1,
        )

    def test_redirects_to_next(self):
        self.client.force_login(PMUserFactory())
        response = self.client.post(
            reverse("planning:semester_add"),
            {"year": "2027", "semester_type": "A", "next": "/planning/schedule/"},
        )
        self.assertRedirects(
            response,
            "/planning/schedule/",
            fetch_redirect_response=False,
        )


# ---------------------------------------------------------------------------
# PeopleView
# ---------------------------------------------------------------------------


class PeopleViewTests(PlanningTestCase):
    def setUp(self):
        self.url = reverse("planning:people")

    def test_redirects_anonymous(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_role_access(self):
        self.assertRoleAccess(
            self.url,
            allowed=["pm"],
            denied=["developer", "observer"],
        )

    def test_shows_all_users(self):
        dev = DeveloperProfileFactory()
        self.client.force_login(PMUserFactory())
        response = self.client.get(self.url)
        self.assertContains(response, dev.user.email)

    def test_tag_filter_includes_only_matching(self):
        tag = Tag.objects.create(name="python-pv")
        dev_with = DeveloperProfileFactory()
        dev_with.tags.add(tag)
        dev_without = DeveloperProfileFactory()
        self.client.force_login(PMUserFactory())
        response = self.client.get(self.url + "?tags=python-pv")
        self.assertContains(response, dev_with.user.email)
        self.assertNotContains(response, dev_without.user.email)

    def test_pm_sees_can_edit_true(self):
        self.client.force_login(PMUserFactory())
        response = self.client.get(self.url)
        self.assertTrue(response.context["can_edit"])

    def test_context_has_all_tags(self):
        tag = Tag.objects.create(name="tag-pv-ctx")
        self.client.force_login(PMUserFactory())
        response = self.client.get(self.url)
        self.assertIn(tag, response.context["all_tags"])

    def test_semester_agnostic(self):
        dev = DeveloperProfileFactory()
        SemesterFactory(year=2027, semester_type=SemesterType.B)
        session = self.client.session
        session["selected_semester"] = "2027B"
        session.save()
        self.client.force_login(PMUserFactory())
        response = self.client.get(self.url)
        self.assertContains(response, dev.user.email)


# ---------------------------------------------------------------------------
# PersonUpdateView
# ---------------------------------------------------------------------------


class PersonUpdateViewTests(PlanningTestCase):
    def setUp(self):
        self.pm = PMUserFactory()
        self.dev = DeveloperProfileFactory()
        self.url = reverse("planning:person_edit", args=[self.dev.user.pk])

    def test_pm_can_update_effort(self):
        self.client.force_login(self.pm)
        response = self.client.post(self.url, {"base_effort_weeks": "18"})
        self.assertEqual(response.status_code, 302)
        self.dev.refresh_from_db()
        self.assertEqual(float(self.dev.base_effort_weeks), 18.0)

    def test_pm_can_update_tags(self):
        tag = TagFactory()
        self.client.force_login(self.pm)
        self.client.post(self.url, {"base_effort_weeks": "20", "tags": [tag.name]})
        self.assertIn(tag, self.dev.tags.all())

    def test_developer_denied(self):
        self.client.force_login(DeveloperProfileFactory().user)
        response = self.client.post(self.url, {"base_effort_weeks": "10"})
        self.assertEqual(response.status_code, 403)

    def test_observer_denied(self):
        obs = UserProjectAccessFactory()
        self.client.force_login(obs.user)
        response = self.client.post(self.url, {"base_effort_weeks": "10"})
        self.assertEqual(response.status_code, 403)

    def test_redirects_to_people(self):
        self.client.force_login(self.pm)
        response = self.client.post(self.url, {"base_effort_weeks": "20"})
        self.assertRedirects(
            response,
            reverse("planning:people"),
            fetch_redirect_response=False,
        )


# ---------------------------------------------------------------------------
# ObserversView — semester filtering
# ---------------------------------------------------------------------------


class ObserversViewSemesterFilterTests(PlanningTestCase):
    def test_shows_users_with_access_records(self):
        SemesterFactory(year=2026, semester_type=SemesterType.A)
        obs_a = UserProjectAccessFactory()
        obs_b = UserProjectAccessFactory()
        self.client.force_login(PMUserFactory())
        response = self.client.get(reverse("planning:observers"))
        pks = [o.pk for o in response.context["observers"]]
        self.assertIn(obs_a.pk, pks)
        self.assertIn(obs_b.pk, pks)

    def test_uses_selected_semester_to_filter_out_developers(self):
        sem_current = SemesterFactory(year=2026, semester_type=SemesterType.A)
        obs_current = UserProjectAccessFactory()
        make_semester_developer(semester=sem_current)
        self.client.force_login(PMUserFactory())
        session = self.client.session
        session["selected_semester"] = "2026A"
        session.save()
        response = self.client.get(reverse("planning:observers"))
        pks = [o.pk for o in response.context["observers"]]
        self.assertIn(obs_current.pk, pks)

    def test_context_contains_selected_semester(self):
        sem = SemesterFactory(year=2026, semester_type=SemesterType.A)
        self.client.force_login(PMUserFactory())
        session = self.client.session
        session["selected_semester"] = "2026A"
        session.save()
        response = self.client.get(reverse("planning:observers"))
        self.assertEqual(response.context["semester"], sem)

    def test_developers_with_access_records_are_not_listed_as_observers(self):
        sem = SemesterFactory(year=2026, semester_type=SemesterType.A)
        dev = make_semester_developer(semester=sem)
        access = UserProjectAccessFactory(user=dev.user)
        self.client.force_login(PMUserFactory())
        session = self.client.session
        session["selected_semester"] = "2026A"
        session.save()

        response = self.client.get(reverse("planning:observers"))
        pks = [o.pk for o in response.context["observers"]]
        self.assertNotIn(access.pk, pks)


# ---------------------------------------------------------------------------
# Bug-fix regression tests
# ---------------------------------------------------------------------------


class ObserverCreateNoDanglingRecordTests(PlanningTestCase):
    """When adding observer access fails because the user is a developer,
    no dangling UserProjectAccess row should be created."""

    def test_no_dangling_record_when_user_is_developer(self):
        pm = PMUserFactory()
        # Create a user who already has developer capacity in the current semester
        dev = make_semester_developer()
        url = reverse("planning:observer_add")
        before = UserProjectAccess.objects.count()
        self.client.force_login(pm)
        self.client.post(url, {"user": dev.user.pk})
        self.assertEqual(
            UserProjectAccess.objects.count(),
            before,
            "A dangling UserProjectAccess row was created for an existing developer",
        )


class PersonUpdateNoSpuriousObserverTests(PlanningTestCase):
    """Editing a developer's profile must not create a spurious UserProjectAccess."""

    def test_no_spurious_observer_created_for_developer(self):
        pm = PMUserFactory()
        dev = make_semester_developer()
        url = reverse("planning:person_edit", args=[dev.user.pk])
        before = UserProjectAccess.objects.count()
        self.client.force_login(pm)
        self.client.post(url, {"base_effort_weeks": "20"})
        self.assertEqual(
            UserProjectAccess.objects.count(),
            before,
            "A spurious UserProjectAccess row was created when editing a developer's profile",
        )

    def test_developer_restrictions_can_be_saved_from_people_edit(self):
        pm = PMUserFactory()
        dev = make_semester_developer()
        project = ProjectFactory()
        url = reverse("planning:person_edit", args=[dev.user.pk])

        self.client.force_login(pm)
        response = self.client.post(
            url,
            {
                "base_effort_weeks": "20",
                "project_access": [project.pk],
            },
        )
        self.assertEqual(response.status_code, 302)

        access = UserProjectAccess.objects.get(user=dev.user)
        self.assertIn(project, access.project_access.all())

    def test_non_numeric_effort_leaves_base_effort_unchanged(self):
        pm = PMUserFactory()
        dev = DeveloperProfileFactory()
        url = reverse("planning:person_edit", args=[dev.user.pk])
        original_effort = float(dev.base_effort_weeks)
        self.client.force_login(pm)
        response = self.client.post(url, {"base_effort_weeks": "not-a-number"})
        self.assertEqual(response.status_code, 302)
        dev.refresh_from_db()
        self.assertEqual(float(dev.base_effort_weeks), original_effort)


class PhaseEditInputValidationTests(PhaseViewTestCase):
    """Bad input to PhaseEditView redirects and leaves the phase unchanged."""

    def _phase_state(self):
        self.phase.refresh_from_db()
        return {
            "developer_id": self.phase.developer_id,
            "project_id": self.phase.project_id,
            "start_date": self.phase.start_date,
            "end_date": self.phase.end_date,
            "effort_multiplier": self.phase.effort_multiplier,
            "lane_id": self.phase.lane_id,
        }

    def test_invalid_date_keeps_existing_phase(self):
        self.client.force_login(self.pm)
        url = reverse("planning:phase_edit", args=[self.phase.pk])
        before = self._phase_state()
        response = self.client.post(
            url,
            {
                "developer": self.dev.pk,
                "project": self.project.pk,
                "start_date": "not-a-date",
                "end_date": "2026-02-09",
                "effort_multiplier": "1.0",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._phase_state(), before)

    def test_invalid_effort_multiplier_keeps_existing_phase(self):
        self.client.force_login(self.pm)
        url = reverse("planning:phase_edit", args=[self.phase.pk])
        before = self._phase_state()
        response = self.client.post(
            url,
            {
                "developer": self.dev.pk,
                "project": self.project.pk,
                "start_date": "2026-01-12",
                "end_date": "2026-02-09",
                "effort_multiplier": "not-a-float",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._phase_state(), before)

    def test_invalid_developer_id_keeps_existing_phase(self):
        self.client.force_login(self.pm)
        url = reverse("planning:phase_edit", args=[self.phase.pk])
        before = self._phase_state()
        response = self.client.post(
            url,
            {
                "developer": "not-an-int",
                "project": self.project.pk,
                "start_date": "2026-01-12",
                "end_date": "2026-02-09",
                "effort_multiplier": "1.0",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._phase_state(), before)

    def test_end_before_start_keeps_existing_phase(self):
        self.client.force_login(self.pm)
        url = reverse("planning:phase_edit", args=[self.phase.pk])
        before = self._phase_state()
        response = self.client.post(
            url,
            {
                "developer": self.dev.pk,
                "project": self.project.pk,
                "start_date": "2026-02-09",
                "end_date": "2026-01-12",
                "effort_multiplier": "1.0",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._phase_state(), before)


class LeaveUpdateEndBeforeStartTests(PlanningTestCase):
    """end_date before start_date must return 400, not silently save bad data."""

    def test_end_before_start_returns_400(self):
        dev = make_semester_developer()
        leave = LeaveFactory(
            developer=dev,
            start_date=datetime.date(2026, 3, 2),
            end_date=datetime.date(2026, 3, 6),
        )
        url = reverse("planning:leave_update", args=[leave.pk])
        self.client.force_login(PMUserFactory())
        response = self.client.post(
            url,
            {
                "start_date": "2026-03-10",
                "end_date": "2026-03-05",
            },
        )
        self.assertEqual(response.status_code, 400)
        leave.refresh_from_db()
        # Original dates must be unchanged
        self.assertEqual(leave.start_date, datetime.date(2026, 3, 2))
        self.assertEqual(leave.end_date, datetime.date(2026, 3, 6))
