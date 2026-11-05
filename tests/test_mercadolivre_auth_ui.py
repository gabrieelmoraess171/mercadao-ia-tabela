import time
from pathlib import Path
from urllib.parse import urlencode, parse_qs

import httpx
from streamlit.testing.v1 import AppTest

from services.mercadolivre_auth import MercadoLivreOAuth, Tokens
from services.models import Classification, Identity, PhotoKind
from services.pipeline import prepare_batch

REDIRECT = "https://retorno.example.test/mercadolivre"


def configure(app):
    app.text_input(key="meli_client_id").set_value("123456")
    app.text_input(key="meli_client_secret").set_value("test-secret")
    app.text_input(key="meli_redirect_uri").set_value(REDIRECT)
    return next(b for b in app.button if b.label == "Gerar autorização do Mercado Livre").click().run()


def test_ui_connects_clears_code_and_disconnects(monkeypatch):
    import services.mercadolivre_auth_ui as ui
    def handle(request):
        return httpx.Response(200, json={"access_token": "test-access", "refresh_token": "test-refresh",
            "expires_in": 21600, "token_type": "bearer"})
    def factory(*args, **kwargs):
        return MercadoLivreOAuth(*args, **kwargs, client=httpx.Client(transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(ui, "MercadoLivreOAuth", factory)
    monkeypatch.delenv("MELI_CLIENT_ID", raising=False)
    monkeypatch.delenv("MELI_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("MELI_REDIRECT_URI", raising=False)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    configure(app)
    assert not app.exception
    attempt = app.session_state["meli_attempt"]
    returned = REDIRECT + "?" + urlencode({"state": attempt.state, "code": "test-code"})
    app.text_input(key="meli_returned_url").set_value(returned)
    next(b for b in app.button if b.label == "Concluir conexão do Mercado Livre").click().run()
    assert not app.exception
    assert app.session_state["meli_tokens"].access_token == "test-access"
    assert "meli_returned_url" not in app.session_state
    next(b for b in app.button if b.label == "Desconectar Mercado Livre deste programa").click().run()
    assert not app.exception and "meli_tokens" not in app.session_state


def test_expired_token_renews_then_is_used_by_price_provider(photo, tmp_path, monkeypatch):
    import services.mercadolivre_auth_ui as ui
    import services.price_search as prices
    requests, used = [], []
    def handle(request):
        requests.append(parse_qs(request.content.decode()))
        return httpx.Response(200, json={"access_token": "renewed-access", "refresh_token": "renewed-refresh",
            "expires_in": 21600, "token_type": "bearer"})
    def factory(*args, **kwargs):
        return MercadoLivreOAuth(*args, **kwargs, client=httpx.Client(transport=httpx.MockTransport(handle)))
    class Provider:
        def __init__(self, ai, token, **kwargs):
            used.append(token)
        def search(self, product):
            return []
        def close(self):
            pass
    monkeypatch.setattr(ui, "MercadoLivreOAuth", factory)
    monkeypatch.setattr(prices, "MercadoLivreProvider", Provider)
    path = photo()
    batch = prepare_batch([path], tmp_path / "out", None,
        overrides={str(path): Classification(kind=PhotoKind.LABEL, sku="024", confidence=1)})
    batch.products[0].identity = Identity(name="Alternador", confidence=1)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    app.session_state["batch"] = batch
    app.session_state["meli_client_id"] = "123456"
    app.session_state["meli_client_secret"] = "test-secret"
    app.session_state["meli_redirect_uri"] = REDIRECT
    app.run()
    app.session_state["meli_tokens"] = Tokens("old-access", "old-refresh", time.time()-10)
    next(b for b in app.button if b.label == "Pesquisar preços dos nomes salvos").click().run()
    assert not app.exception
    assert used == ["renewed-access"]
    assert requests[0]["grant_type"] == ["refresh_token"]
    assert app.session_state["meli_tokens"].refresh_token == "renewed-refresh"
    manifest = (batch.folder / "lote.json").read_text()
    assert all(value not in manifest for value in ("old-access", "old-refresh", "renewed-access", "renewed-refresh", "test-secret"))


def test_invalid_registration_shows_error_without_network(monkeypatch):
    monkeypatch.delenv("MELI_CLIENT_ID", raising=False)
    monkeypatch.delenv("MELI_CLIENT_SECRET", raising=False)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    next(b for b in app.button if b.label == "Gerar autorização do Mercado Livre").click().run()
    assert not app.exception
    assert any("App ID" in error.value for error in app.error)


def test_failed_token_exchange_shows_reason_and_removes_used_link(monkeypatch):
    import services.mercadolivre_auth_ui as ui
    def factory(*args, **kwargs):
        return MercadoLivreOAuth(*args, **kwargs, client=httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(400, json={"error": "invalid_grant", "message": "test-secret test-code"}))))
    monkeypatch.setattr(ui, "MercadoLivreOAuth", factory)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30).run()
    configure(app)
    attempt = app.session_state["meli_attempt"]
    callback = REDIRECT + "?" + urlencode({"state": attempt.state, "code": "test-code"})
    app.text_input(key="meli_returned_url").set_value(callback)
    next(b for b in app.button if b.label == "Concluir conexão do Mercado Livre").click().run()
    assert not app.exception
    assert any("HTTP 400; invalid_grant" in error.value for error in app.error)
    assert all("test-secret" not in error.value and "test-code" not in error.value for error in app.error)
    assert all(key not in app.session_state for key in ("meli_attempt", "meli_authorization_url", "meli_returned_url", "meli_tokens"))
    next(b for b in app.button if b.label == "Gerar autorização do Mercado Livre").click().run()
    assert not app.exception and app.session_state["meli_attempt"].state != attempt.state
