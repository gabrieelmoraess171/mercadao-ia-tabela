from pathlib import Path

from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from services.models import Batch, Classification, Identity, Photo, PhotoKind, Product
from services.file_manager import save_batch


def app_for(batch, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    app.session_state["batch"] = batch
    return app


def test_ui_reanalysis_keeps_unprocessed_photos_and_manual_choices(photo, tmp_path, monkeypatch):
    import services.gemini_service as module
    paths = [photo(f"foto{index}.png") for index in range(4)]
    folder = tmp_path / "antigo"
    folder.mkdir()
    part_folder = folder / "SKU-024"
    part_folder.mkdir()
    first = Classification(kind=PhotoKind.LABEL, sku="024", confidence=1,
                           evidence="Classificação conferida manualmente.")
    batch = Batch(folder=folder, processed=1, total=4, source_paths=paths,
        source_overrides={str(paths[0]): first, str(paths[2]): Classification(kind=PhotoKind.LABEL, sku="025", confidence=1,
            evidence="Classificação conferida manualmente.")}, source_preserve=[str(paths[3])],
        products=[Product(id="0001", sku="024", folder=part_folder, photos=[Photo(path=paths[0], classification=first)])])
    class WorkingAI:
        def __init__(self, *args, **kwargs):
            self.usage, self.model, self.notices = {}, "test-model", []
        def classify(self, path):
            return Classification(kind=PhotoKind.PRODUCT, confidence=1)
        def identify(self, paths):
            return Identity(name="Alternador", confidence=1)
        def close(self):
            pass
    monkeypatch.setattr(module, "GeminiService", WorkingAI)
    # Preserve as fotos para não executar segmentação ONNX neste teste de UI.
    batch.source_preserve = [str(paths[1]), str(paths[3])]
    app = app_for(batch, monkeypatch).run()
    next(t for t in app.text_input if t.label == "Chave da API Gemini").set_value("test-key")
    next(b for b in app.button if b.label == "Retomar identificação e fotos pendentes do lote").click().run()
    assert not app.exception
    recovered = app.session_state["batch"]
    assert recovered.folder != batch.folder and recovered.total == recovered.processed == 4
    assert [p.sku for p in recovered.products] == ["024", "025"]
    assert recovered.products[1].photos[1].preserve_original
    assert (folder / "SKU-024").is_dir()


def test_opening_saved_batch_removes_previous_operation_error(tmp_path, monkeypatch):
    batch = Batch(folder=tmp_path)
    save_batch(batch)
    app = app_for(batch, monkeypatch)
    app.session_state["processing_error"] = "Erro antigo que foi resolvido"
    app.run()
    next(t for t in app.text_input if t.label == "Pasta do lote (contendo lote.json)").set_value(str(tmp_path))
    next(b for b in app.button if b.label == "Abrir resultados salvos").click().run()
    assert not app.exception
    assert "processing_error" not in app.session_state
    assert not any("Erro antigo" in e.value for e in app.error)
