"""Transactional, idempotent workflows for fiscal document ingestion."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone

from smartaudit.documents.models import CTe, CTeNFeLink, DocumentUpload, NFe
from smartaudit.documents.parsers import (
    DocumentParseError,
    ParsedCTe,
    ParsedDocument,
    parse_fiscal_xml,
)


class DocumentIngestionError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        upload: DocumentUpload | None = None,
    ):
        self.code = code
        self.status_code = status_code
        self.upload = upload
        super().__init__(message)


class FiscalDocumentNotFound(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class IngestionResult:
    upload: DocumentUpload
    document: CTe | NFe
    created: bool


def _safe_filename(filename: str) -> str:
    return Path(filename or "document.xml").name[:255]


def _document_for_upload(upload: DocumentUpload) -> CTe | NFe | None:
    if upload.document_type == DocumentUpload.DocumentType.CTE:
        return CTe.objects.filter(upload=upload).first()
    if upload.document_type == DocumentUpload.DocumentType.NFE:
        return NFe.objects.filter(upload=upload).first()
    return None


def _existing_result(tenant, parsed: ParsedDocument) -> IngestionResult | None:
    model = CTe if isinstance(parsed, ParsedCTe) else NFe
    document = (
        model.objects.select_related("upload")
        .filter(tenant=tenant, access_key=parsed.access_key)
        .first()
    )
    if document is None:
        return None
    return IngestionResult(upload=document.upload, document=document, created=False)


def _record_parse_failure(
    *,
    tenant,
    user,
    filename: str,
    digest: str,
    error: DocumentParseError,
) -> DocumentUpload:
    with transaction.atomic():
        upload, _ = DocumentUpload.objects.get_or_create(
            tenant=tenant,
            content_sha256=digest,
            defaults={
                "uploaded_by": user,
                "original_filename": filename,
            },
        )
        upload.document_type = DocumentUpload.DocumentType.UNKNOWN
        upload.status = DocumentUpload.Status.FAILED
        upload.error_code = error.code
        upload.error_message = str(error)
        upload.processed_at = timezone.now()
        upload.save(
            update_fields=(
                "document_type",
                "status",
                "error_code",
                "error_message",
                "processed_at",
                "updated_at",
            )
        )
        return upload


def _sync_cte_links(cte: CTe) -> None:
    matching_nfes = NFe.objects.filter(
        tenant=cte.tenant,
        access_key__in=cte.referenced_nfe_keys,
    )
    for nfe in matching_nfes:
        CTeNFeLink.objects.get_or_create(
            tenant=cte.tenant,
            cte=cte,
            nfe=nfe,
        )


def _sync_nfe_links(nfe: NFe) -> None:
    candidate_ctes = CTe.objects.filter(tenant=nfe.tenant).only(
        "id",
        "tenant_id",
        "referenced_nfe_keys",
    )
    for cte in candidate_ctes:
        if nfe.access_key in cte.referenced_nfe_keys:
            CTeNFeLink.objects.get_or_create(
                tenant=nfe.tenant,
                cte=cte,
                nfe=nfe,
            )


def _create_domain_document(
    tenant,
    upload: DocumentUpload,
    parsed: ParsedDocument,
) -> CTe | NFe:
    values = asdict(parsed)
    values.pop("document_type")
    if isinstance(parsed, ParsedCTe):
        values["referenced_nfe_keys"] = list(parsed.referenced_nfe_keys)
        document = CTe.objects.create(tenant=tenant, upload=upload, **values)
        _sync_cte_links(document)
        return document

    document = NFe.objects.create(tenant=tenant, upload=upload, **values)
    _sync_nfe_links(document)
    return document


def _persist_document(
    *,
    tenant,
    user,
    filename: str,
    xml_content: bytes,
    digest: str,
    parsed: ParsedDocument,
) -> IngestionResult:
    stored_name = ""
    try:
        with transaction.atomic():
            upload, created = DocumentUpload.objects.get_or_create(
                tenant=tenant,
                content_sha256=digest,
                defaults={
                    "uploaded_by": user,
                    "original_filename": filename,
                },
            )
            if not created:
                existing_document = _document_for_upload(upload)
                if existing_document is not None:
                    return IngestionResult(
                        upload=upload,
                        document=existing_document,
                        created=False,
                    )

            upload.uploaded_by = user
            upload.original_filename = filename
            upload.document_type = parsed.document_type
            upload.access_key = parsed.access_key
            upload.status = DocumentUpload.Status.PROCESSING
            upload.error_code = ""
            upload.error_message = ""
            if not upload.source_file:
                upload.source_file.save(
                    f"{digest}.xml",
                    ContentFile(xml_content),
                    save=False,
                )
                stored_name = upload.source_file.name
            upload.save()

            document = _create_domain_document(tenant, upload, parsed)
            upload.status = DocumentUpload.Status.PROCESSED
            upload.processed_at = timezone.now()
            upload.save(
                update_fields=("status", "processed_at", "updated_at")
            )
            return IngestionResult(upload=upload, document=document, created=True)
    except Exception:
        if stored_name:
            upload.source_file.storage.delete(stored_name)
        raise


def ingest_fiscal_xml(
    *,
    tenant,
    user,
    filename: str,
    xml_content: bytes,
) -> IngestionResult:
    """Validate, parse and persist once for each tenant/type/access key."""
    safe_filename = _safe_filename(filename)
    if not safe_filename.casefold().endswith(".xml"):
        raise DocumentIngestionError(
            "INVALID_FILE_TYPE",
            "Envie um arquivo com extensão .xml.",
        )
    if len(xml_content) > settings.DOCUMENT_UPLOAD_MAX_BYTES:
        raise DocumentIngestionError(
            "FILE_TOO_LARGE",
            "O arquivo excede o tamanho máximo permitido.",
            status_code=413,
        )

    digest = sha256(xml_content).hexdigest()
    try:
        parsed = parse_fiscal_xml(xml_content)
    except DocumentParseError as exc:
        upload = _record_parse_failure(
            tenant=tenant,
            user=user,
            filename=safe_filename,
            digest=digest,
            error=exc,
        )
        raise DocumentIngestionError(
            exc.code,
            str(exc),
            upload=upload,
        ) from exc

    existing = _existing_result(tenant, parsed)
    if existing is not None:
        return existing

    try:
        return _persist_document(
            tenant=tenant,
            user=user,
            filename=safe_filename,
            xml_content=xml_content,
            digest=digest,
            parsed=parsed,
        )
    except IntegrityError:
        existing = _existing_result(tenant, parsed)
        if existing is not None:
            return existing
        raise


def list_fiscal_documents(tenant, document_type: str | None = None) -> list[CTe | NFe]:
    if document_type not in {None, "cte", "nfe"}:
        raise DocumentIngestionError(
            "INVALID_DOCUMENT_TYPE",
            "O tipo deve ser cte ou nfe.",
        )

    documents: list[CTe | NFe] = []
    if document_type in {None, "cte"}:
        documents.extend(CTe.objects.for_tenant(tenant).select_related("upload"))
    if document_type in {None, "nfe"}:
        documents.extend(NFe.objects.for_tenant(tenant).select_related("upload"))
    return sorted(documents, key=lambda document: document.issue_at, reverse=True)


def get_fiscal_document(tenant, document_type: str, access_key: str) -> CTe | NFe:
    model = {"cte": CTe, "nfe": NFe}.get(document_type)
    if model is None:
        raise FiscalDocumentNotFound
    document = model.objects.for_tenant(tenant).filter(access_key=access_key).first()
    if document is None:
        raise FiscalDocumentNotFound
    return document
