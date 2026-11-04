"""Fluxo da interface com dois SKUs conferidos, sem serviços pagos."""
from pathlib import Path

from openpyxl import load_workbook
from streamlit.testing.v1 import AppTest

from services.models import PhotoKind


def test_ui_manual_review_produces_two_products_and_photos(photo, tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MELI_ACCESS_TOKEN", raising=False)
    paths = [photo(f"foto{i}.png") for i in range(1, 5)]
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    app.session_state["paths"] = paths
    app.session_state["review_sequence"] = [{"ORDEM": i, "ARQUIVO": path.name,
        "TIPO": PhotoKind.LABEL.value if i in (1, 3) else PhotoKind.PRODUCT.value,
        "SKU": "024" if i == 1 else "025" if i == 3 else "", "PRESERVAR FUNDO ORIGINAL": True,
        "ETIQUETA REPETIDA DA MESMA PEÇA": False} for i, path in enumerate(paths, 1)]
    app.run()
    assert not app.exception
    app.text_input(key="destination").set_value(str(tmp_path / "out"))
    next(button for button in app.button if button.label == "INICIAR PROCESSAMENTO").click().run()
    assert not app.exception
    batch = app.session_state["batch"]
    assert [p.sku for p in batch.products] == ["024", "025"]
    assert all((p.folder / "01.jpg").exists() for p in batch.products)
    book = load_workbook(batch.folder / "PLANILHA_DE_PRECIFICACAO.xlsx")
    assert book.active["A2"].value == "024 - Peça não identificada"
    assert book.active["A3"].value == "025 - Peça não identificada"
    assert book.active.max_column == 5
    assert book.active["E2"].value is None and book.active["E3"].value is None
