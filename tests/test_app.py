from pathlib import Path

from streamlit.testing.v1 import AppTest


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
    # Sem credenciais, imagens ficam isoladas para revisão, com Excel real salvo.
    app.text_input(key="destination").set_value(str(tmp_path / "resultados"))
    next(b for b in app.button if b.label == "INICIAR PROCESSAMENTO").click().run()
    assert not app.exception
    batch = app.session_state["batch"]
    assert (batch.folder / "PLANILHA_DE_PRECIFICACAO.xlsx").exists()
    assert len(batch.products) == 2 and all(p.sku is None for p in batch.products)
