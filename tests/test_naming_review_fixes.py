from openpyxl import load_workbook
import pytest

from services.excel_export import export_excel
from services.models import Batch, Identity, Product
from services.naming import format_identity_name, manual_identity, standardize_identity


@pytest.mark.parametrize("name", [
    "PORTA L.D RENAULT DUSTER 14-20",
    "PORTA D.E VW GOL 12-20",
    "MAÇANETA INTERNA T.E TOYOTA ETIOS 13-21",
    "TAMPA TRASEIRA VW GOL 14-20",
    "PORTA T.D VERACRUZ 07-12",
])
def test_legacy_name_keeps_all_attributes_after_standardizing_and_exporting(tmp_path, name):
    identity = Identity(name=name, confidence=0.9, oem="REF-123", evidence=["Inscrição legível"])
    for _ in range(3):
        assert standardize_identity(identity) == name
        assert format_identity_name(identity) == name
    assert identity.confidence == 0.9 and identity.oem == "REF-123"
    assert identity.evidence == ["Inscrição legível"]
    batch = Batch(folder=tmp_path, excel_layout="company",
        products=[Product(id="1", sku="024", folder=tmp_path, identity=identity)])
    sheet = load_workbook(export_excel(batch)).active
    assert sheet["A2"].value == "024 - " + name


@pytest.mark.parametrize("name,kind,expected", [
    ("Sensor ABS", "SENSOR", "SENSOR ABS"),
    ("Sensor rotação", "SENSOR", "SENSOR ROTACAO"),
    ("Retrovisor elétrico esquerdo", "RETROVISOR", "RETROVISOR ELETRICO L.E"),
    ("Carcaça do alternador", "ALTERNADOR", "CARCACA DO ALTERNADOR"),
    ("Kit de embreagem", "EMBREAGEM", "KIT EMBREAGEM"),
])
def test_catalog_does_not_erase_subcomponent_or_functional_qualifiers(name, kind, expected):
    identity = Identity(name=name, part_type=kind)
    assert standardize_identity(identity) == expected
    assert standardize_identity(identity) == expected


def test_years_inside_old_model_field_are_retained_before_cleanup():
    identity = Identity(name="Porta", part_type="PORTA", vehicle_brand="Renault",
        vehicle_model="Duster 2014-2020", side="direito")
    assert standardize_identity(identity) == "PORTA L.D RENAULT DUSTER 14-20"
    assert identity.years == "14-20" and identity.vehicle_model == "DUSTER"


def test_tail_qualifier_is_preserved_after_years():
    identity = Identity(name="PORTA L.D VW GOL 12-20 C/DETALHE")
    expected = "PORTA C/DETALHE L.D VW GOL 12-20"
    assert standardize_identity(identity) == expected
    assert standardize_identity(identity) == expected


@pytest.mark.parametrize("raw,expected", [
    ("LUZ TETO CORTESIA CENTRAL HYUNDAI VERA CRUZ 07-12", "LUZ TETO CENTRAL HYUNDAI VERA CRUZ 07-12"),
    ("PORTA SUPERIOR L.D VW GOL 12-20", "PORTA SUPERIOR L.D VW GOL 12-20"),
    ("PARACHOQUE DIANT./TRAS. VW GOL 12-20", "PARACHOQUE DIANT./TRAS. VW GOL 12-20"),
])
def test_position_is_not_duplicated_on_repeated_normalization(raw, expected):
    identity = Identity(name=raw)
    for _ in range(4):
        assert standardize_identity(identity) == expected
        assert format_identity_name(identity) == expected


@pytest.mark.parametrize("name", ["PEÇA NÃO IDENTIFICADA", "não identificado", ""])
def test_unknown_names_keep_the_canonical_sentinel_used_by_search_guards(name):
    identity = manual_identity(name)
    assert identity.name == "Peça não identificada"
    assert standardize_identity(identity) == identity.name
