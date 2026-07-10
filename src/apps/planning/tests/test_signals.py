"""Tests for the registration auto-link + pre-registration access transfer."""

from django.test import TestCase

from apps.planning.models import DeveloperProfile
from apps.planning.models import UserProjectAccess
from apps.planning.tests.factories import ProjectFactory
from apps.planning.tests.factories import SemesterFactory
from apps.planning.tests.factories import UserFactory
from apps.planning.views._mixins import _visible_project_ids_for_user


class PreRegistrationTransferTests(TestCase):
    def test_profile_linked_and_access_transferred_on_registration(self):
        semester = SemesterFactory()
        project = ProjectFactory(semester=semester)
        profile = DeveloperProfile.objects.create(name="Prof X", email="prof@x.org")
        access = UserProjectAccess.objects.create(developer_profile=profile)
        access.project_access.add(project)

        # Registering a user with the matching email fires the post_save signal.
        user = UserFactory(email="prof@x.org")

        profile.refresh_from_db()
        access.refresh_from_db()
        self.assertEqual(profile.user, user)
        self.assertEqual(access.user, user)
        self.assertIsNone(access.developer_profile)
        self.assertEqual(
            UserProjectAccess.objects.filter(user=user).count(),
            1,
        )
        # The inherited policy restricts the now-registered user to that project.
        self.assertEqual(
            _visible_project_ids_for_user(user, semester),
            {project.pk},
        )

    def test_case_insensitive_email_match(self):
        profile = DeveloperProfile.objects.create(name="Prof Y", email="prof@Y.org")
        access = UserProjectAccess.objects.create(developer_profile=profile)

        user = UserFactory(email="PROF@y.org")

        access.refresh_from_db()
        self.assertEqual(access.user, user)
        self.assertIsNone(access.developer_profile)

    def test_no_access_row_when_none_pre_provisioned(self):
        DeveloperProfile.objects.create(name="Prof Z", email="prof@z.org")
        user = UserFactory(email="prof@z.org")
        # Linking still happens, but no access policy is fabricated.
        self.assertFalse(UserProjectAccess.objects.filter(user=user).exists())
