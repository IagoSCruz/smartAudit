import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from smartaudit.documents.models import CTe, DocumentUpload
from smartaudit.tenants.models import Membership, Tenant

FIXTURES = Path(__file__).parent / "fixtures"


class DocumentAPITests(TestCase):
    def setUp(self):
        self.media_directory = TemporaryDirectory()
        self.addCleanup(self.media_directory.cleanup)
        media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        media_override.enable()
        self.addCleanup(media_override.disable)

        self.password = "strong-test-password"
        self.user = get_user_model().objects.create_user(
            "operator-documents@example.com",
            self.password,
        )
        self.tenant = Tenant.objects.create(name="Loja A", cnpj="11111111000191")
        self.other_tenant = Tenant.objects.create(
            name="Loja B",
            cnpj="22222222000191",
        )
        self.membership = Membership.objects.create(
            tenant=self.tenant,
            user=self.user,
            role=Membership.Role.OPERATOR,
        )
        Membership.objects.create(
            tenant=self.other_tenant,
            user=self.user,
            role=Membership.Role.OPERATOR,
        )
        login = self.client.post(
            "/api/auth/login",
            data=json.dumps({"email": self.user.email, "password": self.password}),
            content_type="application/json",
        )
        self.token = login.json()["access"]

    def _headers(self, tenant):
        return {
            "HTTP_AUTHORIZATION": f"Bearer {self.token}",
            "HTTP_X_TENANT_ID": str(tenant.pk),
        }

    def _xml_file(self, fixture_name: str):
        return SimpleUploadedFile(
            fixture_name,
            (FIXTURES / fixture_name).read_bytes(),
            content_type="application/xml",
        )

    def test_upload_list_and_detail_are_isolated_by_header_tenant(self):
        upload = self.client.post(
            "/api/documents/upload",
            {
                "uploaded_file": self._xml_file("cte.xml"),
                "tenant_id": self.other_tenant.pk,
            },
            **self._headers(self.tenant),
        )

        self.assertEqual(upload.status_code, 201)
        self.assertTrue(upload.json()["created"])
        stored_upload = DocumentUpload.objects.get(pk=upload.json()["upload_id"])
        self.assertEqual(stored_upload.tenant, self.tenant)

        own_list = self.client.get(
            "/api/documents/",
            **self._headers(self.tenant),
        )
        other_list = self.client.get(
            "/api/documents/",
            **self._headers(self.other_tenant),
        )
        self.assertEqual(own_list.status_code, 200)
        self.assertEqual(len(own_list.json()), 1)
        self.assertEqual(other_list.status_code, 200)
        self.assertEqual(other_list.json(), [])

        access_key = upload.json()["access_key"]
        own_detail = self.client.get(
            f"/api/documents/cte/{access_key}",
            **self._headers(self.tenant),
        )
        other_detail = self.client.get(
            f"/api/documents/cte/{access_key}",
            **self._headers(self.other_tenant),
        )
        self.assertEqual(own_detail.status_code, 200)
        self.assertEqual(own_detail.json()["total_value"], "125.50")
        self.assertEqual(other_detail.status_code, 404)

    def test_duplicate_upload_returns_existing_resource(self):
        first = self.client.post(
            "/api/documents/upload",
            {"uploaded_file": self._xml_file("nfe.xml")},
            **self._headers(self.tenant),
        )
        second = self.client.post(
            "/api/documents/upload",
            {"uploaded_file": self._xml_file("nfe.xml")},
            **self._headers(self.tenant),
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.json()["created"])
        self.assertEqual(first.json()["upload_id"], second.json()["upload_id"])
        self.assertEqual(DocumentUpload.objects.count(), 1)

    def test_viewer_cannot_upload_but_can_list(self):
        self.membership.role = Membership.Role.VIEWER
        self.membership.save(update_fields=("role", "updated_at"))

        upload = self.client.post(
            "/api/documents/upload",
            {"uploaded_file": self._xml_file("cte.xml")},
            **self._headers(self.tenant),
        )
        listing = self.client.get(
            "/api/documents/",
            **self._headers(self.tenant),
        )

        self.assertEqual(upload.status_code, 403)
        self.assertEqual(
            upload.json()["detail"],
            "Seu papel não permite executar esta ação.",
        )
        self.assertEqual(listing.status_code, 200)
        self.assertFalse(CTe.objects.exists())

    def test_unsafe_xml_returns_stable_error_schema(self):
        response = self.client.post(
            "/api/documents/upload",
            {"uploaded_file": self._xml_file("xxe.xml")},
            **self._headers(self.tenant),
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "UNSAFE_XML")
        self.assertIsNotNone(response.json()["upload_id"])
        self.assertEqual(
            DocumentUpload.objects.get().status,
            DocumentUpload.Status.FAILED,
        )

    @override_settings(DOCUMENT_UPLOAD_MAX_BYTES=10)
    def test_oversized_xml_is_rejected_before_parsing(self):
        response = self.client.post(
            "/api/documents/upload",
            {"uploaded_file": self._xml_file("cte.xml")},
            **self._headers(self.tenant),
        )

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["code"], "FILE_TOO_LARGE")
        self.assertFalse(DocumentUpload.objects.exists())
