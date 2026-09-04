from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from smartaudit.tenants.models import Membership, Tenant


class TenantTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Loja Exemplo",
            cnpj="12345678000199",
            divergence_tolerance_amount=Decimal("5.00"),
            divergence_tolerance_percentage=Decimal("0.0200"),
        )
        self.user = get_user_model().objects.create_user(
            "operator@example.com",
            "a-secure-password",
        )

    def test_membership_links_global_user_to_tenant_with_role(self):
        membership = Membership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=Membership.Role.OPERATOR,
        )

        self.assertEqual(membership.tenant, self.tenant)
        self.assertEqual(membership.role, Membership.Role.OPERATOR)
        self.assertIsNotNone(membership.created_at)
        self.assertIsNotNone(membership.updated_at)

    def test_user_cannot_have_duplicate_membership_in_same_tenant(self):
        Membership.objects.create(tenant=self.tenant, user=self.user)

        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(tenant=self.tenant, user=self.user)

    def test_database_rejects_unknown_membership_role(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(
                tenant=self.tenant,
                user=self.user,
                role="owner",
            )

    def test_database_rejects_malformed_cnpj(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Tenant.objects.create(name="Tenant inválido", cnpj="123")
