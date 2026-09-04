"""Abstract models shared across bounded contexts."""

from django.db import models


class BaseModel(models.Model):
    """Provide immutable creation time and last-update auditing."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("-created_at",)


class TenantQuerySet(models.QuerySet):
    def for_tenant(self, tenant):
        return self.filter(tenant=tenant)


class TenantScopedModel(BaseModel):
    """Base for every domain record owned by a tenant."""

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
    )

    objects = TenantQuerySet.as_manager()

    class Meta(BaseModel.Meta):
        abstract = True
