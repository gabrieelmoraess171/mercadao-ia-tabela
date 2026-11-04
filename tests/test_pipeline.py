from decimal import Decimal

from openpyxl import load_workbook

from services.excel_export import export_excel, price_range
from services.file_manager import create_batch, list_images, load_batch, safe_name
from services.image_processor import ImageProcessor
from services.models import Classification, Identity, PhotoKind, Reference
from services.pipeline import Options, prepare_batch, process_batch, search_prices
from services.sku_detector import from_ocr


class Detector:
    def classify(self, path):
        if "label" in path.stem:
            code = path.stem.split("-")[-1]
            return Classification(kind=PhotoKind.LABEL, sku=None if code == "bad" else code, confidence=1)
        return Classification(kind=PhotoKind.PRODUCT, confidence=1)


class Processor:
    def process(self, path, **kwargs):
        if "fail" in path.name:
            raise ValueError("Falha individual simulada")
        return ImageProcessor().process(path, preserve_original=True)


def test_natural_order(photo, tmp_path):
    for name in ["foto10.png", "foto2.png", "foto1.png"]:
        photo(name)
    assert [p.name for p in list_images(tmp_path)] == ["foto1.png", "foto2.png", "foto10.png"]


def test_grouping_variable_lengths_leading_zeros_and_excel(photo, tmp_path):
    paths = [photo(name) for name in ["1-label-024.png", "2.png", "3.png", "4.png", "5-label-025.png", "6.png"]]
    batch = prepare_batch(paths, tmp_path / "out", Detector())
    assert [p.sku for p in batch.products] == ["024", "025"]
    assert [len(p.photos) for p in batch.products] == [4, 2]
    process_batch(batch, processor=Processor())
    assert [len(p.outputs) for p in batch.products] == [3, 1]
    assert len(list(batch.products[0].folder.joinpath("ORIGINAIS").iterdir())) == 4
    restored = load_batch(batch.folder)
    assert restored.products[0].sku == "024"
    book = load_workbook(export_excel(batch))
    assert book.active["A2"].value == "024"
    assert book.active["F2"].value is None
    assert book.active["C2"].value is None
    assert book.active.freeze_panes == "A2"
    assert book.active.auto_filter.ref
    assert book.active["A2"].font.name == "Calibri"
    assert book.sheetnames == ["PRECIFICAÇÃO", "REFERÊNCIAS"]


def test_unreadable_label_and_corrupt_create_boundaries(photo, tmp_path):
    bad = tmp_path / "broken.jpg"
    bad.write_bytes(b"bad")
    paths = [photo("label-024.png"), photo("a.png"), photo("label-bad.png"), photo("b.png"), bad,
             photo("c.png"), photo("label-025.png"), photo("d.png")]
    batch = prepare_batch(paths, tmp_path / "out", Detector())
    assert [p.sku for p in batch.products] == ["024", None, None, "025"]
    assert [p.path.name for p in batch.products[0].photos] == ["label-024.png", "a.png"]
    assert batch.products[2].photos[0].error
    assert batch.processed == len(paths)


def test_duplicate_sku_no_overwrite_and_continues_after_failure(photo, tmp_path):
    paths = [photo("1-label-024.png"), photo("fail.png"), photo("good.png"), photo("2-label-024.png"), photo("other.png")]
    batch = prepare_batch(paths, tmp_path / "out", Detector())
    process_batch(batch, processor=Processor())
    assert batch.products[0].outputs == ["02.jpg"]
    assert batch.products[1].outputs == ["01.jpg"]
    assert batch.products[0].folder != batch.products[1].folder
    assert any("repetido" in s for s in batch.products[1].issues)
    before = (batch.products[1].folder / "01.jpg").stat().st_mtime_ns
    process_batch(batch, processor=Processor())
    assert (batch.products[1].folder / "01.jpg").stat().st_mtime_ns == before
    assert create_batch(tmp_path / "out").folder != batch.folder


def test_only_product_photos_are_processed_and_originals_optional(photo, tmp_path):
    paths = [photo(f"{n}.png") for n in range(5)]
    kinds = [PhotoKind.LABEL, PhotoKind.PRODUCT, PhotoKind.MEASUREMENT, PhotoKind.WEIGHT, PhotoKind.PRODUCT]
    overrides = {str(path): Classification(kind=kind, sku="001" if n == 0 else None, confidence=1)
                 for n, (path, kind) in enumerate(zip(paths, kinds))}
    batch = prepare_batch(paths, tmp_path / "out", Detector(), overrides=overrides)
    process_batch(batch, processor=Processor(), options=Options(save_originals=False))
    assert batch.products[0].outputs == ["01.jpg", "02.jpg"]
    assert not (batch.products[0].folder / "ORIGINAIS").exists()


def test_ocr_labels_and_no_invented_sku():
    assert from_ocr("SKU: 024").sku == "024"
    assert from_ocr("SKU").sku is None
    assert from_ocr("SKU").kind == PhotoKind.LABEL
    assert from_ocr("SKU\nProduto").sku is None
    assert from_ocr("OEM 123456 42 kg").kind == PhotoKind.UNKNOWN


def test_real_tesseract_recognizes_label(tmp_path):
    import pytesseract
    from PIL import Image, ImageDraw, ImageFont
    from services.sku_detector import SkuDetector
    pytesseract.get_tesseract_version()
    file = tmp_path / "label.png"
    image = Image.new("RGB", (900, 300), "white")
    # Pillow inclui fonte padrão escalável nas versões suportadas.
    ImageDraw.Draw(image).text((50, 80), "SKU: 024", font=ImageFont.load_default(size=90), fill="black")
    image.save(file)
    result = SkuDetector().classify(file)
    assert result.kind == PhotoKind.LABEL and result.sku == "024"


def ref(price, code="123456", **kwargs):
    return Reference(title="Peça usada", price=Decimal(str(price)), url=f"https://produto.mercadolivre.com.br/MLB-{code}",
                     condition=kwargs.pop("condition", "used"), verified=kwargs.pop("verified", True),
                     compatible=kwargs.pop("compatible", True), **kwargs)


def test_price_midrange_not_arithmetic_average():
    refs = [ref(350), ref(750, "234567"), ref(400, "345678"), ref(1000, "456789", compatible=False), ref(50, "567890", condition="new")]
    assert price_range(refs) == (Decimal("350"), Decimal("750"), Decimal("550.00"))
    assert price_range([ref(350), ref(750)]) == (None, None, None)
    assert price_range([ref(350), ref(750, "234567", verified=False)]) == (None, None, None)
    duplicate = ref(750)
    duplicate.url += "-titulo-diferente?utm_source=x"
    assert price_range([ref(350), duplicate]) == (None, None, None)


def test_export_references_manual_final_formula_injection(photo, tmp_path):
    batch = prepare_batch([photo("label-024.png"), photo()], tmp_path / "out", Detector())
    product = batch.products[0]
    product.references = [ref(350), ref(750, "234567")]
    product.identity.name = "=HYPERLINK(1)"
    book = load_workbook(export_excel(batch))
    assert [book.active.cell(2, i).value for i in (3,4,5,6)] == [350,750,550,None]
    assert book.active["B2"].data_type == "s"
    assert book["REFERÊNCIAS"].max_row == 3
    product.final = Decimal("600")
    assert load_workbook(export_excel(batch)).active["F2"].value == 600


def test_ai_failure_and_search_unavailable_do_not_stop_batch(photo, tmp_path):
    class BadAI:
        usage = {}
        def identify(self, paths):
            raise RuntimeError("Falha temporária")
    class Unavailable:
        def search(self, product):
            raise RuntimeError("Sem acesso")
    batch = prepare_batch([photo("label-024.png"), photo()], tmp_path / "out", Detector())
    process_batch(batch, ai=BadAI(), processor=Processor())
    assert batch.products[0].outputs
    batch.products[0].identity = Identity(name="Alternador", confidence=1)
    search_prices(batch, Unavailable())
    assert batch.products[0].references == []
    assert load_workbook(export_excel(batch)).active["C2"].value is None


def test_safe_windows_folder_names():
    for name in ['CON', '../pasta\\x:*?', '  .  ', 'NUL.txt']:
        safe = safe_name(name)
        assert safe and not any(c in safe for c in '<>:"/\\|?*')


def test_merge_repeated_label_only_explicitly_and_same_sku(photo, tmp_path):
    paths = [photo("1-label-024.png"), photo("a.png"), photo("2-label-024.png"), photo("b.png"),
             photo("3-label-025.png"), photo("c.png")]
    batch = prepare_batch(paths, tmp_path / "out", Detector(), merge_labels={str(paths[2]), str(paths[4])})
    assert [p.sku for p in batch.products] == ["024", "025"]
    assert len(batch.products[0].photos) == 4


def test_resuming_with_saved_originals_after_source_removed(photo, tmp_path):
    paths = [photo("label-024.png"), photo("produto.png")]
    batch = prepare_batch(paths, tmp_path / "out", Detector())
    process_batch(batch, processor=Processor())
    for path in paths:
        path.unlink()
    restored = load_batch(batch.folder)
    assert all(p.path.exists() for p in restored.products[0].photos)
    before = list((restored.products[0].folder / "ORIGINAIS").iterdir())
    process_batch(restored, processor=Processor())
    assert list((restored.products[0].folder / "ORIGINAIS").iterdir()) == before


def test_scan_api_quota_error_visible_and_does_not_mix_skus(photo, tmp_path):
    from services.gemini_service import AIError
    class Limited:
        def classify(self, path):
            raise AIError("Limite ou cota da API Gemini atingido.")
    batch = prepare_batch([photo("1.png"), photo("2.png")], tmp_path / "out", Limited())
    assert len(batch.products) == 2 and batch.processed == 2
    assert all("cota" in p.photos[0].error for p in batch.products)


def test_500_photo_batch_variable_group_lengths(photo, tmp_path):
    from PIL import Image
    from services.image_processor import white_square
    paths, expected = [], []
    for group in range(100):
        count = 3 + group % 5
        sku = f"{group:05d}"
        paths.append(photo(f"{group:03d}-label-{sku}.png"))
        for index in range(count-1):
            paths.append(photo(f"{group:03d}-produto-{index}.png"))
        expected.append((sku, count))
    assert len(paths) == 500
    batch = prepare_batch(paths, tmp_path / "out", Detector())
    data = white_square(Image.new("RGBA", (30, 20), "red"))
    class LocalTestProcessor:
        def process(self, path, **kwargs):
            return data, []
    process_batch(batch, processor=LocalTestProcessor(), options=Options(save_originals=False))
    assert batch.processed == 500
    assert [(p.sku, len(p.photos)) for p in batch.products] == expected
    assert all(len(p.outputs) == count-1 for p, (_, count) in zip(batch.products, expected))
    assert sum(len(p.outputs) for p in batch.products) == 400
    assert load_workbook(export_excel(batch)).active.max_row == 101
