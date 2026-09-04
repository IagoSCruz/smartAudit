from decimal import Decimal
from pathlib import Path

from django.test import SimpleTestCase

from smartaudit.documents.parsers import (
    DocumentParseError,
    ParsedCTe,
    ParsedNFe,
    parse_fiscal_xml,
)

FIXTURES = Path(__file__).parent / "fixtures"


class FiscalXMLParserTests(SimpleTestCase):
    def test_parses_anonymized_cte_without_float_values(self):
        parsed = parse_fiscal_xml((FIXTURES / "cte.xml").read_bytes())

        self.assertIsInstance(parsed, ParsedCTe)
        self.assertEqual(parsed.access_key, "1" * 44)
        self.assertEqual(parsed.total_freight, Decimal("125.50"))
        self.assertEqual(parsed.cargo_value, Decimal("2500.00"))
        self.assertEqual(parsed.freight_weight, Decimal("18.750"))
        self.assertEqual(parsed.carrier_cnpj, "12345678000199")
        self.assertEqual(parsed.sender_zip, "01001000")
        self.assertEqual(parsed.referenced_nfe_keys, ("2" * 44,))
        self.assertIsNotNone(parsed.issue_at.utcoffset())

    def test_parses_anonymized_nfe_without_float_values(self):
        parsed = parse_fiscal_xml((FIXTURES / "nfe.xml").read_bytes())

        self.assertIsInstance(parsed, ParsedNFe)
        self.assertEqual(parsed.access_key, "2" * 44)
        self.assertEqual(parsed.total_value, Decimal("2500.00"))
        self.assertEqual(parsed.gross_weight, Decimal("18.750"))
        self.assertEqual(parsed.net_weight, Decimal("17.500"))
        self.assertEqual(parsed.total_volume, 2)
        self.assertEqual(parsed.recipient_zip, "20040020")
        self.assertIsNotNone(parsed.issue_at.utcoffset())

    def test_rejects_dtd_and_external_entity_fixture(self):
        with self.assertRaises(DocumentParseError) as caught:
            parse_fiscal_xml((FIXTURES / "xxe.xml").read_bytes())

        self.assertEqual(caught.exception.code, "UNSAFE_XML")
        self.assertIn("referência externa", str(caught.exception))

    def test_rejects_malformed_or_unsupported_xml(self):
        with self.assertRaises(DocumentParseError) as malformed:
            parse_fiscal_xml(b"<NFe>")
        with self.assertRaises(DocumentParseError) as unsupported:
            parse_fiscal_xml(b"<root />")

        self.assertEqual(malformed.exception.code, "INVALID_XML")
        self.assertEqual(unsupported.exception.code, "UNSUPPORTED_DOCUMENT")

    def test_rejects_lookalike_document_outside_official_namespace(self):
        lookalike = b"""
            <NFe><infNFe Id="NFe11111111111111111111111111111111111111111111" /></NFe>
        """

        with self.assertRaises(DocumentParseError) as caught:
            parse_fiscal_xml(lookalike)

        self.assertEqual(caught.exception.code, "UNSUPPORTED_DOCUMENT")
