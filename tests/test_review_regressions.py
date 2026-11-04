from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from services.excel_export import export_excel, price_range
from services.file_manager import load_batch, safe_name, save_batch
from services.image_processor import ImageProcessor
from services.models import Classification, Identity, PhotoKind, Product, Reference
from services.pipeline import prepare_batch, process_batch, search_prices
from services.price_search import MercadoLivreProvider
from services.sku_detector import SkuDetector
from services.gemini_service import AIError


def make_batch(photo, tmp_path):
    paths = [photo("etiqueta.png"), photo("produto.png")]
    overrides = {str(paths[0]): Classification(kind=PhotoKind.LABEL, sku="024", confidence=1),
                 str(paths[1]): Classification(kind=PhotoKind.PRODUCT, confidence=1)}
    return prepare_batch(paths, tmp_path / "out", None, overrides=overrides)


def app_for_batch(batch, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MELI_ACCESS_TOKEN", raising=False)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    app.session_state["batch"] = batch
    return app.run()


def test_name_correction_invalidates_old_price_references(photo, tmp_path, monkeypatch):
    batch = make_batch(photo, tmp_path)
    product = batch.products[0]
    product.identity = Identity(name="Alternador", oem="CODIGO-ANTIGO", confidence=0.9)
    product.references = [Reference(title="Alternador", price=350, url="https://produto.mercadolivre.com.br/MLB-123456",
                                   condition="used", verified=True, compatible=True),
                          Reference(title="Alternador", price=750, url="https://produto.mercadolivre.com.br/MLB-234567",
                                   condition="used", verified=True, compatible=True)]
    app = app_for_batch(batch, monkeypatch)
    assert not app.exception
    app.session_state[f"final-{batch.folder.name}"] = {"edited_rows": {0: {"PEÇA": "Retrovisor", "FINAL": 500.0}},
                                                     "added_rows": [], "deleted_rows": []}
    next(b for b in app.button if b.label == "Salvar nomes e valores finais no Excel").click().run()
    assert not app.exception
    updated = app.session_state["batch"].products[0]
    assert updated.identity.name == "RETROVISOR"
    assert updated.identity.oem is None
    assert price_range(updated.references) == (None, None, None)
    sheet = load_workbook(batch.folder / "PLANILHA_DE_PRECIFICACAO.xlsx").active
    assert sheet["A2"].value == "024 - RETROVISOR" and sheet["B2"].value is None and sheet["E2"].value == 500


def test_manual_reference_editor_updates_real_excel(photo, tmp_path, monkeypatch):
    batch = make_batch(photo, tmp_path)
    app = app_for_batch(batch, monkeypatch)
    assert not app.exception
    key = f"refs-{batch.folder.name}-0001-0"
    first = {"TÍTULO": "Referência 1", "PREÇO": 350.0, "LINK": "https://produto.mercadolivre.com.br/MLB-123456",
             "CONDIÇÃO": "Usada", "VERIFICADO": True, "COMPATÍVEL": True, "OBSERVAÇÃO": "Conferido"}
    second = dict(first, **{"TÍTULO": "Referência 2", "PREÇO": 750.0, "LINK": "https://produto.mercadolivre.com.br/MLB-234567"})
    app.session_state[key] = {"edited_rows": {0: first}, "added_rows": [second], "deleted_rows": []}
    next(b for b in app.button if b.label == "Salvar referências e recalcular Excel").click().run()
    assert not app.exception
    sheet = load_workbook(batch.folder / "PLANILHA_DE_PRECIFICACAO.xlsx").active
    assert [sheet.cell(2, n).value for n in (3, 4, 5, 6)] == [350, 750, 550, None]


def test_cleared_photo_type_does_not_crash_interface(photo, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
    path = photo()
    app.session_state["paths"] = [path]
    app.session_state["review_sequence"] = [{"ORDEM": 1, "ARQUIVO": path.name, "TIPO": None,
        "SKU": "", "PRESERVAR FUNDO ORIGINAL": False, "ETIQUETA REPETIDA DA MESMA PEÇA": False}]
    app.run()
    assert not app.exception


def test_low_confidence_photo_stops_assignment_to_previous_sku(photo, tmp_path):
    paths = [photo(f"f{i}.png") for i in range(3)]
    overrides = {str(paths[0]): Classification(kind=PhotoKind.LABEL, sku="024", confidence=1),
                 str(paths[1]): Classification(kind=PhotoKind.PRODUCT, confidence=0.2),
                 str(paths[2]): Classification(kind=PhotoKind.PRODUCT, confidence=1)}
    batch = prepare_batch(paths, tmp_path / "out", None, overrides=overrides)
    assert [p.sku for p in batch.products] == ["024", None]
    assert len(batch.products[0].photos) == 1


def test_resuming_completed_product_restores_missing_output(photo, tmp_path):
    batch = make_batch(photo, tmp_path)
    batch.products[0].identity = Identity(name="Alternador", confidence=0.9)
    class Processor:
        def process(self, path, **kwargs):
            result, _ = ImageProcessor().process(path, preserve_original=True)
            return result, []
    process_batch(batch, processor=Processor())
    product = batch.products[0]
    assert product.status == "Concluído"
    output = product.folder / "01.jpg"
    output.unlink()
    process_batch(batch, processor=Processor())
    assert output.exists() and product.outputs == ["01.jpg"]


def test_sku_illegible_keeps_label_classification_without_ai(photo, monkeypatch):
    import pytesseract
    monkeypatch.setattr(pytesseract, "image_to_string", lambda *a, **k: "SKU\n")
    result = SkuDetector().classify(photo())
    assert result.kind == PhotoKind.LABEL and result.sku is None


def test_one_unavailable_listing_does_not_discard_other_prices(tmp_path):
    def handle(request):
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"results": [{"id": "MLB123456"}, {"id": "MLB234567"}]})
        if request.url.path == "/items/MLB123456":
            return httpx.Response(404)
        if request.url.path.endswith("/description"):
            return httpx.Response(200, json={"plain_text": "Usada original"})
        return httpx.Response(200, json={"status": "active", "currency_id": "BRL", "price": 750,
            "title": "Alternador usado", "condition": "used", "permalink": "https://produto.mercadolivre.com.br/MLB-234567", "pictures": []})
    provider = MercadoLivreProvider(token="TEST", client=httpx.Client(transport=httpx.MockTransport(handle)))
    refs = provider.search(Product(id="1", sku="024", folder=tmp_path))
    assert len(refs) == 1 and refs[0].price == Decimal("750")


def test_uncertain_identification_needs_review_before_price_search(photo, tmp_path):
    batch = make_batch(photo, tmp_path)
    batch.products[0].identity = Identity(name="Talvez alternador", confidence=0.2)
    class Provider:
        def search(self, product):
            pytest.fail("Não pesquisar automaticamente uma identidade incerta sem revisão")
    search_prices(batch, Provider())
    assert batch.searches == 0
    assert any("confirme" in issue.lower() for issue in load_batch(batch.folder).products[0].issues)


def test_windows_long_filename_has_no_trailing_dot_or_space():
    assert not safe_name("a" * 89 + ".xyz").endswith((".", " "))


def test_preserve_choice_survives_failure_and_reopening(photo, tmp_path):
    paths = [photo("label.png"), photo("product.png")]
    overrides = {str(paths[0]): Classification(kind=PhotoKind.LABEL, sku="024", confidence=1),
                 str(paths[1]): Classification(kind=PhotoKind.PRODUCT, confidence=1)}
    batch = prepare_batch(paths, tmp_path / "out", None, overrides=overrides, preserve={str(paths[1])})
    class Failing:
        def process(self, path, **kwargs):
            raise OSError("Falha transitória no teste")
    process_batch(batch, processor=Failing())
    restored = load_batch(batch.folder)
    captured = []
    class Processor:
        def process(self, path, preserve_original=False):
            captured.append(preserve_original)
            return ImageProcessor().process(path, preserve_original=preserve_original)
    process_batch(restored, processor=Processor())
    assert captured == [True]
    assert (restored.products[0].folder / "01.jpg").exists()


def test_internal_original_paths_follow_product_folder_rename(photo, tmp_path):
    batch = make_batch(photo, tmp_path)
    process_batch(batch, preserve={str(batch.products[0].photos[1].path)})
    for original in batch.products[0].photos:
        original.path.unlink()
    restored = load_batch(batch.folder)
    product = restored.products[0]
    (product.folder / "01.jpg").unlink()
    product.identity = Identity(name="Alternador conferido", confidence=1)
    process_batch(restored)
    assert all(p.path.exists() for p in product.photos)
    assert (product.folder / "01.jpg").exists()


def test_manual_review_allows_search_without_inventing_ai_confidence(photo, tmp_path, monkeypatch):
    batch = make_batch(photo, tmp_path)
    batch.products[0].identity = Identity(name="Alternador", confidence=0.2)
    app = app_for_batch(batch, monkeypatch)
    next(b for b in app.button if b.label == "Salvar nomes e valores finais no Excel").click().run()
    assert not app.exception
    restored = load_batch(batch.folder)
    assert restored.products[0].identity_reviewed
    assert restored.products[0].identity.confidence == 0.2
    called = []
    class Provider:
        def search(self, product):
            called.append(product.sku)
            return []
    search_prices(restored, Provider())
    assert called == ["024"]


def test_grounding_failure_preserves_official_search_candidates(tmp_path):
    class AI:
        def discover(self, query):
            raise AIError("Limite ou cota da API Gemini atingido.")
    def handle(request):
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"results": [{"id": "MLB234567"}]})
        if request.url.path.endswith("/description"):
            return httpx.Response(200, json={"plain_text": "Usada original"})
        return httpx.Response(200, json={"status": "active", "currency_id": "BRL", "price": 750,
            "title": "Alternador usado", "condition": "used", "permalink": "https://produto.mercadolivre.com.br/MLB-234567", "pictures": []})
    provider = MercadoLivreProvider(ai=AI(), token="TEST", use_grounding=True,
        client=httpx.Client(transport=httpx.MockTransport(handle)))
    product = Product(id="1", sku="024", folder=tmp_path)
    refs = provider.search(product)
    assert len(refs) == 1 and refs[0].price == Decimal("750")
    assert not refs[0].compatible and any("cota" in issue for issue in product.issues)


def test_visual_comparison_failure_keeps_verified_price_for_manual_review(photo, tmp_path, monkeypatch):
    class AI:
        def compare(self, *args):
            raise AIError("Limite ou cota da API Gemini atingido.")
    def handle(request):
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"results": [{"id": "MLB234567"}]})
        if request.url.path.endswith("/description"):
            return httpx.Response(200, json={"plain_text": "Usada original"})
        return httpx.Response(200, json={"status": "active", "currency_id": "BRL", "price": 750,
            "title": "Alternador usado", "condition": "used", "permalink": "https://produto.mercadolivre.com.br/MLB-234567",
            "pictures": [{"secure_url": "https://http2.mlstatic.com/test.jpg"}]})
    batch = make_batch(photo, tmp_path)
    provider = MercadoLivreProvider(ai=AI(), token="TEST", client=httpx.Client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(provider, "_image", lambda _: b"imagem de teste")
    refs = provider.search(batch.products[0])
    assert refs[0].price == Decimal("750") and refs[0].verified and not refs[0].compatible
    assert "cota" in refs[0].reason
