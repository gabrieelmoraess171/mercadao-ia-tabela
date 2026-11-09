import os
import re

from .image_processor import open_image
from .models import Classification, PhotoKind


def from_ocr(text: str) -> Classification:
    # Exige a palavra SKU; números de OEM, régua ou balança não iniciam grupos.
    match = re.search(r"\bSKU\b(?P<separator>\s*[:#\-]?\s*)(?P<token>[^\s:;,#]+)", text, re.IGNORECASE)
    if match and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/\-]{0,39}", match["token"]):
        # Em outra linha, uma palavra como Produto/Peso não é prova de SKU.
        # Códigos com letras continuam válidos na mesma linha ou com dígitos.
        multiline = "\n" in match["separator"] or "\r" in match["separator"]
        if not multiline or any(character.isdigit() for character in match["token"]):
            return Classification(kind=PhotoKind.LABEL, sku=match["token"], confidence=0.9, evidence="OCR: " + match.group(0))
    if re.search(r"\bSKU\b", text, re.IGNORECASE):
        return Classification(kind=PhotoKind.LABEL, evidence="Etiqueta SKU com código ilegível.")
    return Classification()


class SkuDetector:
    def __init__(self, ai=None):
        self.ai = ai
        self.ocr_available = True
        self._checked = {}

    def validate_connection(self, paths):
        if not self.ai:
            return
        for path in paths:
            try:
                with open_image(path):
                    pass
            except Exception:
                continue
            result = self.ai.classify(path)
            self._checked[str(path)] = result
            return

    def classify(self, path):
        checked = self._checked.pop(str(path), None)
        result = Classification()
        try:
            import pytesseract
            if os.getenv("TESSERACT_CMD"):
                pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
            with open_image(path) as image:
                image.thumbnail((2000, 2000))
                result = from_ocr(pytesseract.image_to_string(image.convert("RGB"), config="--psm 11", timeout=20))
            if result.kind == PhotoKind.LABEL and result.sku:
                return result
        except Exception:
            self.ocr_available = False
        if checked is not None:
            return checked
        if self.ai:
            return self.ai.classify(path)
        if result.kind == PhotoKind.LABEL:
            return result
        return Classification(evidence="Sem classificação automática. Informe tipo e SKU manualmente.")
