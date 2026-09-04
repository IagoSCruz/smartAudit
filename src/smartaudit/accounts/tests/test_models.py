from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase


class UserTests(TestCase):
    def test_manager_canonicalizes_email(self):
        user = get_user_model().objects.create_user(
            "  OWNER@Example.COM ",
            "a-secure-password",
        )

        self.assertEqual(user.email, "owner@example.com")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_authentication_is_case_insensitive(self):
        get_user_model().objects.create_user(
            "owner@example.com",
            "a-secure-password",
        )

        user = authenticate(
            username="OWNER@EXAMPLE.COM",
            password="a-secure-password",
        )

        self.assertIsNotNone(user)

    def test_direct_save_also_canonicalizes_email(self):
        user = get_user_model()(email="  DIRECT@Example.COM ")
        user.set_password("a-secure-password")
        user.save()

        self.assertEqual(user.email, "direct@example.com")

    def test_superuser_has_required_flags(self):
        user = get_user_model().objects.create_superuser(
            "admin@example.com",
            "a-secure-password",
        )

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
