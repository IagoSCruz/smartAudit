import json

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from smartaudit.tenants.middleware import TenantContextMiddleware
from smartaudit.tenants.models import Membership, Tenant
from smartaudit.tenants.permissions import require_roles
from smartaudit.tenants.services import ACTIVE_TENANT_SESSION_KEY


class TenantAuthorizationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            "operator@example.com",
            "strong-test-password",
        )
        self.tenant = Tenant.objects.create(
            name="Loja A",
            cnpj="11111111000191",
        )
        self.other_tenant = Tenant.objects.create(
            name="Loja B",
            cnpj="22222222000191",
        )
        self.membership = Membership.objects.create(
            user=self.user,
            tenant=self.tenant,
            role=Membership.Role.OPERATOR,
        )

    def _access_token(self):
        response = self.client.post(
            "/api/auth/login",
            data=json.dumps(
                {
                    "email": self.user.email,
                    "password": "strong-test-password",
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["access"]

    def test_api_resolves_active_membership_from_header(self):
        response = self.client.get(
            "/api/tenant",
            HTTP_AUTHORIZATION=f"Bearer {self._access_token()}",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tenant_id"], self.tenant.pk)
        self.assertEqual(response.json()["role"], Membership.Role.OPERATOR)

    def test_api_rejects_cross_tenant_access(self):
        response = self.client.get(
            "/api/tenant",
            HTTP_AUTHORIZATION=f"Bearer {self._access_token()}",
            HTTP_X_TENANT_ID=str(self.other_tenant.pk),
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "Você não possui acesso ativo a este tenant.",
        )

    def test_api_rejects_missing_or_malformed_tenant_header(self):
        token = self._access_token()

        missing = self.client.get(
            "/api/tenant",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        malformed = self.client.get(
            "/api/tenant",
            HTTP_AUTHORIZATION=f"Bearer {token}",
            HTTP_X_TENANT_ID="tenant-a",
        )

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(malformed.status_code, 403)

    def test_api_requires_authentication_in_pt_br(self):
        response = self.client.get(
            "/api/tenant",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Autenticação obrigatória.")

    def test_session_middleware_resolves_authorized_tenant(self):
        request = RequestFactory().get("/")
        request.user = self.user
        request.session = {ACTIVE_TENANT_SESSION_KEY: self.tenant.pk}
        observed = {}

        def endpoint(current_request):
            observed["tenant"] = current_request.tenant
            observed["membership"] = current_request.membership
            return HttpResponse()

        TenantContextMiddleware(endpoint)(request)

        self.assertEqual(observed["tenant"], self.tenant)
        self.assertEqual(observed["membership"], self.membership)

    def test_session_middleware_discards_unauthorized_tenant(self):
        request = RequestFactory().get("/")
        request.user = self.user
        request.session = {ACTIVE_TENANT_SESSION_KEY: self.other_tenant.pk}

        TenantContextMiddleware(lambda _: HttpResponse())(request)

        self.assertIsNone(request.tenant)
        self.assertNotIn(ACTIVE_TENANT_SESSION_KEY, request.session)

    def test_role_guard_rejects_viewer_for_operator_action(self):
        self.membership.role = Membership.Role.VIEWER
        request = RequestFactory().post("/")
        request.membership = self.membership

        @require_roles(Membership.Role.ADMIN, Membership.Role.OPERATOR)
        def operator_action(_request):
            return HttpResponse()

        with self.assertRaisesMessage(
            PermissionDenied,
            "Seu papel não permite executar esta ação.",
        ):
            operator_action(request)

    def test_inactive_membership_is_rejected_by_api(self):
        self.membership.is_active = False
        self.membership.save(update_fields=("is_active", "updated_at"))

        response = self.client.get(
            "/api/tenant",
            HTTP_AUTHORIZATION=f"Bearer {self._access_token()}",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )

        self.assertEqual(response.status_code, 403)
