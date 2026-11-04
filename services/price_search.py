"""Somente API oficial, imagens públicas autorizadas e referências manuais."""
import io
import re
from decimal import Decimal
from typing import Protocol
from urllib.parse import urlparse

import httpx
from PIL import Image

from .models import Product, Reference
from .gemini_service import AIError


class SearchUnavailable(RuntimeError):
    pass


def item_id(url: str) -> str | None:
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.username or parsed.port not in (None, 443):
            return None
    except ValueError:
        return None
    if parsed.hostname not in {"produto.mercadolivre.com.br", "www.mercadolivre.com.br", "mercadolivre.com.br"}:
        return None
    match = re.search(r"\bMLB-?(\d{6,})\b", parsed.path, re.I)
    return "MLB" + match.group(1) if match else None


class PriceProvider(Protocol):
    def search(self, product: Product) -> list[Reference]: ...


class MercadoLivreProvider:
    def __init__(self, ai=None, token: str = "", client=None, use_grounding: bool = False):
        self.ai = ai
        self.token = token
        self.client = client or httpx.Client(timeout=30, follow_redirects=False)
        self.use_grounding = use_grounding
        self._denied_endpoints = set()

    def _api(self, endpoint: str, params=None):
        denied = "Mercado Livre restringiu o acesso. Utilize acesso oficial autorizado ou referências manuais."
        if endpoint in self._denied_endpoints:
            raise SearchUnavailable(denied)
        headers = {"Authorization": "Bearer " + self.token} if self.token else {}
        try:
            response = self.client.get("https://api.mercadolibre.com" + endpoint, params=params, headers=headers)
            if response.status_code in (401, 403):
                self._denied_endpoints.add(endpoint)
                raise SearchUnavailable(denied)
            if response.status_code == 429:
                raise SearchUnavailable("Limite de consultas do Mercado Livre atingido. Tente mais tarde.")
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError):
            raise SearchUnavailable("Não foi possível obter dados verificáveis pela API oficial do Mercado Livre.") from None

    def _image(self, url):
        parsed = urlparse(url or "")
        if parsed.scheme != "https" or parsed.hostname not in {"http2.mlstatic.com", "http.mlstatic.com"}:
            return None
        try:
            # Nunca envia o token Mercado Livre ao servidor de imagens.
            with self.client.stream("GET", url) as response:
                response.raise_for_status()
                data = bytearray()
                for block in response.iter_bytes():
                    data.extend(block)
                    if len(data) > 8 * 1024 * 1024:
                        return None
            with Image.open(io.BytesIO(data)) as image:
                image.thumbnail((1600, 1600))
                stream = io.BytesIO()
                image.convert("RGB").save(stream, "JPEG", quality=90)
                return stream.getvalue()
        except Exception:
            return None

    def search(self, product: Product) -> list[Reference]:
        ids = []
        if self.token:
            try:
                data = self._api("/sites/MLB/search", {"q": product.identity.query(), "condition": "used", "limit": 12})
                ids.extend(row["id"] for row in data.get("results", []))
            except SearchUnavailable:
                if not (self.ai and self.use_grounding):
                    raise
        if self.ai and self.use_grounding:
            try:
                ids.extend(filter(None, (item_id(url) for url in self.ai.discover(product.identity.query()))))
            except AIError as exc:
                if not ids:
                    raise
                product.issues.append(str(exc))
        if not self.token and not (self.ai and self.use_grounding):
            raise SearchUnavailable("Configure acesso oficial do Mercado Livre, ative Google Search ou inclua referências manualmente.")
        references = []
        unavailable = []
        for identifier in list(dict.fromkeys(ids))[:12]:
            if not re.fullmatch(r"MLB\d+", identifier):
                continue
            try:
                item = self._api("/items/" + identifier)
            except SearchUnavailable as exc:
                unavailable.append(str(exc))
                product.issues.append(f"Anúncio {identifier} indisponível: {exc}")
                continue
            if item.get("status") != "active" or item.get("currency_id") != "BRL":
                continue
            url = item.get("permalink", "")
            if not item_id(url):
                continue
            price = item.get("price")
            if not isinstance(price, (int, float)) or price <= 0:
                continue
            reference = Reference(title=item.get("title", "Sem título"), price=Decimal(str(price)), url=url,
                condition=item.get("condition", "unknown"), source="API oficial Mercado Livre", verified=True)
            if reference.condition != "used":
                reference.status = "Descartado: não é usado"
                references.append(reference)
                continue
            try:
                description = self._api("/items/" + identifier + "/description").get("plain_text", "")[:12000]
            except SearchUnavailable:
                description = "Descrição indisponível. Não deduzir compatibilidade ausente."
            photos = item.get("pictures", [])
            image = self._image(photos[0].get("secure_url")) if photos else None
            originals = [p.path for p in product.photos if p.classification.kind.value == "Produto" and not p.error]
            if self.ai and image and originals:
                try:
                    comparison = self.ai.compare(originals, image, {"original": product.identity.model_dump(),
                        "anuncio": {"title": reference.title, "condition": reference.condition,
                                    "attributes": item.get("attributes", []), "description": description}})
                    reference.compatible = comparison.compatible and comparison.confidence >= 0.85
                    reference.reason = comparison.evidence
                    reference.status = "Compatível" if reference.compatible else "Revisão necessária"
                except AIError as exc:
                    reference.reason = str(exc)
                    product.issues.append(str(exc))
            else:
                reference.reason = "Comparação visual indisponível; compatibilidade precisa ser conferida."
            references.append(reference)
        if not references and unavailable:
            raise SearchUnavailable(unavailable[0])
        return references

    def close(self):
        self.client.close()
