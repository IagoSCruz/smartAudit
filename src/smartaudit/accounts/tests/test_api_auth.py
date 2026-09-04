import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from smartaudit.accounts.services import get_active_user_from_token


class APIAuthenticationTests(TestCase):
    def setUp(self):
        self.password = "strong-test-password"
        self.user = get_user_model().objects.create_user(
            "member@example.com",
            self.password,
        )

    def _post(self, path, payload):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_api_shell_is_available(self):
        response = self.client.get("/api/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["name"], "SmartAudit API")

    def test_login_and_refresh_issue_usable_access_tokens(self):
        login = self._post(
            "/api/auth/login",
            {"email": "MEMBER@example.com", "password": self.password},
        )

        self.assertEqual(login.status_code, 200)
        token_pair = login.json()
        self.assertEqual(token_pair["token_type"], "Bearer")
        self.assertTrue(token_pair["access"])
        self.assertTrue(token_pair["refresh"])

        refreshed = self._post(
            "/api/auth/refresh",
            {"refresh": token_pair["refresh"]},
        )
        self.assertEqual(refreshed.status_code, 200)
        refreshed_user = get_active_user_from_token(
            refreshed.json()["access"],
            "access",
        )
        self.assertEqual(refreshed_user, self.user)

    def test_login_does_not_reveal_whether_email_exists(self):
        wrong_password = self._post(
            "/api/auth/login",
            {"email": self.user.email, "password": "wrong-password"},
        )
        unknown_email = self._post(
            "/api/auth/login",
            {"email": "unknown@example.com", "password": "wrong-password"},
        )

        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown_email.status_code, 401)
        self.assertEqual(wrong_password.json(), unknown_email.json())

    def test_access_token_cannot_be_used_as_refresh_token(self):
        login = self._post(
            "/api/auth/login",
            {"email": self.user.email, "password": self.password},
        )

        response = self._post(
            "/api/auth/refresh",
            {"refresh": login.json()["access"]},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["detail"],
            "Tipo de token inválido para esta operação.",
        )

    def test_inactive_user_cannot_login_or_refresh(self):
        login = self._post(
            "/api/auth/login",
            {"email": self.user.email, "password": self.password},
        )
        self.user.is_active = False
        self.user.save(update_fields=("is_active",))

        second_login = self._post(
            "/api/auth/login",
            {"email": self.user.email, "password": self.password},
        )
        refresh = self._post(
            "/api/auth/refresh",
            {"refresh": login.json()["refresh"]},
        )

        self.assertEqual(second_login.status_code, 401)
        self.assertEqual(refresh.status_code, 401)
