"""Pure, side-effect-free parsers for supported Brazilian fiscal XMLs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from xml.etree.ElementTree import Element

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

ACCESS_KEY_RE = re.compile(r"^\d{44}$")
CTE_NAMESPACE = "http://www.portalfiscal.inf.br/cte"
NFE_NAMESPACE = "http://www.portalfiscal.inf.br/nfe"


class DocumentParseError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ParsedCTe:
    document_type: str
    access_key: str
    number: str
    series: str
    issue_at: datetime
    status: str
    sender_cnpj: str
    sender_name: str
    sender_state: str
    sender_zip: str
    recipient_cnpj: str
    recipient_name: str
    recipient_state: str
    recipient_zip: str
    carrier_cnpj: str
    carrier_name: str
    total_freight: Decimal
    cargo_value: Decimal
    freight_weight: Decimal
    referenced_nfe_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ParsedNFe:
    document_type: str
    access_key: str
    number: str
    series: str
    issue_at: datetime
    issuer_cnpj: str
    issuer_name: str
    recipient_cnpj: str
    recipient_name: str
    recipient_zip: str
    total_value: Decimal
    gross_weight: Decimal
    net_weight: Decimal
    total_volume: int


ParsedDocument = ParsedCTe | ParsedNFe


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _namespace(tag: str) -> str:
    if tag.startswith("{"):
        return tag[1:].partition("}")[0]
    return ""


def _first_descendant(
    element: Element,
    name: str,
    namespace: str,
) -> Element | None:
    return next(
        (
            node
            for node in element.iter()
            if _local_name(node.tag) == name and _namespace(node.tag) == namespace
        ),
        None,
    )


def _child(element: Element | None, name: str) -> Element | None:
    if element is None:
        return None
    return next((node for node in element if _local_name(node.tag) == name), None)


def _text(element: Element | None, name: str, default: str = "") -> str:
    node = _child(element, name)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def _digits(value: str) -> str:
    return "".join(character for character in value if character.isdigit())


def _normalized_digits(
    value: str,
    *,
    length: int,
    field_name: str,
    required: bool = False,
) -> str:
    normalized = _digits(value)
    if not normalized and not required:
        return ""
    if len(normalized) != length:
        raise DocumentParseError(
            "INVALID_IDENTIFIER",
            f"O campo {field_name} precisa conter {length} dígitos.",
        )
    return normalized


def _decimal(value: str, field_name: str, default: str = "0") -> Decimal:
    try:
        result = Decimal(value or default)
    except InvalidOperation as exc:
        raise DocumentParseError(
            "INVALID_DECIMAL",
            f"O campo {field_name} possui valor decimal inválido.",
        ) from exc
    if not result.is_finite() or result < 0:
        raise DocumentParseError(
            "INVALID_DECIMAL",
            f"O campo {field_name} precisa ser um decimal não negativo.",
        )
    return result


def _datetime(value: str) -> datetime:
    if not value:
        raise DocumentParseError("MISSING_FIELD", "A data de emissão não foi informada.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DocumentParseError(
            "INVALID_DATETIME",
            "A data de emissão do documento é inválida.",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _integer(value: str, field_name: str) -> int:
    decimal_value = _decimal(value, field_name)
    if decimal_value != decimal_value.to_integral_value():
        raise DocumentParseError(
            "INVALID_INTEGER",
            f"O campo {field_name} precisa ser um número inteiro.",
        )
    return int(decimal_value)


def _access_key(info: Element, prefix: str) -> str:
    identifier = info.attrib.get("Id", "")
    key = identifier.removeprefix(prefix)
    if not ACCESS_KEY_RE.fullmatch(key):
        raise DocumentParseError(
            "INVALID_ACCESS_KEY",
            "A chave de acesso deve conter exatamente 44 dígitos.",
        )
    return key


def _required_text(element: Element | None, name: str, label: str) -> str:
    value = _text(element, name)
    if not value:
        raise DocumentParseError("MISSING_FIELD", f"O campo {label} é obrigatório.")
    return value


def _referenced_nfe_keys(document_info: Element | None) -> tuple[str, ...]:
    keys: list[str] = []
    for nfe_info in document_info if document_info is not None else ():
        if _local_name(nfe_info.tag) != "infNFe":
            continue
        key = _digits(_text(nfe_info, "chave"))
        if not ACCESS_KEY_RE.fullmatch(key):
            raise DocumentParseError(
                "INVALID_REFERENCED_ACCESS_KEY",
                "Uma chave de NF-e referenciada não possui 44 dígitos.",
            )
        keys.append(key)
    return tuple(dict.fromkeys(keys))


def _parse_cte(info: Element) -> ParsedCTe:
    ide = _child(info, "ide")
    issuer = _child(info, "emit")
    sender = _child(info, "rem")
    recipient = _child(info, "dest")
    sender_address = _child(sender, "enderReme")
    recipient_address = _child(recipient, "enderDest")
    values = _child(info, "vPrest")
    normal = _child(info, "infCTeNorm")
    cargo = _child(normal, "infCarga")
    document_info = _child(normal, "infDoc")

    type_map = {
        "0": "normal",
        "1": "complementary",
        "2": "annulment",
        "3": "substitute",
    }
    referenced_keys = _referenced_nfe_keys(document_info)
    weight = Decimal("0")
    for quantity in cargo if cargo is not None else ():
        if _local_name(quantity.tag) != "infQ":
            continue
        measure = _text(quantity, "tpMed").casefold()
        if "peso" in measure:
            weight = max(weight, _decimal(_text(quantity, "qCarga"), "qCarga"))

    return ParsedCTe(
        document_type="cte",
        access_key=_access_key(info, "CTe"),
        number=_required_text(ide, "nCT", "nCT"),
        series=_required_text(ide, "serie", "serie"),
        issue_at=_datetime(_required_text(ide, "dhEmi", "dhEmi")),
        status=type_map.get(_text(ide, "tpCTe"), "normal"),
        sender_cnpj=_normalized_digits(
            _text(sender, "CNPJ"),
            length=14,
            field_name="rem/CNPJ",
        ),
        sender_name=_text(sender, "xNome"),
        sender_state=_text(sender_address, "UF"),
        sender_zip=_normalized_digits(
            _text(sender_address, "CEP"),
            length=8,
            field_name="enderReme/CEP",
        ),
        recipient_cnpj=_normalized_digits(
            _text(recipient, "CNPJ"),
            length=14,
            field_name="dest/CNPJ",
        ),
        recipient_name=_text(recipient, "xNome"),
        recipient_state=_text(recipient_address, "UF"),
        recipient_zip=_normalized_digits(
            _text(recipient_address, "CEP"),
            length=8,
            field_name="enderDest/CEP",
        ),
        carrier_cnpj=_normalized_digits(
            _required_text(issuer, "CNPJ", "emit/CNPJ"),
            length=14,
            field_name="emit/CNPJ",
            required=True,
        ),
        carrier_name=_required_text(issuer, "xNome", "emit/xNome"),
        total_freight=_decimal(
            _required_text(values, "vTPrest", "vPrest/vTPrest"),
            "vTPrest",
        ),
        cargo_value=_decimal(_text(cargo, "vCarga"), "vCarga"),
        freight_weight=weight,
        referenced_nfe_keys=referenced_keys,
    )


def _parse_nfe(info: Element) -> ParsedNFe:
    ide = _child(info, "ide")
    issuer = _child(info, "emit")
    recipient = _child(info, "dest")
    recipient_address = _child(recipient, "enderDest")
    total = _child(_child(info, "total"), "ICMSTot")
    transport = _child(info, "transp")
    volumes = [
        node
        for node in (transport if transport is not None else ())
        if _local_name(node.tag) == "vol"
    ]
    gross_weight = sum(
        (_decimal(_text(volume, "pesoB"), "pesoB") for volume in volumes),
        start=Decimal("0"),
    )
    net_weight = sum(
        (_decimal(_text(volume, "pesoL"), "pesoL") for volume in volumes),
        start=Decimal("0"),
    )
    total_volume = sum(_integer(_text(volume, "qVol"), "qVol") for volume in volumes)

    issue_value = _text(ide, "dhEmi") or _text(ide, "dEmi")
    return ParsedNFe(
        document_type="nfe",
        access_key=_access_key(info, "NFe"),
        number=_required_text(ide, "nNF", "nNF"),
        series=_required_text(ide, "serie", "serie"),
        issue_at=_datetime(issue_value),
        issuer_cnpj=_normalized_digits(
            _required_text(issuer, "CNPJ", "emit/CNPJ"),
            length=14,
            field_name="emit/CNPJ",
            required=True,
        ),
        issuer_name=_required_text(issuer, "xNome", "emit/xNome"),
        recipient_cnpj=_normalized_digits(
            _text(recipient, "CNPJ"),
            length=14,
            field_name="dest/CNPJ",
        ),
        recipient_name=_text(recipient, "xNome"),
        recipient_zip=_normalized_digits(
            _text(recipient_address, "CEP"),
            length=8,
            field_name="enderDest/CEP",
        ),
        total_value=_decimal(
            _required_text(total, "vNF", "total/ICMSTot/vNF"),
            "vNF",
        ),
        gross_weight=gross_weight,
        net_weight=net_weight,
        total_volume=total_volume,
    )


def parse_fiscal_xml(xml_content: bytes) -> ParsedDocument:
    if not xml_content.strip():
        raise DocumentParseError("EMPTY_FILE", "O arquivo XML está vazio.")
    try:
        root = ElementTree.fromstring(
            xml_content,
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
    except DefusedXmlException as exc:
        raise DocumentParseError(
            "UNSAFE_XML",
            "O XML contém DTD, entidade ou referência externa não permitida.",
        ) from exc
    except ElementTree.ParseError as exc:
        raise DocumentParseError("INVALID_XML", "O arquivo XML é inválido.") from exc

    cte_info = _first_descendant(root, "infCte", CTE_NAMESPACE)
    if cte_info is not None:
        return _parse_cte(cte_info)

    nfe_info = _first_descendant(root, "infNFe", NFE_NAMESPACE)
    if nfe_info is not None:
        return _parse_nfe(nfe_info)

    raise DocumentParseError(
        "UNSUPPORTED_DOCUMENT",
        "O XML informado não é um CT-e ou uma NF-e suportada.",
    )
