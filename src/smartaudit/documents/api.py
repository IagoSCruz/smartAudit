"""Tenant-scoped API operations for fiscal documents."""

from datetime import datetime
from decimal import Decimal

from django.conf import settings
from ninja import File, Router, Schema, Status
from ninja.files import UploadedFile

from smartaudit.documents.models import CTe
from smartaudit.documents.services import (
    DocumentIngestionError,
    FiscalDocumentNotFound,
    get_fiscal_document,
    ingest_fiscal_xml,
    list_fiscal_documents,
)
from smartaudit.tenants.models import Membership
from smartaudit.tenants.permissions import require_roles

router = Router(tags=["Documentos fiscais"])


class DocumentErrorOutput(Schema):
    code: str
    detail: str
    upload_id: int | None = None


class UploadOutput(Schema):
    upload_id: int
    document_type: str
    access_key: str
    status: str
    created: bool


class DocumentSummaryOutput(Schema):
    document_type: str
    access_key: str
    number: str
    series: str
    issue_at: datetime
    total_value: Decimal
    status: str


class DocumentDetailOutput(DocumentSummaryOutput):
    issuer_cnpj: str
    issuer_name: str
    recipient_cnpj: str
    recipient_name: str
    recipient_zip: str
    referenced_nfe_keys: list[str]


def _summary(document):
    is_cte = isinstance(document, CTe)
    return {
        "document_type": "cte" if is_cte else "nfe",
        "access_key": document.access_key,
        "number": document.number,
        "series": document.series,
        "issue_at": document.issue_at,
        "total_value": document.total_freight if is_cte else document.total_value,
        "status": document.status if is_cte else "normal",
    }


def _detail(document):
    data = _summary(document)
    if isinstance(document, CTe):
        data.update(
            issuer_cnpj=document.carrier_cnpj,
            issuer_name=document.carrier_name,
            recipient_cnpj=document.recipient_cnpj,
            recipient_name=document.recipient_name,
            recipient_zip=document.recipient_zip,
            referenced_nfe_keys=document.referenced_nfe_keys,
        )
    else:
        data.update(
            issuer_cnpj=document.issuer_cnpj,
            issuer_name=document.issuer_name,
            recipient_cnpj=document.recipient_cnpj,
            recipient_name=document.recipient_name,
            recipient_zip=document.recipient_zip,
            referenced_nfe_keys=[],
        )
    return data


@router.post(
    "/upload",
    response={
        200: UploadOutput,
        201: UploadOutput,
        400: DocumentErrorOutput,
        413: DocumentErrorOutput,
    },
)
@require_roles(Membership.Role.ADMIN, Membership.Role.OPERATOR)
def upload_document(request, uploaded_file: File[UploadedFile]):
    content = uploaded_file.read(settings.DOCUMENT_UPLOAD_MAX_BYTES + 1)
    try:
        result = ingest_fiscal_xml(
            tenant=request.tenant,
            user=request.user,
            filename=uploaded_file.name,
            xml_content=content,
        )
    except DocumentIngestionError as exc:
        return Status(
            exc.status_code,
            {
                "code": exc.code,
                "detail": str(exc),
                "upload_id": exc.upload.pk if exc.upload else None,
            },
        )
    status_code = 201 if result.created else 200
    return Status(
        status_code,
        {
            "upload_id": result.upload.pk,
            "document_type": result.upload.document_type,
            "access_key": result.upload.access_key,
            "status": result.upload.status,
            "created": result.created,
        },
    )


@router.get(
    "/",
    response={200: list[DocumentSummaryOutput], 400: DocumentErrorOutput},
)
def list_documents(request, document_type: str | None = None):
    try:
        documents = list_fiscal_documents(request.tenant, document_type)
    except DocumentIngestionError as exc:
        return Status(400, {"code": exc.code, "detail": str(exc)})
    return [_summary(document) for document in documents]


@router.get(
    "/{document_type}/{access_key}",
    response={200: DocumentDetailOutput, 404: DocumentErrorOutput},
)
def document_detail(request, document_type: str, access_key: str):
    try:
        document = get_fiscal_document(
            request.tenant,
            document_type.casefold(),
            access_key,
        )
    except FiscalDocumentNotFound:
        return Status(
            404,
            {
                "code": "DOCUMENT_NOT_FOUND",
                "detail": "Documento fiscal não encontrado.",
            },
        )
    return _detail(document)
