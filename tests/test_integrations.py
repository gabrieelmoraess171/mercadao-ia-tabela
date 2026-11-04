import json
from decimal import Decimal
from types import SimpleNamespace as NS

import httpx
import pytest

from services.gemini_service import AIError, GeminiService
from services.models import Identity, Photo, PhotoKind, Classification, Product
from services.price_search import MercadoLivreProvider, SearchUnavailable, item_id


def client_with(responses):
    class Models:
        def generate_content(self, **kwargs):
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return NS(text=result, usage_metadata=NS(prompt_token_count=10, candidates_token_count=5))
    return NS(models=Models())


def test_gemini_structured_and_usage(photo):
    service = GeminiService("", client=client_with([Identity(name="Alternador", confidence=0.9).model_dump_json()]), sleep=lambda _: None)
    identity = service.identify([photo()])
    assert identity.name == "Alternador"
    assert service.usage == {"calls": 1, "input_tokens": 10, "output_tokens": 5, "grounding_calls": 0}


def test_invalid_json_no_invention(photo):
    service = GeminiService("", client=client_with(['{"confidence":8}', 'not json']), sleep=lambda _: None)
    with pytest.raises(AIError, match="inválidos"):
        service.identify([photo()])
    with pytest.raises(AIError, match="inválidos"):
        service.identify([photo()])


def test_gemini_retries_capped_and_keys_never_in_errors(photo):
    class RateLimit(Exception):
        code = 429
    service = GeminiService("", client=client_with([RateLimit("SECRET") for _ in range(3)]), sleep=lambda _: None)
    with pytest.raises(AIError, match="cota") as exc:
        service.identify([photo()])
    assert "SECRET" not in str(exc.value)
    assert service.usage["calls"] == 3
    with pytest.raises(AIError, match="cota"):
        service.identify([photo()])
    assert service.usage["calls"] == 3  # não gasta cota em cada foto restante


def test_transient_retry_then_success_and_call_limit(photo):
    class Temporary(Exception):
        code = 503
    service = GeminiService("", client=client_with([Temporary(), Identity(name="Farol").model_dump_json()]),
                            max_calls=2, sleep=lambda _: None)
    assert service.identify([photo()]).name == "Farol"
    with pytest.raises(AIError, match="Limite de chamadas"):
        service.identify([photo()])


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_permanent_api_errors_not_retried(photo, code):
    class Error(Exception):
        pass
    error = Error("Do not expose credential")
    error.code = code
    service = GeminiService("", client=client_with([error]), sleep=lambda _: None)
    with pytest.raises(AIError):
        service.identify([photo()])
    assert service.usage["calls"] == 1


@pytest.mark.parametrize("url", ["http://produto.mercadolivre.com.br/MLB-123456", "https://evil.com/MLB-123456",
                                   "https://127.0.0.1/MLB-123456", "https://produto.mercadolivre.com.br@evil.com/MLB-123456"])
def test_reject_invalid_candidate_links(url):
    assert item_id(url) is None


def test_meli_forbidden_honest_no_prices(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(403)))
    product = Product(id="1", sku="024", folder=tmp_path, identity=Identity(name="Alternador"))
    provider = MercadoLivreProvider(token="TEST", client=client)
    with pytest.raises(SearchUnavailable, match="restringiu"):
        provider.search(product)
    assert not product.references


def test_meli_does_not_request_search_without_authorization(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(lambda r: pytest.fail("Requisição não autorizada")))
    provider = MercadoLivreProvider(client=client)
    with pytest.raises(SearchUnavailable, match="Configure"):
        provider.search(Product(id="1", sku="024", folder=tmp_path))


def test_api_verified_price_needs_visual_compatibility(tmp_path):
    def handle(request):
        assert request.url.host == "api.mercadolibre.com"
        if request.url.path.endswith("/search"):
            return httpx.Response(200, json={"results": [{"id": "MLB123456"}]})
        if request.url.path.endswith("/description"):
            return httpx.Response(200, json={"plain_text": "Original usado"})
        return httpx.Response(200, json={"status": "active", "currency_id": "BRL", "price": 350,
            "title": "Alternador usado", "condition": "used", "permalink": "https://produto.mercadolivre.com.br/MLB-123456", "pictures": []})
    provider = MercadoLivreProvider(token="TEST", client=httpx.Client(transport=httpx.MockTransport(handle)))
    refs = provider.search(Product(id="1", sku="024", folder=tmp_path))
    assert refs[0].price == Decimal("350") and refs[0].verified
    assert not refs[0].compatible


def test_grounding_only_discovers_no_ai_prices(tmp_path):
    class AI:
        def discover(self, query):
            return ["https://evil.com/MLB-123456", "https://produto.mercadolivre.com.br/MLB-123456"]
    seen = []
    def handle(request):
        seen.append(str(request.url))
        return httpx.Response(403)
    provider = MercadoLivreProvider(ai=AI(), use_grounding=True, client=httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(SearchUnavailable):
        provider.search(Product(id="1", sku="024", folder=tmp_path))
    assert seen == ["https://api.mercadolibre.com/items/MLB123456"]


def test_external_image_does_not_receive_access_token():
    import io
    from PIL import Image
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20)).save(buffer, "JPEG")
    def handle(request):
        assert "authorization" not in request.headers
        return httpx.Response(200, content=buffer.getvalue())
    provider = MercadoLivreProvider(token="PRIVATE", client=httpx.Client(transport=httpx.MockTransport(handle)))
    assert provider._image("https://http2.mlstatic.com/D_test.jpg")
    assert provider._image("https://127.0.0.1/test.jpg") is None


def test_official_sdk_serializes_schema_inline_images_and_grounding(photo):
    from google import genai
    from google.genai import types
    requests = []
    def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            assert body["generationConfig"]["responseMimeType"] == "application/json"
            assert body["generationConfig"]["responseJsonSchema"]["properties"]["name"]
            assert body["contents"][0]["parts"][1]["inlineData"]["mimeType"] == "image/jpeg"
            text = Identity(name="Alternador").model_dump_json()
            candidate = {"content": {"parts": [{"text": text}], "role": "model"}, "finishReason": "STOP"}
        else:
            assert body["tools"] == [{"googleSearch": {}}]
            candidate = {"content": {"parts": [{"text": "Encontrado"}], "role": "model"},
                "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://produto.mercadolivre.com.br/MLB-123456", "title": "Anúncio"}}]}}
        return httpx.Response(200, json={"candidates": [candidate], "usageMetadata": {"promptTokenCount": 15, "candidatesTokenCount": 5}})
    client = genai.Client(api_key="test-only", http_options=types.HttpOptions(
        client_args={"transport": httpx.MockTransport(handle), "trust_env": False}))
    service = GeminiService("", client=client, sleep=lambda _: None)
    try:
        assert service.identify([photo()]).name == "Alternador"
        assert service.discover("Alternador usado") == ["https://produto.mercadolivre.com.br/MLB-123456"]
        assert service.usage["grounding_calls"] == 1
    finally:
        service.close()
