"""Tests for planning management commands."""
from django.core.management import call_command
from django.test import TestCase

from apps.planning.models import DeveloperProfile
from apps.planning.models import Phase
from apps.planning.models import Project


class TestSeedCommand(TestCase):
    """Smoke tests for the seed_test_data management command."""

    def test_seed_creates_developers(self):
        call_command("seed_test_data", verbosity=0)
        self.assertTrue(DeveloperProfile.objects.exists())

    def test_seed_creates_projects(self):
        call_command("seed_test_data", verbosity=0)
        self.assertTrue(Project.objects.exists())

    def test_seed_creates_phases(self):
        call_command("seed_test_data", verbosity=0)
        self.assertTrue(Phase.objects.exists())

    def test_seed_is_idempotent(self):
        call_command("seed_test_data", verbosity=0)
        dev_count = DeveloperProfile.objects.count()
        proj_count = Project.objects.count()
        call_command("seed_test_data", verbosity=0)
        self.assertEqual(DeveloperProfile.objects.count(), dev_count)
        self.assertEqual(Project.objects.count(), proj_count)
