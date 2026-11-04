"""Validação opt-in paga: utiliza chave e imagem fornecidas pelo executor."""
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont
from openpyxl import load_workbook

from services.gemini_service import GeminiService, DEFAULT_MODEL
from services.pipeline import Options, prepare_batch, process_batch
from services.sku_detector import SkuDetector


@pytest.mark.skipif(not os.getenv("RUN_GEMINI_LIVE_TEST"), reason="Ative RUN_GEMINI_LIVE_TEST=1 para chamar a API real")
def test_live_label_product_and_excel(tmp_path):
    if not os.getenv("GEMINI_API_KEY") or not os.getenv("GEMINI_TEST_PRODUCT_IMAGE"):
        pytest.skip("A chave e uma fotografia de produto são necessárias para este teste real")
    label = tmp_path / "001-etiqueta.png"
    with Image.new("RGB", (1000, 600), "white") as image:
        ImageDraw.Draw(image).text((90, 180), "SKU: 024", font=ImageFont.load_default(size=120), fill="black")
        image.save(label)
    product_photo = Path(os.environ["GEMINI_TEST_PRODUCT_IMAGE"])
    ai = GeminiService(os.environ["GEMINI_API_KEY"], DEFAULT_MODEL, interval=0, max_calls=8)
    try:
        batch = prepare_batch([label, product_photo], tmp_path / "resultados", SkuDetector(ai), excel_layout="company")
        process_batch(batch, ai=ai, options=Options(save_originals=False))
        assert len(batch.products) == 1 and batch.products[0].sku == "024"
        product = batch.products[0]
        assert product.identity.name != "Peça não identificada"
        expected = os.getenv("GEMINI_TEST_EXPECTED_NAME")
        if expected:
            assert expected.casefold() in product.identity.name.casefold()
        assert product.outputs and (product.folder / product.outputs[0]).exists()
        sheet = load_workbook(batch.folder / "PLANILHA_DE_PRECIFICACAO.xlsx").active
        assert sheet["A2"].value == "024 - " + product.identity.name
        assert sheet.max_column == 5 and sheet["E2"].value is None
    finally:
        ai.close()
