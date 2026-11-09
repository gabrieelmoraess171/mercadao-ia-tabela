"""Nomenclatura determinística; a IA identifica atributos e não escolhe o formato."""
import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Identity


PART_ALIASES = {
    "PORTA": ("PORTA DO CARRO", "PORTA DO VEICULO"),
    "CAPO": ("CAPO DO MOTOR", "CAPOT"),
    "TAMPA TRASEIRA": ("TAMPA DO PORTA MALAS", "TAMPA PORTA MALAS", "PORTA MALAS"),
    "PARALAMA": ("PARA LAMA", "PARA LAMAS", "PARALAMAS"),
    "PARACHOQUE": ("PARA CHOQUE", "PARA CHOQUES", "PARACHOQUES"),
    "ALMA PARA CHOQUE": ("ALMA DO PARA CHOQUE",),
    "GRADE": ("GRADE FRONTAL",),
    "FAROL DE NEBLINA": ("FAROL DE MILHA", "FAROL AUXILIAR", "FAROL NEBLINA"),
    "FAROL": ("CONJUNTO OPTICO DIANTEIRO",),
    "LANTERNA": ("SINALEIRA", "CONJUNTO OPTICO TRASEIRO"),
    "RETROVISOR INTERNO": ("ESPELHO RETROVISOR INTERNO",),
    "RETROVISOR": ("ESPELHO RETROVISOR EXTERNO", "ESPELHO RETROVISOR", "RETROVISOR EXTERNO"),
    "VIDRO PORTA": ("VIDRO DA PORTA", "VIDRO LATERAL"),
    "PARABRISA": ("PARA BRISA", "PARA BRISAS"),
    "VIDRO VIGIA": ("VIDRO TRASEIRO", "VIGIA"),
    "MÁQUINA DE VIDRO": ("MAQUINA VIDRO", "ELEVADOR DE VIDRO", "ELEVADOR DO VIDRO", "MECANISMO DE VIDRO"),
    "MOTOR DE VIDRO": ("MOTOR DO VIDRO", "MOTOR VIDRO ELETRICO"),
    "FECHADURA": (), "MAÇANETA INTERNA": (), "MAÇANETA EXTERNA": (), "MAÇANETA": (),
    "DOBRADIÇA": (), "FORRO DE PORTA": ("FORRO PORTA", "PAINEL DA PORTA"),
    "VOLANTE": (), "PAINEL": (), "AIRBAG": ("BOLSA DE AIRBAG",),
    "MÓDULO AIRBAG": ("MODULO DO AIRBAG", "CENTRAL AIRBAG"),
    "CINTO DE SEGURANÇA": ("CINTO SEGURANCA",), "BANCO": (), "CONSOLE": (),
    "BLOCO MOTOR": ("BLOCO DO MOTOR",), "MOTOR": (),
    "CABEÇOTE": ("CABECOTE DO MOTOR",), "CÁRTER": ("CARTER DO MOTOR",),
    "TAMPA VÁLVULAS": ("TAMPA DE VALVULAS",),
    "COLETOR ADMISSÃO": ("COLETOR DE ADMISSAO",),
    "COLETOR ESCAPE": ("COLETOR DE ESCAPE",), "TURBINA": ("TURBOCOMPRESSOR",),
    "CORPO BORBOLETA": ("CORPO DE BORBOLETA", "TBI"),
    "ALTERNADOR": ("GERADOR ALTERNADOR",),
    "MOTOR DE PARTIDA": ("MOTOR DE ARRANQUE", "MOTOR ARRANQUE", "MOTOR PARTIDA", "ARRANQUE"),
    "REFIL BOMBA COMBUSTÍVEL": ("REFIL DA BOMBA DE COMBUSTIVEL",),
    "BOMBA COMBUSTÍVEL": ("BOMBA DE COMBUSTIVEL", "BOMBA DE GASOLINA"),
    "BOMBA DE ÓLEO": ("BOMBA OLEO",), "BOMBA D'ÁGUA": ("BOMBA DE AGUA", "BOMBA DAGUA"),
    "BOMBA DIREÇÃO": ("BOMBA DE DIRECAO",), "BOMBA VÁCUO": ("BOMBA DE VACUO",),
    "COMPRESSOR AR CONDICIONADO": ("COMPRESSOR DO AR CONDICIONADO", "COMPRESSOR DE AR CONDICIONADO"),
    "RADIADOR": (), "CONDENSADOR": (), "ELETROVENTILADOR": ("VENTOINHA",), "INTERCOOLER": (),
    "VÁLVULA TERMOSTÁTICA": (), "BICO INJETOR": ("INJETOR DE COMBUSTIVEL",),
    "BOBINA IGNIÇÃO": ("BOBINA DE IGNICAO",), "CHICOTE": ("CHICOTE ELETRICO",),
    "MÓDULO INJEÇÃO": ("MODULO DE INJECAO", "CENTRAL DE INJECAO", "ECU"),
    "CAIXA FUSÍVEIS": ("CAIXA DE FUSIVEIS",), "SENSOR": (),
    "CÂMBIO AUTOMÁTICO": ("CAIXA DE CAMBIO AUTOMATICA", "TRANSMISSAO AUTOMATICA"),
    "CÂMBIO MANUAL": ("CAIXA DE CAMBIO MANUAL", "TRANSMISSAO MANUAL"),
    "CÂMBIO": ("CAIXA DE CAMBIO",), "DIFERENCIAL": (),
    "CAIXA TRANSFERÊNCIA": ("CAIXA DE TRANSFERENCIA",),
    "SEMI EIXO": ("SEMIEIXO",), "HOMOCINÉTICA": ("JUNTA HOMOCINETICA",),
    "CARDÃ": ("EIXO CARDA",), "EMBREAGEM": (), "PEDAL": (), "PEDALEIRA": (),
    "AGREGADO": ("AGREGADO DE SUSPENSAO",), "BANDEJA": ("BRACO DE SUSPENSAO",),
    "PIVÔ": (), "BIELETA": (), "AMORTECEDOR": (), "MOLA": (),
    "MANGA EIXO": ("MANGA DE EIXO",), "CUBO RODA": ("CUBO DE RODA",), "ROLAMENTO": (),
    "RODA COM PNEU": ("CONJUNTO RODA E PNEU", "RODA E PNEU"), "RODA": (), "PNEU": (),
    "PINÇA FREIO": ("PINCA DE FREIO",), "DISCO FREIO": ("DISCO DE FREIO",),
    "CILINDRO MESTRE": (), "SERVO FREIO": ("SERVOFREIO", "HIDROVACUO"),
    "MÓDULO ABS": ("MODULO DO ABS", "CENTRAL ABS"),
    "CAIXA DIREÇÃO": ("CAIXA DE DIRECAO",), "COLUNA DIREÇÃO": ("COLUNA DE DIRECAO",),
    "TERMINAL DIREÇÃO": ("TERMINAL DE DIRECAO",), "RESERVATÓRIO": (),
    "TANQUE COMBUSTÍVEL": ("TANQUE DE COMBUSTIVEL",), "ESCAPAMENTO": (), "CATALISADOR": (),
    "SOQUETE CIRCUITO LANTERNA": ("SOQUETE CIRCUITO LATERNA", "CIRCUITO DE LANTERNA", "PLACA CIRCUITO LANTERNA"),
    "SOQUETE LANTERNA": ("SOQUETE DA LANTERNA",),
    "MOLDURA RÁDIO": ("MOLDURA PAINEL MULTIMIDIA", "MOLDURA PAINEL CENTRAL RADIO", "MOLDURA DA MULTIMIDIA"),
    "PAINEL COMANDO RÁDIO": ("PAINEL MOLDURA COMANDO RADIO", "COMANDO RADIO"),
    "CENTRAL MULTIMÍDIA": ("CENTRAL MULTIMIDIA", "MULTIMIDIA"),
    "BOTÃO START STOP": ("BOTAO PARTIDA START STOP", "BOTAO DE PARTIDA", "BOTAO START STOP"),
    "BOTÃO AUTO HOLD": ("BOTAO FREIO DE MAO AUTO HOLD",),
    "DIFUSOR DE AR": ("DIFUSOR AR", "SAIDA DE AR"),
    "COMANDO AR CONDICIONADO": ("COMANDO DO AR CONDICIONADO", "COMANDO AR COND"),
    "LUZ TETO": ("LUZ DE TETO", "LUZ TETO CORTESIA"),
    "CINTA AIRBAG": ("CINTA DO AIRBAG", "CLOCK SPRING"),
    "CHAVE DE SETA": ("COMANDO DE SETA",),
    "PORTA LUVAS": ("PORTA LUVAS OBJETOS",),
    "PORTINHOLA TANQUE": ("PORTINHOLA DO TANQUE", "PORTINHLA DO TANQUE"),
    "TAMPÃO BAGAGITO": ("TAMPAO DO PORTA MALAS", "BAGAGITO"),
    "BRAKE LIGHT": ("BREAKLIGHT LUZ DE FREIO", "BRAKE LIGHT LUZ DE FREIO", "TERCEIRA LUZ DE FREIO"),
    "ANTENA TETO": ("ANTENA DE TETO",), "ACABAMENTO": (), "MOLDURA": (), "FRISO": (),
}
PART_TYPES = tuple(PART_ALIASES)
BRAND_ALIASES = {
    "RENAULT": ("RENAULT",), "VW": ("VOLKSWAGEN", "VW"),
    "GM": ("CHEVROLET", "GM", "GENERAL MOTORS"), "FIAT": ("FIAT",),
    "FORD": ("FORD",), "TOYOTA": ("TOYOTA",), "HONDA": ("HONDA",),
    "HYUNDAI": ("HYUNDAI",), "KIA": ("KIA",), "NISSAN": ("NISSAN",),
    "PEUGEOT": ("PEUGEOT",), "CITROEN": ("CITROEN",), "JEEP": ("JEEP",),
    "MITSUBISHI": ("MITSUBISHI",), "MERCEDES-BENZ": ("MERCEDES BENZ", "MERCEDES"),
    "BMW": ("BMW",), "AUDI": ("AUDI",), "SUZUKI": ("SUZUKI",),
    "CHERY": ("CHERY", "CAOA CHERY"), "JAC": ("JAC",), "BYD": ("BYD",),
}
UNKNOWN = {"", "NAO CONFIRMADO", "NAO CONFIRMADA", "DESCONHECIDO", "DESCONHECIDA", "N A", "NONE", "NULL", "NAO IDENTIFICADO", "NAO IDENTIFICADA", "PECA NAO IDENTIFICADA"}
SIDE_RIGHT = r"\b(?:L[\s./]*D|[DT](?:[./]\s*|\s+)D|DIREIT[AO]S?|DIR\.?|RIGHT|RH)\b"
SIDE_LEFT = r"\b(?:L[\s./]*E|[DT](?:[./]\s*|\s+)E|ESQUERD[AO]S?|ESQ\.?|LEFT|LH)\b"
FRONT = r"\b(?:D[./][DE]|DIANTEIR[AO]S?|DIANT\.?|FRONTAL|FRONT)\b"
REAR = r"\b(?:T[./][DE]|TRASEIR[AO]S?|TRAS\.?|REAR)\b"
YEAR_RANGE = r"\b((?:19|20)\d{2}|\d{2})\s*(?:-|/|\bA\b|\bATE\b|\bAO\b)\s*((?:19|20)\d{2}|\d{2})\b"


def _text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").upper().replace("–", "-").replace("—", "-")).strip()


def _fold(value) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", _text(value)) if not unicodedata.combining(c))


def _known(value) -> str:
    text = _text(value)
    return "" if re.sub(r"[^A-Z0-9 ]", " ", _fold(text)).strip() in UNKNOWN else text


def _side(value) -> str:
    text = _fold(_known(value))
    right, left = bool(re.search(SIDE_RIGHT, text)), bool(re.search(SIDE_LEFT, text))
    if right and left:
        return "L.D/L.E"
    return "L.D" if right or text == "D" else "L.E" if left or text == "E" else ""


def _position(value) -> str:
    text = _fold(_known(value))
    front, rear = bool(re.search(FRONT, text)), bool(re.search(REAR, text))
    if front and rear:
        return "DIANT./TRAS."
    if front:
        return "DIANT."
    if rear:
        return "TRAS."
    positions = set(re.findall(r"\b(?:SUPERIOR|INFERIOR|CENTRAL)\b", text))
    return positions.pop() if len(positions) == 1 else ""


def _years(value) -> str:
    text = _fold(_known(value))
    match = re.search(YEAR_RANGE, text)
    if match:
        return f"{int(match[1]) % 100:02d}-{int(match[2]) % 100:02d}"
    if re.fullmatch(r"(?:19|20)\d{2}|\d{2}", text):
        return f"{int(text) % 100:02d}"
    return ""  # Faixa ambígua não vira aplicação inventada.


def _brand(value) -> str:
    text = _fold(_known(value)).replace("/", " ").strip()
    for canonical, aliases in BRAND_ALIASES.items():
        if text in aliases:
            return canonical
    return _known(value)


def _strip_phrase(text: str, phrase: str) -> str:
    if not phrase:
        return text
    return re.sub(r"\b" + re.escape(_fold(phrase)) + r"\b", " ", text)


def _part_match(value: str) -> tuple[str, str]:
    """Separa o tipo conhecido dos qualificadores, sem apagar características."""
    text = re.sub(r"(?<=[A-Z])-+(?=[A-Z])", " ", _fold(value))
    text = re.sub(r"\s+", " ", text).strip(" .-/")
    prefix = ""
    kit = re.match(r"^(KIT|PAR)(?: DE)?\s+", text)
    if kit:
        prefix, text = kit[1] + " ", text[kit.end():]
    choices = sorted(((alias, canonical) for canonical, aliases in PART_ALIASES.items()
                      for alias in (_fold(canonical), *aliases)), key=lambda row: len(row[0]), reverse=True)
    for alias, canonical in choices:
        match = re.match(re.escape(alias) + r"(?:\b|$)", text)
        if match:
            return prefix + canonical, text[match.end():].strip(" .-/")
    return "", prefix + text


def _part(value: str) -> str:
    canonical, qualifiers = _part_match(value)
    return " ".join(v for v in (canonical, qualifiers) if v)


def _pieces(identity: "Identity", *, manual: bool = False) -> dict[str, str]:
    # Nome e campos estruturados são duas fontes complementares. Não excluir o
    # nome só porque o catálogo trouxe um part_type genérico (ex.: RETROVISOR).
    raw = re.sub(r"(?<=[A-Z])(?=(?:19|20)\d{2}|\d{2}[-/]\d{2}\b)", " ", _fold(identity.name))
    brand = _brand(identity.vehicle_brand)
    model, version = _known(identity.vehicle_model), _known(identity.version)
    side, position = _side(identity.side), _position(identity.position)
    years = _years(identity.years) or _years(model)
    # Campos antigos podem conter atributos repetidos no modelo. Antes de
    # removê-los do texto, retenha o que foi explicitamente informado.
    side = side or _side(model)
    position = position or _position(model)
    year_match = re.search(YEAR_RANGE, raw)
    if year_match:
        years = years or _years(year_match[0])

    brand_match = None
    candidates = BRAND_ALIASES.get(brand, (brand,)) if brand else tuple(
        alias for aliases in BRAND_ALIASES.values() for alias in aliases)
    for alias in sorted(candidates, key=len, reverse=True):
        if alias and (found := re.search(r"\b" + re.escape(_fold(alias)) + r"\b", raw)):
            brand_match = found
            brand = brand or _brand(alias)
            break
    base = raw
    suffix = ""
    if brand_match:
        base = raw[:brand_match.start()]
        tail = raw[brand_match.end():].strip()
        match = re.search(YEAR_RANGE, tail)
        if match:
            model = model or tail[:match.start()]
            suffix = tail[match.end():].strip(" .-/")
        else:
            model = model or tail
    elif not brand and year_match:
        # Aplicação explicitamente escrita depois da abreviação de lado.
        marker = re.search(r"\b[LDT][./][DE]\b", raw)
        if marker and marker.end() < year_match.start():
            model = model or raw[marker.end():year_match.start()].strip()

    for field in (identity.vehicle_brand, model, version, identity.manufacturer):
        base = _strip_phrase(base, _known(field))
    base = re.sub(YEAR_RANGE, " ", base)
    if not _known(base) and identity.part_type:
        base = _fold(identity.part_type)
    canonical, qualifiers = _part_match(base)
    # Se o nome é genérico/desconhecido, o tipo informado ainda pode identificá-lo.
    if _fold(identity.name) in UNKNOWN and _known(identity.part_type):
        canonical, qualifiers = _part_match(identity.part_type)

    side_source = qualifiers if canonical else base
    side = side or _side(side_source)
    abbreviated = re.search(r"\b([DE])\.?\s*$", side_source)
    if not side and abbreviated:
        side = "L.D" if abbreviated[1] == "D" else "L.E"
    # TRASEIRA em TAMPA TRASEIRA pertence ao tipo; não é descartada como posição.
    position = position or _position(side_source)
    cleaned = re.sub(SIDE_RIGHT + "|" + SIDE_LEFT + "|" + FRONT + "|" + REAR, " ", side_source)
    if position in ("SUPERIOR", "INFERIOR", "CENTRAL"):
        cleaned = _strip_phrase(cleaned, position)
    if abbreviated:
        cleaned = re.sub(r"\b[DE]\.?\s*$", " ", cleaned)
    if canonical:
        part = " ".join(v for v in (canonical, re.sub(r"\s+", " ", cleaned).strip(" .-/"), suffix) if v)
    else:
        part = " ".join(v for v in (re.sub(r"\s+", " ", cleaned).strip(" .-/"), suffix) if v)
    if not part and _known(identity.part_type):
        part = _part(identity.part_type)

    model = re.sub(YEAR_RANGE, " ", _fold(model))
    model = re.sub(SIDE_RIGHT + "|" + SIDE_LEFT + "|" + FRONT + "|" + REAR, " ", model)
    for alias in BRAND_ALIASES.get(brand, (brand,)):
        model = _strip_phrase(model, alias)
    model = re.sub(r"\s+", " ", model).strip(" .-/")
    version = _text(version)
    if version and version in model:
        version = ""
    if part in ("FAROL", "FAROL DE NEBLINA") and position == "DIANT.":
        position = ""
    return dict(part=part, side=side, position=position, brand=brand, model=model, version=version, years=years)


def _format(values: dict[str, str]) -> str:
    side, position = values["side"], values["position"]
    if side in ("L.D", "L.E") and position in ("DIANT.", "TRAS."):
        side = ("D." if position == "DIANT." else "T.") + side[-1]
        position = ""
    return " ".join(value for value in (values["part"], position, side, values["brand"], values["model"], values["version"], values["years"]) if value) or "Peça não identificada"


def format_identity_name(identity: "Identity") -> str:
    if _fold(identity.name) in UNKNOWN and not _known(identity.part_type):
        return "Peça não identificada"
    return _format(_pieces(identity))


def standardize_identity(identity: "Identity") -> str:
    if _fold(identity.name) in UNKNOWN and not _known(identity.part_type):
        identity.name = "Peça não identificada"
        return "Peça não identificada"
    values = _pieces(identity)
    name = _format(values)
    if name != "Peça não identificada":
        # Persistir todos os atributos derivados torna a normalização idempotente,
        # inclusive ao retomar lotes antigos que só guardavam o nome completo.
        identity.part_type = values["part"] or None
        identity.side = values["side"] or None
        identity.position = values["position"] or None
        identity.vehicle_brand = values["brand"] or None
        identity.vehicle_model = values["model"] or None
        identity.version = values["version"] or None
        identity.years = values["years"] or None
        identity.name = name
    return name


def manual_identity(name: str) -> "Identity":
    from .models import Identity
    identity = Identity(name=name.strip(), evidence=["Nome conferido manualmente; somente dados informados pelo usuário."])
    standardize_identity(identity)
    return identity
