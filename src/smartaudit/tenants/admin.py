from django.contrib import admin

from smartaudit.tenants.models import Membership, Tenant


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "cnpj", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "cnpj")
    inlines = (MembershipInline,)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "tenant", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "tenant__name", "tenant__cnpj")
    autocomplete_fields = ("user", "tenant")
