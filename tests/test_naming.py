import pytest

from services.models import Identity
from services.naming import format_identity_name, manual_identity, standardize_identity


@pytest.mark.parametrize("raw,expected", [
    ("porta direita Renault Duster 2014 a 2020", "PORTA L.D RENAULT DUSTER 14-20"),
    ("porta esquerda Renault Sandero 2012-2022", "PORTA L.E RENAULT SANDERO 12-22"),
    ("maçaneta interna traseira esquerda Toyota Etios 2013-2021", "MAÇANETA INTERNA T.E TOYOTA ETIOS 13-21"),
    ("porta dianteira direita Volkswagen Passat B6 2006-2011", "PORTA D.D VW PASSAT B6 06-11"),
    ("PORTA T.D VW GOL 12-20", "PORTA T.D VW GOL 12-20"),
    ("PORTA T.D VERACRUZ07-12", "PORTA T.D VERACRUZ 07-12"),
    ("espelho retrovisor externo esquerdo Chevrolet Cobalt 2012-2020", "RETROVISOR L.E GM COBALT 12-20"),
    ("motor de arranque", "MOTOR DE PARTIDA"),
    ("MOTOR DE PARTIDA", "MOTOR DE PARTIDA"),
    ("para-lama", "PARALAMA"),
    ("carcaça do alternador", "CARCACA DO ALTERNADOR"),
    ("kit de embreagem", "KIT EMBREAGEM"),
    ("roda e pneu", "RODA COM PNEU"),
])
def test_company_names_are_stable(raw, expected):
    identity = manual_identity(raw)
    assert identity.name == expected
    assert manual_identity(expected).name == expected
    assert standardize_identity(identity) == expected
    assert format_identity_name(Identity(name=raw)) == expected


def test_structured_attributes_and_unknown_application():
    identity = Identity(name="Porta do carro direita", part_type="PORTA", vehicle_brand="Renault",
        vehicle_model="Duster", years="2014-2020", side="direito")
    assert standardize_identity(identity) == "PORTA L.D RENAULT DUSTER 14-20"
    assert manual_identity("alternador").vehicle_brand is None
    assert manual_identity("alternador").years is None
    assert format_identity_name(Identity()) == "Peça não identificada"
    assert format_identity_name(Identity(name="kit embreagem", part_type="EMBREAGEM")) == "KIT EMBREAGEM"


def test_different_position_and_assembly_remain_distinct():
    assert manual_identity("PORTA D.D VW GOL 12-20").name != manual_identity("PORTA T.D VW GOL 12-20").name
    assert manual_identity("KIT EMBREAGEM").name != manual_identity("EMBREAGEM").name
