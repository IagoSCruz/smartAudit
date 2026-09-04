from django.contrib import admin

from smartaudit.documents.models import CTe, CTeNFeLink, DocumentUpload, NFe


@admin.register(DocumentUpload)
class DocumentUploadAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename",
        "tenant",
        "document_type",
        "status",
        "uploaded_by",
        "created_at",
    )
    list_filter = ("document_type", "status")
    search_fields = ("original_filename", "access_key", "content_sha256")
    autocomplete_fields = ("tenant", "uploaded_by")
    readonly_fields = ("content_sha256", "processed_at", "created_at", "updated_at")


@admin.register(CTe)
class CTeAdmin(admin.ModelAdmin):
    list_display = ("number", "series", "tenant", "carrier_name", "issue_at")
    search_fields = ("access_key", "number", "carrier_cnpj", "carrier_name")
    autocomplete_fields = ("tenant", "upload")


@admin.register(NFe)
class NFeAdmin(admin.ModelAdmin):
    list_display = ("number", "series", "tenant", "issuer_name", "issue_at")
    search_fields = ("access_key", "number", "issuer_cnpj", "issuer_name")
    autocomplete_fields = ("tenant", "upload")


@admin.register(CTeNFeLink)
class CTeNFeLinkAdmin(admin.ModelAdmin):
    list_display = ("cte", "nfe", "tenant", "created_at")
    autocomplete_fields = ("tenant", "cte", "nfe")
