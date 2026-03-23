"""Integration tests for planning views."""
from django.test import TestCase
from django.urls import reverse

from apps.planning.tests.factories import AdminUserFactory
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
