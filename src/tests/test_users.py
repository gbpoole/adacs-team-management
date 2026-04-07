"""Tests for the custom User model manager."""
from django.contrib.auth import get_user_model
from django.test import TestCase


class TestUserManager(TestCase):
    def test_create_user_basic(self):
        User = get_user_model()
        user = User.objects.create_user(email="dev@example.com", password="testpass")
        self.assertEqual(user.email, "dev@example.com")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password("testpass"))

    def test_create_user_empty_email_raises(self):
        User = get_user_model()
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="testpass")

    def test_create_user_normalises_email(self):
        User = get_user_model()
        user = User.objects.create_user(email="Dev@EXAMPLE.COM", password="pass")
        self.assertEqual(user.email, "Dev@example.com")

    def test_create_superuser_sets_flags(self):
        User = get_user_model()
        user = User.objects.create_superuser(email="admin@example.com", password="adminpass")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertEqual(user.role, "admin")

    def test_create_superuser_is_staff_false_raises(self):
        User = get_user_model()
        with self.assertRaises(ValueError):
            User.objects.create_superuser(email="a@b.com", password="p", is_staff=False)

    def test_create_superuser_is_superuser_false_raises(self):
        User = get_user_model()
        with self.assertRaises(ValueError):
            User.objects.create_superuser(email="a@b.com", password="p", is_superuser=False)
