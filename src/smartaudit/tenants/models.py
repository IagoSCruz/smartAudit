from decimal import Decimal

from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from smartaudit.core.models import BaseModel


class Tenant(BaseModel):
    """Company whose freight data is isolated from every other customer."""

    name = models.CharField("nome", max_length=160)
    cnpj = models.CharField(
        "CNPJ",
        max_length=14,
        unique=True,
        validators=[
            RegexValidator(
                regex=r"^\d{14}$",
                message="Informe o CNPJ com exatamente 14 dígitos.",
            )
        ],
        help_text="Somente os 14 dígitos.",
    )
    divergence_tolerance_amount = models.DecimalField(
        "tolerância de divergência em reais",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    divergence_tolerance_percentage = models.DecimalField(
        "tolerância percentual",
        max_digits=7,
        decimal_places=4,
        default=Decimal("0.0000"),
        help_text="Fração decimal entre 0 e 1; por exemplo, 0,02 representa 2%.",
    )
    duplicate_window_days = models.PositiveSmallIntegerField(
        "janela de duplicidade em dias",
        default=30,
    )
    is_active = models.BooleanField("ativo", default=True, db_index=True)

    class Meta(BaseModel.Meta):
        verbose_name = "tenant"
        verbose_name_plural = "tenants"
        constraints = [
            models.CheckConstraint(
                condition=Q(cnpj__regex=r"^\d{14}$"),
                name="tenants_cnpj_has_14_digits",
            ),
            models.CheckConstraint(
                condition=Q(divergence_tolerance_amount__gte=0),
                name="tenants_tolerance_amount_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(divergence_tolerance_percentage__gte=0)
                    & Q(divergence_tolerance_percentage__lte=1)
                ),
                name="tenants_tolerance_percentage_between_0_and_1",
            ),
            models.CheckConstraint(
                condition=Q(duplicate_window_days__gte=1),
                name="tenants_duplicate_window_days_positive",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Membership(BaseModel):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrador"
        OPERATOR = "operator", "Operador"
        VIEWER = "viewer", "Visualizador"

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    role = models.CharField(
        "papel",
        max_length=16,
        choices=Role.choices,
        default=Role.VIEWER,
        db_index=True,
    )
    is_active = models.BooleanField("ativo", default=True, db_index=True)

    class Meta(BaseModel.Meta):
        verbose_name = "vínculo"
        verbose_name_plural = "vínculos"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "user"),
                name="tenants_membership_tenant_user_unique",
            ),
            models.CheckConstraint(
                condition=Q(role__in=("admin", "operator", "viewer")),
                name="tenants_membership_role_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=("tenant", "role", "is_active"),
                name="tenants_membership_scope_idx",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user} — {self.tenant} ({self.get_role_display()})"
