from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from smartaudit.documents.models import CTe, CTeNFeLink, DocumentUpload, NFe
from smartaudit.documents.services import DocumentIngestionError, ingest_fiscal_xml
from smartaudit.tenants.models import Tenant

FIXTURES = Path(__file__).parent / "fixtures"


class DocumentIngestionTests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        media_override.enable()
        self.addCleanup(media_override.disable)
        self.tenant = Tenant.objects.create(name="Loja A", cnpj="11111111000191")
        self.other_tenant = Tenant.objects.create(
            name="Loja B",
            cnpj="22222222000191",
        )
        self.user = get_user_model().objects.create_user(
            "documents@example.com",
            "strong-test-password",
        )
        self.cte_xml = (FIXTURES / "cte.xml").read_bytes()
        self.nfe_xml = (FIXTURES / "nfe.xml").read_bytes()

    def _ingest(self, tenant, filename, content):
        return ingest_fiscal_xml(
            tenant=tenant,
            user=self.user,
            filename=filename,
            xml_content=content,
        )

    def test_ingestion_is_idempotent_by_tenant_type_and_access_key(self):
        first = self._ingest(self.tenant, "cte.xml", self.cte_xml)
        second = self._ingest(
            self.tenant,
            "same-key-different-bytes.xml",
            self.cte_xml + b"\n",
        )

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.document, second.document)
        self.assertEqual(DocumentUpload.objects.count(), 1)
        self.assertEqual(CTe.objects.count(), 1)
        self.assertEqual(first.upload.status, DocumentUpload.Status.PROCESSED)
        self.assertTrue(first.upload.source_file.name.endswith(".xml"))

    def test_same_access_key_is_allowed_in_different_tenants(self):
        first = self._ingest(self.tenant, "cte.xml", self.cte_xml)
        second = self._ingest(self.other_tenant, "cte.xml", self.cte_xml)

        self.assertNotEqual(first.document.pk, second.document.pk)
        self.assertEqual(CTe.objects.count(), 2)

    def test_links_cte_and_nfe_regardless_of_ingestion_order(self):
        cte_result = self._ingest(self.tenant, "cte.xml", self.cte_xml)
        nfe_result = self._ingest(self.tenant, "nfe.xml", self.nfe_xml)

        link = CTeNFeLink.objects.get()
        self.assertEqual(link.tenant, self.tenant)
        self.assertEqual(link.cte, cte_result.document)
        self.assertEqual(link.nfe, nfe_result.document)

    def test_invalid_xml_persists_only_safe_failure_metadata(self):
        with self.assertRaises(DocumentIngestionError) as caught:
            self._ingest(self.tenant, "attack.xml", (FIXTURES / "xxe.xml").read_bytes())

        upload = DocumentUpload.objects.get()
        self.assertEqual(caught.exception.code, "UNSAFE_XML")
        self.assertEqual(upload.status, DocumentUpload.Status.FAILED)
        self.assertEqual(upload.document_type, DocumentUpload.DocumentType.UNKNOWN)
        self.assertFalse(upload.source_file)
        self.assertNotIn("/etc/passwd", upload.error_message)

    def test_database_and_file_are_cleaned_when_domain_persistence_fails(self):
        with patch(
            "smartaudit.documents.services._create_domain_document",
            side_effect=RuntimeError("simulated persistence failure"),
        ):
            with self.assertRaises(RuntimeError):
                self._ingest(self.tenant, "cte.xml", self.cte_xml)

        self.assertFalse(DocumentUpload.objects.exists())
        self.assertFalse(CTe.objects.exists())
        self.assertFalse(any(Path(self.media_directory.name).rglob("*.xml")))

    def test_nfe_fields_are_persisted_as_decimals(self):
        result = self._ingest(self.tenant, "nfe.xml", self.nfe_xml)

        nfe = NFe.objects.get(pk=result.document.pk)
        self.assertEqual(str(nfe.total_value), "2500.00")
        self.assertEqual(str(nfe.gross_weight), "18.750")

    def test_database_rejects_non_normalized_fiscal_identifiers(self):
        result = self._ingest(self.tenant, "cte.xml", self.cte_xml)

        with self.assertRaises(IntegrityError), transaction.atomic():
            CTe.objects.filter(pk=result.document.pk).update(
                carrier_cnpj="ABCDEFGHIJKLMN"
            )
