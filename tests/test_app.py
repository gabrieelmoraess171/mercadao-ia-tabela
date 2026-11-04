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
    # A análise automática sem chave deve parar, sem produzir um lote vazio.
    app.text_input(key="destination").set_value(str(tmp_path / "resultados"))
    next(b for b in app.button if b.label == "INICIAR PROCESSAMENTO").click().run()
    assert not app.exception
    assert "batch" not in app.session_state
    assert any("chave Gemini" in error.value for error in app.error)
    assert not (tmp_path / "resultados").exists()
