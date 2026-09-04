"""Tenant-scoped records produced by fiscal XML ingestion."""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

from smartaudit.core.models import TenantScopedModel

ACCESS_KEY_PATTERN = r"^\d{44}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"
CNPJ_PATTERN = r"^\d{14}$"
ZIP_PATTERN = r"^\d{8}$"


def document_upload_path(instance, _filename: str) -> str:
    digest = instance.content_sha256
    return f"documents/{instance.tenant_id}/{digest[:2]}/{digest}.xml"


class DocumentUpload(TenantScopedModel):
    class DocumentType(models.TextChoices):
        UNKNOWN = "unknown", "Não identificado"
        CTE = "cte", "CT-e"
        NFE = "nfe", "NF-e"

    class Status(models.TextChoices):
        PENDING = "pending", "Pendente"
        PROCESSING = "processing", "Processando"
        PROCESSED = "processed", "Processado"
        FAILED = "failed", "Falhou"

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="document_uploads",
    )
    original_filename = models.CharField("nome original", max_length=255)
    document_type = models.CharField(
        "tipo",
        max_length=16,
        choices=DocumentType.choices,
        default=DocumentType.UNKNOWN,
        db_index=True,
    )
    status = models.CharField(
        "status",
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    content_sha256 = models.CharField(
        "SHA-256",
        max_length=64,
        validators=[RegexValidator(SHA256_PATTERN)],
    )
    access_key = models.CharField(
        "chave de acesso",
        max_length=44,
        blank=True,
        validators=[RegexValidator(ACCESS_KEY_PATTERN)],
    )
    source_file = models.FileField(
        "XML original",
        upload_to=document_upload_path,
        max_length=500,
        blank=True,
    )
    error_code = models.CharField("código do erro", max_length=64, blank=True)
    error_message = models.TextField("mensagem de erro", blank=True)
    processed_at = models.DateTimeField("processado em", null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        verbose_name = "upload de documento"
        verbose_name_plural = "uploads de documentos"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "content_sha256"),
                name="documents_upload_tenant_hash_unique",
            ),
            models.UniqueConstraint(
                fields=("tenant", "document_type", "access_key"),
                condition=~Q(access_key=""),
                name="documents_upload_tenant_type_key_unique",
            ),
            models.CheckConstraint(
                condition=Q(content_sha256__regex=SHA256_PATTERN),
                name="documents_upload_sha256_valid",
            ),
            models.CheckConstraint(
                condition=Q(access_key="") | Q(access_key__regex=ACCESS_KEY_PATTERN),
                name="documents_upload_access_key_valid",
            ),
            models.CheckConstraint(
                condition=Q(document_type__in=("unknown", "cte", "nfe")),
                name="documents_upload_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("pending", "processing", "processed", "failed")),
                name="documents_upload_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.get_status_display()})"


class CTe(TenantScopedModel):
    class Status(models.TextChoices):
        NORMAL = "normal", "Normal"
        COMPLEMENTARY = "complementary", "Complementar"
        ANNULMENT = "annulment", "Anulação"
        SUBSTITUTE = "substitute", "Substituição"

    upload = models.OneToOneField(
        DocumentUpload,
        on_delete=models.PROTECT,
        related_name="cte",
    )
    access_key = models.CharField(
        "chave de acesso",
        max_length=44,
        validators=[RegexValidator(ACCESS_KEY_PATTERN)],
    )
    number = models.CharField("número", max_length=20)
    series = models.CharField("série", max_length=10)
    issue_at = models.DateTimeField("emitido em")
    status = models.CharField(
        "status",
        max_length=20,
        choices=Status.choices,
        default=Status.NORMAL,
    )
    sender_cnpj = models.CharField(
        "CNPJ do remetente",
        max_length=14,
        blank=True,
        validators=[RegexValidator(CNPJ_PATTERN)],
    )
    sender_name = models.CharField("remetente", max_length=255, blank=True)
    sender_state = models.CharField("UF do remetente", max_length=2, blank=True)
    sender_zip = models.CharField(
        "CEP do remetente",
        max_length=8,
        blank=True,
        validators=[RegexValidator(ZIP_PATTERN)],
    )
    recipient_cnpj = models.CharField(
        "CNPJ do destinatário",
        max_length=14,
        blank=True,
        validators=[RegexValidator(CNPJ_PATTERN)],
    )
    recipient_name = models.CharField("destinatário", max_length=255, blank=True)
    recipient_state = models.CharField(
        "UF do destinatário",
        max_length=2,
        blank=True,
    )
    recipient_zip = models.CharField(
        "CEP do destinatário",
        max_length=8,
        blank=True,
        validators=[RegexValidator(ZIP_PATTERN)],
    )
    carrier_cnpj = models.CharField(
        "CNPJ da transportadora",
        max_length=14,
        validators=[RegexValidator(CNPJ_PATTERN)],
    )
    carrier_name = models.CharField("transportadora", max_length=255)
    total_freight = models.DecimalField(
        "frete total",
        max_digits=15,
        decimal_places=2,
    )
    cargo_value = models.DecimalField(
        "valor da carga",
        max_digits=15,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    freight_weight = models.DecimalField(
        "peso da carga",
        max_digits=15,
        decimal_places=3,
        default=Decimal("0.000"),
    )
    referenced_nfe_keys = models.JSONField(
        "chaves de NF-e referenciadas",
        default=list,
    )

    class Meta(TenantScopedModel.Meta):
        verbose_name = "CT-e"
        verbose_name_plural = "CT-es"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "access_key"),
                name="documents_cte_tenant_key_unique",
            ),
            models.CheckConstraint(
                condition=Q(access_key__regex=ACCESS_KEY_PATTERN),
                name="documents_cte_access_key_valid",
            ),
            models.CheckConstraint(
                condition=Q(total_freight__gte=0),
                name="documents_cte_total_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(cargo_value__gte=0),
                name="documents_cte_cargo_value_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(freight_weight__gte=0),
                name="documents_cte_weight_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(status__in=("normal", "complementary", "annulment", "substitute")),
                name="documents_cte_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(sender_cnpj="") | Q(sender_cnpj__regex=CNPJ_PATTERN))
                    & (Q(recipient_cnpj="") | Q(recipient_cnpj__regex=CNPJ_PATTERN))
                    & Q(carrier_cnpj__regex=CNPJ_PATTERN)
                ),
                name="documents_cte_cnpj_normalized",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(sender_zip="") | Q(sender_zip__regex=ZIP_PATTERN))
                    & (Q(recipient_zip="") | Q(recipient_zip__regex=ZIP_PATTERN))
                ),
                name="documents_cte_zip_normalized",
            ),
        ]

    def clean(self):
        super().clean()
        if self.upload_id and self.tenant_id != self.upload.tenant_id:
            raise ValidationError("O upload e o CT-e precisam pertencer ao mesmo tenant.")

    def __str__(self) -> str:
        return f"CT-e {self.number} — {self.access_key}"


class NFe(TenantScopedModel):
    upload = models.OneToOneField(
        DocumentUpload,
        on_delete=models.PROTECT,
        related_name="nfe",
    )
    access_key = models.CharField(
        "chave de acesso",
        max_length=44,
        validators=[RegexValidator(ACCESS_KEY_PATTERN)],
    )
    number = models.CharField("número", max_length=20)
    series = models.CharField("série", max_length=10)
    issue_at = models.DateTimeField("emitida em")
    issuer_cnpj = models.CharField(
        "CNPJ do emitente",
        max_length=14,
        validators=[RegexValidator(CNPJ_PATTERN)],
    )
    issuer_name = models.CharField("emitente", max_length=255)
    recipient_cnpj = models.CharField(
        "CNPJ do destinatário",
        max_length=14,
        blank=True,
        validators=[RegexValidator(CNPJ_PATTERN)],
    )
    recipient_name = models.CharField("destinatário", max_length=255, blank=True)
    recipient_zip = models.CharField(
        "CEP do destinatário",
        max_length=8,
        blank=True,
        validators=[RegexValidator(ZIP_PATTERN)],
    )
    total_value = models.DecimalField(
        "valor total",
        max_digits=15,
        decimal_places=2,
    )
    gross_weight = models.DecimalField(
        "peso bruto",
        max_digits=15,
        decimal_places=3,
        default=Decimal("0.000"),
    )
    net_weight = models.DecimalField(
        "peso líquido",
        max_digits=15,
        decimal_places=3,
        default=Decimal("0.000"),
    )
    total_volume = models.PositiveIntegerField("volumes", default=0)

    class Meta(TenantScopedModel.Meta):
        verbose_name = "NF-e"
        verbose_name_plural = "NF-es"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "access_key"),
                name="documents_nfe_tenant_key_unique",
            ),
            models.CheckConstraint(
                condition=Q(access_key__regex=ACCESS_KEY_PATTERN),
                name="documents_nfe_access_key_valid",
            ),
            models.CheckConstraint(
                condition=Q(total_value__gte=0),
                name="documents_nfe_total_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(gross_weight__gte=0) & Q(net_weight__gte=0),
                name="documents_nfe_weights_non_negative",
            ),
            models.CheckConstraint(
                condition=(
                    Q(issuer_cnpj__regex=CNPJ_PATTERN)
                    & (Q(recipient_cnpj="") | Q(recipient_cnpj__regex=CNPJ_PATTERN))
                ),
                name="documents_nfe_cnpj_normalized",
            ),
            models.CheckConstraint(
                condition=Q(recipient_zip="") | Q(recipient_zip__regex=ZIP_PATTERN),
                name="documents_nfe_zip_normalized",
            ),
        ]

    def clean(self):
        super().clean()
        if self.upload_id and self.tenant_id != self.upload.tenant_id:
            raise ValidationError("O upload e a NF-e precisam pertencer ao mesmo tenant.")

    def __str__(self) -> str:
        return f"NF-e {self.number} — {self.access_key}"


class CTeNFeLink(TenantScopedModel):
    cte = models.ForeignKey(CTe, on_delete=models.PROTECT, related_name="nfe_links")
    nfe = models.ForeignKey(NFe, on_delete=models.PROTECT, related_name="cte_links")

    class Meta(TenantScopedModel.Meta):
        verbose_name = "vínculo CT-e/NF-e"
        verbose_name_plural = "vínculos CT-e/NF-e"
        constraints = [
            models.UniqueConstraint(
                fields=("tenant", "cte", "nfe"),
                name="documents_cte_nfe_link_unique",
            )
        ]

    def clean(self):
        super().clean()
        if not self.tenant_id or not self.cte_id or not self.nfe_id:
            return
        if self.cte.tenant_id != self.tenant_id or self.nfe.tenant_id != self.tenant_id:
            raise ValidationError(
                "O vínculo, o CT-e e a NF-e precisam pertencer ao mesmo tenant."
            )

    def __str__(self) -> str:
        return f"{self.cte} ↔ {self.nfe}"
