import os
import re

from .image_processor import open_image
from .models import Classification, PhotoKind


def from_ocr(text: str) -> Classification:
    # Exige a palavra SKU; números de OEM, régua ou balança não iniciam grupos.
    match = re.search(r"\bSKU[ \t]*[:#\-]?[ \t]*([A-Za-z0-9][A-Za-z0-9._\-]{0,39})", text, re.IGNORECASE)
    if match:
        return Classification(kind=PhotoKind.LABEL, sku=match.group(1), confidence=0.9, evidence="OCR: " + match.group(0))
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
        if str(path) in self._checked:
            return self._checked.pop(str(path))
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
        if self.ai:
            return self.ai.classify(path)
        if result.kind == PhotoKind.LABEL:
            return result
        return Classification(evidence="Sem classificação automática. Informe tipo e SKU manualmente.")
