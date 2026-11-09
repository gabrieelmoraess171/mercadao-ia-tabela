from pathlib import Path

from PIL import Image
from streamlit.testing.v1 import AppTest

from services.models import Batch, Classification, Identity, Photo, PhotoKind, Product


def test_app_starts_and_local_folder_workflow(photo, tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MELI_ACCESS_TOKEN", raising=False)
    photo("foto10.png")
    photo("foto2.png")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    assert not app.exception
    assert "PRECIFICADOR" in app.title[0].value
    app.text_input(key="source_folder").set_value(str(tmp_path))
    next(b for b in app.button if b.label == "Carregar fotografias da pasta").click().run()
    assert not app.exception
    assert [p.name for p in app.session_state["paths"]] == ["foto2.png", "foto10.png"]
    # A análise automática sem chave deve parar, sem produzir um lote vazio.
    app.text_input(key="destination").set_value(str(tmp_path / "resultados"))
    next(b for b in app.button if b.label == "INICIAR PROCESSAMENTO").click().run()
    assert not app.exception
    assert "batch" not in app.session_state
    assert any("chave Gemini" in error.value for error in app.error)
    assert not (tmp_path / "resultados").exists()


def test_attention_tab_displays_uncertain_original_and_edit(photo, tmp_path):
    source = photo("codigo.jpg")
    product_folder = tmp_path / "produto"
    product_folder.mkdir()
    output = product_folder / "01.jpg"
    Image.new("RGB", (1200, 1200), "white").save(output)
    review = Photo(path=source, classification=Classification(kind=PhotoKind.DETAIL, confidence=1),
                   review_reason="Confira a inscrição.", output="01.jpg")
    product = Product(id="0001", sku="024", folder=product_folder, photos=[review],
                      outputs=["01.jpg"], identity=Identity(name="Peça de teste", confidence=1),
                      identity_reviewed=True)
    batch = Batch(folder=tmp_path, products=[product], total=1, processed=1)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    app.session_state["batch"] = batch
    app.run()
    assert not app.exception
    assert [tab.label for tab in app.tabs] == ["Atenção — edição futura"]
    assert any("Confira a inscrição." in warning.value for warning in app.warning)
