from decimal import Decimal
import hashlib
import shutil

from openpyxl import Workbook, load_workbook
import pytest

from services.company_workbook import HEADERS, attach_source, reference_products, validate_source
from services.excel_export import export_excel
from services.file_manager import load_batch, save_batch
from services.models import Batch, Product, Reference
from services.naming import manual_identity


def product(tmp_path, sku="024", name="porta direita Renault Duster 2014-2020"):
    return Product(id="0001", sku=sku, folder=tmp_path, identity=manual_identity(name))


def base_file(tmp_path):
    book = Workbook()
    book.active.append(HEADERS)
    book.active.append(["024 - PORTA L.D RENAULT DUSTER 14-20", 100, 200, "=(B2+C2)/2", "329,00 CADA"])
    book.active.append(["025 - ALTERNADOR", 80, 160, 120, 100])
    book.create_sheet("NOTAS")["A1"] = "Preservar"
    source = tmp_path / "estoque.xlsx"
    book.save(source)
    return source


def batch_at(tmp_path):
    folder = tmp_path / "lote"
    folder.mkdir()
    return Batch(folder=folder, excel_layout="company")


def test_five_columns_company_style_and_repeated_exports(tmp_path):
    batch = batch_at(tmp_path)
    batch.products = [product(batch.folder)]
    output = export_excel(batch)
    export_excel(batch)
    book = load_workbook(output)
    sheet = book.active
    assert [c.value for c in sheet[1]] == HEADERS
    assert sheet.max_row == 2 and sheet.max_column == 5
    assert sheet["A2"].value == "024 - PORTA L.D RENAULT DUSTER 14-20"
    assert all(sheet.cell(2, col).value is None for col in range(2, 6))
    assert sheet["A1"].fill.fgColor.rgb.endswith("92D050")
    assert sheet.column_dimensions["A"].width == 71
    assert sheet.freeze_panes == "A2"


def test_base_copy_preserves_values_formulas_and_other_sheets(tmp_path):
    source = base_file(tmp_path)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    batch = batch_at(tmp_path)
    attach_source(batch, source)
    batch.products = [product(batch.folder), product(batch.folder, "026", "motor de arranque")]
    output = export_excel(batch)
    sheet = load_workbook(output).active
    assert [sheet.cell(2, col).value for col in range(2, 6)] == [100, 200, "=(B2+C2)/2", "329,00 CADA"]
    assert sheet["A3"].value == "025 - ALTERNADOR"
    assert sheet["A4"].value == "026 - MOTOR DE PARTIDA"
    assert load_workbook(output)["NOTAS"]["A1"].value == "Preservar"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    known = reference_products(batch.workbook_template)
    assert known["025"]["final"] == Decimal("100")
    # Uma edição posterior feita no Excel também é preservada.
    book = load_workbook(output)
    book.active["E2"] = 450
    book.save(output)
    export_excel(batch)
    assert load_workbook(output).active["E2"].value == 450
    batch.products[0].final = Decimal("420")
    batch.products[0].final_override = True
    export_excel(batch)
    assert load_workbook(output).active["E2"].value == 420


def test_unknown_names_never_replace_existing_names_and_rows_do_not_grow(tmp_path):
    source = base_file(tmp_path)
    batch = batch_at(tmp_path)
    attach_source(batch, source)
    batch.products = [Product(id="1", sku="024", folder=batch.folder), Product(id="2", folder=batch.folder)]
    for _ in range(3):
        output = export_excel(batch)
    assert load_workbook(output).active["A2"].value == "024 - PORTA L.D RENAULT DUSTER 14-20"
    assert load_workbook(output).active.max_row == 4
    save_batch(batch)
    moved = tmp_path / "movido"
    shutil.move(batch.folder, moved)
    restored = load_batch(moved)
    assert restored.workbook_template == moved / "BASE_PLANILHA.xlsx"
    export_excel(restored)
    assert load_workbook(moved / output.name).active.max_row == 4


def test_verified_comparison_and_clearing_references(tmp_path):
    batch = batch_at(tmp_path)
    part = product(batch.folder)
    part.references = [Reference(title="Porta", price=price, url=f"https://produto.mercadolivre.com.br/MLB-{sku}-porta-_JM",
        condition="used", verified=True, compatible=True) for price, sku in [(100, 123456), (200, 123457)]]
    batch.products = [part]
    output = export_excel(batch)
    assert [load_workbook(output).active.cell(2, c).value for c in range(2, 5)] == [100, 200, 150]
    part.references = []
    part.references_edited = True
    export_excel(batch)
    assert load_workbook(output).active["B2"].value is None
    assert load_workbook(output)["REFERÊNCIAS"].max_row == 1


def test_duplicate_skus_do_not_overwrite(tmp_path):
    source = base_file(tmp_path)
    batch = batch_at(tmp_path)
    attach_source(batch, source)
    batch.products = [product(batch.folder), product(batch.folder)]
    batch.products[0].final = Decimal("999")
    batch.products[0].final_override = True
    output = export_excel(batch)
    assert load_workbook(output).active["E2"].value == "329,00 CADA"
    assert any("repetido" in message for message in batch.issues)


def test_invalid_layout_is_rejected_before_writing(tmp_path):
    book = Workbook()
    book.active.append([HEADERS[0], "TELEFONE"])
    source = tmp_path / "invalida.xlsx"
    book.save(source)
    with pytest.raises(ValueError, match="coluna"):
        validate_source(source)


def test_old_six_columns_convert_without_losing_final(tmp_path):
    batch = batch_at(tmp_path)
    batch.excel_layout = "standard"
    batch.products = [product(batch.folder)]
    batch.products[0].final = Decimal("300")
    export_excel(batch)
    batch.excel_layout = "company"
    output = export_excel(batch)
    sheet = load_workbook(output).active
    assert sheet.max_column == 5 and sheet["E2"].value == 300
    assert sheet["A2"].value.startswith("024 - PORTA L.D")


def test_ui_uses_existing_sku_name_without_identification_api(photo, tmp_path, monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from services.models import PhotoKind
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    source = base_file(tmp_path)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"), default_timeout=30)
    paths = [photo("label.png"), photo("part.png")]
    app.session_state["paths"] = paths
    app.session_state["review_sequence"] = [{"ORDEM": i, "ARQUIVO": path.name,
        "TIPO": PhotoKind.LABEL.value if i == 1 else PhotoKind.PRODUCT.value,
        "SKU": "024" if i == 1 else "", "PRESERVAR FUNDO ORIGINAL": True,
        "ETIQUETA REPETIDA DA MESMA PEÇA": False} for i, path in enumerate(paths, 1)]
    app.run()
    app.text_input(key="destination").set_value(str(tmp_path / "out"))
    app.text_input(key="workbook_source").set_value(str(source))
    next(b for b in app.button if b.label == "INICIAR PROCESSAMENTO").click().run()
    assert not app.exception
    batch = app.session_state["batch"]
    assert batch.products[0].identity.name == "PORTA L.D RENAULT DUSTER 14-20"
    assert batch.products[0].identity_reviewed
    assert (batch.products[0].folder / "01.jpg").exists()
    assert load_workbook(batch.folder / "PLANILHA_DE_PRECIFICACAO.xlsx").active["E2"].value == "329,00 CADA"
