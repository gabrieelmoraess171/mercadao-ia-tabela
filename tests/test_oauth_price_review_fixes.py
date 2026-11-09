"""Regressões da revisão: conta OAuth, retorno e anúncios individuais."""
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import time

import httpx
import pytest

from services import mercadolivre_auth_ui as ui
from services.excel_export import price_range
from services.mercadolivre_auth import AuthorizationError, Tokens
from services.models import Product, Reference
from services.price_search import MercadoLivreProvider, item_id


def test_starting_other_account_does_not_keep_previous_token_after_failure(monkeypatch):
    state = {"meli_tokens": Tokens("old-account-access", "old-refresh", time.time() + 3600)}

    class OAuth:
        def begin(self):
            return SimpleNamespace(used=False), "https://auth.example.test/new-attempt"

        def finish(self, attempt, returned):
            attempt.used = True
            raise AuthorizationError("HTTP 400; invalid_grant")

        def close(self):
            pass

    monkeypatch.setattr(ui, "st", SimpleNamespace(session_state=state))
    monkeypatch.setattr(ui, "_oauth", OAuth)
    ui._begin()
    assert "meli_tokens" not in state
    state["meli_returned_url"] = "callback-new-account"
    ui._finish()
    assert ui.access_token() == ""
    assert all(key not in state for key in ("meli_tokens", "meli_attempt", "meli_authorization_url"))
    assert "invalid_grant" in state["meli_auth_notice"][1]


@pytest.mark.parametrize("url", [
    "https://www.mercadolivre.com.br/p/MLB12345678",
    "https://www.mercadolivre.com.br/alternador/p/MLB12345678",
    "https://www.mercadolivre.com.br/p/MLB12345678?wid=MLB87654321",
    "https://www.mercadolivre.com.br/ofertas/MLB12345678",
    "https://produto.mercadolivre.com.br@evil.example/MLB-12345678",
    "https://:secret@produto.mercadolivre.com.br/MLB-12345678",
    None,
])
def test_catalog_pages_and_other_non_item_urls_are_not_listings(url):
    assert item_id(url) is None


@pytest.mark.parametrize("url", [
    "https://produto.mercadolivre.com.br/MLB-12345678-alternador-_JM",
    "https://produto.mercadolivre.com.br/MLB12345678-alternador-_JM?quantity=1#tracking",
    "https://www.mercadolivre.com.br/MLB-12345678",
    "https://mercadolivre.com.br:443/MLB-12345678/",
])
def test_real_individual_listing_forms_keep_same_id(url):
    assert item_id(url) == "MLB12345678"


def test_even_manually_marked_catalog_references_do_not_produce_price_range():
    refs = [Reference(title="Catálogo", url=f"https://www.mercadolivre.com.br/p/MLB{identifier}",
                      price=value, verified=True, compatible=True, condition="used")
            for identifier, value in [(12345678, Decimal("100")), (87654321, Decimal("200"))]]
    assert price_range(refs) == (None, None, None)


@pytest.mark.parametrize("first_price,first_permalink", [
    (100, "https://produto.mercadolivre.com.br/MLB-99999999-outro-_JM"),
    (True, "https://produto.mercadolivre.com.br/MLB-12345678-item-_JM"),
    (float("nan"), "https://produto.mercadolivre.com.br/MLB-12345678-item-_JM"),
    (float("inf"), "https://produto.mercadolivre.com.br/MLB-12345678-item-_JM"),
])
def test_bad_price_or_mismatched_item_link_does_not_discard_other_listing(tmp_path, first_price, first_permalink):
    import json

    def handle(request):
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"results": [{"id": "MLB12345678"}, {"id": "MLB87654321"}]})
        if request.url.path.endswith("/description"):
            return httpx.Response(200, json={"plain_text": "Peça usada"})
        first = request.url.path.endswith("12345678")
        data = {"status": "active", "currency_id": "BRL", "price": first_price if first else 200,
                "title": "Alternador", "condition": "used", "pictures": [],
                "permalink": first_permalink if first else "https://produto.mercadolivre.com.br/MLB-87654321-item-_JM"}
        return httpx.Response(200, text=json.dumps(data))

    provider = MercadoLivreProvider(token="test-access", client=httpx.Client(transport=httpx.MockTransport(handle)))
    try:
        refs = provider.search(Product(id="1", sku="024", folder=tmp_path))
    finally:
        provider.close()
    assert len(refs) == 1 and refs[0].price == Decimal("200")
    assert item_id(refs[0].url) == "MLB87654321"


def test_return_page_directs_user_back_to_original_session():
    html = (Path(__file__).resolve().parents[1] / "oauth-retorno/retorno.html").read_text()
    assert "aba original" in html
    assert 'href="http://127.0.0.1:8501"' not in html
