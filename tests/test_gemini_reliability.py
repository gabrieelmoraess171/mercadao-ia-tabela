import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from services.gemini_service import AIError, AIUnavailableError, DEFAULT_MODEL, GeminiService
from services.models import Classification, Identity, PhotoKind
from services.pipeline import prepare_batch
from services.sku_detector import SkuDetector
from services.file_manager import load_batch


def client_with(responses):
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(text=response, usage_metadata=None)
    return SimpleNamespace(models=SimpleNamespace(generate_content=generate), close=lambda: None), calls


class Overloaded(Exception):
    code = 503


def test_503_uses_configured_alternative_and_exposes_notice(photo):
    result = Classification(kind=PhotoKind.LABEL, sku="024", confidence=1, evidence="SKU: 024")
    client, calls = client_with([Overloaded(), result.model_dump_json()])
    ai = GeminiService("", model="gemini-3.8-flash", client=client, sleep=lambda _: None)
    assert ai.classify(photo()).sku == "024"
    assert [r["model"] for r in calls] == ["gemini-3.8-flash", DEFAULT_MODEL]
    assert ai.model == DEFAULT_MODEL and ai.notices


def test_alias_migrates_to_stable_model_and_missing_confidence_is_rejected(photo):
    client, calls = client_with([json.dumps({"kind": "Produto", "sku": None, "evidence": "Peça"})])
    ai = GeminiService("", model="gemini-flash-latest", client=client, sleep=lambda _: None)
    with pytest.raises(AIError, match="inválidos"):
        ai.classify(photo())
    assert calls[0]["model"] == DEFAULT_MODEL
    assert set(calls[0]["config"].response_json_schema["required"]) == {"kind", "sku", "confidence", "evidence"}


def test_first_identification_is_not_seeded_with_a_failed_previous_answer(photo):
    expected = Identity(name="Alternador", confidence=0.9, evidence=["Carcaça, polia e conectores"])
    client, calls = client_with([expected.model_dump_json()])
    ai = GeminiService("", client=client, sleep=lambda _: None)
    result = ai.identify([photo()])
    prompt = calls[0]["contents"][0].text
    assert result.name == "Alternador" and result.oem is None
    assert "Identidade parcial das fotos anteriores" not in prompt
    assert '"name":"Peça não identificada"' not in prompt
    assert "nome genérico correto" in prompt


def test_empty_identity_name_is_not_counted_as_identified(photo):
    client, _ = client_with([Identity(name="", confidence=0.9).model_dump_json()])
    ai = GeminiService("", client=client, sleep=lambda _: None)
    with pytest.raises(AIError, match="inválidos"):
        ai.identify([photo()])


def test_service_failure_is_specific_and_blocks_further_calls(photo):
    client, calls = client_with([Overloaded("do not show private content") for _ in range(3)])
    ai = GeminiService("", client=client, sleep=lambda _: None)
    for _ in range(2):
        with pytest.raises(AIUnavailableError, match="503") as error:
            ai.classify(photo())
        assert "private content" not in str(error.value)
    assert len(calls) == 3


def test_invalid_key_400_has_safe_actionable_message(photo):
    class InvalidKey(Exception):
        code = 400
        message = "API key not valid: private-key-value"
    client, calls = client_with([InvalidKey()])
    ai = GeminiService("", client=client, sleep=lambda _: None)
    with pytest.raises(AIUnavailableError, match="Chave Gemini inválida") as error:
        ai.classify(photo())
    assert "private-key-value" not in str(error.value)
    assert len(calls) == 1


def test_preflight_failure_creates_no_empty_lot(photo, tmp_path):
    class AI:
        def classify(self, path):
            raise AIUnavailableError("Gemini indisponível (503)", 503)
    destination = tmp_path / "out"
    with pytest.raises(AIUnavailableError, match="503"):
        prepare_batch([photo("a.png"), photo("b.png")], destination, SkuDetector(AI()))
    assert not destination.exists()


def test_preflight_photo_is_reused_without_duplicate_api_call(photo, tmp_path, monkeypatch):
    import pytesseract
    monkeypatch.setattr(pytesseract, "image_to_string", lambda *a, **k: "")
    paths = [photo("label.png"), photo("product.png")]
    called = []
    class AI:
        def classify(self, path):
            called.append(path)
            return Classification(kind=PhotoKind.LABEL if path == paths[0] else PhotoKind.PRODUCT,
                                  sku="024" if path == paths[0] else None, confidence=1)
    batch = prepare_batch(paths, tmp_path / "out", SkuDetector(AI()))
    assert called == paths
    assert batch.products[0].sku == "024" and len(batch.products[0].photos) == 2


def test_mid_scan_service_failure_saves_partial_progress_without_fake_groups(photo, tmp_path):
    paths = [photo(f"p{i}.png") for i in range(3)]
    class Detector:
        def classify(self, path):
            if path == paths[0]:
                return Classification(kind=PhotoKind.LABEL, sku="024", confidence=1)
            raise AIUnavailableError("Gemini indisponível (503)", 503)
    with pytest.raises(AIUnavailableError) as error:
        prepare_batch(paths, tmp_path / "out", Detector())
    batch = error.value.batch
    assert batch is not None
    restored = load_batch(batch.folder)
    assert restored.processed == 1 and len(restored.products) == 1
    assert len(restored.products[0].photos) == 1 and "503" in restored.error


def test_moderately_confident_product_is_analyzed_and_flagged_without_inventing_sku(photo, tmp_path):
    paths = [photo("label.png"), photo("part.png"), photo("unreadable-label.png"), photo("next.png")]
    results = [Classification(kind=PhotoKind.LABEL, sku="024", confidence=1),
               Classification(kind=PhotoKind.PRODUCT, confidence=0.7),
               Classification(kind=PhotoKind.LABEL, sku="025", confidence=0.7),
               Classification(kind=PhotoKind.PRODUCT, confidence=0.9)]
    class Detector:
        def classify(self, path):
            return results[paths.index(path)]
    batch = prepare_batch(paths, tmp_path / "out", Detector())
    assert [p.sku for p in batch.products] == ["024", None]
    assert batch.products[0].photos[1].classification.kind == PhotoKind.PRODUCT
    assert batch.products[0].photos[1].classification.confidence == 0.7
    assert batch.products[0].photos[1].review_reason
    assert batch.products[1].photos[0].classification.sku is None


def test_ui_shows_preflight_error_without_empty_result_list(photo, tmp_path, monkeypatch):
    import services.gemini_service as module
    class FailingAI:
        def __init__(self, *args, **kwargs):
            self.usage = {}
        def classify(self, path):
            raise AIUnavailableError("Gemini indisponível (503)", 503)
        def close(self):
            pass
    monkeypatch.setattr(module, "GeminiService", FailingAI)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    app.session_state["paths"] = [photo()]
    app.run()
    next(t for t in app.text_input if t.label == "Chave da API Gemini").set_value("test-key")
    app.text_input(key="destination").set_value(str(tmp_path / "out"))
    next(b for b in app.button if b.label == "INICIAR PROCESSAMENTO").click().run()
    assert not app.exception and any("503" in error.value for error in app.error)
    assert "batch" not in app.session_state and not (tmp_path / "out").exists()


def test_ui_reanalyzes_old_unknown_lot_and_preserves_previous_results(photo, tmp_path, monkeypatch):
    import pytesseract
    import services.gemini_service as module
    monkeypatch.setattr(pytesseract, "image_to_string", lambda *a, **k: "")
    paths = [photo("label.png"), photo("product.png")]
    class UnknownDetector:
        def classify(self, path):
            return Classification()
    old = prepare_batch(paths, tmp_path / "out", UnknownDetector())
    for product in old.products:
        for item in product.photos:
            item.preserve_original = True
    class WorkingAI:
        def __init__(self, *args, **kwargs):
            self.usage, self.model, self.notices = {}, DEFAULT_MODEL, []
        def classify(self, path):
            return Classification(kind=PhotoKind.LABEL if path == paths[0] else PhotoKind.PRODUCT,
                                  sku="024" if path == paths[0] else None, confidence=1)
        def identify(self, paths):
            return Identity(name="Alternador", confidence=0.9, evidence=["Identificação de teste"])
        def close(self):
            pass
    monkeypatch.setattr(module, "GeminiService", WorkingAI)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    app.session_state["batch"] = old
    app.run()
    next(t for t in app.text_input if t.label == "Chave da API Gemini").set_value("test-key")
    next(b for b in app.button if b.label == "Reanalisar lote com a IA").click().run()
    assert not app.exception
    fixed = app.session_state["batch"]
    assert fixed.folder != old.folder and old.folder.exists()
    assert len(fixed.products) == 1 and fixed.products[0].sku == "024"
    assert fixed.products[0].identity.name == "ALTERNADOR"
    assert (fixed.products[0].folder / "01.jpg").exists()
    assert load_workbook(fixed.folder / "PLANILHA_DE_PRECIFICACAO.xlsx").active["A2"].value == "024 - ALTERNADOR"
